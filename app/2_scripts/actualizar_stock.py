import psycopg2
import os
import json
import csv
from dotenv import load_dotenv

# --- CONFIGURACIÓN DE RUTAS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
# AHORA BUSCA EL ARCHIVO CSV
CSV_FILE_PATH = os.path.join(BASE_DIR, "1_input_data", "stock_precios.csv")

# --- CONEXIÓN A LA NUBE ---
dotenv_path = os.path.join(os.path.dirname(BASE_DIR), '.env')
load_dotenv(dotenv_path)
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_update():
    reporte = {"libros_procesados": 0, "libros_actualizados": 0, "error": None, "detalles": []}
    datos_actualizacion = []
    
    # 1. LEER EL ARCHIVO CSV
    try:
        with open(CSV_FILE_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convertimos las cabeceras a minúsculas para evitar errores de tipeo en el Excel
                row_limpia = {k.strip().lower(): v for k, v in row.items() if k}
                
                titulo = row_limpia.get("titulo") or row_limpia.get("título")
                nuevo_stock = row_limpia.get("stock")
                nuevo_precio = row_limpia.get("precio")
                
                if titulo and nuevo_stock is not None and nuevo_precio is not None:
                    datos_actualizacion.append({
                        "titulo": titulo.strip().upper(),
                        "stock": nuevo_stock,
                        "precio": nuevo_precio
                    })
    except FileNotFoundError:
        reporte["error"] = f"No se encontró el archivo {CSV_FILE_PATH}."
        print(json.dumps(reporte))
        return
    except Exception as e:
        reporte["error"] = f"Error al leer el CSV: {str(e)}"
        print(json.dumps(reporte))
        return

    # 2. ACTUALIZAR EN LA BASE DE DATOS
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        for item in datos_actualizacion:
            titulo = item["titulo"]
            nuevo_stock = item["stock"]
            nuevo_precio = item["precio"]
                
            reporte["libros_procesados"] += 1
            
            # Buscar el libro en la base de datos de PostgreSQL
            cursor.execute("SELECT libro_id, precio, precio_original FROM libros WHERE titulo = %s", (titulo,))
            libro_db = cursor.fetchone()
            
            if libro_db:
                libro_id, precio_actual, precio_orig_actual = libro_db
                
                try:
                    nuevo_precio_float = float(nuevo_precio)
                    nuevo_stock_int = int(nuevo_stock)
                except ValueError:
                    reporte["detalles"].append(f"Error de formato (números) en: {titulo}")
                    continue
                
                # Actualizar stock, el nuevo precio como precio base y el precio anterior pasa a original
                cursor.execute("""
                    UPDATE libros 
                    SET stock = %s, precio = %s, precio_original = %s 
                    WHERE libro_id = %s
                """, (nuevo_stock_int, nuevo_precio_float, precio_actual, libro_id))
                
                reporte["libros_actualizados"] += 1
                reporte["detalles"].append(f"Actualizado: {titulo} (Stock: {nuevo_stock_int}, Precio: ${nuevo_precio_float})")
            else:
                reporte["detalles"].append(f"No encontrado en BD: {titulo}")
                
        conn.commit()
        
    except psycopg2.Error as e:
        reporte["error"] = f"Error de base de datos: {e}"
        if conn: conn.rollback()
    except Exception as e:
        reporte["error"] = str(e)
    finally:
        if conn: conn.close()
        
    # Imprimir el reporte final en formato JSON para que la interfaz lo pueda leer y mostrar en la ventanita
    print(json.dumps(reporte, indent=2))

if __name__ == "__main__":
    run_update()