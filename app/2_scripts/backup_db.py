import sqlite3
import os
import pandas as pd
from datetime import datetime

# --- CONFIGURAR RUTAS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")

# --- RUTAS DE RESPALDO ORGANIZADAS EN SUBCARPETAS ---
BACKUP_DIR_RAIZ = os.path.join(BASE_DIR, "4_backups")
BACKUP_DIR_SQLITE = os.path.join(BACKUP_DIR_RAIZ, "backup_sqlite", "manual")
BACKUP_DIR_EXCEL = os.path.join(BACKUP_DIR_RAIZ, "backup_excel")

def backup_database():
    print("Iniciando proceso de respaldo doble (SQLite y Excel)...")

    # -- VERIFICAR QUE LA BASE DE DATOS ORIGINAL EXISTA --
    if not os.path.exists(DB_PATH):
        print(f"Error: No se encontro la base de datos en: {DB_PATH}")
        return

    # -- CREAR CARPETAS DE RESPALDOS SI NO EXISTEN --
    # Crea la carpeta raíz y las subcarpetas de forma segura
    try:
        os.makedirs(BACKUP_DIR_SQLITE, exist_ok=True)
        os.makedirs(BACKUP_DIR_EXCEL, exist_ok=True)
        print("Carpetas de respaldo verificadas/creadas con éxito.")
    except OSError as e:
        print(f"Error al crear las carpetas de respaldo: {e}")
        return

    # -- GENERAR MARCA DE TIEMPO PARA LOS NOMBRES DE ARCHIVO --
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Nombres de archivo apuntando a las nuevas subcarpetas
    backup_db_filename = f"libreria_respaldo_manual_{timestamp}.db"
    backup_db_path = os.path.join(BACKUP_DIR_SQLITE, backup_db_filename)
    
    backup_excel_filename = f"libreria_respaldo_manual_{timestamp}.xlsx"
    backup_excel_path = os.path.join(BACKUP_DIR_EXCEL, backup_excel_filename)

    origen = None
    destino_db = None

    try:
        # Conectar a la base de datos de origen
        origen = sqlite3.connect(DB_PATH)

        # ==========================================
        # 1. RESPALDO NATIVO SQLITE (.db)
        # ==========================================
        print(f"Creando respaldo SQLite en: {BACKUP_DIR_SQLITE}")
        destino_db = sqlite3.connect(backup_db_path)
        origen.backup(destino_db)
        print(f"  -> Respaldo SQLite creado: {backup_db_filename}")

        # ==========================================
        # 2. RESPALDO EN EXCEL (.xlsx)
        # ==========================================
        print(f"Creando respaldo Excel en: {BACKUP_DIR_EXCEL}")
        
        # -- OBTENER LA LISTA DE TODAS LAS TABLAS EN LA BASE DE DATOS --
        cursor = origen.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tablas = [fila[0] for fila in cursor.fetchall()]

        # -- ESCRIBIR CADA TABLA EN UNA PESTAÑA DEL EXCEL --
        with pd.ExcelWriter(backup_excel_path, engine='openpyxl') as writer:
            for tabla in tablas:
                # Extraer la tabla completa usando Pandas
                df = pd.read_sql_query(f"SELECT * FROM {tabla}", origen)
                # Guardarla en el Excel sin la columna numérica de índice
                df.to_excel(writer, sheet_name=tabla, index=False)
        
        print(f"  -> Respaldo Excel creado: {backup_excel_filename}")

    except sqlite3.Error as e:
        print(f"Error de SQLite durante el respaldo: {e}")
    except Exception as e:
        print(f"Error inesperado al crear los respaldos: {e}")
    finally:
        # -- CERRAR CONEXIONES --
        if destino_db:
            destino_db.close()
        if origen:
            origen.close()
        print("\nProceso de respaldo finalizado.")

if __name__ == "__main__":
    # -- EJECUTAR FUNCION --
    backup_database()