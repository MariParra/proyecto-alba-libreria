import sqlite3
import pandas as pd
import os
import unicodedata
from datetime import datetime

# --- (CONFIGURACIÓN DE RUTAS - SIN CAMBIOS) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) 
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
posibles_rutas = [
    os.path.join(BASE_DIR, "migracion_corregido.csv"),
    os.path.join(BASE_DIR, "1_input_data", "migracion_corregido.csv"),
    os.path.join(BASE_DIR, "1_input_data", "migracion_20260715.csv") 
]
CSV_PATH = next((ruta for ruta in posibles_rutas if os.path.exists(ruta)), None)
OUTPUT_SQL_PATH = os.path.join(BASE_DIR, "4_output_reports", "migracion_asignaciones.sql")
MISSING_CLIENTS_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_clientes_faltantes.csv")
MISSING_BOOKS_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_libros_faltantes.csv")
SKIPPED_ROWS_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_filas_omitidas.csv")

def normalize_name(name):
    if not isinstance(name, str): return ""
    s = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    return s.strip().upper()

MANUAL_CLIENT_FIXES = {
    "LUIS ALFREDO PEREZ DROGUETT": "Luis Pérez (Danae Martínez)",
    "KELLY ARANDA": "Kelly Araneda",
    "KELLY": "Kelly Araneda",
    "MARIANA": "Mariana parra", 
    "MELANIE": "Melanie Thomas", 
    "TAMARA AGUILERA CONTRERAS": "Tamara Aguilera",
    "JOSNELIS": "Josnelis hernandez",
    "KARLA VICENCIO": "Karla Vicencio Vargas"
}

def generate_migration_sql():
    if not CSV_PATH:
        print("Error: No se encontró ningún archivo CSV de migración.")
        return
        
    print(f"Iniciando migración de asignaciones desde:\n{CSV_PATH} ...")
    
    try:
        df = pd.read_csv(CSV_PATH, sep=None, engine='python', encoding='utf-8-sig', on_bad_lines='warn')
        df.columns = [str(c).strip().strip('\ufeff').strip('"').strip("'") for c in df.columns]
        df_original = df.copy()
    except Exception as e:
        print(f"Error al procesar el CSV: {e}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        db_clientes = pd.read_sql_query("SELECT cliente_id, nombre FROM clientes", conn).values
        cliente_map = {normalize_name(nombre): id for id, nombre in db_clientes}
        libro_map = {normalize_name(titulo): id for id, titulo in pd.read_sql_query("SELECT libro_id, titulo FROM libros", conn).values}
        
        sql_inserts = []
        clientes_no_encontrados = set()
        libros_no_encontrados = set()
        omitted_rows = []
        
        meses_map = {'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04', 'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08', 'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'}

        for index, row in df_original.iterrows():
            reason = ""
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

            libro_id_sql = "NULL"
            libro_titulo = row.get('Titulo') 
            if pd.notna(libro_titulo) and str(libro_titulo).strip():
                libro_titulo_norm = normalize_name(libro_titulo)
                libro_id = libro_map.get(libro_titulo_norm)
                if libro_id:
                    libro_id_sql = str(libro_id)
                else:
                    libros_no_encontrados.add(libro_titulo)
            
            mes_texto = str(row.get('Mes', '')).strip().lower()
            mes_val = meses_map.get(mes_texto)
            
            try:
                ano_val = str(int(float(row['Año'])))
            except (ValueError, TypeError):
                reason = "Año inválido o vacío"
                omitted_rows.append(list(row) + [reason])
                continue
            
            if not mes_val:
                reason = "Mes inválido o vacío"
                omitted_rows.append(list(row) + [reason])
                continue
            
            # --- NUEVA LÓGICA DE ESTADO BASADA EN MÉTODO DE ENTREGA ---
            
            # 1. Obtener el método de entrega del cliente desde la BD
            cursor.execute("SELECT metodo_entrega FROM suscripciones WHERE cliente_id = ?", (cliente_id,))
            resultado_metodo = cursor.fetchone()
            metodo_entrega = resultado_metodo[0] if resultado_metodo else "SIN INFORMACION"
            
            # 2. Definir el estado basado en el método
            if metodo_entrega == 'RETIRO':
                estado_envio = 'RETIRADO'
            elif metodo_entrega in ['BLUEXPRESS', 'PAKET', 'STARKEN']:
                estado_envio = 'ENVIADO'
            else: # Fallback para 'SIN INFORMACION' o cualquier otro caso
                # Usamos la lógica de fecha original como respaldo
                fecha_limite = datetime(2026, 7, 31).date()
                fecha_asignacion_dt = datetime(int(ano_val), int(mes_val), 1).date()
                if fecha_asignacion_dt <= fecha_limite:
                    estado_envio = 'OK'
                else:
                    estado_envio = 'PENDIENTE'

            # Para migraciones antiguas, asumimos que todo está pagado
            pagado = 'TRUE'
            envio_pagado = 'TRUE'
            
            fecha_asignacion_sql = f"{ano_val}-{mes_val}-01 00:00:00"
            
            sql = (
                f"INSERT INTO asignaciones (cliente_id, libro_suscripcion_id, ano, mes, pagado, envio_pagado, estado_envio, fecha_asignacion) "
                f"VALUES ({cliente_id}, {libro_id_sql}, '{ano_val}', '{mes_val}', '{pagado}', '{envio_pagado}', '{estado_envio}', '{fecha_asignacion_sql}') "
                f"ON CONFLICT(cliente_id, ano_mes) DO UPDATE SET "
                f"libro_suscripcion_id = excluded.libro_suscripcion_id, "
                f"estado_envio = excluded.estado_envio, "
                f"pagado = excluded.pagado, "
                f"envio_pagado = excluded.envio_pagado;"
            )
            sql_inserts.append(sql)
            
        conn.close()

        with open(OUTPUT_SQL_PATH, 'w', encoding='utf-8') as f:
            for insert in sql_inserts:
                f.write(insert + "\n")
        print(f"\n✅ Éxito: {len(sql_inserts)} comandos SQL generados en '{OUTPUT_SQL_PATH}'.")
        
        # --- (Lógica de reportes - SIN CAMBIOS) ---
        if omitted_rows:
            omitted_df = pd.DataFrame(omitted_rows, columns=list(df_original.columns) + ['Motivo_Omision'])
            omitted_df.to_csv(SKIPPED_ROWS_REPORT_PATH, index=False, encoding='utf-8-sig', sep=';')
            print(f"¡Atención! {len(omitted_rows)} filas fueron omitidas. Revisa: '{SKIPPED_ROWS_REPORT_PATH}'")

        if clientes_no_encontrados:
            pd.DataFrame([{"Nombre Cliente No Encontrado": c} for c in clientes_no_encontrados]).to_csv(MISSING_CLIENTS_REPORT_PATH, index=False, encoding='utf-8-sig', sep=';')
            print(f"{len(clientes_no_encontrados)} clientes no se encontraron. Revisa '{MISSING_CLIENTS_REPORT_PATH}'.")
        
        if libros_no_encontrados:
            pd.DataFrame([{"Título Libro No Encontrado": l} for l in libros_no_encontrados]).to_csv(MISSING_BOOKS_REPORT_PATH, index=False, encoding='utf-8-sig', sep=';')
            print(f"{len(libros_no_encontrados)} libros no se encontraron. Revisa '{MISSING_BOOKS_REPORT_PATH}'.")
            
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")

if __name__ == "__main__":
    generate_migration_sql()