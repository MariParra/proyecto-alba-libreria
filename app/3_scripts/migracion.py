import sqlite3
import pandas as pd
import os
import json
import difflib

# -- CONFIGURAR RUTAS --
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
JSON_PATH = os.path.join(BASE_DIR, "1_input_data", "libros.json")
CSV_PATH = os.path.join(BASE_DIR, "1_input_data", "INSCRIPCIONES CAJA MENSUAL - CAJITAS.csv") 
CLEAN_CSV_PATH = os.path.join(BASE_DIR, "4_output_reports", "CAJITAS_CORREGIDO.csv")
OUTPUT_SQL_PATH = os.path.join(BASE_DIR, "4_output_reports", "migracion_asignaciones.sql")
MISSING_REPORT_PATH = os.path.join(BASE_DIR, "4_output_reports", "reporte_faltantes.csv")

def get_best_match(raw_title, official_dict):
    """Algoritmo de corrección automática de títulos (Fuzzy Matching)."""
    raw_upper = str(raw_title).strip().upper()
    if not raw_upper or raw_upper == 'NAN': return raw_title
    if raw_upper in official_dict: return official_dict[raw_upper]
    
    for off_up, off_orig in official_dict.items():
        if raw_upper in off_up: return off_orig
        
    matches = difflib.get_close_matches(raw_upper, official_dict.keys(), n=1, cutoff=0.6)
    if matches: return official_dict[matches[0]]
    
    return raw_title

def generate_migration_sql():
    print("Iniciando estandarización y migración...")
    
    # --- 1. CARGAR CATÁLOGO OFICIAL (JSON) ---
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            official_titles = json.load(f)
        official_dict = {t.upper(): t for t in official_titles}
    except Exception as e:
        print(f"Error al leer libros.json: {e}")
        return
        
    # --- 2. CARGAR Y CORREGIR EL CSV (CON LÓGICA RESTAURADA) ---
    try:
        df = pd.read_csv(CSV_PATH, sep=None, engine='python', on_bad_lines='skip')
        df.columns = df.columns.str.strip() # Limpieza de encabezados
        
        col_libro = next((c for c in df.columns if 'libro' in c.lower() or 'titulo' in c.lower()), 'Titulo')
        col_cliente = next((c for c in df.columns if 'client' in c.lower()), 'Clienta')
        
        print(f"Filas originales en el CSV: {len(df)}")
        df.dropna(subset=[col_cliente, 'Año', 'Mes'], inplace=True) # DROPNA reforzado
        print(f"Filas con datos válidos después de la limpieza: {len(df)}")
        
        print(f"Corrigiendo nombres de libros en la columna '{col_libro}'...")
        df[col_libro] = df[col_libro].apply(lambda x: get_best_match(x, official_dict) if pd.notna(x) else x)
        
        df.to_csv(CLEAN_CSV_PATH, index=False, encoding='utf-8-sig', sep=';')
    except Exception as e:
        print(f"Error procesando el CSV: {e}")
        return

    # --- 3. CONECTAR A BD Y GENERAR SQL ---
    try:
        conn = sqlite3.connect(DB_PATH)
        cliente_map = {str(nombre).strip().upper(): id for id, nombre in pd.read_sql_query("SELECT cliente_id, nombre FROM clientes", conn).values}
        libro_map = {str(titulo).strip().upper(): id for id, titulo in pd.read_sql_query("SELECT libro_id, titulo FROM libros", conn).values}
        
        sql_inserts, libros_no_encontrados = [], set()
        
        meses_map = {'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04', 'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08', 'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'}

        for _, row in df.iterrows():
            cliente_nombre_raw = str(row.get(col_cliente, '')).strip()
            libro_titulo_raw = str(row.get(col_libro, '')).strip()
            
            if not cliente_nombre_raw or cliente_nombre_raw.lower() == 'nan': continue
            
            cliente_id = cliente_map.get(cliente_nombre_raw.upper())
            if not cliente_id: continue 

            libro_id_sql = "NULL"
            if libro_titulo_raw and libro_titulo_raw.lower() != 'nan':
                libro_id = libro_map.get(libro_titulo_raw.upper())
                if libro_id: 
                    libro_id_sql = str(libro_id)
                else: 
                    libros_no_encontrados.add(libro_titulo_raw)
            
            mes_texto = str(row.get('Mes', '')).strip().lower()
            
            try:
                ano_val = str(int(float(row['Año'])))
            except (ValueError, TypeError):
                continue
            
            mes_val = meses_map.get(mes_texto)
            if not mes_val: continue
            
            fecha_asignacion = f"{ano_val}-{mes_val}-01 00:00:00"
            pagado_csv = str(row.get('Pagado', 'FALSE')).strip().upper()
            
            # REGLA DE NEGOCIO ESTRICA
            if int(ano_val) < 2026 or (int(ano_val) == 2026 and int(mes_val) <= 6):
                estado_envio = 'OK'
                envio_pagado = 'TRUE'
                pagado = 'TRUE'
            else:
                estado_envio = 'PENDIENTE'
                envio_pagado = 'FALSE'
                pagado = 'FALSE'
                
            sql = (
                f"INSERT INTO asignaciones (cliente_id, libro_suscripcion_id, ano, mes, pagado, envio_pagado, estado_envio, fecha_asignacion) "
                f"VALUES ({cliente_id}, {libro_id_sql}, '{ano_val}', '{mes_val}', '{pagado}', '{envio_pagado}', '{estado_envio}', '{fecha_asignacion}') "
                f"ON CONFLICT(cliente_id, ano, mes) DO UPDATE SET "
                f"libro_suscripcion_id = excluded.libro_suscripcion_id, "
                f"estado_envio = excluded.estado_envio, "
                f"pagado = excluded.pagado, "
                f"envio_pagado = excluded.envio_pagado, "
                f"fecha_asignacion = excluded.fecha_asignacion;"
            )
            sql_inserts.append(sql)
            
        conn.close()

        with open(OUTPUT_SQL_PATH, 'w', encoding='utf-8') as f:
            for insert in sql_inserts: f.write(insert + "\n")
        print(f"\n✅ Éxito: {len(sql_inserts)} comandos SQL generados en '{OUTPUT_SQL_PATH}'.")
        
        if libros_no_encontrados:
            pd.DataFrame([{"Tipo": "Libro", "Nombre": l} for l in libros_no_encontrados]).to_csv(MISSING_REPORT_PATH, index=False, encoding='utf-8-sig')
            print(f"⚠️ ¡Atención! Algunos libros no se encontraron. Revisa '{MISSING_REPORT_PATH}'.")
            
    except Exception as e:
        print(f"Ocurrió un error inesperado en la fase de BD: {e}")

if __name__ == "__main__":
    generate_migration_sql()