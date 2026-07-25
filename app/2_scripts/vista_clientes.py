import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=60)
def cargar_todos_los_clientes():
    conn = get_db_connection()
    try:
        response = conn.table("clientes").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error al cargar clientes: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_librero_total_cliente(cliente_id):
    """Busca libros cruzando los datos manualmente para evitar errores de llaves foráneas."""
    conn = get_db_connection()
    libros_consolidados = []

    # Cargamos el catálogo de libros completo para buscar los títulos
    try:
        res_libros = conn.table("libros").select("libro_id, titulo").execute()
        df_libros = pd.DataFrame(res_libros.data)
    except:
        df_libros = pd.DataFrame()

    # 1. Búsqueda en LIBRERO HISTÓRICO
    try:
        res_hist = conn.table("librero_historico").select("*").eq("cliente_id", cliente_id).execute()
        if res_hist.data:
            df_hist = pd.DataFrame(res_hist.data)
            # Cruzamos los IDs con los títulos
            if not df_libros.empty:
                df_hist = df_hist.merge(df_libros, on="libro_id", how="left")
            
            for _, row in df_hist.iterrows():
                titulo = row.get('titulo', 'LIBRO EXTERNO / NO EN CATÁLOGO')
                if pd.isna(titulo): titulo = 'LIBRO EXTERNO / NO EN CATÁLOGO'
                
                libros_consolidados.append({
                    "Título del Libro": str(titulo).upper(),
                    "Origen": str(row.get('origen', 'HISTÓRICO')).upper(),
                    "Detalle": f"Autor: {row.get('autor_historico', '-')}",
                    "Fecha": "-"
                })
    except Exception as e:
        pass

    # 2. Búsqueda en REGISTRO DE VENTAS (Caja)
    try:
        res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta, metodo_envio").eq("cliente_id", cliente_id).execute()
        for row in res_ventas.data:
            texto_libros = row.get('libros_vendidos', '')
            items = texto_libros.split(" | ")
            for item in items:
                partes = item.split(" x ", 1)
                titulo = partes[1] if len(partes) == 2 else item
                
                fecha = row.get('fecha_venta', '')
                fecha_formateada = pd.to_datetime(fecha).strftime('%d-%m-%Y') if fecha else "-"
                
                libros_consolidados.append({
                    "Título del Libro": titulo.upper(),
                    "Origen": "VENTA CAJA",
                    "Detalle": f"Envío: {row.get('metodo_envio', '-')}",
                    "Fecha": fecha_formateada
                })
    except:
        pass

    # 3. Búsqueda en ASIGNACIONES (Suscripciones)
    try:
        res_asig = conn.table("asignaciones").select("*").eq("cliente_id", cliente_id).execute()
        if res_asig.data:
            df_asig = pd.DataFrame(res_asig.data)
            if not df_libros.empty:
                df_asig = df_asig.merge(df_libros, left_on='libro_suscripcion_id', right_on='libro_id', how='left')
                
            for _, row in df_asig.iterrows():
                titulo = row.get('titulo', f"LIBRO ID {row.get('libro_suscripcion_id')}")
                if pd.isna(titulo): titulo = f"LIBRO ID {row.get('libro_suscripcion_id')}"
                mes = row.get('mes', '')
                ano = row.get('ano', '')
                
                libros_consolidados.append({
                    "Título del Libro": str(titulo).upper(),
                    "Origen": f"ASIGNACIÓN {mes}/{ano}",
                    "Detalle": f"Estado: {row.get('estado_envio', '-')}",
                    "Fecha": row.get('fecha_asignacion', '-')
                })
    except:
        pass

    df = pd.DataFrame(libros_consolidados)
    if not df.empty:
        df = df.drop_duplicates(subset=['Título del Libro']) # Evita que un libro salga doble si está en ventas y en el histórico
    return df

