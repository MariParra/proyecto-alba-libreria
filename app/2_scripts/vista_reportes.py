import streamlit as st
import pandas as pd
import io
from utilidades import get_db_connection

# --- FUNCIÓN DE UTILIDAD PARA GENERAR EXCEL ---
def convertir_df_a_excel(df):
    """
    Convierte un DataFrame de pandas a un archivo Excel en memoria.
    Esta versión es más robusta y maneja correctamente los valores nulos.
    """
    output = io.BytesIO()
    # Usamos xlsxwriter como motor para generar el archivo
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
        
        # UX: Auto-ajustar el ancho de las columnas para que se lea bien
        worksheet = writer.sheets['Datos']
        
        for i, col in enumerate(df.columns):
            # Lógica mejorada para calcular el ancho de la columna
            # 1. Rellenamos los valores nulos con una cadena vacía para evitar errores
            # 2. Convertimos todo a string para poder medir la longitud
            # 3. Obtenemos el largo máximo entre los datos y el título de la columna
            try:
                max_len = max(
                    df[col].fillna('').astype(str).map(len).max(), # Largo máximo del contenido
                    len(str(col)) # Largo del título de la columna
                ) + 2 # Añadimos un pequeño margen
                worksheet.set_column(i, i, max_len)
            except (ValueError, TypeError):
                # Si la columna está completamente vacía o tiene un error, usamos un ancho por defecto
                worksheet.set_column(i, i, 15)
            
    return output.getvalue()

# --- FUNCIONES DE EXTRACCIÓN DE DATOS ---
def obtener_tabla(nombre_tabla):
    conn = get_db_connection()
    res = conn.table(nombre_tabla).select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def obtener_reporte_bajo_stock(limite=5):
    conn = get_db_connection()
    res = conn.table("libros").select("titulo, autor, editorial, stock, precio").lte("stock", limite).order("stock").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def obtener_reporte_logistica_envios():
    conn = get_db_connection()
    # Clientes activos con su información de contacto
    res = conn.table("clientes").select("nombre, email, telefono, direccion, rut").eq("status", "ACTIVA").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

# --- VISTA PRINCIPAL ---
def mostrar_reportes():
    st.title("📥 Reportes y Descargas")
    st.markdown("Genera reportes estratégicos o descarga la información bruta de tu base de datos para análisis en Excel.")
    
    # UI: Pestañas para separar la intención del usuario
    tab1, tab2 = st.tabs(["📊 Reportes Inteligentes", "💾 Exportar Tablas Base"])
    
    with tab1:
        st.markdown("### Reportes listos para usar")
        st.info("💡 Estos reportes están diseñados para ayudarte en la toma de decisiones y la logística diaria.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.markdown("#### ⚠️ Alerta de Stock")
                st.write("Libros que tienen 5 o menos unidades en inventario. Ideal para planificar tus próximas compras.")
                df_stock = obtener_reporte_bajo_stock()
                
                if not df_stock.empty:
                    excel_stock = convertir_df_a_excel(df_stock)
                    st.download_button(
                        label="Descargar Reporte de Stock (.xlsx)",
                        data=excel_stock,
                        file_name="reporte_bajo_stock.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    st.success("¡Excelente! No tienes libros con bajo stock.")

        with col2:
            with st.container(border=True):
                st.markdown("#### 🚚 Logística de Envíos")
                st.write("Listado de clientes con estado 'ACTIVA' y sus direcciones para preparar los despachos del mes.")
                df_envios = obtener_reporte_logistica_envios()
                
                if not df_envios.empty:
                    excel_envios = convertir_df_a_excel(df_envios)
                    st.download_button(
                        label="Descargar Lista de Envíos (.xlsx)",
                        data=excel_envios,
                        file_name="clientes_para_despacho.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    st.warning("No hay clientes activos en este momento.")

    with tab2:
        st.markdown("### Descarga de Datos Brutos")
        st.write("Selecciona la tabla exacta que deseas descargar. Útil para auditorías o cruces de datos personalizados.")
        
        # Diccionario amigable para el usuario vs nombre real de la tabla
        tablas_disponibles = {
            "Catálogo de Libros": "libros",
            "Directorio de Clientes": "clientes",
            "Registro de Ventas Directas": "registro_ventas",
            "Asignaciones de Suscripción": "asignaciones",
            "Historial de Lectura": "librero_historico"
        }
        
        tabla_seleccionada = st.selectbox("Selecciona la información a exportar:", list(tablas_disponibles.keys()))
        
        if st.button("Generar Archivo Excel", icon="⚙️"):
            with st.spinner("Extrayendo información de la base de datos..."):
                nombre_real_tabla = tablas_disponibles[tabla_seleccionada]
                df_tabla = obtener_tabla(nombre_real_tabla)
                
                if not df_tabla.empty:
                    excel_data = convertir_df_a_excel(df_tabla)
                    st.success(f"¡Datos de '{tabla_seleccionada}' procesados exitosamente!")
                    st.download_button(
                        label=f"⬇️ Clic aquí para guardar '{tabla_seleccionada}.xlsx'",
                        data=excel_data,
                        file_name=f"{nombre_real_tabla}_export.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                else:
                    st.warning(f"La tabla '{tabla_seleccionada}' está vacía actualmente.")

if __name__ == '__main__':
    mostrar_reportes()