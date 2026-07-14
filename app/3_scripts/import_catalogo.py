import sqlite3
import os
import requests
import time
import json

# -- CONFIGURAR RUTAS --
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "libreria.db")
JSON_FILE_PATH = os.path.join(BASE_DIR, "libros.json")

# -- ASIGNAR CLAVE DE API --
API_KEY = "AIzaSyCBBVxSu1idcCwsFovSKxF6LpZdUP3EaDE" 

def fetch_book_data(title):
    # -- CODIFICAR TITULO PARA URL --
    encoded_title = requests.utils.quote(title)
    
    # -- CONSTRUIR URLS DE BUSQUEDA --
    url_intitle = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{encoded_title}&langRestrict=es&maxResults=1&key={API_KEY}"
    url_general = f"https://www.googleapis.com/books/v1/volumes?q={encoded_title}&langRestrict=es&maxResults=1&key={API_KEY}"

    # -- BUSCAR POR TITULO EXACTO --
    try:
        response = requests.get(url_intitle, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "items" in data and data["items"]:
                info = data["items"][0]["volumeInfo"]
                official_title = info.get("title", title)
                author = ", ".join(info.get("authors", ["SIN INFORMACION"]))
                genre = ", ".join(info.get("categories", ["SIN INFORMACION"]))
                publisher = info.get("publisher", "SIN INFORMACION")
                return official_title, author, genre, publisher
    except Exception:
        pass

    # -- BUSCAR DE FORMA GENERAL --
    try:
        response = requests.get(url_general, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "items" in data and data["items"]:
                info = data["items"][0]["volumeInfo"]
                official_title = info.get("title", title)
                author = ", ".join(info.get("authors", ["SIN INFORMACION"]))
                genre = ", ".join(info.get("categories", ["SIN INFORMACION"]))
                publisher = info.get("publisher", "SIN INFORMACION")
                return official_title, author, genre, publisher
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

    # -- INICIAR CONTADORES --
    success_count = 0
    skipped_count = 0

    # -- PROCESAR CADA LIBRO --
    for title in book_titles:
        # -- VERIFICAR SI EL TITULO ORIGINAL YA EXISTE --
        cursor.execute("SELECT 1 FROM libros WHERE UPPER(titulo) = UPPER(?)", (title,))
        if cursor.fetchone():
            skipped_count += 1
            continue

        print(f"Buscando en Google Books: {title}...")
        
        # -- OBTENER DATOS DE LA API --
        official_title, author, genre, publisher = fetch_book_data(title)
        
        # -- VERIFICAR SI EL TITULO OFICIAL YA EXISTE --
        cursor.execute("SELECT 1 FROM libros WHERE UPPER(titulo) = UPPER(?)", (official_title,))
        if cursor.fetchone():
            skipped_count += 1
            continue

        # -- INSERTAR NUEVO LIBRO --
        try:
            cursor.execute(
                "INSERT INTO libros (titulo, autor, genero, editorial) VALUES (?, ?, ?, ?)",
                (official_title, author, genre, publisher)
            )
            conn.commit()
            success_count += 1
        except Exception as e:
            print(f"Error guardando '{title}': {e}")
        
        # -- ESPERAR UN SEGUNDO PARA NO SATURAR LA API --
        time.sleep(1) 

    # -- CERRAR CONEXION --
    conn.close()
    print(f"\nImportacion completada: {success_count} guardados con exito, {skipped_count} saltados por duplicado.")

if __name__ == "__main__":
    run_import()