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
    
    # -- CONECTAR A GOOGLE SHEETS --
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

    # -- CONECTAR A SQLITE Y CREAR ESTRUCTURA --
    try:
        conn = sqlite3.connect(LOCAL_DB_NAME)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # --- 1. TABLA CLIENTES ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            cliente_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            telefono TEXT DEFAULT 'SIN INFORMACION',
            instagram TEXT DEFAULT 'SIN INFORMACION',
            direccion TEXT DEFAULT 'SIN INFORMACION',
            rut TEXT DEFAULT 'SIN INFORMACION',
            status TEXT DEFAULT 'ACTIVA'
        );
        """)

        # --- 2. TABLA SUSCRIPCIONES ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS suscripciones (
            suscripcion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER UNIQUE,
            fecha_pago TEXT DEFAULT 'SIN INFORMACION',
            metodo_entrega TEXT DEFAULT 'SIN INFORMACION' CHECK(metodo_entrega IN ('BLUEXPRESS', 'PAKET', 'RETIRO', 'SIN INFORMACION')),
            generos_preferencia TEXT DEFAULT 'SIN INFORMACION',
            FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id)
        );
        """)

        # --- 3. TABLA LIBROS ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS libros (
            libro_id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL UNIQUE,
            autor TEXT DEFAULT 'SIN INFORMACION',
            genero TEXT DEFAULT 'SIN INFORMACION',
            editorial TEXT DEFAULT 'SIN INFORMACION',
            precio INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 0,
            encuadernacion TEXT DEFAULT 'TAPA BLANDA' CHECK(encuadernacion IN ('TAPA DURA', 'TAPA BLANDA', 'BOLSILLO'))
        );
        """)

        # --- 4. TABLA ASIGNACIONES ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS asignaciones (
            asignacion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            libro_suscripcion_id INTEGER,
            libros_extras TEXT DEFAULT 'SIN EXTRAS',
            ano TEXT NOT NULL,
            mes TEXT NOT NULL,
            ano_mes TEXT GENERATED ALWAYS AS (ano || mes) STORED,
            pagado TEXT DEFAULT 'FALSE',
            envio_pagado TEXT DEFAULT 'FALSE',
            estado_envio TEXT DEFAULT 'PENDIENTE',
            fecha_asignacion TIMESTAMP,
            comentario TEXT DEFAULT 'SIN COMENTARIOS',
            FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id),
            FOREIGN KEY (libro_suscripcion_id) REFERENCES libros(libro_id),
            UNIQUE(cliente_id, ano_mes)
        );
        """)
        
        # --- 5. TRIGGERS DE MAYÚSCULAS ---
        
        # --- TRIGGERS PARA LA TABLA CLIENTES ---
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_clientes_insert
        AFTER INSERT ON clientes FOR EACH ROW
        BEGIN
            UPDATE clientes SET 
                nombre = UPPER(NEW.nombre), 
                email = UPPER(NEW.email),
                telefono = UPPER(NEW.telefono),
                instagram = UPPER(NEW.instagram),
                direccion = UPPER(NEW.direccion),
                rut = UPPER(NEW.rut),
                status = UPPER(NEW.status)
            WHERE cliente_id = NEW.cliente_id;
        END;
        """)
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_clientes_update
        AFTER UPDATE ON clientes FOR EACH ROW
        BEGIN
            UPDATE clientes SET 
                nombre = UPPER(NEW.nombre), 
                email = UPPER(NEW.email),
                telefono = UPPER(NEW.telefono),
                instagram = UPPER(NEW.instagram),
                direccion = UPPER(NEW.direccion),
                rut = UPPER(NEW.rut),
                status = UPPER(NEW.status)
            WHERE cliente_id = NEW.cliente_id;
        END;
        """)

        # --- TRIGGERS PARA LA TABLA SUSCRIPCIONES ---
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_suscripciones_insert
        AFTER INSERT ON suscripciones FOR EACH ROW
        BEGIN
            UPDATE suscripciones SET
                fecha_pago = UPPER(NEW.fecha_pago),
                metodo_entrega = UPPER(NEW.metodo_entrega),
                generos_preferencia = UPPER(NEW.generos_preferencia)
            WHERE suscripcion_id = NEW.suscripcion_id;
        END;
        """)
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_suscripciones_update
        AFTER UPDATE ON suscripciones FOR EACH ROW
        BEGIN
            UPDATE suscripciones SET
                fecha_pago = UPPER(NEW.fecha_pago),
                metodo_entrega = UPPER(NEW.metodo_entrega),
                generos_preferencia = UPPER(NEW.generos_preferencia)
            WHERE suscripcion_id = NEW.suscripcion_id;
        END;
        """)

        # --- TRIGGERS PARA LA TABLA LIBROS ---
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_libros_insert
        AFTER INSERT ON libros FOR EACH ROW
        BEGIN
            UPDATE libros SET 
                titulo = UPPER(NEW.titulo), 
                autor = UPPER(NEW.autor),
                genero = UPPER(NEW.genero),
                editorial = UPPER(NEW.editorial),
                encuadernacion = UPPER(NEW.encuadernacion)
            WHERE libro_id = NEW.libro_id;
        END;
        """)
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_libros_update
        AFTER UPDATE ON libros FOR EACH ROW
        BEGIN
            UPDATE libros SET 
                titulo = UPPER(NEW.titulo), 
                autor = UPPER(NEW.autor),
                genero = UPPER(NEW.genero),
                editorial = UPPER(NEW.editorial),
                encuadernacion = UPPER(NEW.encuadernacion)
            WHERE libro_id = NEW.libro_id;
        END;
        """)

        # --- TRIGGERS PARA LA TABLA ASIGNACIONES ---
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_asignaciones_insert
        AFTER INSERT ON asignaciones FOR EACH ROW
        BEGIN
            UPDATE asignaciones SET
                libros_extras = UPPER(NEW.libros_extras),
                pagado = UPPER(NEW.pagado),
                envio_pagado = UPPER(NEW.envio_pagado),
                estado_envio = UPPER(NEW.estado_envio),
                comentario = UPPER(NEW.comentario)
            WHERE asignacion_id = NEW.asignacion_id;
        END;
        """)
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uppercase_asignaciones_update
        AFTER UPDATE ON asignaciones FOR EACH ROW
        BEGIN
            UPDATE asignaciones SET
                libros_extras = UPPER(NEW.libros_extras),
                pagado = UPPER(NEW.pagado),
                envio_pagado = UPPER(NEW.envio_pagado),
                estado_envio = UPPER(NEW.estado_envio),
                comentario = UPPER(NEW.comentario)
            WHERE asignacion_id = NEW.asignacion_id;
        END;
        """)
        
        conn.commit()
        print("Base de datos local verificada y estructurada con triggers de mayúsculas.")
    except sqlite3.Error as e:
        print(f"Error de base de datos SQLite: {e}")
        return
        
    # -- PROCESAR E INSERTAR DATOS --
    try:
        processed_clients = 0
        for index, row in df.iterrows():
            # Limpia y convierte a mayúsculas usando la función clean_field
            email = clean_field(row.get("Email", row.get("Dirección de correo electrónico", "")))
            name = clean_field(row.get("Nombre ", row.get("Nombre", "")))
            
            if name == "SIN INFORMACION": 
                continue
            
            if email == "SIN INFORMACION": 
                email = f"SIN_CORREO_{index}@ALBALIBRERIA.CL"
                
            phone = clean_field(row.get("Teléfono", ""))
            instagram = clean_field(row.get("Instagram", ""))
            status = clean_field(row.get("Estado cliente", "ACTIVA"))
            address = clean_field(row.get("Datos de envío: Favor escribir en este formato", ""))
            rut = clean_field(row.get("Rut y dirección para facturación", ""))
            pay_date = clean_field(row.get("Fecha de pago", ""))
            delivery_method = clean_field(row.get("Método de entrega", ""))
            genres = clean_field(row.get("Selecciona los géneros de tu preferencia (puedes elegir los que quieras)", ""))
            
            if genres != "SIN INFORMACION":
                genres = genres.replace("DARK ACADEMY", "DARK ACADEMIA")

            # -- INSERTAR O ACTUALIZAR CLIENTE --
            cursor.execute("""
            INSERT INTO clientes (email, nombre, telefono, instagram, direccion, rut, status) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                nombre=excluded.nombre, telefono=excluded.telefono, instagram=excluded.instagram, 
                direccion=excluded.direccion, rut=excluded.rut, status=excluded.status;
            """, (email, name, phone, instagram, address, rut, status))
            
            # -- OBTENER ID DEL CLIENTE PROCESADO --
            cursor.execute("SELECT cliente_id FROM clientes WHERE email = ?", (email,))
            client_id = cursor.fetchone()[0]
            
            # -- INSERTAR O ACTUALIZAR SUSCRIPCION --
            cursor.execute("""
            INSERT INTO suscripciones (cliente_id, fecha_pago, metodo_entrega, generos_preferencia) VALUES (?, ?, ?, ?)
            ON CONFLICT(cliente_id) DO UPDATE SET
                fecha_pago=excluded.fecha_pago, metodo_entrega=excluded.metodo_entrega, generos_preferencia=excluded.generos_preferencia;
            """, (client_id, pay_date, delivery_method, genres))
            
            processed_clients += 1
            
        conn.commit()
        print(f"Sincronización exitosa: {processed_clients} clientes y suscripciones procesadas.")
    except Exception as e:
        print(f"Error durante el procesamiento de datos: {e}")
    finally:
        if conn:
            conn.close()
            print("Conexión con la base de datos cerrada.")

if __name__ == "__main__":
    sync_system()