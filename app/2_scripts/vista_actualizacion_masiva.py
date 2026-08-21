import streamlit as st
import pandas as pd
import io
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# ==========================================================
# 🛠️ FUNCIONES DE GENERACIÓN DE PLANTILLAS (EXCEL)
# ==========================================================

def generar_plantilla_actualizacion_libros():
    """
    Genera una plantilla Excel con TODOS los libros y sus datos actuales,
    incluyendo los nuevos campos booleanos, superando la limitación de 1000.
    """
    conn = get_db_connection()
    try:
        all_books = []
        chunk_size = 1000
        # Bucle dinámico ilimitado (hasta 100.000 libros)
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("libros").select(
                "libro_id, titulo, autor, editorial, genero, encuadernacion, stock, precio, costo, precio_original, apto_cajita, destacado, visible_catalogo"
            ).order("libro_id").range(start, end).execute()
            
            if res.data:
                all_books.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_books:
            return None
            
        df = pd.DataFrame(all_books)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Libros')
            worksheet = writer.sheets['Actualizar Libros']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_actualizacion_masiva", 
            funcion="generar_plantilla_actualizacion_libros",
            error=e,
            email_usuario=email_usuario
        )
        st.error(f"Error generando plantilla de libros: {e}")
        return None

def generar_plantilla_actualizacion_clientes():
    """Genera una plantilla Excel con TODOS los clientes actuales, superando la limitación de 1000."""
    conn = get_db_connection()
    try:
        all_clients = []
        chunk_size = 1000
        # Bucle dinámico ilimitado (hasta 100.000 clientes)
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("clientes")\
                .select("cliente_id, nombre, rut, email, telefono, instagram, direccion, status")\
                .order("cliente_id")\
                .range(start, end).execute()
            if res.data:
                all_clients.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_clients:
            return None
            
        df = pd.DataFrame(all_clients)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Clientes')
            worksheet = writer.sheets['Actualizar Clientes']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_actualizacion_masiva", 
            funcion="generar_plantilla_actualizacion_clientes",
            error=e,
            email_usuario=email_usuario
        )
        st.error(f"Error generando plantilla de clientes: {e}")
        return None

def generar_plantilla_actualizacion_costos():
    """Genera una plantilla Excel con TODOS los costos no de ventas actuales, superando la limitación de 1000 de Supabase."""
    conn = get_db_connection()
    try:
        all_costs = []
        chunk_size = 1000
        # Bucle dinámico seguro (hasta 100.000 costos) con bypass
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("costos_no_ventas")\
                .select("costo_id, fecha_ocurrencia, tipo_costo, monto, comentario, creado_por")\
                .order("costo_id")\
                .range(start, end).execute()
            if res.data:
                all_costs.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_costs:
            return None
            
        df = pd.DataFrame(all_costs)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Costos')
            worksheet = writer.sheets['Actualizar Costos']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_actualizacion_masiva", 
            funcion="generar_plantilla_actualizacion_costos",
            error=e,
            email_usuario=email_usuario
        )
        st.error(f"Error generando plantilla de costos: {e}")
        return None

# ==========================================================
# 📥 FUNCIONES DE PROCESAMIENTO Y ACTUALIZACIÓN EN BD
# ==========================================================

