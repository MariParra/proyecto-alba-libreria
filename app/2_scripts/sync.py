import psycopg2
import gspread
import pandas as pd
import os
import random
import json
from dotenv import load_dotenv

# --- CONFIGURACIÓN ---
GOOGLE_SHEET_NAME = "INSCRIPCIONES CAJA MENSUAL"
WORKSHEET_NAME = "formulario"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
CREDENTIALS_FILE = os.path.join(BASE_DIR, "config", "credentials.json")

# --- CONEXIÓN A LA NUBE ---
dotenv_path = os.path.join(os.path.dirname(BASE_DIR), '.env')
load_dotenv(dotenv_path)
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def clean_field(value):
    val_str = str(value).strip().upper()
    if not val_str or val_str in ["NAN", "NONE", "NULL", ""]:
        return "SIN INFORMACION"
    return val_str

def resetear_emails_duplicados(cursor):
    # En PostgreSQL, el comodín % se usa en LIKE igual que en SQLite
    cursor.execute("SELECT cliente_id, email FROM clientes WHERE email LIKE 'SIN_CORREO_%%' OR email = 'SIN INFORMACION'")
    clientes_a_revisar = cursor.fetchall()
    
    for cliente_id, email_actual in clientes_a_revisar:
        nuevo_email = f"SIN_CORREO_ID_{cliente_id}@ALBALIBRERIA.CL"
        if email_actual != nuevo_email:
            # Comprobar para no romper la transacción en PostgreSQL
            cursor.execute("SELECT 1 FROM clientes WHERE email = %s", (nuevo_email,))
            if not cursor.fetchone():
                cursor.execute("UPDATE clientes SET email = %s WHERE cliente_id = %s", (nuevo_email, cliente_id))

