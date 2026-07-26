import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto

def obtener_unicos(df, columna):
    if columna not in df.columns: return []
    return sorted(df[columna].dropna().astype(str).unique())

@st.cache_data(ttl=60)
def cargar_todos_los_clientes():
    conn = get_db_connection()
    try:
        response = conn.table("clientes").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e: return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_librero_total_cliente(cliente_id):
    conn = get_db_connection()
    libros_consolidados = []
    try:
        res_libros = conn.table("libros").select("libro_id, titulo").execute()
        df_libros = pd.DataFrame(res_libros.data)
    except: df_libros = pd.DataFrame()

    try:
        res_hist = conn.table("librero_historico").select("*").eq("cliente_id", cliente_id).execute()
        if res_hist.data:
            df_hist = pd.DataFrame(res_hist.data)
            if not df_libros.empty: df_hist = df_hist.merge(df_libros, on="libro_id", how="left")
            for _, row in df_hist.iterrows():
                titulo = row.get('titulo', 'LIBRO EXTERNO / NO EN CATÁLOGO')
                if pd.isna(titulo): titulo = 'LIBRO EXTERNO'
                libros_consolidados.append({"Título del Libro": str(titulo).upper(), "Origen": str(row.get('origen', 'HISTÓRICO')).upper(), "Detalle": f"Autor: {row.get('autor_historico', '-')}", "Fecha": "-"})
    except: pass

    try:
        res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta, metodo_envio").eq("cliente_id", cliente_id).execute()
        for row in res_ventas.data:
            items = row.get('libros_vendidos', '').split(" | ")
            for item in items:
                partes = item.split(" x ", 1)
                titulo = partes[1] if len(partes) == 2 else item
                fecha = pd.to_datetime(row.get('fecha_venta', '')).strftime('%d-%m-%Y') if row.get('fecha_venta', '') else "-"
                libros_consolidados.append({"Título del Libro": titulo.upper(), "Origen": "VENTA CAJA", "Detalle": f"Envío: {row.get('metodo_envio', '-')}", "Fecha": fecha})
    except: pass

    try:
        res_asig = conn.table("asignaciones").select("*").eq("cliente_id", cliente_id).execute()
        if res_asig.data:
            df_asig = pd.DataFrame(res_asig.data)
            if not df_libros.empty: df_asig = df_asig.merge(df_libros, left_on='libro_suscripcion_id', right_on='libro_id', how='left')
            for _, row in df_asig.iterrows():
                titulo = row.get('titulo', f"LIBRO ID {row.get('libro_suscripcion_id')}")
                if pd.isna(titulo): titulo = f"LIBRO ID {row.get('libro_suscripcion_id')}"
                libros_consolidados.append({"Título del Libro": str(titulo).upper(), "Origen": f"ASIGNACIÓN {row.get('mes', '')}/{row.get('ano', '')}", "Detalle": f"Estado: {row.get('estado_envio', '-')}", "Fecha": row.get('fecha_asignacion', '-')})
    except: pass

    df = pd.DataFrame(libros_consolidados)
    if not df.empty: df = df.drop_duplicates(subset=['Título del Libro']) 
    return df

def actualizar_datos_cliente(cliente_id, datos):
    conn = get_db_connection()
    try:
        conn.table("clientes").update(datos).eq("cliente_id", cliente_id).execute()
        cargar_todos_los_clientes.clear()
        return True, ""
    except Exception as e: return False, str(e)

