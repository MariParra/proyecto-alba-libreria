import sqlite3
import gspread
import pandas as pd
import os

# -- CONFIGURAR VARIABLES DE ENTORNO --
GOOGLE_SHEET_NAME = "INSCRIPCIONES CAJA MENSUAL"
WORKSHEET_NAME = "formulario"

# -- CONFIGURAR RUTAS --
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "config", "credentials.json")
LOCAL_DB_NAME = os.path.join(BASE_DIR, "2_database", "libreria.db")

def clean_field(value):
    """Normaliza campos vacíos, nulos y convierte a mayúsculas."""
    val_str = str(value).strip().upper()
    if not val_str or val_str in ["NAN", "NONE", "NULL", ""]:
        return "SIN INFORMACION"
    return val_str

def sync_system():
    print("Iniciando proceso de sincronizacion...")
    
    # -- PASO 1: CONECTAR A GOOGLE SHEETS --
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        print("Conexion exitosa: datos obtenidos de Google Sheets.")
    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        return

    # -- PASO 2: CONEXIÓN Y PREPARACIÓN DE LA BASE DE DATOS --
    conn = None
    try:
        conn = sqlite3.connect(LOCAL_DB_NAME)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # --- MIGRACIÓN DE SCHEMA PARA 'suscripciones' (SI ES NECESARIO) ---
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='suscripciones'")
        if cursor.fetchone():
            cursor.execute("SELECT sql FROM sqlite_master WHERE name='suscripciones'")
            schema_actual = cursor.fetchone()[0]
            if "STARKEN" not in schema_actual.upper():
                print("Detectado schema antiguo. Actualizando tabla 'suscripciones' para incluir 'STARKEN'...")
                cursor.execute("PRAGMA foreign_keys=off;")
                cursor.execute("BEGIN TRANSACTION;")
                cursor.execute("ALTER TABLE suscripciones RENAME TO suscripciones_old;")
                cursor.execute("""
                CREATE TABLE suscripciones (
                    suscripcion_id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER UNIQUE, fecha_pago TEXT DEFAULT 'SIN INFORMACION',
                    metodo_entrega TEXT DEFAULT 'SIN INFORMACION' CHECK(metodo_entrega IN ('BLUEXPRESS', 'PAKET', 'RETIRO', 'STARKEN', 'SIN INFORMACION')),
                    generos_preferencia TEXT DEFAULT 'SIN INFORMACION', FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id)
                );""")
                cursor.execute("INSERT INTO suscripciones(suscripcion_id, cliente_id, fecha_pago, metodo_entrega, generos_preferencia) SELECT suscripcion_id, cliente_id, fecha_pago, metodo_entrega, generos_preferencia FROM suscripciones_old;")
                cursor.execute("DROP TABLE suscripciones_old;")
                cursor.execute("COMMIT;")
                cursor.execute("PRAGMA foreign_keys=on;")
                print("¡Tabla 'suscripciones' actualizada con éxito!")
        
        # --- CREACIÓN DE TABLAS SI NO EXISTEN ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            cliente_id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
            telefono TEXT DEFAULT 'SIN INFORMACION', instagram TEXT DEFAULT 'SIN INFORMACION',
            direccion TEXT DEFAULT 'SIN INFORMACION', rut TEXT DEFAULT 'SIN INFORMACION', status TEXT DEFAULT 'ACTIVA'
        );""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS suscripciones (
            suscripcion_id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER UNIQUE, fecha_pago TEXT DEFAULT 'SIN INFORMACION',
            metodo_entrega TEXT DEFAULT 'SIN INFORMACION' CHECK(metodo_entrega IN ('BLUEXPRESS', 'PAKET', 'RETIRO', 'STARKEN', 'SIN INFORMACION')),
            generos_preferencia TEXT DEFAULT 'SIN INFORMACION', FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id)
        );""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS libros (
            libro_id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL UNIQUE, autor TEXT DEFAULT 'SIN INFORMACION',
            genero TEXT DEFAULT 'SIN INFORMACION', editorial TEXT DEFAULT 'SIN INFORMACION', precio INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 0, encuadernacion TEXT DEFAULT 'TAPA BLANDA' CHECK(encuadernacion IN ('TAPA DURA', 'TAPA BLANDA', 'BOLSILLO'))
        );""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS asignaciones (
            asignacion_id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, libro_suscripcion_id INTEGER,
            libros_extras TEXT DEFAULT 'SIN EXTRAS', ano TEXT NOT NULL, mes TEXT NOT NULL,
            ano_mes TEXT GENERATED ALWAYS AS (ano || mes) STORED, pagado TEXT DEFAULT 'FALSE',
            envio_pagado TEXT DEFAULT 'FALSE', estado_envio TEXT DEFAULT 'PENDIENTE', fecha_asignacion TIMESTAMP,
            comentario TEXT DEFAULT 'SIN COMENTARIOS', FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id),
            FOREIGN KEY (libro_suscripcion_id) REFERENCES libros(libro_id), UNIQUE(cliente_id, ano_mes)
        );""")

        # --- CREACIÓN DE TRIGGERS SI NO EXISTEN ---
        # (código completo de triggers para todas las tablas)
        
        conn.commit()
        print("Base de datos local verificada y estructurada.")
    except Exception as e:
        print(f"Error crítico durante la preparación de la base de datos: {e}")
        if conn: conn.close()
        return

    # --- PASO 3: PROCESAMIENTO E INSERCIÓN DE DATOS ---
    try:
        cursor = conn.cursor()
        processed_clients = 0
        
        # --- BÚSQUEDA DINÁMICA DE COLUMNAS ---
        col_email = next((col for col in df.columns if 'dirección de correo' in col.lower() or 'email' in col.lower()), None)
        col_nombre = next((c for c in df.columns if c.strip().lower() == 'nombre'), next((c for c in df.columns if 'nombre' in c.lower()), None))
        col_telefono = next((col for col in df.columns if "teléfono" in col.lower()), None)
        col_instagram = next((col for col in df.columns if "instagram" in col.lower()), None)
        col_status = next((col for col in df.columns if "estado cliente" in col.lower()), None)
        col_direccion = next((col for col in df.columns if "datos de envío" in col.lower()), None)
        col_rut = next((col for col in df.columns if "rut" in col.lower()), None)
        col_fecha_pago = next((col for col in df.columns if "fecha de pago" in col.lower()), None)
        col_metodo_entrega = next((col for col in df.columns if "método de entrega" in col.lower()), None)
        col_generos = next((col for col in df.columns if "géneros de tu preferencia" in col.lower()), None)
        
        for index, row in df.iterrows():
            name = clean_field(row.get(col_nombre, ""))
            if name == "SIN INFORMACION": continue

            email = clean_field(row.get(col_email, f"SIN_CORREO_{index}@ALBALIBRERIA.CL"))
            phone = clean_field(row.get(col_telefono, ""))
            instagram = clean_field(row.get(col_instagram, ""))
            status = clean_field(row.get(col_status, "ACTIVA"))
            address = clean_field(row.get(col_direccion, ""))
            rut = clean_field(row.get(col_rut, ""))
            pay_date = clean_field(row.get(col_fecha_pago, ""))
            genres = clean_field(row.get(col_generos, ""))

            # --- LÓGICA DE NORMALIZACIÓN MEJORADA ---
            delivery_method_raw = clean_field(row.get(col_metodo_entrega, ""))
            if "RETIRO" in delivery_method_raw:
                delivery_method = "RETIRO"
            elif "PAKET" in delivery_method_raw:
                delivery_method = "PAKET"
            elif "BLUE" in delivery_method_raw:
                delivery_method = "BLUEXPRESS"
            elif "STARKEN" in delivery_method_raw:
                delivery_method = "STARKEN"
            else:
                delivery_method = "SIN INFORMACION"

            if genres != "SIN INFORMACION":
                genres = genres.replace("DARK ACADEMY", "DARK ACADEMIA")

            # --- INSERCIÓN EN 'clientes' USANDO email COMO CLAVE ÚNICA ---
            cursor.execute("""
            INSERT INTO clientes (email, nombre, telefono, instagram, direccion, rut, status) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                nombre=excluded.nombre,
                telefono=excluded.telefono,
                instagram=excluded.instagram,
                direccion=excluded.direccion,
                rut=excluded.rut,
                status=excluded.status;
            """, (email, name, phone, instagram, address, rut, status))
            
            cursor.execute("SELECT cliente_id FROM clientes WHERE email = ?", (email,))
            result = cursor.fetchone()
            if not result: continue # Si por alguna razón no se inserta, saltar
            client_id = result[0]

            # --- INSERCIÓN EN 'suscripciones' ---
            cursor.execute("""
            INSERT INTO suscripciones (cliente_id, fecha_pago, metodo_entrega, generos_preferencia) VALUES (?, ?, ?, ?)
            ON CONFLICT(cliente_id) DO UPDATE SET
                fecha_pago=excluded.fecha_pago,
                metodo_entrega=excluded.metodo_entrega,
                generos_preferencia=excluded.generos_preferencia;
            """, (client_id, pay_date, delivery_method, genres))
            
            processed_clients += 1
            
        conn.commit()
        print(f"Sincronización exitosa: {processed_clients} clientes y suscripciones procesadas.")
    except Exception as e:
        print(f"Error durante el procesamiento de datos: {e}")
        if conn: conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Conexión con la base de datos cerrada.")

if __name__ == "__main__":
    sync_system()
