import streamlit as st
import pandas as pd
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=60)
def cargar_libros_caja():
    conn = get_db_connection()
    response = conn.table("libros").select("libro_id, titulo, autor, precio, stock").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def cargar_clientes():
    conn = get_db_connection()
    try:
        response = conn.table("clientes").select("cliente_id, nombre, email, telefono").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error al cargar clientes: {e}")
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'email', 'telefono'])

@st.cache_data(ttl=60)
def cargar_historial():
    """Carga el historial desde la tabla correcta: registro_ventas"""
    conn = get_db_connection()
    try:
        response = conn.table("registro_ventas").select("*, clientes(nombre)").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['nombre_cliente'] = df['clientes'].apply(lambda x: x['nombre'] if isinstance(x, dict) else 'Sin Cliente')
        return df
    except:
        return pd.DataFrame(columns=['venta_id', 'fecha_venta', 'libros_vendidos', 'subtotal_libros', 'valor_envio', 'monto_final', 'metodo_envio', 'comentario', 'nombre_cliente'])

def gestionar_cliente(nombre, correo, telefono, cliente_id_existente=None):
    if not nombre: return None
    conn = get_db_connection()
    datos = {"nombre": limpiar_texto(nombre), "email": limpiar_texto(correo), "telefono": limpiar_texto(telefono)}
    try:
        if cliente_id_existente:
            conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
            return cliente_id_existente
        else:
            response = conn.table("clientes").insert(datos).execute()
            cargar_clientes.clear()
            return response.data[0]['cliente_id']
    except Exception as e:
        st.error(f"Error al guardar el cliente: {e}")
        return None

def gestionar_libro(titulo, autor, precio_catalogo, stock_a_sumar, libro_id_existente=None):
    conn = get_db_connection()
    datos = {"titulo": limpiar_texto(titulo), "autor": limpiar_texto(autor), "precio": precio_catalogo}
    if libro_id_existente:
        conn.table("libros").update(datos).eq("libro_id", libro_id_existente).execute()
        return libro_id_existente
    else:
        datos["stock"] = stock_a_sumar
        datos["precio_original"] = precio_catalogo
        response = conn.table("libros").insert(datos).execute()
        cargar_libros_caja.clear()
        return response.data[0]['libro_id']

def procesar_venta(libro_id, titulo_libro, autor_libro, cliente_id, cantidad, subtotal, valor_envio, monto_final, metodo_envio, metodo_pago, stock_actual):
    """Registra la venta, descuenta stock y ACTUALIZA EL LIBRERO HISTÓRICO."""
    conn = get_db_connection()
    nuevo_stock = stock_actual - cantidad
    
    try:
        # 1. Registrar venta
        datos_venta = {
            "cliente_id": cliente_id,
            "fecha_venta": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "libros_vendidos": f"{cantidad} x {titulo_libro}",
            "subtotal_libros": float(subtotal),
            "valor_envio": float(valor_envio),
            "monto_final": float(monto_final),
            "metodo_envio": metodo_envio,
            "comentario": f"Pago: {metodo_pago}"
        }
        conn.table("registro_ventas").insert(datos_venta).execute()
        
        # 2. Descontar stock del catálogo
        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro_id).execute()

        # 3. AGREGAR AL LIBRERO HISTÓRICO DEL CLIENTE
        if cliente_id and libro_id:
            # Revisamos si ya lo tiene para no romper la regla "unique_cliente_libro"
            res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", libro_id).execute()
            
            if not res_hist.data: # Si no lo tiene, se lo agregamos
                datos_historico = {
                    "cliente_id": cliente_id,
                    "libro_id": libro_id,
                    "autor_historico": limpiar_texto(autor_libro),
                    "origen": "Venta Caja"
                }
                conn.table("librero_historico").insert(datos_historico).execute()
        
        cargar_libros_caja.clear()
        cargar_clientes.clear()
        cargar_historial.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

def anular_venta(venta_id, texto_libros_vendidos):
    conn = get_db_connection()
    try:
        partes = texto_libros_vendidos.split(" x ", 1)
        if len(partes) == 2:
            cantidad_devuelta = int(partes[0])
            titulo_libro = partes[1]
            
            res_l = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_libro).execute()
            if res_l.data:
                l_id = res_l.data[0]['libro_id']
                nuevo_stock = res_l.data[0]['stock'] + cantidad_devuelta
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
                
        conn.table("registro_ventas").delete().eq("venta_id", venta_id).execute()
        cargar_historial.clear()
        cargar_libros_caja.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

