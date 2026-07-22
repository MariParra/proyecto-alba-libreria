import sqlite3
import pandas as pd
import os
import json
from datetime import datetime
from thefuzz import process

# --- CONFIGURACIÓN DE RUTAS Y UMBRAL ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBREROS_DIR = os.path.join(BASE_DIR, "6_libreros")
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
DIR_REPORTES = os.path.join(BASE_DIR, "4_output_reports")
UMBRAL_DE_CONFIANZA = 90 # Porcentaje de similitud mínimo

os.makedirs(LIBREROS_DIR, exist_ok=True)
os.makedirs(DIR_REPORTES, exist_ok=True)
TXT_NO_ENCONTRADOS = os.path.join(DIR_REPORTES, "libros_no_encontrados_historico.txt")

def run_importar_libreros():
    reporte = { "clientas_procesadas": 0, "libros_historicos_agregados": 0, "libros_ya_existentes": 0, "libros_no_encontrados": 0, "error": None }
    archivos = [f for f in os.listdir(LIBREROS_DIR) if f.endswith(('.xlsx', '.csv'))]
    
    if not archivos:
        reporte["error"] = "No se encontraron archivos .xlsx o .csv en la carpeta 6_libreros."
        print(json.dumps(reporte)); return

    libros_faltantes_global = []

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT libro_id, UPPER(titulo) FROM libros")
        inventario_completo = {titulo_db: libro_id for libro_id, titulo_db in cursor.fetchall()}
        lista_titulos_db = list(inventario_completo.keys())

        if not lista_titulos_db:
            reporte["error"] = "No hay libros en la base de datos para comparar."
            print(json.dumps(reporte)); return

        for archivo in archivos:
            nombre_base = os.path.splitext(archivo)[0].upper().strip()
            nombre_limpio = nombre_base.replace("LIBRERO DE", "").replace("HISTORICO", "").replace("LIBRERO", "").strip()
            
            cursor.execute("SELECT cliente_id FROM clientes WHERE UPPER(nombre) LIKE ?", (f"%{nombre_limpio}%",))
            cliente_res = cursor.fetchone()
            
            if not cliente_res: continue
            cliente_id = cliente_res[0]
            reporte["clientas_procesadas"] += 1
            
            try:
                ruta_archivo = os.path.join(LIBREROS_DIR, archivo)
                if archivo.endswith('.csv'): df = pd.read_csv(ruta_archivo, sep=None, engine='python')
                else: df = pd.read_excel(ruta_archivo)
            except Exception as e:
                print(f"  - Error leyendo {archivo}: {e}")
                continue

            col_titulo = next((c for c in df.columns if any(k in str(c).lower() for k in ['titulo', 'título', 'libro', 'nombre'])), df.columns[0])

            for index, row in df.iterrows():
                titulo_historial = str(row.get(col_titulo, '')).strip().upper()
                if not titulo_historial or titulo_historial == 'NAN': continue

                mejor_coincidencia, puntaje = process.extractOne(titulo_historial, lista_titulos_db)
                
                libro_id_encontrado = None
                if puntaje >= UMBRAL_DE_CONFIANZA:
                    libro_id_encontrado = inventario_completo[mejor_coincidencia]

                if libro_id_encontrado:
                    try:
                        cursor.execute("INSERT INTO librero_historico (cliente_id, libro_id) VALUES (?, ?)", (cliente_id, libro_id_encontrado))
                        reporte["libros_historicos_agregados"] += 1
                    except sqlite3.IntegrityError:
                        reporte["libros_ya_existentes"] += 1
                else:
                    reporte["libros_no_encontrados"] += 1
                    libros_faltantes_global.append(f"{titulo_historial} (Archivo: {archivo}, Mejor coincidencia: '{mejor_coincidencia}' con {puntaje}%)")

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