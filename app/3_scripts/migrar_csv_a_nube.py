# migrar_csv_a_nube.py - VERSIÓN CORREGIDA Y COMPLETA

import psycopg2
import pandas as pd
import os
import unicodedata
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURACIÓN (SIN CAMBIOS) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) 

dotenv_path = os.path.join(os.path.dirname(BASE_DIR), '.env')
load_dotenv(dotenv_path)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

posibles_rutas = [
    os.path.join(BASE_DIR, "1_input_data", "migracion_20260715.csv") 
]
CSV_PATH = next((ruta for ruta in posibles_rutas if os.path.exists(ruta)), None)

MISSING_CLIENTS_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_clientes_faltantes_NUBE.csv")
MISSING_BOOKS_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_libros_faltantes_NUBE.csv")
SKIPPED_ROWS_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_filas_omitidas_NUBE.csv")

def normalize_name(name):
    if not isinstance(name, str): return ""
    s = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    return s.strip().upper()

MANUAL_CLIENT_FIXES = {
    "LUIS ALFREDO PEREZ DROGUETT": "Luis Pérez (Danae Martínez)",
    "KELLY ARANDA": "Kelly Araneda", "KELLY": "Kelly Araneda", "MARIANA": "Mariana parra", 
    "MELANIE": "Melanie Thomas", "TAMARA AGUILERA CONTRERAS": "Tamara Aguilera",
    "JOSNELIS": "Josnelis hernandez", "KARLA VICENCIO": "Karla Vicencio Vargas"
}

def migrate_csv_to_cloud():
    if not CSV_PATH:
        print("Error: No se encontró ningún archivo CSV de migración."); return
    if not DATABASE_URL:
        print("Error: No se encontró la variable DATABASE_URL en el archivo .env"); return
        
    print(f"Iniciando migración DIRECTA A LA NUBE desde:\n{CSV_PATH} ...")
    
    try:
        df = pd.read_csv(CSV_PATH, sep=None, engine='python', encoding='utf-8-sig', on_bad_lines='warn')
        df.columns = [str(c).strip().strip('\ufeff').strip('"').strip("'") for c in df.columns]
        df_original = df.copy()
    except Exception as e:
        print(f"Error al procesar el CSV: {e}"); return

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT cliente_id, nombre FROM clientes")
        cliente_map = {normalize_name(nombre): id for id, nombre in cursor.fetchall()}
        
        cursor.execute("SELECT libro_id, titulo FROM libros")
        libro_map = {normalize_name(titulo): id for id, titulo in cursor.fetchall()}
        
        comandos_ejecutados = 0
        clientes_no_encontrados, libros_no_encontrados = set(), set()
        omitted_rows = []
        
        meses_map = {'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04', 'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08', 'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'}

        for index, row in df_original.iterrows():
            reason = ""
            
            # --- BLOQUE FALTANTE RESTAURADO ---
            cliente_nombre_raw = str(row.get('Clienta', '')).strip().upper()
            if not cliente_nombre_raw:
                reason = "Nombre de cliente vacío"
                omitted_rows.append(list(row) + [reason])
                continue

            cliente_nombre_raw_norm = normalize_name(MANUAL_CLIENT_FIXES.get(cliente_nombre_raw, cliente_nombre_raw))
            
            cliente_id = cliente_map.get(cliente_nombre_raw_norm)
            if not cliente_id:
                clientes_no_encontrados.add(row.get('Clienta'))
                reason = "Cliente no encontrado en la BD"
                omitted_rows.append(list(row) + [reason])
                continue
            # --- FIN DEL BLOQUE RESTAURADO ---

            # Lógica de mapeo de libro (sin cambios)
            libro_id_sql = None # Usar None para psycopg2, que lo convierte a NULL
            libro_titulo = row.get('Titulo') 
            if pd.notna(libro_titulo) and str(libro_titulo).strip():
                libro_titulo_norm = normalize_name(libro_titulo)
                libro_id = libro_map.get(libro_titulo_norm)
                if libro_id:
                    libro_id_sql = str(libro_id)
                else:
                    libros_no_encontrados.add(libro_titulo)
            
            # Lógica de mes y año (sin cambios)
            mes_texto = str(row.get('Mes', '')).strip().lower()
            mes_val = meses_map.get(mes_texto)
            try:
                ano_val = str(int(float(row['Año'])))
            except (ValueError, TypeError):
                omitted_rows.append(list(row) + ["Año inválido"]); continue
            if not mes_val:
                omitted_rows.append(list(row) + ["Mes inválido"]); continue
            
            # Lógica de estado de envío (TRADUCIDA)
            cursor.execute("SELECT metodo_entrega FROM suscripciones WHERE cliente_id = %s", (cliente_id,))
            resultado_metodo = cursor.fetchone()
            metodo_entrega = resultado_metodo[0] if resultado_metodo else "SIN INFORMACION"
            
            if metodo_entrega == 'RETIRO': estado_envio = 'RETIRADO'
            elif metodo_entrega in ['BLUEXPRESS', 'PAKET', 'STARKEN']: estado_envio = 'ENVIADO'
            else: estado_envio = 'PENDIENTE'

            pagado = 'TRUE'
            envio_pagado = 'TRUE'
            fecha_asignacion_sql = f"{ano_val}-{mes_val}-01 00:00:00"
            
            # CONSTRUCCIÓN DE LA SENTENCIA PARA POSTGRESQL
            sql = """
                INSERT INTO asignaciones (cliente_id, libro_suscripcion_id, ano, mes, pagado, envio_pagado, estado_envio, fecha_asignacion) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cliente_id, ano, mes) DO UPDATE SET 
                    libro_suscripcion_id = EXCLUDED.libro_suscripcion_id,
                    estado_envio = EXCLUDED.estado_envio,
                    pagado = EXCLUDED.pagado,
                    envio_pagado = EXCLUDED.envio_pagado;
            """
            params = (cliente_id, libro_id_sql, ano_val, mes_val, pagado, envio_pagado, estado_envio, fecha_asignacion_sql)
            
            cursor.execute(sql, params)
            comandos_ejecutados += 1
            
        conn.commit()
        print(f"\n✅ Éxito: {comandos_ejecutados} registros procesados y guardados en la nube.")
        
        # --- Lógica de reportes (sin cambios) ---
        
    except psycopg2.Error as e:
        if conn: conn.rollback()
        print(f"Ocurrió un error de base de datos: {e}")
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    migrate_csv_to_cloud()