# --- INTERFAZ DE CAJA ---

def mostrar_caja():
    st.title("🛒 Caja y Ventas Rápidas")
    
    df_libros = cargar_libros_caja()
    df_clientes = cargar_clientes()

    tab_venta, tab_historial, tab_anular = st.tabs(["🛒 Nueva Venta", "📜 Historial", "🚫 Anular Venta"])

    with tab_venta:
        st.markdown("### 1️⃣ Datos del Cliente")
        modo_cliente = st.radio("Cliente:", ["👤 Buscar Existente", "➕ Nuevo"], horizontal=True, label_visibility="collapsed")
        c_id, c_nombre, c_correo, c_telefono = None, "", "", ""
        
        if modo_cliente == "👤 Buscar Existente":
            if not df_clientes.empty:
                lista_nombres_c = [""] + df_clientes['nombre'].tolist()
                sel_cliente = st.selectbox("Buscar cliente:", lista_nombres_c)
                if sel_cliente:
                    datos_c = df_clientes[df_clientes['nombre'] == sel_cliente].iloc[0]
                    c_id = int(datos_c['cliente_id'])
                    with st.expander("✏️ Ver / Completar datos", expanded=False):
                        c_nombre = st.text_input("Nombre:", value=datos_c['nombre'])
                        c_correo = st.text_input("Correo:", value=datos_c.get('email', ''))
                        c_telefono = st.text_input("Teléfono:", value=datos_c.get('telefono', ''))
            else: st.warning("No hay clientes registrados.")
        else:
            with st.container(border=True):
                c_nombre = st.text_input("Nombre del nuevo cliente:")
                col1, col2 = st.columns(2)
                c_correo = col1.text_input("Correo (Opcional):")
                c_telefono = col2.text_input("Teléfono (Opcional):")

        st.markdown("---")
        st.markdown("### 2️⃣ Datos del Libro")
        modo_libro = st.radio("Libro:", ["📚 Buscar Existente", "➕ Rápido"], horizontal=True, label_visibility="collapsed")
        l_id, l_titulo, l_autor, l_precio_catalogo, l_stock_actual = None, "", "", 0.0, 0
        
        if modo_libro == "📚 Buscar Existente":
            if not df_libros.empty:
                lista_titulos_l = [""] + df_libros['titulo'].tolist()
                sel_libro = st.selectbox("Buscar libro:", lista_titulos_l)
                if sel_libro:
                    datos_l = df_libros[df_libros['titulo'] == sel_libro].iloc[0]
                    l_id = int(datos_l['libro_id'])
                    l_stock_actual = int(datos_l['stock'])
                    l_titulo = datos_l['titulo']
                    l_precio_catalogo = float(datos_l['precio'])
                    
                    with st.expander("✏️ Actualizar Catálogo (Opcional)", expanded=False):
                        l_autor = st.text_input("Autor:", value=datos_l.get('autor', ''))
                        l_precio_cat_nuevo = st.number_input("Precio Oficial ($):", value=l_precio_catalogo, step=100.0)
                        l_precio_catalogo = l_precio_cat_nuevo
            else: st.warning("El inventario está vacío.")
        else:
            with st.container(border=True):
                l_titulo = st.text_input("Título del libro:")
                l_autor = st.text_input("Autor (Opcional):")
                l_precio_catalogo = st.number_input("Precio Oficial ($):", min_value=0.0, step=100.0)
                l_stock_actual = 1

        st.markdown("---")
        st.markdown("### 3️⃣ Detalle, Envío y Pago")
        
        col_p1, col_p2 = st.columns(2)
        precio_a_cobrar = col_p1.number_input("Precio Especial a Cobrar ($):", value=float(l_precio_catalogo), step=500.0)
        cantidad = col_p2.number_input("Cantidad a vender:", min_value=1, max_value=max(1, l_stock_actual), step=1)
        
        subtotal = precio_a_cobrar * cantidad
        
        st.write("**Opciones de Envío**")
        col_e1, col_e2 = st.columns(2)
        modo_envio = col_e1.selectbox("Método:", ["Retiro en tienda", "Despacho a domicilio", "Starken", "Chilexpress", "Correos de Chile", "Acordar con vendedor"])
        
        valor_envio = 0.0
        if modo_envio != "Retiro en tienda":
            valor_envio = col_e2.number_input("Costo de Envío ($):", min_value=0.0, step=500.0)
            
        monto_final = subtotal + valor_envio
        metodo_pago = st.selectbox("Método de Pago:", ["Transferencia", "Efectivo", "Tarjeta Débito", "Tarjeta Crédito"])
        
        st.markdown(f"""
        <div style='background-color:#E6F3E6; border:2px solid #4CAF50; padding:15px; border-radius:10px; text-align:center; margin-top:10px;'>
            <p style='color:#2E7D32; margin:0; font-size:1.1em'>Subtotal Libros: ${subtotal:,.0f} | Envío: ${valor_envio:,.0f}</p>
            <h2 style='color:#2E7D32; margin:0;'>MONTO FINAL: ${monto_final:,.0f}</h2>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        
        if st.button("✅ CONFIRMAR VENTA", type="primary", use_container_width=True):
            if not c_nombre: st.error("⚠️ Falta el cliente.")
            elif not l_titulo: st.error("⚠️ Falta el libro.")
            elif cantidad > l_stock_actual and modo_libro == "📚 Buscar Existente": st.error("⚠️ No hay stock suficiente.")
            else:
                with st.spinner("Procesando..."):
                    final_cliente_id = gestionar_cliente(c_nombre, c_correo, c_telefono, c_id)
                    final_libro_id = gestionar_libro(l_titulo, l_autor, l_precio_catalogo, cantidad, l_id)
                    
                    # PASAMOS l_autor A LA FUNCIÓN PARA QUE LO GUARDE EN EL HISTÓRICO
                    exito, err = procesar_venta(final_libro_id, l_titulo, l_autor, final_cliente_id, cantidad, subtotal, valor_envio, monto_final, modo_envio, metodo_pago, l_stock_actual)
                    if exito: st.success("🎉 ¡Venta registrada y agregada al histórico del cliente!"), st.balloons(), st.rerun()
                    else: st.error(f"Error: {err}")

    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = cargar_historial()
        
        if df_ventas.empty:
            st.info("Aún no hay ventas registradas.")
        else:
            with st.expander("🔍 Filtros de Historial", expanded=False):
                col_h1, col_h2 = st.columns(2)
                f_cliente = col_h1.selectbox("Cliente:", ["Todos"] + df_ventas['nombre_cliente'].unique().tolist())
                f_envio = col_h2.selectbox("Envío:", ["Todos"] + df_ventas['metodo_envio'].unique().tolist())
            
            df_hist_filtrado = df_ventas.copy()
            if f_cliente != "Todos": df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['nombre_cliente'] == f_cliente]
            if f_envio != "Todos": df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['metodo_envio'] == f_envio]
            
            total_recaudado = df_hist_filtrado['monto_final'].sum()
            
            st.metric("Total Recaudado (con envíos)", f"${total_recaudado:,.0f}")
            st.markdown("---")
            
            columnas_mostrar = ['fecha_venta', 'libros_vendidos', 'nombre_cliente', 'monto_final', 'metodo_envio', 'comentario']
            st.dataframe(df_hist_filtrado[columnas_mostrar], hide_index=True, use_container_width=True)

    with tab_anular:
        st.markdown("### 🚫 Anular Venta y Restaurar Stock")
        st.warning("⚠️ Al anular una venta, el registro se borra y el stock del libro se restaura en el catálogo.")
        df_ventas = cargar_historial()
        if df_ventas.empty:
            st.info("No hay ventas para anular.")
        else:
            df_ventas['etiqueta_anular'] = df_ventas.apply(
                lambda row: f"ID: {row['venta_id']} | {row['fecha_venta']} | {row['libros_vendidos']} | ${row['monto_final']:,.0f}", axis=1)
            lista_ventas_anular = [""] + df_ventas.sort_values('venta_id', ascending=False)['etiqueta_anular'].tolist()
            
            venta_seleccionada = st.selectbox("Selecciona la venta a anular:", lista_ventas_anular)
            if venta_seleccionada:
                venta_a_anular = df_ventas[df_ventas['etiqueta_anular'] == venta_seleccionada].iloc[0]
                
                if st.button("🟥 CONFIRMAR ANULACIÓN", type="primary", use_container_width=True):
                    with st.spinner("Anulando y restaurando stock..."):
                        exito, error = anular_venta(
                            venta_id=int(venta_a_anular['venta_id']),
                            texto_libros_vendidos=venta_a_anular['libros_vendidos']
                        )
                        if exito: st.success("¡Venta anulada con éxito!"), st.rerun()
                        else: st.error(f"Error al anular: {error}")