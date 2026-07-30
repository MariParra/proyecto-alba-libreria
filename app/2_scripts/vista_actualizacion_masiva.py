import streamlit as st
import pandas as pd
import io
from utilidades import get_db_connection, limpiar_texto

# ==========================================================
# 🛠️ FUNCIONES DE GENERACIÓN DE PLANTILLAS (EXCEL)
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
        st.error(f"Error generando plantilla de libros: {e}")
        return None

def generar_plantilla_actualizacion_clientes():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, rut, email, telefono, instagram, direccion, status").execute()
        df = pd.DataFrame(res.data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Clientes')
            worksheet = writer.sheets['Actualizar Clientes']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        st.error(f"Error generando plantilla de clientes: {e}")
        return None

# ==========================================================
# 📥 FUNCIONES DE PROCESAMIENTO Y ACTUALIZACIÓN EN BD
# ==========================================================

def procesar_actualizacion_libros(df):
    conn = get_db_connection()
    updates, errores = 0, []
    
    columnas_texto = ['titulo', 'autor', 'editorial', 'genero', 'encuadernacion']
    columnas_float = ['precio', 'costo']

    for i, fila in df.iterrows():
        try:
            if 'libro_id' not in fila or pd.isna(fila['libro_id']):
                continue
            
            libro_id = int(fila['libro_id'])
            datos_update = {}
            
            for col in df.columns:
                if col in fila and pd.notna(fila[col]) and col != 'libro_id':
                    if col in columnas_texto:
                        datos_update[col] = limpiar_texto(str(fila[col]))
                    
                    # --- CORRECCIÓN CLAVE ---
                    # Tratamos el stock estrictamente como un entero para evitar "0.0"
                    elif col == 'stock':
                        datos_update[col] = int(float(fila[col]))
                        
                    elif col in columnas_float:
                        datos_update[col] = float(fila[col])

            if datos_update:
                conn.table("libros").update(datos_update).eq("libro_id", libro_id).execute()
                updates += 1
        except Exception as e:
            errores.append(f"Fila {i+2} (ID Libro: {fila.get('libro_id', 'N/A')}): {str(e)}")
            
    return updates, errores

def procesar_actualizacion_clientes(df):
    conn = get_db_connection()
    updates, errores = 0, []
    
    # Estandarizamos los nombres de las columnas del Excel
    df.columns = df.columns.str.lower().str.strip()
    
    # Soporte para si escriben "correo" en lugar de "email"
    if 'correo' in df.columns and 'email' not in df.columns:
        df.rename(columns={'correo': 'email'}, inplace=True)
        
    columnas_permitidas = ['rut', 'direccion', 'email', 'telefono', 'instagram', 'nombre', 'status']

    for i, fila in df.iterrows():
        try:
            if 'cliente_id' not in fila or pd.isna(fila['cliente_id']):
                errores.append(f"Fila {i+2}: Falta la columna 'cliente_id'.")
                continue
            
            cliente_id = int(fila['cliente_id'])
            datos_update = {}
            
            for col in columnas_permitidas:
                if col in fila and pd.notna(fila[col]):
                    valor_celda = str(fila[col]).strip()
                    if valor_celda.lower() != 'nan' and valor_celda != '':
                        datos_update[col] = valor_celda

            if datos_update:
                conn.table("clientes").update(datos_update).eq("cliente_id", cliente_id).execute()
                updates += 1
        except Exception as e:
            errores.append(f"Fila {i+2} (ID Cliente: {fila.get('cliente_id', 'N/A')}): {str(e)}")
            
    return updates, errores

# ==========================================================
# 🎨 INTERFAZ GRÁFICA DE USUARIO (UX/UI)
# ==========================================================

def mostrar_actualizacion_masiva():
    st.markdown("<h2 style='color: #4A4D7E;'>⚡ Actualización Masiva de Datos</h2>", unsafe_allow_html=True)
    st.markdown("Modifica registros de forma masiva subiendo un archivo Excel/CSV. **La columna ID es obligatoria** para aplicar los cambios.")
    
    # Separación por pestañas para una navegación limpia
    tab_libros, tab_clientes = st.tabs(["📚 Actualizar Libros", "👥 Actualizar Clientes"])
    
    # --- PESTAÑA 1: LIBROS ---
    with tab_libros:
        st.markdown("### 1. Descarga el Inventario Actual")
        st.caption("Obtén el archivo Excel con tus libros actuales, modifícalo en tu equipo y súbelo abajo.")
        
        plantilla_libros = generar_plantilla_actualizacion_libros()
        if plantilla_libros:
            st.download_button(
                label="📥 Descargar Inventario de Libros (.xlsx)",
                data=plantilla_libros,
                file_name="inventario_libros_actualizar.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        st.markdown("---")
        st.markdown("### 2. Sube tus Modificaciones")
        archivo_libros = st.file_uploader("Sube el archivo Excel modificado de Libros", type=['xlsx', 'csv'], key="up_libros")
        
        if archivo_libros and st.button("🚀 Aplicar Cambios en Libros", type="primary", use_container_width=True):
            with st.spinner("Actualizando catálogo de libros en Supabase..."):
                df = pd.read_excel(archivo_libros) if archivo_libros.name.endswith('.xlsx') else pd.read_csv(archivo_libros)
                updates, errores = procesar_actualizacion_libros(df)
                
                if updates > 0:
                    st.success(f"✅ ¡Se actualizaron {updates} libros exitosamente!")
                    st.balloons()
                if errores:
                    st.error(f"⚠️ Se presentaron {len(errores)} errores:")
                    for e in errores: st.write(e)
                st.cache_data.clear()

    # --- PESTAÑA 2: CLIENTES ---
    with tab_clientes:
        st.markdown("### 1. Descarga el Listado de Clientes Actual")
        st.caption("Obtén el archivo Excel con tus clientes actuales, edita su RUT, dirección o correo y súbelo abajo.")
        
        plantilla_clientes = generar_plantilla_actualizacion_clientes()
        if plantilla_clientes:
            st.download_button(
                label="📥 Descargar Listado de Clientes (.xlsx)",
                data=plantilla_clientes,
                file_name="listado_clientes_actualizar.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        st.markdown("---")
        st.markdown("### 2. Sube tus Modificaciones")
        archivo_clientes = st.file_uploader("Sube el archivo Excel modificado de Clientes", type=['xlsx', 'csv'], key="up_clientes")
        
        if archivo_clientes and st.button("🚀 Aplicar Cambios en Clientes", type="primary", use_container_width=True):
            with st.spinner("Actualizando datos de clientes en Supabase..."):
                # Leemos todo como string para no romper formatos de RUT o teléfonos
                df_cli = pd.read_excel(archivo_clientes, dtype=str) if archivo_clientes.name.endswith('.xlsx') else pd.read_csv(archivo_clientes, dtype=str)
                updates_cli, errores_cli = procesar_actualizacion_clientes(df_cli)
                
                if updates_cli > 0:
                    st.success(f"✅ ¡Se actualizaron {updates_cli} perfiles de clientes exitosamente!")
                    st.balloons()
                if errores_cli:
                    st.error(f"⚠️ Se presentaron {len(errores_cli)} errores:")
                    for e in errores_cli: st.write(e)
                st.cache_data.clear()

if __name__ == "__main__":
    mostrar_actualizacion_masiva()