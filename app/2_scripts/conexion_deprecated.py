import sqlite3
import os
import shutil
import datetime
import subprocess
from config import DB_NAME

def conectar_db():
    # -- ESTABLECER CONEXION CON LA BASE DE DATOS --
    return sqlite3.connect(DB_NAME)

def realizar_respaldo_automatico(etiqueta="OPEN"):
    """
    Crea un respaldo de la base de datos en la subcarpeta 'backup_sqlite',
    usando la etiqueta proporcionada (ej: OPEN, CLOSE).
    """
    print(f"Iniciando respaldo automático con etiqueta: {etiqueta}...")
    
    # -- VERIFICAR EXISTENCIA DE LA BASE DE DATOS --
    if not os.path.exists(DB_NAME):
        print(f"Advertencia: No se encontro la base de datos para respaldar: {DB_NAME}")
        return

    # -- CONSTRUIR RUTA DINÁMICA HACIA LA SUBCARPETA DE RESPALDOS SQLITE --
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # La ruta ahora apunta a la subcarpeta específica para respaldos .db
        carpeta_respaldos_sqlite = os.path.join(base_dir, "4_backups", "backup_sqlite", "self-acting")
        
        # -- CREAR CARPETA DE RESPALDOS SI NO EXISTE --
        os.makedirs(carpeta_respaldos_sqlite, exist_ok=True)

    except Exception as e:
        print(f"Error al crear o encontrar la carpeta de respaldos: {e}")
        return

    # -- GENERAR NOMBRE DE RESPALDO CON FECHA, HORA Y ETIQUETA --
    ahora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_respaldo = os.path.join(carpeta_respaldos_sqlite, f"respaldo_evento_{ahora}_{etiqueta}.db")

    # -- COPIAR ARCHIVO DE BASE DE DATOS AL RESPALDO --
    try:
        shutil.copy2(DB_NAME, nombre_respaldo)
        print(f"  -> Respaldo '{etiqueta}' creado con éxito en: {nombre_respaldo}")
    except Exception as e:
        print(f"Error al realizar la copia de respaldo: {e}")

def ejecutar_script_externo(nombre_script):
    # -- VERIFICAR EXISTENCIA DEL SCRIPT EXTERNO --
    if not os.path.exists(nombre_script):
        raise FileNotFoundError(f"No se encontró el archivo '{nombre_script}'")
        
    # -- EJECUTAR SCRIPT COMO SUBPROCESO --
    # Se usa subprocess.run para mayor control
    return subprocess.run(["python", nombre_script], capture_output=True, text=True, check=True, encoding='utf-8')