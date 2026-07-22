import sqlite3
import pandas as pd
import os
import json
from datetime import datetime

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FILE_PATH = os.path.join(BASE_DIR, "1_input_data", "stock_precios.csv")
DB_PATH = os.path.join(BASE_DIR, "2_database", "libreria.db")
DIR_REPORTES = os.path.join(BASE_DIR, "4_output_reports")
os.makedirs(DIR_REPORTES, exist_ok=True) 
TXT_NO_ENCONTRADOS = os.path.join(DIR_REPORTES, "libros_no_encontrados_stock.txt")


def run_stock_update():
    reporte = {
        "libros_procesados": 0,
        "libros_actualizados": 0,
        "nuevos_libros": 0, # Usado para libros omitidos/no encontrados
        "error": None
    }

    try:
        try:
            df = pd.read_csv(CSV_FILE_PATH, sep=',')
            if len(df.columns) < 2: raise ValueError
        except:
            df = pd.read_csv(CSV_FILE_PATH, sep=';')
            
    except FileNotFoundError:
        reporte["error"] = f"No se encontró el archivo 'stock_precios.csv'."
        print(json.dumps(reporte))
        return
    except Exception as e:
        reporte["error"] = f"Error al leer el CSV: {e}"
        print(json.dumps(reporte))
        return

    libros_faltantes = []
    
    # Detectar qué columnas opcionales vienen en el CSV (en minúsculas para evitar errores)
    cols = [c.lower() for c in df.columns]
    has_autor = 'autor' in cols
    has_editorial = 'editorial' in cols

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for index, row in df.iterrows():
            # Convertimos las llaves a minúsculas para encontrar las columnas fácilmente
            row_dict = {str(k).lower(): v for k, v in row.items()}
            
            titulo = str(row_dict.get('titulo', '')).strip().upper()
            stock = row_dict.get('stock')
            precio = row_dict.get('precio')

            if not titulo or titulo == 'NAN':
                continue
                
            reporte["libros_procesados"] += 1

            try:
                stock_val = int(float(stock)) if pd.notna(stock) else 0
                precio_val = float(str(precio).replace(',', '.')) if pd.notna(precio) else 0.0
            except (ValueError, TypeError):
                continue

            cursor.execute("SELECT libro_id FROM libros WHERE UPPER(titulo) = ?", (titulo,))
            libro_existente = cursor.fetchone()

            if libro_existente:
                libro_id = libro_existente[0]
                
                # Campos base obligatorios a actualizar
                update_fields = ["stock = ?", "precio = ?", "precio_original = ?"]
                params = [stock_val, precio_val, precio_val]
                
                # --- ACTUALIZACIÓN DINÁMICA DE AUTOR ---
                if has_autor and pd.notna(row_dict.get('autor')):
                    autor_val = str(row_dict.get('autor')).strip().upper()
                    if autor_val and autor_val != 'NAN':
                        update_fields.append("autor = ?")
                        params.append(autor_val)
                        
                # --- ACTUALIZACIÓN DINÁMICA DE EDITORIAL ---
                if has_editorial and pd.notna(row_dict.get('editorial')):
                    editorial_val = str(row_dict.get('editorial')).strip().upper()
                    if editorial_val and editorial_val != 'NAN':
                        update_fields.append("editorial = ?")
                        params.append(editorial_val)
                        
                # Construimos la consulta final y la ejecutamos
                params.append(libro_id)
                query = f"UPDATE libros SET {', '.join(update_fields)} WHERE libro_id = ?"
                
                cursor.execute(query, tuple(params))
                reporte["libros_actualizados"] += 1
            else:
                reporte["nuevos_libros"] += 1
                libros_faltantes.append(titulo)

        conn.commit()

        if libros_faltantes:
            with open(TXT_NO_ENCONTRADOS, 'w', encoding='utf-8') as f:
                f.write(f"--- REPORTE DE STOCK: LIBROS NO ENCONTRADOS ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ---\n")
                f.write("Los siguientes títulos están en tu Excel, pero NO en tu Base de Datos.\n")
                f.write("Revisa si hay errores de tipeo o si son libros nuevos que debes crear primero:\n\n")
                for t in libros_faltantes:
                    f.write(f"- {t}\n")

    except sqlite3.Error as e:
        reporte["error"] = f"Error de base de datos: {e}"
        conn.rollback()
    except Exception as e:
        reporte["error"] = f"Error inesperado: {e}"
    finally:
        if conn:
            conn.close()
    
    print(json.dumps(reporte))

if __name__ == "__main__":
    run_stock_update()