def actualizar_datos_cliente(cliente_id, datos):
    conn = get_db_connection()
    try:
        conn.table("clientes").update(datos).eq("cliente_id", cliente_id).execute()
        cargar_todos_los_clientes.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

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
            datos = {
                "nombre": limpiar_texto(row['nombre']),
                "email": limpiar_texto(row['email']),
                "telefono": limpiar_texto(row['telefono']),
                "instagram": limpiar_texto(row['instagram']),
                "rut": limpiar_texto(row['rut']),
                "direccion": limpiar_texto(row['direccion']),
                "status": limpiar_texto(row['status'])
            }
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
        
    tab_todos, tab_individual = st.tabs(["👥 Directorio de Todos los Clientes", "👤 Perfil y Librero Individual"])
    
    # --- PESTAÑA 1: TODOS LOS CLIENTES (Editable) ---
    with tab_todos:
        st.markdown("### 📋 Directorio General")
        st.caption("Puedes hacer doble clic en las celdas para modificar directamente el RUT, Status, Instagram, etc.")
        
        columnas_mostrar = ['cliente_id', 'nombre', 'status', 'email', 'telefono', 'instagram', 'rut', 'direccion']
        # Nos aseguramos de que existan las columnas
        for col in columnas_mostrar:
            if col not in df_clientes.columns: df_clientes[col] = ""
            
        df_mostrar = df_clientes[columnas_mostrar].copy()
        
        if 'clientes_original' not in st.session_state or not st.session_state.clientes_original.equals(df_mostrar):
            st.session_state.clientes_original = df_mostrar.copy()
            
        df_editado = st.data_editor(
            df_mostrar,
            hide_index=True,
            use_container_width=True,
            disabled=['cliente_id', 'nombre'] # El ID y el nombre no se tocan desde la tabla general
        )
        
        if not df_mostrar.equals(df_editado):
            if st.button("💾 Guardar Cambios en Clientes", type="primary"):
                with st.spinner("Actualizando clientes..."):
                    num = actualizar_clientes_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} clientes!")
                    st.rerun()

    # --- PESTAÑA 2: INDIVIDUAL (Perfil y Librero) ---
    with tab_individual:
        lista_clientes = [""] + df_clientes['nombre'].dropna().tolist()
        cliente_seleccionado = st.selectbox("🔍 Escribe o selecciona el nombre del cliente:", lista_clientes)
        
        if cliente_seleccionado:
            cliente_info = df_clientes[df_clientes['nombre'] == cliente_seleccionado].iloc[0]
            c_id = int(cliente_info['cliente_id'])
            
            col_perfil, col_librero = st.columns([1, 1.5]) # Layout lado a lado en PC, apilado en móvil
            
            with col_perfil:
                with st.container(border=True):
                    st.markdown(f"#### 👤 Perfil ({cliente_info.get('status', 'REGULAR')})")
                    with st.form("form_editar_cliente"):
                        c_nombre = st.text_input("Nombre Completo:", value=cliente_info.get('nombre', ''))
                        c_email = st.text_input("Email:", value=cliente_info.get('email', ''))
                        c_telefono = st.text_input("Teléfono:", value=cliente_info.get('telefono', ''))
                        c_instagram = st.text_input("Instagram:", value=cliente_info.get('instagram', ''))
                        c_rut = st.text_input("RUT:", value=cliente_info.get('rut', ''))
                        c_direccion = st.text_input("Dirección:", value=cliente_info.get('direccion', ''))
                        
                        if st.form_submit_button("💾 Guardar Perfil", type="primary", use_container_width=True):
                            datos_actualizados = {
                                "nombre": limpiar_texto(c_nombre), "email": limpiar_texto(c_email),
                                "telefono": limpiar_texto(c_telefono), "instagram": limpiar_texto(c_instagram),
                                "rut": limpiar_texto(c_rut), "direccion": limpiar_texto(c_direccion)
                            }
                            exito, error = actualizar_datos_cliente(c_id, datos_actualizados)
                            if exito: st.success("¡Perfil actualizado!"), st.rerun()
                            else: st.error(f"Error: {error}")
            
            with col_librero:
                with st.container(border=True):
                    st.markdown(f"#### 📚 Colección de Libros")
                    df_librero = cargar_librero_total_cliente(c_id)
                    
                    if df_librero.empty:
                        st.info("Aún no tiene libros en su historial.")
                    else:
                        st.metric("Total de libros únicos", len(df_librero))
                        st.dataframe(df_librero, hide_index=True, use_container_width=True)