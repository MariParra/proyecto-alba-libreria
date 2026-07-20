import sqlite3
import os
import requests
import time
import json
import re

# --- CONFIGURACIÓN DE RUTAS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) 

JSON_FILE_PATH = os.path.join(BASE_DIR, "1_input_data", "libros.json") 
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
API_KEY = "AIzaSyCBBVxSu1idcCwsFovSKxF6LpZdUP3EaDE" 

# (El resto de las funciones de mapeo de género y API no necesitan cambios)
# ... (GENRES_MAP, clean_and_map_genre, fetch_book_data_from_api) ...
GENRES_MAP = {
    "DARK ROMANCE": "Dark Romance", "DARK ACADEMIA": "Dark Academy", "DARK ACADEMY": "Dark Academy",
    "PSYCHOLOGICAL THRILLER": "Thriller Psicológico", "THRILLER PSICOLÓGICO": "Thriller Psicológico", "THRILLER PSICOLOGICO": "Thriller Psicológico",
    "ROMANTASY": "Romantasy", "SCIENCE FICTION": "Ciencia Ficción", "CIENCIA FICCIÓN": "Ciencia Ficción", "CIENCIA FICCION": "Ciencia Ficción", "SCI-FI": "Ciencia Ficción",
    "ROMANCE": "Romance", "ROMÁNTICA": "Romance", "ROMANTICA": "Romance", "LOVE": "Romance",
    "FANTASY": "Fantasía", "FANTASÍA": "Fantasía", "FANTASIA": "Fantasía",
    "DYSTOPIA": "Distopía", "DISTOPÍA": "Distopía", "DISTOPIA": "Distopía",
    "HISTORICAL": "Histórico", "HISTÓRICO": "Histórico", "HISTORICO": "Histórico",
    "CLASSIC": "Clásicos", "CLÁSICO": "Clásicos", "CLASICO": "Clásicos",
    "POETRY": "Poesía", "POESÍA": "Poesía", "POESIA": "Poesía",
    "LGBT": "LGTBQ+", "QUEER": "LGTBQ+", "GAY": "LGTBQ+", "LESBIAN": "LGTBQ+",
    "EROTIC": "Spicy", "ERÓTICA": "Spicy", "EROTICA": "Spicy", "SPICY": "Spicy",
    "HORROR": "Terror y Horror", "TERROR": "Terror y Horror", "MACABRE": "Terror y Horror",
    "THRILLER": "Thriller", "SUSPENSE": "Thriller", "SUSPENSO": "Thriller", "MYSTERY": "Thriller", "MISTERIO": "Thriller", "DETECTIVE": "Thriller", "POLICIAL": "Thriller",
    "FICTION": "Ficción General", "FICCIÓN": "Ficción General", "LITERARY": "Ficción General",
    "HEALING FICTION": "healing fiction"
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

def fetch_book_data_from_api(title):
    clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
    encoded_title = requests.utils.quote(clean_title)
    url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{encoded_title}&maxResults=1&key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "items" in data and data["items"]:
            info = data["items"][0]["volumeInfo"]
            return {
                "autor": ", ".join(info.get("authors", ["SIN INFORMACION"])),
                "genero": clean_and_map_genre(info.get("categories", []), info.get("description", "")),
                "editorial": info.get("publisher", "SIN INFORMACION")
            }
    except requests.exceptions.RequestException: pass
    return {}


def run_import():
    reporte = {"libros_procesados": 0, "nuevos_libros": 0, "libros_actualizados": 0, "error": None}
    
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            libros_a_procesar = json.load(f)
    except FileNotFoundError:
        reporte["error"] = f"No se encontró el archivo {JSON_FILE_PATH}."
        print(json.dumps(reporte))
        return
    except json.JSONDecodeError:
        reporte["error"] = f"El archivo {JSON_FILE_PATH} no es un JSON válido."
        print(json.dumps(reporte))
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for libro_data in libros_a_procesar:
            reporte["libros_procesados"] += 1
            
            titulo = clean_value(libro_data.get("titulo"), default=None)
            if not titulo:
                print(f"  - Omitiendo registro sin título: {libro_data}")
                continue

            print(f"Procesando: {titulo}")

            # --- LÓGICA DE ENCUADERNACIÓN CORREGIDA ---
            encuadernacion_valida = ['TAPA DURA', 'TAPA BLANDA', 'BOLSILLO']
            enc_json = libro_data.get("encuadernacion")
            
            # Limpia, convierte a mayúsculas y valida el valor de encuadernación
            if isinstance(enc_json, str) and enc_json.strip().upper() in encuadernacion_valida:
                encuadernacion_final = enc_json.strip().upper()
            else:
                encuadernacion_final = 'TAPA BLANDA' # Valor por defecto si es nulo, vacío o inválido

            libro_final = {
                "titulo": titulo,
                "autor": clean_value(libro_data.get("autor")),
                "genero": clean_value(libro_data.get("genero")),
                "editorial": clean_value(libro_data.get("editorial")),
                "encuadernacion": encuadernacion_final
            }

            if any(libro_final[key] == "SIN INFORMACION" for key in ["autor", "genero", "editorial"]):
                print("  - Información incompleta. Consultando Google Books API...")
                api_data = fetch_book_data_from_api(libro_final['titulo'])
                if api_data:
                    if libro_final["autor"] == "SIN INFORMACION": libro_final["autor"] = api_data.get("autor", "SIN INFORMACION")
                    if libro_final["genero"] == "SIN INFORMACION": libro_final["genero"] = api_data.get("genero", "OTRO")
                    if libro_final["editorial"] == "SIN INFORMACION": libro_final["editorial"] = api_data.get("editorial", "SIN INFORMACION")
                    print("  - Datos enriquecidos.")
                else:
                    print("  - No se encontraron datos adicionales en la API.")
                time.sleep(1)

            cursor.execute("SELECT * FROM libros WHERE titulo = ?", (libro_final['titulo'],))
            libro_existente = cursor.fetchone()

            if not libro_existente:
                print(f"  - Creando nuevo libro en la base de datos.")
                cursor.execute("""
                    INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (libro_final['titulo'], libro_final['autor'], libro_final['genero'], 
                    libro_final['editorial'], libro_final['encuadernacion'], 0, 0.0))
                reporte["nuevos_libros"] += 1
            else:
                libro_id, _, autor_db, genero_db, editorial_db, enc_db, _, _ = libro_existente
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
                    set_clause = ", ".join([f"{field} = ?" for field in update_fields])
                    params = list(update_fields.values()) + [libro_id]
                    cursor.execute(f"UPDATE libros SET {set_clause} WHERE libro_id = ?", tuple(params))
                    print(f"  - Actualizando campos: {', '.join(update_fields.keys())}")
                    reporte["libros_actualizados"] += 1
                else:
                    print("  - El libro ya existe y no requiere actualización.")
        
        # El commit se hace fuera del bucle, al final de todas las operaciones
        conn.commit()

    except sqlite3.Error as e:
        reporte["error"] = str(e)
        conn.rollback() # Si hay un error, revierte todos los cambios de esta ejecución
    except Exception as e:
        reporte["error"] = str(e)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    print("\n--- REPORTE DE IMPORTACIÓN ---")
    print(json.dumps(reporte, indent=2))

if __name__ == "__main__":
    run_import()