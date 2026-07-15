import sqlite3
import os
import requests
import time
import json
import re

# --- CONFIGURACIÓN ---
# Rutas relativas asumiendo que este script corre en el directorio principal del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
JSON_FILE_PATH = os.path.join(BASE_DIR, "1_input_data", "libros.json")
# Esta clave es de ejemplo, asegúrate de tener la tuya si la cambiaste
API_KEY = "AIzaSyCBBVxSu1idcCwsFovSKxF6LpZdUP3EaDE" 

# --- MAPE DE GÉNEROS RESTAURADO ---
GENRES_MAP = {
    # Subgéneros y términos compuestos
    "DARK ROMANCE": "Dark Romance", "DARK ACADEMIA": "Dark Academy", "DARK ACADEMY": "Dark Academy",
    "PSYCHOLOGICAL THRILLER": "Thriller Psicológico", "THRILLER PSICOLÓGICO": "Thriller Psicológico", "THRILLER PSICOLOGICO": "Thriller Psicológico",
    "ROMANTASY": "Romantasy", "SCIENCE FICTION": "Ciencia Ficción", "CIENCIA FICCIÓN": "Ciencia Ficción", "CIENCIA FICCION": "Ciencia Ficción", "SCI-FI": "Ciencia Ficción",
    # Géneros principales
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
    # Fallbacks
    "FICTION": "Ficción General", "FICCIÓN": "Ficción General", "LITERARY": "Ficción General"
}

def clean_and_map_genre(categories_list, description):
    if categories_list:
        categorias_str = " ".join(categories_list).upper()
        for key, val in GENRES_MAP.items():
            if key in categorias_str:
                return val
    if description:
        desc_upper = str(description).upper()
        for key, val in GENRES_MAP.items():
            if key in desc_upper:
                return val
    if not categories_list and not description:
        return "SIN INFORMACION"
    return "OTRO"

def fetch_book_data(title):
    clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
    encoded_title = requests.utils.quote(clean_title)
    url_intitle = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{encoded_title}&maxResults=1&key={API_KEY}"
    url_general = f"https://www.googleapis.com/books/v1/volumes?q={encoded_title}&maxResults=1&key={API_KEY}"

    def extract_data(data):
        if "items" in data and data["items"]:
            info = data["items"][0]["volumeInfo"]
            return {
                "titulo": info.get("title", title),
                "autor": ", ".join(info.get("authors", ["SIN INFORMACION"])),
                "genero": clean_and_map_genre(info.get("categories", []), info.get("description", "")),
                "editorial": info.get("publisher", "SIN INFORMACION")
            }
        return None

    try:
        response = requests.get(url_intitle, timeout=10)
        if response.status_code == 200:
            result = extract_data(response.json())
            if result: return result
    except Exception: pass
    try:
        response = requests.get(url_general, timeout=10)
        if response.status_code == 200:
            result = extract_data(response.json())
            if result: return result
    except Exception: pass
    
    return {"titulo": title, "autor": "SIN INFORMACION", "genero": "SIN INFORMACION", "editorial": "SIN INFORMACION"}

def run_import():
    reporte = {"clientes_procesados": 0, "nuevos_clientes": 0, "clientes_actualizados": 0, "error": None}
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            book_titles_from_json = json.load(f)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for title_in_json in book_titles_from_json:
            if not title_in_json: continue
            
            reporte["clientes_procesados"] += 1
            
            # 1. Buscar datos enriquecidos en Google Books API
            libro_api = fetch_book_data(title_in_json)
            
            # 2. Verificar si el libro ya existe en la BD (por título)
            cursor.execute("SELECT * FROM libros WHERE titulo = ?", (libro_api['titulo'],))
            libro_existente = cursor.fetchone()
            
            if not libro_existente:
                # 3. INSERT si no existe: Se inserta con stock 0 por defecto.
                cursor.execute("""
                    INSERT INTO libros (titulo, autor, genero, editorial, stock, precio) VALUES (?, ?, ?, ?, ?, ?)
                """, (libro_api['titulo'], libro_api['autor'], libro_api['genero'], libro_api['editorial'], 0, 0.0))
                reporte["nuevos_clientes"] += 1
            else:
                # 4. UPDATE si existe, pero solo si los campos están vacíos. NUNCA se toca stock ni precio.
                libro_id, _, autor_db, genero_db, editorial_db, _, _ = libro_existente
                update_fields = []
                params = []
                
                if (not autor_db or autor_db == "SIN INFORMACION") and libro_api.get('autor'):
                    update_fields.append("autor = ?")
                    params.append(libro_api['autor'])
                if (not genero_db or genero_db == "SIN INFORMACION") and libro_api.get('genero'):
                    update_fields.append("genero = ?")
                    params.append(libro_api['genero'])
                if (not editorial_db or editorial_db == "SIN INFORMACION") and libro_api.get('editorial'):
                    update_fields.append("editorial = ?")
                    params.append(libro_api['editorial'])
                    
                if update_fields:
                    query = f"UPDATE libros SET {', '.join(update_fields)} WHERE libro_id = ?"
                    params.append(libro_id)
                    cursor.execute(query, params)
                    reporte["clientes_actualizados"] += 1
            
            time.sleep(1) # Pausa para no saturar la API de Google
            
        conn.commit()
        conn.close()
    except Exception as e:
        reporte["error"] = str(e)
        
    print(json.dumps(reporte))

if __name__ == "__main__":
    run_import()