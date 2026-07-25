import streamlit as st
import pandas as pd
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=60)
def cargar_libros_caja():
    conn = get_db_connection()
    response = conn.table("libros").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def cargar_clientes():
    conn = get_db_connection()
    # Si la tabla no existe aún, esto evitará que la app se caiga
    try:
        response = conn.table("clientes").select("*").execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'correo', 'telefono'])

@st.cache_data(ttl=60)
def cargar_historial():
    conn = get_db_connection()
    try:
        # Traemos las ventas uniendo los nombres de libros y clientes
        response = conn.table("ventas").select("*, libros(titulo), clientes(nombre)").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['titulo_libro'] = df['libros'].apply(lambda x: x['titulo'] if isinstance(x, dict) else 'Desconocido')
            df['nombre_cliente'] = df['clientes'].apply(lambda x: x['nombre'] if isinstance(x, dict) else 'Desconocido')
        return df
    except:
        return pd.DataFrame(columns=['venta_id', 'fecha', 'cantidad', 'total', 'metodo_pago', 'titulo_libro', 'nombre_cliente'])

def gestionar_cliente(nombre, correo, telefono, cliente_id_existente=None):
    """Crea un cliente nuevo o actualiza uno existente si se rellenaron datos."""
    conn = get_db_connection()
    datos = {"nombre": limpiar_texto(nombre), "correo": limpiar_texto(correo), "telefono": limpiar_texto(telefono)}
    
    if cliente_id_existente:
        conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
        return cliente_id_existente
    else:
        response = conn.table("clientes").insert(datos).execute()
        return response.data[0]['cliente_id']

def gestionar_libro(titulo, autor, precio, stock_a_sumar, libro_id_existente=None):
    """Crea un libro rápido desde la caja o actualiza sus datos faltantes."""
    conn = get_db_connection()
    datos = {"titulo": limpiar_texto(titulo), "autor": limpiar_texto(autor), "precio": precio}
    
    if libro_id_existente:
        conn.table("libros").update(datos).eq("libro_id", libro_id_existente).execute()
        return libro_id_existente
    else:
        datos["stock"] = stock_a_sumar
        datos["precio_original"] = precio
        response = conn.table("libros").insert(datos).execute()
        return response.data[0]['libro_id']

def procesar_venta(libro_id, cliente_id, cantidad, total, metodo, stock_actual):
    """Registra la venta y descuenta el stock."""
    conn = get_db_connection()
    nuevo_stock = stock_actual - cantidad
    
    try:
        # 1. Registrar Venta
        datos_venta = {
            "libro_id": libro_id,
            "cliente_id": cliente_id,
            "cantidad": cantidad,
            "total": total,
            "metodo_pago": metodo,
            "fecha": datetime.now().isoformat()
        }
        conn.table("ventas").insert(datos_venta).execute()
        
        # 2. Descontar Stock
        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro_id).execute()
        
        # Limpiar cachés
        cargar_libros_caja.clear()
        cargar_clientes.clear()
        cargar_historial.clear()
        return True, ""
    except Exception as e:
        return False, str(e)


# --- INTERFAZ PRINCIPAL ---

