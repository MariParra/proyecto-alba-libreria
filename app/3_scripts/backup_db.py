import sqlite3
import os
import pandas as pd
from datetime import datetime

# -- CONFIGURAR RUTAS --
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
BACKUP_DIR = os.path.join(BASE_DIR, "5_backups")

def backup_database():
    print("Iniciando proceso de respaldo doble (SQLite y Excel)...")

    # -- VERIFICAR QUE LA BASE DE DATOS ORIGINAL EXISTA --
    if not os.path.exists(DB_PATH):
        print(f"Error: No se encontro la base de datos en: {DB_PATH}")
        return

    # -- CREAR CARPETA DE RESPALDOS SI NO EXISTE --
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print("Carpeta 'respaldos' creada con exito.")

    # -- GENERAR MARCA DE TIEMPO PARA LOS NOMBRES DE ARCHIVO --
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_db_filename = f"libreria_respaldo_{timestamp}.db"
    backup_db_path = os.path.join(BACKUP_DIR, backup_db_filename)
    backup_excel_filename = f"libreria_respaldo_{timestamp}.xlsx"
    backup_excel_path = os.path.join(BACKUP_DIR, backup_excel_filename)

    origen = None
    destino_db = None

    try:
        # ==========================================
        # 1. RESPALDO NATIVO SQLITE (.db)
        # ==========================================
        origen = sqlite3.connect(DB_PATH)
        destino_db = sqlite3.connect(backup_db_path)
        origen.backup(destino_db)
        print(f"Respaldo SQLite creado: {backup_db_filename}")

        # ==========================================
        # 2. RESPALDO EN EXCEL (.xlsx)
        # ==========================================
        # -- OBTENER LA LISTA DE TODAS LAS TABLAS EN LA BASE DE DATOS --
        cursor = origen.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tablas = [fila[0] for fila in cursor.fetchall()]

        # -- ESCRIBIR CADA TABLA EN UNA PESTANA DEL EXCEL --
        with pd.ExcelWriter(backup_excel_path, engine='openpyxl') as writer:
            for tabla in tablas:
                # Extraer la tabla completa usando Pandas
                df = pd.read_sql_query(f"SELECT * FROM {tabla}", origen)
                # Guardarla en el Excel sin la columna numerica de indice
                df.to_excel(writer, sheet_name=tabla, index=False)
        
        print(f"Respaldo Excel creado: {backup_excel_filename}")

    except sqlite3.Error as e:
        print(f"Error de SQLite durante el respaldo: {e}")
    except Exception as e:
        print(f"Error inesperado al crear el Excel: {e}")
    finally:
        # -- CERRAR CONEXIONES --
        if destino_db:
            destino_db.close()
        if origen:
            origen.close()
        print(f"Proceso finalizado. Archivos guardados en: {BACKUP_DIR}")

if __name__ == "__main__":
    # -- EJECUTAR FUNCION --
    backup_database()
