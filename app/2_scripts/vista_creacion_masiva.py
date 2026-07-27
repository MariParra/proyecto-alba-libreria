import streamlit as st
import pandas as pd
import io
import json
import unicodedata
from utilidades import get_db_connection

def normalizar_texto(texto):
    """Normaliza el texto eliminando acentos y mayúsculas para búsquedas exactas."""
    if pd.isna(texto): return ""
    s = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
    return ' '.join(s.strip().upper().split())

# ==========================================
# --- LÓGICA 1: CREACIÓN DE LIBROS NUEVOS ---
# ==========================================
def generar_plantilla_libros():
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
    exitos, duplicados, errores = 0, 0, []
    
    res_libros = conn.table("libros").select("titulo, autor").execute()
    catalogo_actual = [(str(l['titulo']).strip().lower(), str(l.get('autor', '')).strip().lower()) for l in res_libros.data] if res_libros.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de catálogo...")
    total_filas = len(df)
    
    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        titulo_excel = str(fila.get('titulo', '')).strip()
        autor_excel = str(fila.get('autor', '')).strip()
        
        if not titulo_excel or titulo_excel.lower() == 'nan':
            errores.append(f"Fila {indice + 2}: Falta el 'titulo'. Es obligatorio.")
            continue
            
        if (titulo_excel.lower(), autor_excel.lower()) in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El libro '{titulo_excel}' ya existe.")
            continue
            
        try:
            nuevo_libro = {col: (None if pd.isna(fila[col]) else fila[col]) for col in df.columns}
            conn.table("libros").insert(nuevo_libro).execute()
            exitos += 1
            catalogo_actual.append((titulo_excel.lower(), autor_excel.lower()))
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{titulo_excel}'): Error -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ==========================================
# --- LÓGICA 2: IMPORTACIÓN DE VENTAS ---
# ==========================================
def generar_plantilla_ventas():
    columnas = ['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente', 'Titulo_Libro', 'Cantidad', 'Precio_Unitario', 'Valor_Envio', 'Metodo_Envio', 'Comentario']
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Ventas Pasadas')
        worksheet = writer.sheets['Ventas Pasadas']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 20)
    return output.getvalue()

def procesar_nuevos_libros(df):
    conn = get_db_connection()
    exitos, duplicados, errores = 0, 0, []
    
    res_libros = conn.table("libros").select("titulo, autor").execute()
    catalogo_actual = [(str(l['titulo']).strip().lower(), str(l.get('autor', '')).strip().lower()) for l in res_libros.data] if res_libros.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de catálogo...")
    total_filas = len(df)
    
    # Definimos cuáles son las columnas de texto que deben limpiarse
    columnas_texto = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion']
    
    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        
        # Validamos usando la función que quita tildes y pone en mayúsculas
        titulo_limpio = normalizar_texto(fila.get('titulo', ''))
        autor_limpio = normalizar_texto(fila.get('autor', ''))
        
        if not titulo_limpio:
            errores.append(f"Fila {indice + 2}: Falta el 'titulo'. Es obligatorio.")
            continue
            
        if (titulo_limpio.lower(), autor_limpio.lower()) in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El libro '{titulo_limpio}' ya existe.")
            continue
            
        try:
            nuevo_libro = {}
            for col in df.columns:
                if pd.isna(fila[col]):
                    nuevo_libro[col] = None
                elif col in columnas_texto:
                    # --- 🛠️ LA MAGIA OCURRE AQUÍ ---
                    # Aplicamos la normalización (UPPER y sin tildes) a todos los textos
                    nuevo_libro[col] = normalizar_texto(fila[col])
                else:
                    # Para columnas numéricas como stock o precio, guardamos el valor tal cual
                    nuevo_libro[col] = fila[col]
                    
            conn.table("libros").insert(nuevo_libro).execute()
            exitos += 1
            catalogo_actual.append((titulo_limpio.lower(), autor_limpio.lower()))
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{titulo_limpio}'): Error -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ==========================================
# --- VISTA PRINCIPAL ---
# ==========================================
def mostrar_creacion_masiva_libros():
    st.title("✨ Importación Masiva (Libros y Ventas)")
    st.markdown("Añade decenas de registros a la vez usando nuestras plantillas de Excel.")
    
    # Creamos las dos pestañas para separar la lógica de negocio
    tab_libros, tab_ventas = st.tabs(["📚 Nuevos Libros", "🛒 Ventas Pasadas"])
    
    with tab_libros:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Libros")
            st.download_button(
                label="📥 Descargar Plantilla Libros (.xlsx)",
                data=generar_plantilla_libros(),
                file_name="plantilla_nuevos_libros.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with st.container(border=True):
            st.markdown("### Paso 2: Sube tu Excel Lleno")
            archivo_libros = st.file_uploader("Sube el archivo de libros", type=["xlsx"], key="up_libros")
            if archivo_libros:
                df = pd.read_excel(archivo_libros, engine='openpyxl')
                if 'titulo' not in df.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de libros.")
                else:
                    if st.button("🚀 Ingresar Libros", type="primary", use_container_width=True):
                        with st.spinner("Creando libros..."):
                            exitos, duplicados, errores = procesar_nuevos_libros(df)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("✅ Ingresados", exitos)
                            c2.metric("⚠️ Duplicados", duplicados)
                            c3.metric("❌ Errores", len(errores) - duplicados)
                            if exitos > 0: st.success(f"¡{exitos} libros añadidos!")
                            if errores:
                                with st.expander("Ver lista de conflictos"):
                                    for err in errores: st.write(err)

    with tab_ventas:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Ventas")
            st.info("💡 **Tip UX:** Si una clienta compró 3 libros en el mismo día, usa 3 filas en el Excel con la misma fecha y el mismo nombre. El sistema las agrupará en una sola Venta/Boleta automáticamente calculando los subtotales.")
            st.download_button(
                label="📥 Descargar Plantilla Ventas (.xlsx)",
                data=generar_plantilla_ventas(),
                file_name="plantilla_ventas_pasadas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el Archivo de Ventas")
            archivo_ventas = st.file_uploader("Sube el archivo de ventas", type=["xlsx"], key="up_ventas")
            if archivo_ventas:
                df_v = pd.read_excel(archivo_ventas, engine='openpyxl')
                if 'Nombre_Cliente' not in df_v.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de ventas.")
                else:
                    if st.button("🚀 Registrar Ventas Masivamente", type="primary", use_container_width=True):
                        with st.spinner("Procesando y agrupando ventas..."):
                            exitos_v, errores_v = procesar_ventas_masivas(df_v)
                            c1, c2 = st.columns(2)
                            c1.metric("✅ Boletas Exitosas", exitos_v)
                            c2.metric("❌ Errores", len(errores_v))
                            if exitos_v > 0: 
                                st.balloons()
                                st.success("¡Ventas registradas correctamente en el historial!")
                            if errores_v:
                                with st.expander("Ver lista de conflictos (Clientes no encontrados)"):
                                    for err in errores_v: st.write(err)