def procesar_actualizacion_libros(df):
    conn = get_db_connection()
    updates, errores = 0, []
    
    columnas_texto = ['titulo', 'autor', 'editorial', 'genero', 'encuadernacion']
    columnas_float = ['precio', 'costo', 'precio_original']
    columnas_bool = ['apto_cajita', 'destacado', 'visible_catalogo']

    # Cargar datos originales para la lógica de precios
    ids_libros = df['libro_id'].dropna().astype(int).tolist()
    df_original = pd.DataFrame()
    if ids_libros:
        original_data = []
        for idx in range(0, len(ids_libros), 1000):
            chunk = ids_libros[idx:idx + 1000]
            res_original = conn.table("libros").select("libro_id, precio, precio_original").in_("libro_id", chunk).execute()
            if res_original.data:
                original_data.extend(res_original.data)
                
        if original_data:
            df_original = pd.DataFrame(original_data).set_index('libro_id')
            df_original['Dcto %'] = 0.0
            mask_dcto = (df_original['precio_original'] > df_original['precio']) & (df_original['precio_original'] > 0)
            df_original.loc[mask_dcto, 'Dcto %'] = (((df_original.loc[mask_dcto, 'precio_original'] - df_original.loc[mask_dcto, 'precio']) / df_original.loc[mask_dcto, 'precio_original']) * 100)

    for i, fila in df.iterrows():
        try:
            if 'libro_id' not in fila or pd.isna(fila['libro_id']):
                continue
            
            libro_id = int(fila['libro_id'])
            datos_update = {}
            
            for col in df.columns:
                if col in fila and pd.notna(fila[col]) and col != 'libro_id':
                    if col in columnas_texto:
                        datos_update[col] = limpiar_texto_para_busqueda(str(fila[col]))
                    elif col == 'stock':
                        datos_update[col] = int(float(fila[col]))
                    elif col in columnas_float:
                        datos_update[col] = float(fila[col])
                    elif col in columnas_bool:
                        datos_update[col] = bool(fila[col])

            # Lógica de Recálculo de Precios
            if 'precio_original' in datos_update and not df_original.empty and libro_id in df_original.index:
                nuevo_precio_orig = float(datos_update['precio_original'])
                porcentaje_dcto_actual = float(df_original.loc[libro_id].get('Dcto %', 0))
                
                if porcentaje_dcto_actual > 0:
                    factor = 1.0 - (porcentaje_dcto_actual / 100.0)
                    datos_update['precio'] = round(nuevo_precio_orig * factor, 0)
                else:
                    datos_update['precio'] = nuevo_precio_orig
            
            if 'precio' in fila and pd.notna(fila['precio']):
                if 'precio' not in datos_update or datos_update['precio'] != float(fila['precio']):
                    datos_update['precio'] = float(fila['precio'])

            if datos_update:
                conn.table("libros").update(datos_update).eq("libro_id", libro_id).execute()
                updates += 1
        except Exception as e:
            errores.append(f"Fila {i+2} (ID Libro: {fila.get('libro_id', 'N/A')}): {str(e)}")
            
    return updates, errores

def procesar_actualizacion_clientes(df):
    conn = get_db_connection()
    updates, errores = 0, []
    
    df.columns = df.columns.str.lower().str.strip()
    
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

def procesar_actualizacion_costos(df):
    """Procesa y actualiza en caliente los costos no operacionales en Supabase."""
    conn = get_db_connection()
    updates, errores = 0, []
    
    df.columns = df.columns.str.lower().str.strip()
    columnas_permitidas = ['fecha_ocurrencia', 'tipo_costo', 'monto', 'comentario']

    for i, fila in df.iterrows():
        try:
            if 'costo_id' not in fila or pd.isna(fila['costo_id']):
                errores.append(f"Fila {i+2}: Falta la columna obligatoria 'costo_id'.")
                continue
            
            costo_id = int(float(fila['costo_id']))
            datos_update = {}
            
            for col in columnas_permitidas:
                if col in fila and pd.notna(fila[col]):
                    valor_celda = str(fila[col]).strip()
                    if valor_celda.lower() != 'nan' and valor_celda != '':
                        if col == 'monto':
                            datos_update[col] = float(valor_celda)
                        elif col == 'fecha_ocurrencia':
                            datos_update[col] = pd.to_datetime(valor_celda).strftime("%Y-%m-%d")
                        else:
                            datos_update[col] = limpiar_texto_para_busqueda(valor_celda).upper() if col == 'tipo_costo' else valor_celda

            if datos_update:
                conn.table("costos_no_ventas").update(datos_update).eq("costo_id", costo_id).execute()
                updates += 1
        except Exception as e:
            errores.append(f"Fila {i+2} (ID Costo: {fila.get('costo_id', 'N/A')}): {str(e)}")
            
    return updates, errores