def actualizar_clientes_batch(df_editado):
    df_original = st.session_state.get('clientes_original')
    if df_original is None: return 0
    df_original_comp = df_original.set_index('cliente_id')
    df_editado_comp = df_editado.set_index('cliente_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates = 0
    for c_id, row in filas_cambiadas.iterrows():
        try:
            datos = {"nombre": limpiar_texto(row['nombre']), "email": limpiar_texto(row['email']), "telefono": limpiar_texto(row['telefono']), "instagram": limpiar_texto(row['instagram']), "rut": limpiar_texto(row['rut']), "direccion": limpiar_texto(row['direccion']), "status": limpiar_texto(row['status'])}
            conn.table("clientes").update(datos).eq("cliente_id", c_id).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_todos_los_clientes.clear()
    return updates


# --- INTERFAZ PRINCIPAL ---

def mostrar_clientes():
    st.title("👥 Gestión de Clientes y Librero")
    df_clientes = cargar_todos_los_clientes()
    if df_clientes.empty:
        st.warning("No hay clientes registrados en el sistema.")
        return

    with st.expander("🔍 Buscador y Filtros", expanded=False):
        col_f1, col_f2 = st.columns(2)
        f_nombre = col_f1.text_input("Buscar por Nombre:")
        f_status = col_f2.multiselect("Filtrar por Status:", obtener_unicos(df_clientes, 'status'))
        col_f3, col_f4 = st.columns(2)
        f_email = col_f3.text_input("Buscar por Email:")
        f_telefono = col_f4.text_input("Buscar por Teléfono:")
        col_f5, col_f6 = st.columns(2)
        f_instagram = col_f5.text_input("Buscar por Instagram:")
        f_rut = col_f6.text_input("Buscar por RUT:")

    df_filtrado = df_clientes.copy()
    if f_nombre: df_filtrado = df_filtrado[df_filtrado['nombre'].str.contains(limpiar_texto(f_nombre), case=False, na=False)]
    if f_status: df_filtrado = df_filtrado[df_filtrado['status'].isin(f_status)]
    if f_email: df_filtrado = df_filtrado[df_filtrado['email'].str.contains(limpiar_texto(f_email), case=False, na=False)]
    if f_telefono: df_filtrado = df_filtrado[df_filtrado['telefono'].str.contains(limpiar_texto(f_telefono), case=False, na=False)]
    if f_instagram: df_filtrado = df_filtrado[df_filtrado['instagram'].str.contains(limpiar_texto(f_instagram), case=False, na=False)]
    if f_rut: df_filtrado = df_filtrado[df_filtrado['rut'].str.contains(limpiar_texto(f_rut), case=False, na=False)]

    tab_todos, tab_individual = st.tabs(["👥 Directorio", "👤 Perfil Individual"])
    
    with tab_todos:
        st.markdown(f"### 📋 Directorio ({len(df_filtrado)} clientes)")
        modo_vista = st.radio("Vista:", ["📱 Vista Móvil (Resumen)", "💻 Vista PC (Tabla Editable)"], horizontal=True, label_visibility="collapsed")
        
        columnas_mostrar = ['cliente_id', 'nombre', 'status', 'email', 'telefono', 'instagram', 'rut', 'direccion']
        for col in columnas_mostrar:
            if col not in df_filtrado.columns: df_filtrado[col] = ""
            
        if modo_vista == "📱 Vista Móvil (Resumen)":
            st.caption("Selecciona qué columnas ver:")
            columnas_fijas = ['nombre', 'status']
            opcionales = [c for c in columnas_mostrar if c not in columnas_fijas + ['cliente_id']]
            cols_extra = st.multiselect("Añadir/Quitar:", options=opcionales, default=['telefono'])
            st.dataframe(df_filtrado[columnas_fijas + cols_extra], hide_index=True, use_container_width=True)
        else:
            st.caption("Doble clic en las celdas para modificar directamente.")
            df_mostrar = df_filtrado[columnas_mostrar].copy()
            if 'clientes_original' not in st.session_state or not st.session_state.clientes_original.equals(df_mostrar):
                st.session_state.clientes_original = df_mostrar.copy()
            df_editado = st.data_editor(df_mostrar, hide_index=True, use_container_width=True, disabled=['cliente_id', 'nombre'])
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Clientes", type="primary"):
                    num = actualizar_clientes_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} clientes!"), st.rerun()

    with tab_individual:
        lista_nombres = [""] + df_filtrado['nombre'].dropna().tolist()
        cliente_seleccionado = st.selectbox("🔍 Escribe o selecciona el nombre del cliente:", lista_nombres)
        
        if cliente_seleccionado:
            cliente_info = df_filtrado[df_filtrado['nombre'] == cliente_seleccionado].iloc[0]
            c_id = int(cliente_info['cliente_id'])
            
            # --- VISTA 100% VERTICAL PARA MÓVILES ---
            st.markdown(f"#### 👤 Perfil de Contacto ({cliente_info.get('status', 'REGULAR')})")
            with st.container(border=True):
                with st.form("form_editar_cliente"):
                    c_nombre = st.text_input("Nombre Completo:", value=cliente_info.get('nombre', ''))
                    c_email = st.text_input("Email:", value=cliente_info.get('email', ''))
                    c_telefono = st.text_input("Teléfono:", value=cliente_info.get('telefono', ''))
                    c_instagram = st.text_input("Instagram:", value=cliente_info.get('instagram', ''))
                    c_rut = st.text_input("RUT:", value=cliente_info.get('rut', ''))
                    c_direccion = st.text_input("Dirección:", value=cliente_info.get('direccion', ''))
                    
                    if st.form_submit_button("💾 Guardar Perfil", type="primary", use_container_width=True):
                        datos_act = {"nombre": limpiar_texto(c_nombre), "email": limpiar_texto(c_email), "telefono": limpiar_texto(c_telefono), "instagram": limpiar_texto(c_instagram), "rut": limpiar_texto(c_rut), "direccion": limpiar_texto(c_direccion)}
                        exito, error = actualizar_datos_cliente(c_id, datos_act)
                        if exito: st.success("¡Perfil actualizado!"), st.rerun()
                        else: st.error(f"Error: {error}")
            
            st.markdown("---")
            st.markdown(f"#### 📚 Colección de Libros (Historial)")
            with st.container(border=True):
                df_librero = cargar_librero_total_cliente(c_id)
                if df_librero.empty:
                    st.info("Aún no tiene libros en su historial.")
                else:
                    st.metric("Total de libros únicos adquiridos", len(df_librero))
                    st.dataframe(df_librero, hide_index=True, use_container_width=True)