def sync_system():
    print("Iniciando proceso de sincronizacion...")
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        df = pd.DataFrame(worksheet.get_all_records())
        print("Conexion exitosa: datos obtenidos de Google Sheets.")
    except Exception as e:
        print(f'{{"error": "Error al conectar con Google Sheets: {e}"}}')
        return

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # 1. Mantenimiento de correos
        resetear_emails_duplicados(cursor)
        
        # 2. Proceso de sincronización principal
        processed_clients = 0
        
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
            
            email_raw = clean_field(row.get(col_email, ""))
            email_sync = f"SIN_CORREO_{index}@ALBALIBRERIA.CL" if email_raw == "SIN INFORMACION" else email_raw
            
            phone_sync = clean_field(row.get(col_telefono, ""))
            instagram_sync = clean_field(row.get(col_instagram, ""))
            address_sync = clean_field(row.get(col_direccion, ""))
            rut_sync = clean_field(row.get(col_rut, ""))
            status_sync = clean_field(row.get(col_status, "ACTIVA"))
            pay_date = clean_field(row.get(col_fecha_pago, ""))
            genres = clean_field(row.get(col_generos, "")).replace("DARK ACADEMY", "DARK ACADEMIA")
            
            delivery_method_raw = clean_field(row.get(col_metodo_entrega, ""))
            if "RETIRO" in delivery_method_raw: delivery_method = "RETIRO"
            elif "PAKET" in delivery_method_raw: delivery_method = "PAKET"
            elif "BLUE" in delivery_method_raw: delivery_method = "BLUEXPRESS"
            elif "STARKEN" in delivery_method_raw: delivery_method = "STARKEN"
            else: delivery_method = "SIN INFORMACION"

            # 1. BUSCAR CLIENTE POR NOMBRE
            cursor.execute("SELECT cliente_id FROM clientes WHERE nombre = %s", (name,))
            res = cursor.fetchone()
            
            client_id = None
            if res:
                client_id = res[0]
                
                # Revisar si el email a actualizar ya lo tiene otro cliente (evitar error SQL)
                cursor.execute("SELECT cliente_id FROM clientes WHERE email = %s AND cliente_id != %s", (email_sync, client_id))
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE clientes SET status = %s, telefono = CASE WHEN telefono = 'SIN INFORMACION' THEN %s ELSE telefono END,
                        direccion = CASE WHEN direccion = 'SIN INFORMACION' THEN %s ELSE direccion END, rut = CASE WHEN rut = 'SIN INFORMACION' THEN %s ELSE rut END,
                        instagram = CASE WHEN instagram = 'SIN INFORMACION' THEN %s ELSE instagram END WHERE cliente_id = %s
                    """, (status_sync, phone_sync, address_sync, rut_sync, instagram_sync, client_id))
                else:
                    cursor.execute("""
                        UPDATE clientes SET status = %s, telefono = CASE WHEN telefono = 'SIN INFORMACION' THEN %s ELSE telefono END,
                        direccion = CASE WHEN direccion = 'SIN INFORMACION' THEN %s ELSE direccion END, rut = CASE WHEN rut = 'SIN INFORMACION' THEN %s ELSE rut END,
                        instagram = CASE WHEN instagram = 'SIN INFORMACION' THEN %s ELSE instagram END,
                        email = CASE WHEN email LIKE 'SIN_CORREO_%%' OR email = 'SIN INFORMACION' THEN %s ELSE email END
                        WHERE cliente_id = %s
                    """, (status_sync, phone_sync, address_sync, rut_sync, instagram_sync, email_sync, client_id))
            else:
                # 2. BUSCAR POR EMAIL
                if email_sync != "SIN INFORMACION" and "SIN_CORREO" not in email_sync:
                    cursor.execute("SELECT cliente_id FROM clientes WHERE email = %s", (email_sync,))
                    res_em = cursor.fetchone()
                    if res_em:
                        client_id = res_em[0]
                        cursor.execute("""
                            UPDATE clientes SET status = %s, nombre = %s, telefono = CASE WHEN telefono = 'SIN INFORMACION' THEN %s ELSE telefono END,
                            direccion = CASE WHEN direccion = 'SIN INFORMACION' THEN %s ELSE direccion END, rut = CASE WHEN rut = 'SIN INFORMACION' THEN %s ELSE rut END,
                            instagram = CASE WHEN instagram = 'SIN INFORMACION' THEN %s ELSE instagram END WHERE cliente_id = %s
                        """, (status_sync, name, phone_sync, address_sync, rut_sync, instagram_sync, client_id))
                
                # 3. CREAR NUEVO
                if not client_id:
                    # Prevenir duplicados verificando el correo
                    cursor.execute("SELECT 1 FROM clientes WHERE email = %s", (email_sync,))
                    if cursor.fetchone():
                        email_sync = f"CONFLICTO_{index}_{random.randint(1000,9999)}@ALBALIBRERIA.CL"
                    
                    cursor.execute("INSERT INTO clientes (email, nombre, telefono, instagram, direccion, rut, status) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING cliente_id", 
                        (email_sync, name, phone_sync, instagram_sync, address_sync, rut_sync, status_sync))
                    client_id = cursor.fetchone()[0]

            # --- ACTUALIZAR SUSCRIPCIONES ---
            cursor.execute("SELECT suscripcion_id FROM suscripciones WHERE cliente_id = %s", (client_id,))
            if cursor.fetchone():
                cursor.execute("UPDATE suscripciones SET fecha_pago = %s, metodo_entrega = %s, generos_preferencia = %s WHERE cliente_id = %s", 
                            (pay_date, delivery_method, genres, client_id))
            else:
                cursor.execute("INSERT INTO suscripciones (cliente_id, fecha_pago, metodo_entrega, generos_preferencia) VALUES (%s, %s, %s, %s)", 
                            (client_id, pay_date, delivery_method, genres))
            
            processed_clients += 1
            
        conn.commit()
        print(f'{{"exito": true, "mensaje": "Sincronización exitosa: {processed_clients} clientes procesados."}}')

    except Exception as e:
        print(f'{{"error": "Error crítico en BD: {e}"}}')
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    sync_system()