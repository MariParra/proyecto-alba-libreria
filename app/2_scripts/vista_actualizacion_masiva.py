import streamlit as st
import pandas as pd
import io
from utilidades import get_db_connection

# ==========================================================
# --- LÓGICA 1: ACTUALIZACIÓN DE LIBROS ---
# ==========================================================
def generar_plantilla_actualizacion_libros():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, editorial, genero, encuadernacion, stock, precio, costo").execute()
        df = pd.DataFrame(res.data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Libros')
            worksheet = writer.sheets['Actualizar Libros']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        st.error(f"Error generando plantilla: {e}")
        return None

def procesar_actualizacion_libros(df):
    conn = get_db_connection()
    updates, errores = 0, []
    
    columnas_actualizables = ['titulo', 'autor', 'editorial', 'genero', 'encuadernacion', 'stock', 'precio', 'costo']

    for i, fila in df.iterrows():
        try:
            libro_id = int(fila['libro_id'])
            datos_update = {}
            for col in columnas_actualizables:
                if col in fila and pd.notna(fila[col]):
                    datos_update[col] = fila[col]
            
            if datos_update:
                conn.table("libros").update(datos_update).eq("libro_id", libro_id).execute()
                updates += 1
        except Exception as e:
            errores.append(f"Fila {i+2} (ID: {fila.get('libro_id', 'N/A')}): {str(e)}")
            
    return updates, errores

# ==========================================================
# --- LÓGICA 2: ACTUALIZACIÓN DE VENTAS ---
# ==========================================================
def generar_plantilla_actualizacion_ventas():
    conn = get_db_connection()
    try:
        res = conn.table("registro_ventas").select("venta_id, fecha_venta, cliente_id, monto_final, estado, abono, costo_venta, metodo_envio, comentario").execute()
        df = pd.DataFrame(res.data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Ventas')
            worksheet = writer.sheets['Actualizar Ventas']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except:
        return None

def procesar_actualizacion_ventas(df):
    conn = get_db_connection()
    updates, errores = 0, []
    
    columnas_actualizables = ['estado', 'abono', 'costo_venta', 'metodo_envio', 'comentario']

    for i, fila in df.iterrows():
        try:
            venta_id = int(fila['venta_id'])
            datos_update = {}
            for col in columnas_actualizables:
                if col in fila and pd.notna(fila[col]):
                    if col in ['abono', 'costo_venta']:
                        datos_update[col] = float(fila[col])
                    else:
                        datos_update[col] = str(fila[col])

            if datos_update:
                conn.table("registro_ventas").update(datos_update).eq("venta_id", venta_id).execute()
                updates += 1
        except Exception as e:
            errores.append(f"Fila {i+2} (ID: {fila.get('venta_id', 'N/A')}): {str(e)}")

    return updates, errores

# ==========================================
# --- VISTA PRINCIPAL ---
# ==========================================
def mostrar_actualizacion_masiva():
    st.title("⚡ Actualización Masiva")
    st.markdown("Modifica cientos de registros a la vez descargando, editando y volviendo a subir el catálogo.")

    tab_libros, tab_ventas = st.tabs(["📚 Libros", "🛒 Ventas"])

    with tab_libros:
        st.markdown("### 1. Descarga el Catálogo de Libros Actual")
        st.download_button(
            label="📥 Descargar Libros (.xlsx)",
            data=generar_plantilla_actualizacion_libros(),
            file_name="catalogo_libros_actual.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("### 2. Sube el archivo con tus modificaciones")
        st.warning("El sistema usará la columna `libro_id` para encontrar y actualizar los registros. No modifiques esa columna.")
        archivo_libros = st.file_uploader("Sube el archivo de libros modificados", type=["xlsx"], key="upd_libros")

        if archivo_libros:
            if st.button("🚀 Aplicar Cambios en Libros", type="primary"):
                df_l = pd.read_excel(archivo_libros)
                with st.spinner("Actualizando libros..."):
                    updates, errores = procesar_actualizacion_libros(df_l)
                    st.success(f"¡Se procesaron {updates} actualizaciones de libros!")
                    if errores:
                        with st.expander("Ver errores"):
                            for err in errores: st.write(err)

    with tab_ventas:
        st.markdown("### 1. Descarga el Historial de Ventas Actual")
        st.download_button(
            label="📥 Descargar Ventas (.xlsx)",
            data=generar_plantilla_actualizacion_ventas(),
            file_name="historial_ventas_actual.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("### 2. Sube el archivo con tus modificaciones")
        st.warning("El sistema usará la columna `venta_id` para encontrar y actualizar los registros. No modifiques esa columna.")
        archivo_ventas = st.file_uploader("Sube el archivo de ventas modificado", type=["xlsx"], key="upd_ventas")

        if archivo_ventas:
            if st.button("🚀 Aplicar Cambios en Ventas", type="primary"):
                df_v = pd.read_excel(archivo_ventas)
                with st.spinner("Actualizando ventas..."):
                    updates, errores = procesar_actualizacion_ventas(df_v)
                    st.success(f"¡Se procesaron {updates} actualizaciones de ventas!")
                    if errores:
                        with st.expander("Ver errores"):
                            for err in errores: st.write(err)