def mostrar_caja():
    st.title("🛒 Caja y Ventas Rápidas")
    
    df_libros = cargar_libros_caja()
    df_clientes = cargar_clientes()

    tab_venta, tab_historial = st.tabs(["🛒 Nueva Venta", "📜 Historial"])

    # ==========================================
    # PESTAÑA 1: NUEVA VENTA (MÓVIL FRIENDLY)
    # ==========================================
    with tab_venta:
        st.markdown("### 1️⃣ Datos del Cliente")
        modo_cliente = st.radio("Selecciona opción:", ["👤 Buscar Existente", "➕ Cliente Nuevo"], horizontal=True, label_visibility="collapsed")
        
        c_id, c_nombre, c_correo, c_telefono = None, "", "", ""
        
        if modo_cliente == "👤 Buscar Existente":
            if not df_clientes.empty:
                lista_nombres_c = [""] + df_clientes['nombre'].tolist()
                sel_cliente = st.selectbox("Buscar cliente por nombre:", lista_nombres_c)
                if sel_cliente:
                    datos_c = df_clientes[df_clientes['nombre'] == sel_cliente].iloc[0]
                    c_id = int(datos_c['cliente_id'])
                    
                    with st.expander("✏️ Ver / Completar datos del cliente", expanded=False):
                        st.caption("Si falta un dato, rellénalo aquí y se guardará automáticamente con la venta.")
                        c_nombre = st.text_input("Nombre:", value=datos_c['nombre'], key="c_nom")
                        c_correo = st.text_input("Correo:", value=datos_c.get('correo', ''), key="c_cor")
                        c_telefono = st.text_input("Teléfono:", value=datos_c.get('telefono', ''), key="c_tel")
            else:
                st.warning("No hay clientes registrados aún.")
        else:
            with st.container(border=True):
                c_nombre = st.text_input("Nombre del nuevo cliente:")
                col1, col2 = st.columns(2)
                c_correo = col1.text_input("Correo (Opcional):")
                c_telefono = col2.text_input("Teléfono (Opcional):")

        st.markdown("---")
        st.markdown("### 2️⃣ Datos del Libro")
        modo_libro = st.radio("Selecciona opción:", ["📚 Buscar Existente", "➕ Libro Rápido (No en catálogo)"], horizontal=True, label_visibility="collapsed")
        
        l_id, l_titulo, l_autor, l_precio, l_stock_actual = None, "", "", 0.0, 0
        
        if modo_libro == "📚 Buscar Existente":
            if not df_libros.empty:
                lista_titulos_l = [""] + df_libros['titulo'].tolist()
                sel_libro = st.selectbox("Buscar libro por título:", lista_titulos_l)
                if sel_libro:
                    datos_l = df_libros[df_libros['titulo'] == sel_libro].iloc[0]
                    l_id = int(datos_l['libro_id'])
                    l_stock_actual = int(datos_l['stock'])
                    
                    with st.expander("✏️ Ver / Completar datos del libro", expanded=True):
                        l_titulo = st.text_input("Título:", value=datos_l['titulo'], disabled=True)
                        l_autor = st.text_input("Autor:", value=datos_l.get('autor', ''))
                        
                        col3, col4 = st.columns(2)
                        col3.metric("Stock Disponible", l_stock_actual)
                        l_precio = col4.number_input("Precio ($):", value=float(datos_l['precio']), step=100.0)
            else:
                st.warning("El inventario está vacío.")
        else:
            with st.container(border=True):
                st.caption("Usa esto para vender un libro que no habías ingresado al sistema. Se agregará al inventario automáticamente.")
                l_titulo = st.text_input("Título del libro:")
                l_autor = st.text_input("Autor (Opcional):")
                l_precio = st.number_input("Precio ($):", min_value=0.0, step=100.0)
                l_stock_actual = 1 # Asumimos que hay al menos 1 si lo está vendiendo

        st.markdown("---")
        st.markdown("### 3️⃣ Detalle y Pago")
        col5, col6 = st.columns(2)
        cantidad = col5.number_input("Cantidad a vender:", min_value=1, max_value=max(1, l_stock_actual), step=1)
        metodo_pago = col6.selectbox("Método de Pago:", ["Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Transferencia"])
        
        total_pagar = float(l_precio) * cantidad
        
        # Caja de Total Dinámica
        st.markdown(f"""
        <div style="background-color: #E6F3E6; border: 2px solid #4CAF50; padding: 15px; border-radius: 10px; text-align: center;">
            <h2 style="color: #2E7D32; margin:0;">Total a Pagar: ${total_pagar:,.0f}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("") # Espaciador
        
        # VALIDACIONES Y BOTÓN DE VENTA
        if st.button("✅ CONFIRMAR VENTA", type="primary", use_container_width=True):
            if not c_nombre:
                st.error("⚠️ Debes ingresar o seleccionar el nombre del cliente.")
            elif not l_titulo:
                st.error("⚠️ Debes ingresar o seleccionar un libro.")
            elif cantidad > l_stock_actual and modo_libro == "📚 Buscar Existente":
                st.error("⚠️ No hay suficiente stock para realizar esta venta.")
            else:
                with st.spinner("Procesando..."):
                    # 1. Gestionar Cliente (Crear o Actualizar info faltante)
                    final_cliente_id = gestionar_cliente(c_nombre, c_correo, c_telefono, c_id)
                    
                    # 2. Gestionar Libro
                    final_libro_id = gestionar_libro(l_titulo, l_autor, l_precio, cantidad, l_id)
                    
                    # 3. Registrar Venta
                    exito, err = procesar_venta(final_libro_id, final_cliente_id, cantidad, total_pagar, metodo_pago, l_stock_actual)
                    
                    if exito:
                        st.success("🎉 ¡Venta registrada con éxito!")
                        st.balloons()
                        # Refrescar la página para limpiar los campos
                        st.rerun()
                    else:
                        st.error(f"Error al registrar: {err}")

    # ==========================================
    # PESTAÑA 2: HISTORIAL Y FILTROS
    # ==========================================
    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = cargar_historial()
        
        if df_ventas.empty:
            st.info("Aún no hay ventas registradas en el sistema.")
        else:
            with st.expander("🔍 Filtros de Historial", expanded=False):
                f_cliente = st.selectbox("Filtrar por Cliente:", ["Todos"] + df_ventas['nombre_cliente'].unique().tolist())
                f_metodo = st.selectbox("Filtrar por Método de Pago:", ["Todos"] + df_ventas['metodo_pago'].unique().tolist())
            
            df_hist_filtrado = df_ventas.copy()
            if f_cliente != "Todos":
                df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['nombre_cliente'] == f_cliente]
            if f_metodo != "Todos":
                df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['metodo_pago'] == f_metodo]
            
            # Tarjetas de resumen métrico
            total_recaudado = df_hist_filtrado['total'].sum()
            total_libros_vendidos = df_hist_filtrado['cantidad'].sum()
            
            c_res1, c_res2 = st.columns(2)
            c_res1.metric("Recaudación", f"${total_recaudado:,.0f}")
            c_res2.metric("Libros Vendidos", total_libros_vendidos)
            
            st.markdown("---")
            # Mostrar la tabla limpia
            columnas_mostrar = ['fecha', 'titulo_libro', 'nombre_cliente', 'cantidad', 'total', 'metodo_pago']
            # Formatear fecha para que sea legible
            df_hist_filtrado['fecha'] = pd.to_datetime(df_hist_filtrado['fecha']).dt.strftime('%d-%m-%Y %H:%M')
            
            st.dataframe(df_hist_filtrado[columnas_mostrar], hide_index=True, use_container_width=True)