# ==========================================================
# 🎨 INTERFAZ GRÁFICA DE USUARIO (UX/UI)
# ==========================================================

def mostrar_actualizacion_masiva():
    st.markdown("<h2 style='color: #4A4D7E;'>⚡ Actualización Masiva de Datos</h2>", unsafe_allow_html=True)
    st.markdown("Modifica registros de forma masiva subiendo un archivo Excel/CSV. **La columna ID es obligatoria** para aplicar los cambios.")
    
    tab_libros, tab_clientes, tab_costos = st.tabs([
        "📚 Actualizar Libros", "👥 Actualizar Clientes", "💸 Actualizar Costos"
    ])
    
    # ---------------- TAB: LIBROS ----------------
    with tab_libros:
        st.markdown("### 1. Descarga el Inventario Actual")
        st.caption("Obtén el archivo Excel con tus libros actuales, modifícalo en tu equipo y súbelo abajo.")
        
        try:
            plantilla_libros = generar_plantilla_actualizacion_libros()
            if plantilla_libros:
                st.download_button(
                    label="📥 Descargar Inventario de Libros (.xlsx)",
                    data=plantilla_libros,
                    file_name="inventario_libros_actualizar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista="vista_actualizacion_masiva", 
                funcion="generar_plantilla_actualizacion_libros",
                error=e,
                email_usuario=email_usuario
            )
            st.error(f"Error al generar la plantilla de libros: {e}")
            
        st.markdown("---")
        st.markdown("### 2. Sube tus Modificaciones")
        archivo_libros = st.file_uploader("Sube el archivo Excel modificado de Libros", type=['xlsx', 'csv'], key="up_libros")
        
        if archivo_libros:
            if st.button("🚀 Aplicar Cambios en Libros", type="primary", use_container_width=True):
                with st.spinner("Actualizando catálogo de libros en Supabase..."):
                    try:
                        df = pd.read_excel(archivo_libros) if archivo_libros.name.endswith('.xlsx') else pd.read_csv(archivo_libros)
                        updates, errores = procesar_actualizacion_libros(df)
                        
                        if updates > 0:
                            st.success(f"✅ ¡Se actualizaron {updates} libros exitosamente!")
                            st.balloons()
                        if errores:
                            st.error(f"⚠️ Se presentaron {len(errores)} errores durante la actualización:")
                            for err in errores: st.write(err)
                        
                        if updates > 0 and not errores:
                            st.cache_data.clear()
                            
                    except Exception as e:
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        log_error(
                            vista="vista_actualizacion_masiva", 
                            funcion="procesar_actualizacion_libros",
                            error=e,
                            email_usuario=email_usuario
                        )
                        st.error(f"Error al procesar el archivo: {e}")
                        st.caption("Verifica que el formato del archivo sea correcto y que las columnas no hayan sido modificadas.")

    # ---------------- TAB: CLIENTES ----------------
    with tab_clientes:
        st.markdown("### 1. Descarga el Listado de Clientes Actual")
        st.caption("Obtén el archivo Excel con tus clientes actuales, edita su RUT, dirección o correo y súbelo abajo.")
        
        try:
            plantilla_clientes = generar_plantilla_actualizacion_clientes()
            if plantilla_clientes:
                st.download_button(
                    label="📥 Descargar Listado de Clientes (.xlsx)",
                    data=plantilla_clientes,
                    file_name="listado_clientes_actualizar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista="vista_actualizacion_masiva", 
                funcion="generar_plantilla_actualizacion_clientes",
                error=e,
                email_usuario=email_usuario
            )
            st.error(f"Error al generar la plantilla de clientes: {e}")
            
        st.markdown("---")
        st.markdown("### 2. Sube tus Modificaciones")
        archivo_clientes = st.file_uploader("Sube el archivo Excel modificado de Clientes", type=['xlsx', 'csv'], key="up_clientes")
        
        if archivo_clientes:
            if st.button("🚀 Aplicar Cambios en Clientes", type="primary", use_container_width=True):
                with st.spinner("Actualizando datos de clientes en Supabase..."):
                    try:
                        df_cli = pd.read_excel(archivo_clientes, dtype=str) if archivo_clientes.name.endswith('.xlsx') else pd.read_csv(archivo_clientes, dtype=str)
                        updates_cli, errores_cli = procesar_actualizacion_clientes(df_cli)
                        
                        if updates_cli > 0:
                            st.success(f"✅ ¡Se actualizaron {updates_cli} perfiles de clientes exitosamente!")
                            st.balloons()
                        if errores_cli:
                            st.error(f"⚠️ Se presentaron {len(errores_cli)} errores durante la actualización:")
                            for err in errores_cli: st.write(err)
                        
                        if updates_cli > 0 and not errores_cli:
                            st.cache_data.clear()

                    except Exception as e:
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        log_error(
                            vista="vista_actualizacion_masiva", 
                            funcion="procesar_actualizacion_clientes",
                            error=e,
                            email_usuario=email_usuario
                        )
                        st.error(f"Error al procesar el archivo de clientes: {e}")
                        st.caption("Verifica que el formato del archivo sea correcto y que las columnas no hayan sido modificadas.")

    # ---------------- TAB: COSTOS NO VENTAS ----------------
    with tab_costos:
        st.markdown("### 1. Descarga el Listado de Costos Actual")
        st.caption("Obtén el archivo Excel con tus costos no operacionales actuales, edita su monto, tipo de costo o comentario y súbelo abajo.")
        
        try:
            plantilla_costos = generar_plantilla_actualizacion_costos()
            if plantilla_costos:
                st.download_button(
                    label="📥 Descargar Listado de Costos (.xlsx)",
                    data=plantilla_costos,
                    file_name="listado_costos_actualizar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista="vista_actualizacion_masiva", 
                funcion="generar_plantilla_actualizacion_costos",
                error=e,
                email_usuario=email_usuario
            )
            st.error(f"Error al generar la plantilla de costos: {e}")
            
        st.markdown("---")
        st.markdown("### 2. Sube tus Modificaciones")
        archivo_costos = st.file_uploader("Sube el archivo Excel modificado de Costos", type=['xlsx', 'csv'], key="up_costos")
        
        if archivo_costos:
            if st.button("🚀 Aplicar Cambios en Costos", type="primary", use_container_width=True):
                with st.spinner("Actualizando datos de costos en Supabase..."):
                    try:
                        df_cos = pd.read_excel(archivo_costos, dtype=str) if archivo_costos.name.endswith('.xlsx') else pd.read_csv(archivo_costos, dtype=str)
                        updates_cos, errores_cos = procesar_actualizacion_costos(df_cos)
                        
                        if updates_cos > 0:
                            st.success(f"✅ ¡Se actualizaron {updates_cos} registros de costos exitosamente!")
                            st.balloons()
                        if errores_cos:
                            st.error(f"⚠️ Se presentaron {len(errores_cos)} errores durante la actualización:")
                            for err in errores_cos: st.write(err)
                        
                        if updates_cos > 0 and not errores_cos:
                            st.cache_data.clear()

                    except Exception as e:
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        log_error(
                            vista="vista_actualizacion_masiva", 
                            funcion="procesar_actualizacion_costos",
                            error=e,
                            email_usuario=email_usuario
                        )
                        st.error(f"Error al procesar el archivo de costos: {e}")
                        st.caption("Verifica que el formato del archivo sea correcto y que las columnas no hayan sido modificadas.")

if __name__ == "__main__":
    mostrar_actualizacion_masiva()