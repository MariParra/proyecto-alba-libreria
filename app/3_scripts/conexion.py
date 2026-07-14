# aplicativo/conexion.py

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
    # -- VERIFICAR EXISTENCIA DE LA BASE DE DATOS --
    if not os.path.exists(DB_NAME):
        print(f"Advertencia: No se encontro la base de datos para respaldar: {DB_NAME}")
        return

    # -- CONSTRUIR RUTA DINAMICA HACIA 5_backups --
    # Sube un nivel desde 'aplicativo' hasta 'app', y luego entra a '5_backups'
    archivo_actual = str(__file__)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(archivo_actual)))
    carpeta_respaldos = os.path.join(BASE_DIR, "5_backups")
    
    # -- CREAR CARPETA DE RESPALDOS SI NO EXISTE --
    if not os.path.exists(carpeta_respaldos):
        try:
            os.makedirs(carpeta_respaldos)
        except Exception as e:
            print(f"Error al crear carpeta de respaldos en {carpeta_respaldos}: {e}")
            return

    # -- GENERAR NOMBRE DE RESPALDO CON FECHA, HORA Y ETIQUETA DE EVENTO --
    ahora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_respaldo = os.path.join(carpeta_respaldos, f"respaldo_club_{ahora}_{etiqueta}.db")

    # -- COPIAR ARCHIVO DE BASE DE DATOS AL RESPALDO --
    try:
        shutil.copy2(DB_NAME, nombre_respaldo)
        print(f"Respaldo creado ({etiqueta}): {nombre_respaldo}")
    except Exception as e:
        print(f"Error en respaldo: {e}")

def ejecutar_script_externo(nombre_script):
    # -- VERIFICAR EXISTENCIA DEL SCRIPT EXTERNO --
    if not os.path.exists(nombre_script):
        raise FileNotFoundError(f"No se encontró el archivo '{nombre_script}'")
        
    # -- EJECUTAR SCRIPT COMO SUBPROCESO --
    subprocess.run(["python", nombre_script], capture_output=True, text=True, check=True)