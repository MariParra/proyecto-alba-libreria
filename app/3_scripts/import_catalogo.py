import sqlite3
import os
import requests
import time
import json
import re

# -- CONFIGURAR RUTAS --
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
JSON_FILE_PATH = os.path.join(BASE_DIR, "1_input_data", "libros.json")

# -- ASIGNAR CLAVE DE API --
API_KEY = "AIzaSyCBBVxSu1idcCwsFovSKxF6LpZdUP3EaDE"

# -- DEFINIR MAPA DE HOMOLOGACION DE GENEROS --
# IMPORTANTE: El orden importa. Los géneros compuestos van primero.
GENRES_MAP = {
    # 1. Subgéneros y términos compuestos (evita colisiones)
    "DARK ROMANCE": "Dark Romance",
    "DARK ACADEMIA": "Dark Academy",
    "DARK ACADEMY": "Dark Academy",
    "PSYCHOLOGICAL THRILLER": "Thriller Psicológico",
    "THRILLER PSICOLÓGICO": "Thriller Psicológico",
    "THRILLER PSICOLOGICO": "Thriller Psicológico",
    "ROMANTASY": "Romantasy",
    "SCIENCE FICTION": "Ciencia Ficción",
    "CIENCIA FICCIÓN": "Ciencia Ficción",
    "CIENCIA FICCION": "Ciencia Ficción",
    "SCI-FI": "Ciencia Ficción",
    
    # 2. Géneros principales
    "ROMANCE": "Romance",
    "ROMÁNTICA": "Romance",
    "ROMANTICA": "Romance",
    "LOVE": "Romance",
    "FANTASY": "Fantasía",
    "FANTASÍA": "Fantasía",
    "FANTASIA": "Fantasía",
    "DYSTOPIA": "Distopía",
    "DISTOPÍA": "Distopía",
    "DISTOPIA": "Distopía",
    "HISTORICAL": "Histórico",
    "HISTÓRICO": "Histórico",
    "HISTORICO": "Histórico",
    "CLASSIC": "Clásicos",
    "CLÁSICO": "Clásicos",
    "CLASICO": "Clásicos",
    "POETRY": "Poesía",
    "POESÍA": "Poesía",
    "POESIA": "Poesía",
    "LGBT": "LGTBQ+",
    "QUEER": "LGTBQ+",
    "GAY": "LGTBQ+",
    "LESBIAN": "LGTBQ+",
    "EROTIC": "Spicy",
    "ERÓTICA": "Spicy",
    "EROTICA": "Spicy",
    "SPICY": "Spicy",
    "HORROR": "Terror y Horror",
    "TERROR": "Terror y Horror",
    "MACABRE": "Terror y Horror",
    "THRILLER": "Thriller",
    "SUSPENSE": "Thriller",
    "SUSPENSO": "Thriller",
    "MYSTERY": "Thriller", 
    "MISTERIO": "Thriller",
    "DETECTIVE": "Thriller",
    "POLICIAL": "Thriller",
    
    # 3. Categorías generales (Fallbacks)
    "FICTION": "Ficción General",
    "FICCIÓN": "Ficción General",
    "LITERARY": "Ficción General"
}

def clean_and_map_genre(categories_list, description):
    # -- BUSCAR PRIMERO EN LAS CATEGORÍAS OFICIALES --
    if categories_list:
        categorias_str = " ".join(categories_list).upper()
        for key, val in GENRES_MAP.items():
            if key in categorias_str:
                return val

    # -- SI NO HAY CATEGORÍAS (O NO HUBO MATCH), BUSCAR EN LA SINOPSIS (DESCRIPCIÓN) --
    if description:
        desc_upper = str(description).upper()
        for key, val in GENRES_MAP.items():
            # Buscamos palabras clave en la descripción
            if key in desc_upper:
                return val

    # Si no hay categorías ni descripción, o no hace match con nada
    if not categories_list and not description:
        return "SIN INFORMACION"
    
    return "OTRO"

def fetch_book_data(title):
    # -- LIMPIAR EL TÍTULO (Expresión regular corregida) --
    clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
    encoded_title = requests.utils.quote(clean_title)

    # -- URLS SIN RESTRICCIÓN DE IDIOMA --
    url_intitle = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{encoded_title}&maxResults=1&key={API_KEY}"
    url_general = f"https://www.googleapis.com/books/v1/volumes?q={encoded_title}&maxResults=1&key={API_KEY}"

    def extract_data(data):
        if "items" in data and data["items"]:
            info = data["items"][0]["volumeInfo"]
            official_title = info.get("title", title)
            author = ", ".join(info.get("authors", ["SIN INFORMACION"]))
            
            raw_categories = info.get("categories", [])
            description = info.get("description", "")
            
            mapped_genre = clean_and_map_genre(raw_categories, description)
            publisher = info.get("publisher", "SIN INFORMACION")
            
            return official_title, author, mapped_genre, publisher
        return None

    # -- BUSCAR POR TITULO EXACTO --
    try:
        response = requests.get(url_intitle, timeout=10)
        if response.status_code == 200:
            result = extract_data(response.json())
            if result: return result
    except Exception:
        pass

    # -- BUSCAR DE FORMA GENERAL --
    try:
        response = requests.get(url_general, timeout=10)
        if response.status_code == 200:
            result = extract_data(response.json())
            if result: return result
    except Exception:
        pass

    # -- RETORNAR VALORES POR DEFECTO SI NO EXISTE --
    return title, "SIN INFORMACION", "SIN INFORMACION", "SIN INFORMACION"

def run_import():
    # -- LIMPIAR TABLA DE LIBROS --
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        print("\nLimpiando la tabla 'libros' para una importacion con datos reales...")
        cursor.execute("DELETE FROM libros;")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='libros';")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error al limpiar la base de datos: {e}")
        return

    # -- VERIFICAR EXISTENCIA DEL ARCHIVO JSON --
    if not os.path.exists(JSON_FILE_PATH):
        print(f"Error: No se encontro '{JSON_FILE_PATH}'")
        return

    # -- LEER ARCHIVO JSON --
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as file:
        book_titles = json.load(file)

    if not book_titles:
        print("El archivo 'libros.json' esta vacio.")
        return

    print(f"\nIniciando importacion de {len(book_titles)} libros usando API Key...")
    
    # -- CONECTAR A BASE DE DATOS --
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    success_count = 0
    skipped_count = 0

    # -- PROCESAR CADA LIBRO --
    for title in book_titles:
        # Verificar si el título original ya existe
        cursor.execute("SELECT 1 FROM libros WHERE UPPER(titulo) = UPPER(?)", (title,))
        if cursor.fetchone():
            skipped_count += 1
            continue

        print(f"Buscando en Google Books: {title}...")
        official_title, author, genre, publisher = fetch_book_data(title)

        # Verificar si el título oficial ya existe
        cursor.execute("SELECT 1 FROM libros WHERE UPPER(titulo) = UPPER(?)", (official_title,))
        if cursor.fetchone():
            skipped_count += 1
            continue

        # Insertar nuevo libro
        try:
            cursor.execute(
                "INSERT INTO libros (titulo, autor, genero, editorial) VALUES (?, ?, ?, ?)",
                (official_title, author, genre, publisher)
            )
            conn.commit()
            success_count += 1
        except Exception as e:
            print(f"Error guardando '{title}': {e}")
            
        time.sleep(1)

    conn.close()
    print(f"\nImportacion completada: {success_count} guardados con exito, {skipped_count} saltados por duplicado.")

if __name__ == "__main__":
    run_import()