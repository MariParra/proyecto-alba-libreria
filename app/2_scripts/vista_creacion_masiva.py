import streamlit as st
import pandas as pd
import io
from utilidades import get_db_connection

def generar_plantilla_libros():
    """Genera un archivo Excel vacío solo con los encabezados necesarios."""
    # Omitimos libro_id porque la base de datos lo genera automáticamente
    columnas = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion', 'stock', 'precio', 'precio_original']
    df_vacio = pd.DataFrame(columns=columnas)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Nuevos Libros')
        # Ajustar ancho de columnas para que sea amigable
        worksheet = writer.sheets['Nuevos Libros']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 15)
            
    return output.getvalue()

def procesar_nuevos_libros(df):
    conn = get_db_connection()
    exitos = 0
    errores = []
    duplicados = 0
    
    # 1. Reemplazar valores NaN de pandas por None de Python nativo
    df_clean = df.where(pd.notnull(df), None)
    
    # 2. Traer catálogo actual para validar duplicados
    res_libros = conn.table("libros").select("titulo, autor").execute()
    catalogo_actual = [(str(l['titulo']).strip().lower(), str(l.get('autor', '') or '').strip().lower()) for l in res_libros.data] if res_libros.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de catálogo...")
    total_filas = len(df_clean)
    
    for indice, fila in df_clean.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        
        titulo_excel = str(fila.get('titulo', '') or '').strip()
        autor_excel = str(fila.get('autor', '') or '').strip()
        
        # Validación UX: Título es obligatorio
        if not titulo_excel or titulo_excel.lower() == 'none' or titulo_excel.lower() == 'nan':
            errores.append(f"Fila {indice + 2}: Falta el 'titulo'. Es obligatorio.")
            continue
            
        # Validación UX: Evitar duplicados
        if (titulo_excel.lower(), autor_excel.lower()) in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El libro '{titulo_excel}' de '{autor_excel}' ya existe en la base de datos.")
            continue
            
        try:
            nuevo_libro = {}
            for col in df_clean.columns:
                val = fila[col]
                if val is None:
                    nuevo_libro[col] = None
                elif hasattr(val, 'item'):
                    nuevo_libro[col] = val.item()
                elif isinstance(val, str):
                    nuevo_libro[col] = val.strip()
                else:
                    nuevo_libro[col] = val

            nuevo_libro['titulo'] = titulo_excel
            nuevo_libro['autor'] = autor_excel if autor_excel else None

            # --- INSERTAR Y MOSTRAR RESPUESTA REAL ---
            res = conn.table("libros").insert(nuevo_libro).execute()
            
            # Esto te mostrará en la app qué devolvió exactamente la BD
            st.write("🔍 **Respuesta de la BD para fila:**", res.data)

            if res.data and len(res.data) > 0:
                exitos += 1
                catalogo_actual.append((titulo_excel.lower(), autor_excel.lower()))
            else:
                errores.append(f"Fila {indice + 2} ('{titulo_excel}'): La BD aceptó la solicitud pero no guardó la fila (Posible problema de RLS).")
            
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{titulo_excel}'): Error -> {str(e)}")
            
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores
    
if __name__ == '__main__':
    mostrar_creacion_masiva_libros()
