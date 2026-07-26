import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS (CLIENTES) ---
@st.cache_data(ttl=60)
def cargar_clientes():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_historial_cliente(cliente_id):
    conn = get_db_connection()
    try:
        # Petición a Supabase para cruzar el histórico con el nombre del libro
        res = conn.table("librero_historico").select("*, libros(titulo)").eq("cliente_id", cliente_id).execute()
        df = pd.DataFrame(res.data)
        
        # Procesamos la respuesta para dejarla amigable
        if not df.empty and 'libros' in df.columns:
            # Extraemos el título del diccionario anidado que nos manda Supabase
            df['titulo_libro'] = df['libros'].apply(lambda x: x.get('titulo', '') if isinstance(x, dict) else "")
            
            # Limpiamos columnas innecesarias para mostrar
            df = df[['origen', 'titulo_libro', 'autor_historico']]
            df.columns = ['Fecha / Origen', 'Título', 'Autor']
        return df
    except: return pd.DataFrame()

def actualizar_cliente_batch(df_editado):
    df_original = st.session_state.get('clientes_original')
    if df_original is None: return 0
    diff_mask = df_original.set_index('cliente_id').ne(df_editado.set_index('cliente_id')).any(axis=1)
    filas_cambiadas = df_editado.set_index('cliente_id')[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates = 0
    for c_id, row in filas_cambiadas.iterrows():
        try:
            estado_bruto = str(row.get('status', '')).upper().strip()
            # Aplicamos regla de negocio estricta: INACTIVO se convierte en NO ACTIVA
            if estado_bruto == "INACTIVO": estado_bruto = "NO ACTIVA"
            
            datos = {
                "nombre": limpiar_texto(str(row.get('nombre', ''))),
                "email": limpiar_texto(str(row.get('email', ''))),
                "telefono": limpiar_texto(str(row.get('telefono', ''))),
                "direccion": limpiar_texto(str(row.get('direccion', ''))),
                "rut": limpiar_texto(str(row.get('rut', ''))),
                "status": estado_bruto
            }
            conn.table("clientes").update(datos).eq("cliente_id", int(c_id)).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_clientes.clear()
    return updates

# --- FUNCIONES DE BASE DE DATOS (SUSCRIPCIONES BASE) ---
def emparejar_suscripciones():
    conn = get_db_connection()
    try:
        res_cli = conn.table("clientes").select("cliente_id").eq("status", "ACTIVA").execute()
        res_sub = conn.table("suscripciones").select("cliente_id").execute()
        faltantes = set([c['cliente_id'] for c in res_cli.data]) - set([s['cliente_id'] for s in res_sub.data])
        for c_id in faltantes:
            conn.table("suscripciones").insert({"cliente_id": int(c_id), "valor_suscripcion": 0.0, "fecha_pago": "", "metodo_entrega": "Retiro en tienda", "generos_preferencia": ""}).execute()
        if faltantes: cargar_suscripciones_base.clear()
    except Exception: pass

@st.cache_data(ttl=60)
def cargar_suscripciones_base():
    conn = get_db_connection()
    try:
        res_sub = conn.table("suscripciones").select("*").execute()
        res_cli = conn.table("clientes").select("cliente_id, nombre, status").execute()
        df_sub = pd.DataFrame(res_sub.data)
        df_cli = pd.DataFrame(res_cli.data)
        if df_sub.empty: return pd.DataFrame()
        if not df_cli.empty: return df_sub.merge(df_cli, on='cliente_id', how='left')
        return df_sub
    except: return pd.DataFrame()

def actualizar_suscripciones_batch(df_editado):
    df_original = st.session_state.get('suscripciones_original')
    if df_original is None: return 0
    diff_mask = df_original.set_index('suscripcion_id').ne(df_editado.set_index('suscripcion_id')).any(axis=1)
    filas_cambiadas = df_editado.set_index('suscripcion_id')[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates = 0
    for s_id, row in filas_cambiadas.iterrows():
        try:
            datos = {
                "fecha_pago": str(row.get('fecha_pago', '')),
                "metodo_entrega": str(row.get('metodo_entrega', '')),
                "generos_preferencia": str(row.get('generos_preferencia', '')),
                "valor_suscripcion": float(row.get('valor_suscripcion', 0.0))
            }
            conn.table("suscripciones").update(datos).eq("suscripcion_id", int(s_id)).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_suscripciones_base.clear()
    return updates

# --- INTERFAZ PRINCIPAL ---
def mostrar_clientes():
    st.title("👥 Gestión de Clientes y CRM")
    
    # Menú estilo móvil en lugar de pestañas
    opciones_menu = [
        "📁 Directorio General (Editar Contactos)", 
        "💳 Planes y Preferencias", 
        "👤 Ficha Individual (Historial de Lectura)"
    ]
    opcion = st.selectbox("👉 SELECCIONA LA HERRAMIENTA:", opciones_menu)
    st.markdown("---")
    
    df_clientes = cargar_clientes()
    
    # =======================================================
    # 1. DIRECTORIO GENERAL (EDITAR DATOS DE CONTACTO)
    # =======================================================
    if opcion == "📁 Directorio General (Editar Contactos)":
        st.markdown("### 📁 Directorio de Clientes")
        if df_clientes.empty: st.warning("No hay clientes registrados.")
        else:
            # Filtros mejorados
            col_f1, col_f2 = st.columns(2)
            f_nombre = col_f1.text_input("🔍 Buscar Nombre o Correo:")
            
            # Nos aseguramos de mostrar estados limpios
            estados_unicos = [e for e in df_clientes['status'].unique().tolist() if e and e != "INACTIVO"]
            f_status = col_f2.selectbox("Filtrar por Estado:", ["Todos"] + estados_unicos)
            
            df_filtrado = df_clientes.copy()
            if f_nombre: 
                mask_nombre = df_filtrado['nombre'].str.contains(limpiar_texto(f_nombre), case=False, na=False)
                mask_email = df_filtrado['email'].str.contains(limpiar_texto(f_nombre), case=False, na=False)
                df_filtrado = df_filtrado[mask_nombre | mask_email]
                
            if f_status != "Todos": 
                df_filtrado = df_filtrado[df_filtrado['status'] == f_status]
            
            columnas_mostrar = ['cliente_id', 'nombre', 'email', 'telefono', 'status', 'direccion', 'rut']
            df_mostrar = df_filtrado[columnas_mostrar].copy()
            
            if 'clientes_original' not in st.session_state or not st.session_state.clientes_original.equals(df_mostrar):
                st.session_state.clientes_original = df_mostrar.copy()
                
            st.caption("Doble clic en las celdas para modificar los datos personales.")
            
            # Opciones de Selectbox restringidas a la nueva regla
            config_cols = {
                "cliente_id": st.column_config.NumberColumn("ID", disabled=True), 
                "status": st.column_config.SelectboxColumn("Estado", options=["ACTIVA", "NO ACTIVA"], required=True),
                "telefono": st.column_config.TextColumn("Teléfono")
            }
            
            df_editado = st.data_editor(df_mostrar, column_config=config_cols, hide_index=True, use_container_width=True)
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Clientes", type="primary"):
                    num = actualizar_cliente_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} clientes!"), st.rerun()

    # =======================================================
    # 2. PLANES Y PREFERENCIAS (SUSCRIPCIONES)
    # =======================================================
    elif opcion == "💳 Planes y Preferencias":
        st.markdown("### 💳 Valores Base y Detalles de Suscripción")
        emparejar_suscripciones()
        df_subs = cargar_suscripciones_base()
        
        if df_subs.empty:
            st.warning("No hay suscripciones configuradas.")
        else:
            df_subs = df_subs.sort_values(by="status", ascending=False)
            
            c_sub1, c_sub2 = st.columns(2)
            f_nombre_sub = c_sub1.text_input("🔍 Buscar Cliente (Planes):")
            f_status_sub = c_sub2.selectbox("Filtrar Estado:", ["Todos", "ACTIVA", "NO ACTIVA"])
            
            df_filtrado_sub = df_subs.copy()
            if f_nombre_sub: df_filtrado_sub = df_filtrado_sub[df_filtrado_sub['nombre'].str.contains(limpiar_texto(f_nombre_sub), case=False, na=False)]
            if f_status_sub != "Todos": df_filtrado_sub = df_filtrado_sub[df_filtrado_sub['status'] == f_status_sub]
            
            col_mostrar_sub = ['suscripcion_id', 'nombre', 'status', 'fecha_pago', 'metodo_entrega', 'generos_preferencia', 'valor_suscripcion']
            df_mostrar_sub = df_filtrado_sub[col_mostrar_sub].copy()
            df_mostrar_sub['valor_suscripcion'] = pd.to_numeric(df_mostrar_sub['valor_suscripcion'], errors='coerce').fillna(0.0)
            
            if 'suscripciones_original' not in st.session_state or not st.session_state.suscripciones_original.equals(df_mostrar_sub):
                st.session_state.suscripciones_original = df_mostrar_sub.copy()
            
            config_cols_sub = {
                "suscripcion_id": st.column_config.NumberColumn("ID", disabled=True),
                "nombre": st.column_config.TextColumn("Cliente", disabled=True),
                "status": st.column_config.TextColumn("Estado", disabled=True),
                "fecha_pago": st.column_config.TextColumn("Día de Pago (Ej: 05)"),
                "metodo_entrega": st.column_config.SelectboxColumn("Método", options=["Retiro en tienda", "Despacho a domicilio", "Starken", "Chilexpress", "Correos de Chile", "Acordar con vendedor", "Paket"]),
                "generos_preferencia": st.column_config.TextColumn("Géneros Favoritos"),
                "valor_suscripcion": st.column_config.NumberColumn("Valor Plan Base ($)", format="$%.0f", min_value=0.0)
            }
            
            st.caption("Doble clic para editar los planes, fechas o gustos.")
            df_editado_sub = st.data_editor(df_mostrar_sub, column_config=config_cols_sub, hide_index=True, use_container_width=True)
            
            if not df_mostrar_sub.equals(df_editado_sub):
                if st.button("💾 Guardar Cambios de Planes", type="primary"):
                    with st.spinner("Actualizando planes..."):
                        num = actualizar_suscripciones_batch(df_editado_sub)
                        st.success(f"¡Se actualizaron {num} planes!")
                        st.rerun()

    # =======================================================
    # 3. FICHA INDIVIDUAL (HISTORIAL Y LIBRERO)
    # =======================================================
    elif opcion == "👤 Ficha Individual (Historial de Lectura)":
        st.markdown("### 👤 Ficha e Historial del Cliente")
        if not df_clientes.empty:
            
            # Selector inteligente: muestra ID, nombre y estado para ubicarlos fácil
            lista_clientes = [""] + df_clientes.apply(lambda x: f"ID:{x['cliente_id']} - {x['nombre']} ({x['status']})", axis=1).tolist()
            cliente_sel = st.selectbox("🔍 Buscar Cliente:", lista_clientes)
            
            if cliente_sel:
                c_id = int(cliente_sel.split(" - ")[0].replace("ID:", ""))
                datos_c = df_clientes[df_clientes['cliente_id'] == c_id].iloc[0]
                
                # Tarjeta de presentación bonita
                with st.container(border=True):
                    col_info1, col_info2 = st.columns(2)
                    col_info1.markdown(f"#### 👤 {datos_c['nombre']}")
                    col_info1.caption(f"**Email:** {datos_c.get('email', 'No registrado')}")
                    col_info1.caption(f"**Tel:** {datos_c.get('telefono', 'No registrado')}")
                    
                    estado_icono = "🟢" if datos_c.get('status') == "ACTIVA" else "🔴"
                    col_info2.markdown(f"**Estado:** {estado_icono} {datos_c.get('status', '-')}")
                    
                    # Intentar traer sus preferencias rápidamente
                    try:
                        conn = get_db_connection()
                        res_susc = conn.table("suscripciones").select("generos_preferencia").eq("cliente_id", c_id).execute()
                        if res_susc.data and res_susc.data[0].get('generos_preferencia'):
                            col_info2.caption(f"**Gustos:** {res_susc.data[0]['generos_preferencia']}")
                    except: pass

                # Historial de Lectura (El Librero)
                st.markdown("#### 📚 Librero (Historial de libros poseídos)")
                df_historial = cargar_historial_cliente(c_id)
                
                if df_historial.empty: 
                    st.info("Este cliente aún no tiene libros registrados en su historial.")
                else: 
                    st.success(f"El cliente posee **{len(df_historial)}** libros registrados.")
                    st.dataframe(df_historial, hide_index=True, use_container_width=True)