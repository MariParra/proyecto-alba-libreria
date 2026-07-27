8import streamlit as st
import pandas as pd
import io
from utilidades import get_db_connection

def generar_plantilla_libros():
    """Genera un archivo Excel vacío solo con los encabezados necesarios."""
    columnas = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion', 'stock', 'precio', 'precio_original']
    df_vacio = pd.DataFrame(columns=columnas)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Nuevos Libros')
        worksheet = writer.sheets['Nuevos Libros']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 15)
            
    return output.getvalue()

def procesar_nuevos_libros(df):
    conn = get_db_connection()
    exitos = 0
    errores = []
    duplicados = 0
    
    # 1. Reemplazar valores NaN de pandas por None nativo de Python
    df_clean = df.where(pd.notnull(df), None)
    
    # 2. Traer catálogo actual para validar duplicados (en mayúsculas para comparar homogéneamente)
    res_libros = conn.table("libros").select("titulo, autor").execute()
    catalogo_actual = set()
    if res_libros.data:
        for l in res_libros.data:
            t = str(l.get('titulo') or '').strip().upper()
            a = str(l.get('autor') or '').strip().upper()
            if t:
                catalogo_actual.add((t, a))
    
    barra_progreso = st.progress(0, text="Iniciando carga de catálogo...")
    total_filas = len(df_clean)
    
    for indice, fila in df_clean.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        
        # Convertir título y autor a MAYÚSCULAS
        titulo_excel = str(fila.get('titulo', '') or '').strip().upper()
        autor_excel = str(fila.get('autor', '') or '').strip().upper()
        
        # Validación UX: Título es obligatorio
        if not titulo_excel or titulo_excel in ['NONE', 'NAN', '']:
            errores.append(f"Fila {indice + 2}: Falta el 'titulo'. Es obligatorio.")
            continue
            
        # Validación UX: Evitar duplicados
        if (titulo_excel, autor_excel) in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El libro '{titulo_excel}' de '{autor_excel}' ya existe en la base de datos.")
            continue
            
        try:
            nuevo_libro = {}
            for col in df_clean.columns:
                val = fila[col]
                if val is None:
                    nuevo_libro[col] = None
                elif hasattr(val, 'item'):  # Convierte int64, float64 de numpy a int/float
                    nuevo_libro[col] = val.item()
                elif isinstance(val, str):
                    # --- CONVERSIÓN A MAYÚSCULAS ---
                    val_str = val.strip().upper()
                    nuevo_libro[col] = val_str if val_str not in ['NONE', 'NAN', ''] else None
                else:
                    nuevo_libro[col] = val

            # Asegurar que título y autor estén limpios y en MAYÚSCULAS
            nuevo_libro['titulo'] = titulo_excel
            nuevo_libro['autor'] = autor_excel if autor_excel else None

            # Insertar en Supabase
            res = conn.table("libros").insert(nuevo_libro).execute()
            
            if res.data and len(res.data) > 0:
                exitos += 1
                catalogo_actual.add((titulo_excel, autor_excel))
            else:
                errores.append(
                    f"Fila {indice + 2} ('{titulo_excel}'): La BD no devolvió los datos insertados. "
                    f"Verifica las políticas RLS en la tabla 'libros' de Supabase."
                )
            
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{titulo_excel}'): Error en BD -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

def mostrar_creacion_masiva_libros():
    st.title("✨ Agregar Nuevos Libros al Catálogo")
    st.markdown("Añade decenas o cientos de libros nuevos rápidamente usando nuestra plantilla de Excel.")
    
    with st.container(border=True):
        st.markdown("### Paso 1: Descarga la Plantilla")
        st.write("Descarga este archivo, llénalo con los datos de tus libros nuevos y guárdalo. **Nota:** No cambies el nombre de las columnas en la fila 1.")
        
        plantilla_excel = generar_plantilla_libros()
        st.download_button(
            label="📥 Descargar Plantilla en Blanco (.xlsx)",
            data=plantilla_excel,
            file_name="plantilla_nuevos_libros.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    with st.container(border=True):
        st.markdown("### Paso 2: Sube tu Excel Lleno")
        archivo_subido = st.file_uploader("Sube el archivo aquí", type=["xlsx"])
        
        if archivo_subido:
            df = pd.read_excel(archivo_subido, engine='openpyxl')
            
            if 'titulo' not in df.columns:
                st.error("🛑 El archivo no es válido. Por favor, usa la plantilla descargada en el Paso 1 (debe contener la columna 'titulo').")
                st.stop()
                
            st.info(f"📊 Se detectaron **{len(df)} filas** para procesar.")
            
            if st.button("🚀 Ingresar Libros a la Base de Datos", type="primary", use_container_width=True):
                with st.spinner("Creando registros..."):
                    exitos, duplicados, errores = procesar_nuevos_libros(df)
                    
                    st.markdown("### 📋 Resumen de la Carga")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ Nuevos Ingresados", exitos)
                    c2.metric("⚠️ Duplicados Omitidos", duplicados)
                    c3.metric("❌ Errores", len(errores) - duplicados)
                    
                    if exitos > 0:
                        st.balloons()
                        st.success(f"¡{exitos} libros se añadieron exitosamente a tu catálogo!")
                        
                    if errores:
                        st.warning("Detalle de las filas no procesadas:")
                        with st.expander("Ver lista de conflictos y errores"):
                            for err in errores:
                                st.write(err)

if __name__ == '__main__':
    mostrar_creacion_masiva_libros()


