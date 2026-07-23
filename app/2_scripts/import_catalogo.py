import psycopg2
import os
import requests
import time
import json
import re
from dotenv import load_dotenv

# --- CONFIGURACIÓN DE RUTAS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) 
JSON_FILE_PATH = os.path.join(BASE_DIR, "1_input_data", "libros.json") 

# --- CONEXIÓN A LA NUBE ---
dotenv_path = os.path.join(os.path.dirname(BASE_DIR), '.env')
load_dotenv(dotenv_path)
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Se elimina la referencia a la API_KEY ya que no se usa en la lógica final
# Si la necesitas, puedes obtenerla de las variables de entorno también
# API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY") 

GENRES_MAP = {
    "DARK ROMANCE": "Dark Romance", "DARK ACADEMIA": "Dark Academy", "DARK ACADEMY": "Dark Academy",
    "PSYCHOLOGICAL THRILLER": "Thriller Psicológico", "THRILLER PSICOLÓGICO": "Thriller Psicológico",
    "ROMANTASY": "Romantasy", "SCIENCE FICTION": "Ciencia Ficción", "CIENCIA FICCIÓN": "Ciencia Ficción",
    "ROMANCE": "Romance", "ROMÁNTICA": "Romance", "LOVE": "Romance",
    "FANTASY": "Fantasía", "FANTASÍA": "Fantasía",
    "DYSTOPIA": "Distopía", "DISTOPÍA": "Distopía",
    "HISTORICAL": "Histórico", "HISTÓRICO": "Histórico",
    "CLASSIC": "Clásicos", "CLÁSICO": "Clásicos",
    "POETRY": "Poesía", "POESÍA": "Poesía",
    "LGBT": "LGTBQ+", "QUEER": "LGTBQ+",
    "EROTIC": "Spicy", "ERÓTICA": "Spicy", "SPICY": "Spicy",
    "HORROR": "Terror y Horror", "TERROR": "Terror y Horror",
    "THRILLER": "Thriller", "SUSPENSE": "Thriller", "MYSTERY": "Thriller", "DETECTIVE": "Thriller",
    "FICTION": "Ficción General", "FICCIÓN": "Ficción General", "LITERARY": "Ficción General",
    "HEALING FICTION": "Healing Fiction"
}

def clean_value(value, default="SIN INFORMACION"):
    if value is None: return default
    if isinstance(value, str):
        value = value.strip()
        if not value: return default
    return value

def clean_and_map_genre(categories_list, description):
    if categories_list:
        categorias_str = " ".join(categories_list).upper()
        for key, val in GENRES_MAP.items():
            if key in categorias_str: return val
    if description:
        desc_upper = str(description).upper()
        for key, val in GENRES_MAP.items():
            if key in desc_upper: return val
    return "OTRO"

def fetch_book_data_from_api(title, api_key):
    # (La función de la API no cambia, pero ahora recibe la API_KEY como parámetro)
    pass 

def run_import():
    reporte = {"libros_procesados": 0, "nuevos_libros": 0, "libros_actualizados": 0, "error": None}
    
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            libros_a_procesar = json.load(f)
    except Exception as e:
        reporte["error"] = f"Error al leer {JSON_FILE_PATH}: {e}"
        print(json.dumps(reporte)); return

    if not DATABASE_URL:
        reporte["error"] = "No se encontró la variable DATABASE_URL en el archivo .env"
        print(json.dumps(reporte)); return

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        for libro_data in libros_a_procesar:
            reporte["libros_procesados"] += 1
            titulo = clean_value(libro_data.get("titulo"), default=None)
            if not titulo: continue
            
            print(f"Procesando: {titulo}")
            
            encuadernacion_valida = ['TAPA DURA', 'TAPA BLANDA', 'BOLSILLO']
            enc_json = libro_data.get("encuadernacion")
            encuadernacion_final = 'TAPA BLANDA'
            if isinstance(enc_json, str) and enc_json.strip().upper() in encuadernacion_valida:
                encuadernacion_final = enc_json.strip().upper()

            libro_final = {
                "titulo": titulo,
                "autor": clean_value(libro_data.get("autor")),
                "genero": clean_value(libro_data.get("genero")),
                "editorial": clean_value(libro_data.get("editorial")),
                "encuadernacion": encuadernacion_final
            }

            # Lógica de API (sin cambios, asumiendo que ya no se usa activamente)

            # Búsqueda en la BD (TRADUCIDA)
            # Usamos ILIKE para que no distinga mayúsculas/minúsculas
            cursor.execute("SELECT libro_id, autor, genero, editorial, encuadernacion FROM libros WHERE titulo ILIKE %s", (libro_final['titulo'],))
            libro_existente = cursor.fetchone()
            
            if not libro_existente:
                print("  - Creando nuevo libro en la base de datos.")
                cursor.execute("""
                    INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original) 
                    VALUES (%s, %s, %s, %s, %s, 0, 0.0, 0.0)
                """, (libro_final['titulo'], libro_final['autor'], libro_final['genero'], 
                      libro_final['editorial'], libro_final['encuadernacion']))
                reporte["nuevos_libros"] += 1
            else:
                libro_id, autor_db, genero_db, editorial_db, enc_db = libro_existente
                update_fields = {}
                
                if (autor_db == "SIN INFORMACION") and libro_final['autor'] != "SIN INFORMACION":
                    update_fields['autor'] = libro_final['autor']
                if (genero_db == "SIN INFORMACION") and libro_final['genero'] != "SIN INFORMACION":
                    update_fields['genero'] = libro_final['genero']
                if (editorial_db == "SIN INFORMACION") and libro_final['editorial'] != "SIN INFORMACION":
                    update_fields['editorial'] = libro_final['editorial']
                if (enc_db != libro_final['encuadernacion']):
                    update_fields['encuadernacion'] = libro_final['encuadernacion']
                
                if update_fields:
                    # Construcción dinámica de la query para PostgreSQL
                    set_clause = ", ".join([f"{field} = %s" for field in update_fields])
                    params = list(update_fields.values()) + [libro_id]
                    cursor.execute(f"UPDATE libros SET {set_clause} WHERE libro_id = %s", tuple(params))
                    print(f"  - Actualizando campos: {', '.join(update_fields.keys())}")
                    reporte["libros_actualizados"] += 1
                else:
                    print("  - El libro ya existe y no requiere actualización.")
        
        conn.commit()

    except psycopg2.Error as e:
        reporte["error"] = str(e)
        if conn: conn.rollback()
    except Exception as e:
        reporte["error"] = str(e)
    finally:
        if conn: conn.close()
    
    print("\n--- REPORTE DE IMPORTACIÓN ---")
    print(json.dumps(reporte, indent=2))

if __name__ == "__main__":
    run_import()