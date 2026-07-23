import psycopg2
import pandas as pd
import os
import json
import re
import unicodedata
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURACIÓN ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
LIBREROS_DIR = os.path.join(BASE_DIR, "5_libreros")
DIR_REPORTES = os.path.join(BASE_DIR, "3_output_reports")

os.makedirs(LIBREROS_DIR, exist_ok=True)
os.makedirs(DIR_REPORTES, exist_ok=True)

TXT_NO_ENCONTRADOS = os.path.join(DIR_REPORTES, "libros_no_encontrados_historico_NUBE.txt")

# --- CONEXIÓN A LA NUBE ---
dotenv_path = os.path.join(os.path.dirname(BASE_DIR), '.env')
load_dotenv(dotenv_path)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# En app/3_scripts/libreros.py

import re # Asegúrate de que 'import re' esté al principio del archivo

def normalize_text(text):
    if not isinstance(text, str): return ""
    
    # NUEVA LÓGICA: Elimina paréntesis y su contenido (ej: "(Saga #1)")
    # Esto transformará "El rey (El príncipe cautivo #3)" en "El rey"
    text = re.sub(r'\s*\([^)]*\)', '', text).strip()
    
    # Quita acentos y tildes
    s = ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')
    
    # Limpia espacios extra y convierte a mayúsculas
    return ' '.join(s.strip().upper().split())


def run_importar_libreros():
    reporte = { "coincidencias_perfectas": 0, "coincidencias_por_titulo": 0, "ya_existentes": 0, "no_encontrados": 0, "error": None }
    libros_faltantes_global = []
    conn = None
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # --- PREPARAMOS LOS DATOS DEL INVENTARIO ---
        cursor.execute("SELECT libro_id, titulo, autor FROM libros")
        inventario_raw = cursor.fetchall()
        
        # Mapa para búsqueda exacta (Título normalizado, Autor normalizado) -> ID
        inventario_exacto_dupla = { (normalize_text(titulo), normalize_text(autor)): id for id, titulo, autor in inventario_raw if titulo and autor }
        
        # Mapa para búsqueda exacta por Título normalizado -> ID
        inventario_exacto_titulo = { normalize_text(titulo): id for id, titulo, autor in inventario_raw if titulo }
        
        if not inventario_raw:
            reporte["error"] = "No hay libros en la base de datos para comparar."
            print(json.dumps(reporte)); return

        archivos = [f for f in os.listdir(LIBREROS_DIR) if f.endswith(('.xlsx', '.csv'))]
        
        for archivo in archivos:
            nombre_base = os.path.splitext(archivo)[0].upper().strip()
            nombre_limpio = nombre_base.replace("LIBRERO DE", "").replace("HISTORICO", "").replace("LIBRERO", "").strip()
            
            # TRADUCCIÓN: LIKE a ILIKE y ? a %s
            cursor.execute("SELECT cliente_id FROM clientes WHERE nombre ILIKE %s", (f"%{nombre_limpio}%",))
            cliente_res = cursor.fetchone()
            if not cliente_res: continue
            
            cliente_id = cliente_res[0]
            ruta_archivo = os.path.join(LIBREROS_DIR, archivo)
            
            df = pd.read_excel(ruta_archivo) if archivo.endswith('.xlsx') else pd.read_csv(ruta_archivo, sep=None, engine='python', encoding='utf-8-sig', on_bad_lines='warn')
            
            col_titulo = next((c for c in df.columns if any(k in str(c).lower() for k in ['titulo', 'título', 'libro', 'nombre'])), df.columns[0])
            col_autor = next((c for c in df.columns if 'autor' in str(c).lower()), None)
            
            for index, row in df.iterrows():
                titulo_csv = normalize_text(row.get(col_titulo, ''))
                autor_csv_raw = str(row.get(col_autor, '')) # Guardamos el autor original para la BD
                autor_csv_norm = normalize_text(autor_csv_raw) if col_autor else ''
                
                if not titulo_csv or titulo_csv == 'NAN': continue
                
                libro_id_encontrado = None
                metodo_encontrado = None
                
                # --- PRIORIDAD 1: Búsqueda por Dupla (Título, Autor) ---
                if autor_csv_norm and (titulo_csv, autor_csv_norm) in inventario_exacto_dupla:
                    libro_id_encontrado = inventario_exacto_dupla[(titulo_csv, autor_csv_norm)]
                    metodo_encontrado = "coincidencias_perfectas"
                
                # --- PRIORIDAD 2: Búsqueda por Título Exacto ---
                if not libro_id_encontrado and titulo_csv in inventario_exacto_titulo:
                    libro_id_encontrado = inventario_exacto_titulo[titulo_csv]
                    metodo_encontrado = "coincidencias_por_titulo"
                    
                # --- GUARDADO ---
                if libro_id_encontrado:
                    # Primero comprobamos si ya existe para evitar errores en PostgreSQL
                    cursor.execute("SELECT 1 FROM librero_historico WHERE cliente_id = %s AND libro_id = %s", (cliente_id, libro_id_encontrado))
                    if cursor.fetchone():
                        reporte["ya_existentes"] += 1
                    else:
                        # Si no existe, lo insertamos
                        cursor.execute("INSERT INTO librero_historico (cliente_id, libro_id, autor_historico) VALUES (%s, %s, %s)", (cliente_id, libro_id_encontrado, autor_csv_raw.strip()))
                        reporte[metodo_encontrado] += 1
                else:
                    reporte["no_encontrados"] += 1
                    libros_faltantes_global.append(f"{row.get(col_titulo, '')} | {autor_csv_raw} (Archivo: {archivo})")
                    
        conn.commit()
        
        if libros_faltantes_global:
            with open(TXT_NO_ENCONTRADOS, 'w', encoding='utf-8') as f:
                f.write(f"--- REPORTE DE HISTÓRICOS: LIBROS NO ENCONTRADOS ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ---\n\n")
                for t in set(libros_faltantes_global): f.write(f"- {t}\n")
                
    except Exception as e:
        reporte["error"] = str(e)
    finally:
        if conn: conn.close()
    
    print(json.dumps(reporte))

if __name__ == "__main__":
    run_importar_libreros()