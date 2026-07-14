import sqlite3
import os
import json
import time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

# --- CONFIGURACION DE RUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "libreria.db")
JSON_FILE_PATH = os.path.join(BASE_DIR, "libros.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")

def get_authorized_session():
    # -- AUTENTICARSE CON CREDENTIALS.JSON PARA OBTENER UNA SESION CON CUOTA --
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"DEBUG: No se encontro {CREDENTIALS_FILE}. Se realizara consulta publica.")
        return None
    try:
        # Definir el alcance necesario para consultar la API de Google Books
        scopes = ["https://www.googleapis.com/auth/books"]
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=scopes
        )
        # Crear una sesion autenticada que inyectara los tokens en cada peticion
        session = AuthorizedSession(credentials)
        return session
    except Exception as e:
        print(f"DEBUG: Error al iniciar sesion autenticada: {e}")
        return None

def fetch_book_data(session, title):
    # -- PREPARAR URL DE BUSQUEDA --
    import requests
    encoded_title = requests.utils.quote(title)
    
    # Intentamos primero con filtro de titulo
    url_intitle = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{encoded_title}&langRestrict=es&maxResults=1"
    url_general = f"https://www.googleapis.com/books/v1/volumes?q={encoded_title}&langRestrict=es&maxResults=1"

    # Intentar buscar usando la sesion autenticada (Plan A con intitle)
    try:
        if session:
            response = session.get(url_intitle, timeout=10)
        else:
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

    # Plan B (Busqueda general si intitle falla o no arroja resultados)
    try:
        if session:
            response = session.get(url_general, timeout=10)
        else:
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

    # Plan C: Quedarse con el titulo original del JSON como respaldo
    return title, "SIN INFORMACION", "SIN INFORMACION", "SIN INFORMACION"

def run_import():
    # --- Limpiar la tabla de libros para una importacion limpia ---
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        print("\nLimpiando la tabla 'libros' para una importacion limpia...")
        cursor.execute("DELETE FROM libros;")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='libros';")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error al vaciar la base de datos: {e}")
        return

    # --- Validar existencia del JSON ---
    if not os.path.exists(JSON_FILE_PATH):
        print(f"Error: No se encontro el archivo '{JSON_FILE_PATH}'")
        return

    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            book_titles = json.load(file)
    except Exception as e:
        print(f"Error al leer el archivo JSON: {e}")
        return

    if not book_titles:
        print("El archivo 'libros.json' esta vacio.")
        return

    print(f"\nIniciando importacion definitiva de {len(book_titles)} libros...")
    
    # Iniciar sesion con credenciales de GCP
    session = get_authorized_session()
    if session:
        print("Autenticacion exitosa: Conectando a Google Books mediante Cuenta de Servicio.")
    else:
        print("Advertencia: No se pudo autenticar. Se procedera con consultas publicas.")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    success_count = 0
    skipped_count = 0

    for title in book_titles:
        # Evitar duplicados por seguridad
        cursor.execute("SELECT 1 FROM libros WHERE UPPER(titulo) = UPPER(?)", (title,))
        if cursor.fetchone():
            skipped_count += 1
            continue

        print(f"Importando: {title}...")
        official_title, author, genre, publisher = fetch_book_data(session, title)
        
        # Segunda verificacion con el titulo oficial obtenido
        cursor.execute("SELECT 1 FROM libros WHERE UPPER(titulo) = UPPER(?)", (official_title,))
        if cursor.fetchone():
            skipped_count += 1
            continue

        try:
            cursor.execute(
                "INSERT INTO libros (titulo, autor, genero, editorial) VALUES (?, ?, ?, ?)",
                (official_title, author, genre, publisher)
            )
            conn.commit()
            success_count += 1
        except Exception as e:
            print(f"Error al guardar '{title}': {e}")
        
        # Pausa recomendada de 1 segundo
        time.sleep(1)

    conn.close()
    
    print("\n--- RESUMEN DE IMPORTACION ---")
    print(f"Libros importados con exito: {success_count}")
    print(f"Libros saltados (ya existian): {skipped_count}")

if __name__ == "__main__":
    run_import()