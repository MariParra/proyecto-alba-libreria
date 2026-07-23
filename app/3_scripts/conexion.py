import psycopg2
import os
from dotenv import load_dotenv

def conectar_db():
    """
    Se conecta a la base de datos PostgreSQL en la nube usando la URL 
    almacenada en el archivo .env.
    """
    # 1. Cargar las variables del archivo .env
    # Buscamos el archivo .env en la carpeta raíz del proyecto
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ENV_PATH = os.path.join(BASE_DIR, ".env")
    load_dotenv(ENV_PATH)

    # 2. Obtener la URL de la base de datos
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise Exception("No se encontró la variable DATABASE_URL en el archivo .env. Asegúrate de que el archivo exista en la raíz del proyecto.")

    # 3. Pequeña corrección para compatibilidad
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    # 4. Intentar conectar a la base de datos en la nube
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        # Si falla, lanzamos un error claro para saber qué pasó
        raise Exception(f"No se pudo conectar a la base de datos en la nube. Revisa tu conexión a internet y la DATABASE_URL en el archivo .env. Detalle del error: {e}")