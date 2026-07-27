import streamlit as st
import pandas as pd
from datetime import datetime
import json

from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS ---
@st.cache_data(ttl=60)
def cargar_libros_caja():
    """Carga los libros con su información esencial para la venta."""
    conn = get_db_connection()
    try:
        response = conn.table("libros").select("libro_id, titulo, autor, precio, stock").execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error cargando libros para la caja: {e}")
        return pd.DataFrame()
    
@st.cache_data(ttl=60)
def cargar_historial():
    """
    Carga el historial de ventas y procesa la columna 'libros_vendidos'
    para que sea legible, ya sea en formato de texto antiguo o en JSON nuevo.
    """
    conn = get_db_connection()
    try:
        res_ventas = conn.table("registro_ventas").select("*").order("venta_id", desc=True).execute()
        if not res_ventas.data:
            return pd.DataFrame()

        df_ventas = pd.DataFrame(res_ventas.data)
        
        # --- LÓGICA INTELIGENTE DE VISUALIZACIÓN ---
        def formatear_libros(libros_data):
            if not isinstance(libros_data, str) or not libros_data.strip():
                return "Sin Detalle"
            
            # Intenta leerlo como JSON
            if libros_data.strip().startswith('['):
                try:
                    lista_libros = json.loads(libros_data)
                    # Extrae "cantidad x titulo" de cada libro en el JSON
                    return " | ".join([f"{item.get('cantidad', 1)} x {item.get('titulo', 'N/A')}" for item in lista_libros])
                except json.JSONDecodeError:
                    # Si falla el parseo de JSON, devuelve el texto original
                    return libros_data
            else:
                # Si no es un JSON, es el formato de texto antiguo, lo devolvemos tal cual
                return libros_data

        df_ventas['libros_vendidos'] = df_ventas['libros_vendidos'].apply(formatear_libros)
        # ----------------------------------------------

        # Unir con nombres de clientes
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        if res_clientes.data:
            df_clientes = pd.DataFrame(res_clientes.data)
            df_ventas = df_ventas.merge(df_clientes, on='cliente_id', how='left')
            df_ventas.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
            df_ventas['nombre_cliente'] = df_ventas['nombre_cliente'].fillna('Cliente Eliminado')
        else:
            df_ventas['nombre_cliente'] = 'Sin Cliente'
            
        return df_ventas
    except Exception as e:
        st.error(f"Error cargando historial: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_clientes():
    conn = get_db_connection()
    try:
        response = conn.table("clientes").select("cliente_id, nombre, email, telefono, status").execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'email', 'telefono', 'status'])

@st.cache_data(ttl=60)
def cargar_historial():
    conn = get_db_connection()
    try:
        res_ventas = conn.table("registro_ventas").select("*").execute()
        df_ventas = pd.DataFrame(res_ventas.data)
        if df_ventas.empty: return pd.DataFrame()
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        df_clientes = pd.DataFrame(res_clientes.data)
        if not df_clientes.empty:
            df_ventas = df_ventas.merge(df_clientes, on='cliente_id', how='left')
            df_ventas.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
            df_ventas['nombre_cliente'] = df_ventas['nombre_cliente'].fillna('Sin Cliente')
        else:
            df_ventas['nombre_cliente'] = 'Sin Cliente'
        return df_ventas
    except:
        return pd.DataFrame()

def verificar_estado_cliente(cliente_id):
    conn = get_db_connection()
    try:
        res = conn.table("suscripciones").select("suscripcion_id").eq("cliente_id", cliente_id).execute()
        if res.data and len(res.data) > 0: return "SUSCRITO"
        return "CLIENTE REGULAR"
    except: return "CLIENTE REGULAR"

def gestionar_cliente(nombre, correo, telefono, cliente_id_existente=None):
    if not nombre: return None
    conn = get_db_connection()
    datos = {"nombre": limpiar_texto(nombre), "email": limpiar_texto(correo), "telefono": limpiar_texto(telefono)}
    try:
        if cliente_id_existente:
            datos["status"] = verificar_estado_cliente(cliente_id_existente)
            conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
            return cliente_id_existente
        else:
            datos["status"] = "CLIENTE REGULAR"
            response = conn.table("clientes").insert(datos).execute()
            cargar_clientes.clear()
            return response.data[0]['cliente_id']
    except: return None

def gestionar_libro(titulo, autor, precio_catalogo, stock_a_sumar, libro_id_existente=None):
    conn = get_db_connection()
    datos = {"titulo": limpiar_texto(titulo), "autor": limpiar_texto(autor), "precio": float(precio_catalogo)}
    if libro_id_existente:
        conn.table("libros").update(datos).eq("libro_id", libro_id_existente).execute()
        return libro_id_existente
    else:
        datos["stock"] = int(stock_a_sumar)
        datos["precio_original"] = float(precio_catalogo)
        response = conn.table("libros").insert(datos).execute()
        cargar_libros_caja.clear()
        return response.data[0]['libro_id']
    
def procesar_venta_carrito(carrito, cliente_id, valor_envio, metodo_envio, metodo_pago, comentario, fecha_venta):
    conn = get_db_connection()
    texto_libros = " | ".join([f"{item['cantidad']} x {item['titulo'].upper()}" for item in carrito])
    subtotal_libros = sum([item['subtotal'] for item in carrito])
    monto_final = subtotal_libros + valor_envio
    try:
        datos_venta = {
            "cliente_id": cliente_id, "fecha_venta": fecha_venta.strftime("%Y-%m-%d %H:%M:%S"),
            "libros_vendidos": texto_libros, "subtotal_libros": float(subtotal_libros),
            "valor_envio": float(valor_envio), "monto_final": float(monto_final),
            "metodo_envio": metodo_envio, "comentario": f"Pago: {metodo_pago}. {comentario}".strip()
        }
        conn.table("registro_ventas").insert(datos_venta).execute()
        for item in carrito:
            l_id = item['libro_id']
            if item['es_nuevo']: l_id = gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], item['cantidad'], None)
            else:
                gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], 0, l_id)
                nuevo_stock = item['stock_actual'] - item['cantidad']
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()

            if cliente_id and l_id:
                res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", l_id).execute()
                if not res_hist.data:
                    datos_historico = {"cliente_id": cliente_id, "libro_id": l_id, "autor_historico": limpiar_texto(item['autor']), "origen": "VENTA CAJA"}
                    conn.table("librero_historico").insert(datos_historico).execute()
        
        st.session_state.carrito_caja = []
        cargar_libros_caja.clear()
        cargar_clientes.clear()
        cargar_historial.clear()
        return True, ""
    except Exception as e: return False, str(e)

def anular_venta(venta_id, texto_libros_vendidos):
    conn = get_db_connection()
    try:
        items = texto_libros_vendidos.split(" | ")
        for item in items:
            partes = item.split(" x ", 1)
            if len(partes) == 2:
                cantidad_devuelta, titulo_libro = int(partes[0].strip()), partes[1].strip()
                res_l = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_libro).execute()
                if res_l.data:
                    l_id, nuevo_stock = res_l.data[0]['libro_id'], res_l.data[0]['stock'] + cantidad_devuelta
                    conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
        conn.table("registro_ventas").delete().eq("venta_id", venta_id).execute()
        cargar_historial.clear()
        cargar_libros_caja.clear()
        return True, ""
    except Exception as e: return False, str(e)

def actualizar_historial_batch(df_editado):
    df_original = st.session_state.get('historial_original')
    if df_original is None: return 0
    df_original_comp = df_original.set_index('venta_id')
    df_editado_comp = df_editado.set_index('venta_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    if filas_cambiadas.empty: return 0
    conn = get_db_connection()
    updates = 0
    for venta_id, row in filas_cambiadas.iterrows():
        try:
            datos = {"valor_envio": float(row['valor_envio']), "monto_final": float(row['monto_final']), "metodo_envio": str(row['metodo_envio']), "comentario": str(row['comentario'])}
            conn.table("registro_ventas").update(datos).eq("venta_id", venta_id).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_historial.clear()
    return updates

# --- INTERFAZ DE CAJA ---

def mostrar_caja():
    if 'carrito_caja' not in st.session_state:
        st.session_state.carrito_caja = []

    st.title("🛒 Caja y Ventas Rápidas")
    
    df_libros = cargar_libros_caja()
    df_clientes = cargar_clientes()

    tab_venta, tab_historial, tab_anular = st.tabs(["🛒 Nueva Venta", "📜 Historial Editable", "🚫 Anular Venta"])

    with tab_venta:
        st.markdown("### 1️⃣ Datos del Cliente")
        modo_cliente = st.radio("Cliente:", ["👤 Buscar Existente", "➕ Nuevo"], horizontal=True, label_visibility="collapsed")
        c_id, c_nombre, c_correo, c_telefono = None, "", "", ""
        if modo_cliente == "👤 Buscar Existente":
            if not df_clientes.empty:
                sel_cliente = st.selectbox("Buscar cliente:", [""] + df_clientes['nombre'].tolist())
                if sel_cliente:
                    datos_c = df_clientes[df_clientes['nombre'] == sel_cliente].iloc[0]
                    c_id = int(datos_c['cliente_id'])
                    with st.expander(f"✏️ Ver datos (Status: {datos_c.get('status', 'REGULAR')})", expanded=False):
                        c_nombre = st.text_input("Nombre:", value=datos_c['nombre'])
                        c_correo = st.text_input("Correo:", value=datos_c.get('email', ''))
                        c_telefono = st.text_input("Teléfono:", value=datos_c.get('telefono', ''))
            else: st.warning("No hay clientes registrados.")
        else:
            with st.container(border=True):
                c_nombre = st.text_input("Nombre del nuevo cliente:")
                c_correo = st.text_input("Correo (Opcional):")
                c_telefono = st.text_input("Teléfono (Opcional):")

        st.markdown("---")
        st.markdown("### 2️⃣ Añadir Libros al Carrito")
        with st.container(border=True):
            modo_libro = st.radio("Libro:", ["📚 Buscar Existente", "➕ Rápido (No en catálogo)"], horizontal=True, label_visibility="collapsed")
            l_id, l_titulo, l_autor, l_precio_catalogo, l_stock_actual, es_nuevo = None, "", "", 0.0, 0, False
            if modo_libro == "📚 Buscar Existente":
                if not df_libros.empty:
                    sel_libro = st.selectbox("Buscar libro:", [""] + df_libros['titulo'].tolist())
                    if sel_libro:
                        datos_l = df_libros[df_libros['titulo'] == sel_libro].iloc[0]
                        l_id, l_stock_actual, l_titulo, l_precio_catalogo, l_autor = int(datos_l['libro_id']), int(datos_l['stock']), datos_l['titulo'], float(datos_l['precio']), datos_l.get('autor', '')
                        with st.expander("✏️ Actualizar Catálogo (Opcional)", expanded=False):
                            l_autor = st.text_input("Autor:", value=l_autor)
                            l_precio_catalogo = st.number_input("Precio Oficial ($):", value=l_precio_catalogo, step=100.0)
                else: st.warning("El inventario está vacío.")
            else:
                es_nuevo = True
                l_titulo = st.text_input("Título del libro:")
                l_autor = st.text_input("Autor (Opcional):")
                l_precio_catalogo = st.number_input("Precio Oficial ($):", min_value=0.0, step=100.0)
                l_stock_actual = 999 
            
            st.markdown("👇 **Precio Especial y Cantidad para esta venta**")
            col_c1, col_c2 = st.columns(2)
            precio_a_cobrar = col_c1.number_input("Precio a Cobrar ($):", value=float(l_precio_catalogo), step=500.0)
            cantidad = col_c2.number_input("Cantidad:", min_value=1, max_value=max(1, l_stock_actual), step=1)
            
            libro_sin_stock = l_stock_actual <= 0 and not es_nuevo
            if libro_sin_stock:
                st.warning("⚠️ Atención: Estás vendiendo un libro sin stock físico (venta por encargo).")
            # ---------------------------------------------
            
            if st.button("➕ AÑADIR AL CARRITO", use_container_width=True):
                if not l_titulo: 
                    st.error("Debes seleccionar un libro.")
                else:
                    st.session_state.carrito_caja.append({
                        'libro_id': l_id, 'titulo': l_titulo, 'autor': l_autor, 'precio_catalogo': l_precio_catalogo,
                        'precio_cobrado': precio_a_cobrar, 'cantidad': cantidad, 'subtotal': precio_a_cobrar * cantidad,
                        'stock_actual': l_stock_actual, 'es_nuevo': es_nuevo
                    })
                    st.success(f"{l_titulo} añadido.")
                    st.rerun()

        subtotal_carrito = 0
        if len(st.session_state.carrito_caja) > 0:
            st.markdown("#### 🛒 Tu Carrito Actual")
            df_carrito = pd.DataFrame(st.session_state.carrito_caja)
            st.dataframe(df_carrito[['cantidad', 'titulo', 'precio_cobrado', 'subtotal']], hide_index=True, use_container_width=True)
            subtotal_carrito = df_carrito['subtotal'].sum()
            if st.button("🗑️ Vaciar Carrito"):
                st.session_state.carrito_caja = []
                st.rerun()

        st.markdown("---")
        st.markdown("### 3️⃣ Envío, Pago y Confirmación")
        fecha_venta_manual = st.date_input("Fecha de la Venta:", value=datetime.now())
        col_e1, col_e2 = st.columns(2)
        modo_envio = col_e1.selectbox("Modo de Envío:", ["Retiro en tienda", "Despacho a domicilio", "Starken", "Chilexpress", "Correos de Chile", "Acordar con vendedor"])
        valor_envio = col_e2.number_input("Costo de Envío ($):", min_value=0.0, step=500.0) if modo_envio != "Retiro en tienda" else 0.0
            
        metodo_pago = st.selectbox("Método de Pago:", ["Transferencia", "Efectivo", "Tarjeta Débito", "Tarjeta Crédito"])
        comentario_venta = st.text_area("Comentario (Opcional):", placeholder="Ej: Entregar por conserjería...")
        
        monto_final = subtotal_carrito + valor_envio
        st.markdown(f"<div style='background-color:#E6F3E6; border:2px solid #4CAF50; padding:15px; border-radius:10px; text-align:center;'><p style='color:#2E7D32; margin:0;'>Subtotal Libros: ${subtotal_carrito:,.0f} | Envío: ${valor_envio:,.0f}</p><h2 style='color:#2E7D32; margin:0;'>MONTO FINAL: ${monto_final:,.0f}</h2></div>", unsafe_allow_html=True)
        st.write("")
        
        if st.button("✅ CONFIRMAR VENTA TOTAL", type="primary", use_container_width=True):
            if not c_nombre: st.error("⚠️ Falta el cliente.")
            elif len(st.session_state.carrito_caja) == 0: st.error("⚠️ El carrito está vacío.")
            else:
                with st.spinner("Procesando Venta..."):
                    final_cliente_id = gestionar_cliente(c_nombre, c_correo, c_telefono, c_id)
                    exito, err = procesar_venta_carrito(st.session_state.carrito_caja, final_cliente_id, valor_envio, modo_envio, metodo_pago, comentario_venta, fecha_venta_manual)
                    if exito: st.success("🎉 ¡Venta registrada!"), st.balloons(), st.rerun()
                    else: st.error(f"Error: {err}")

    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = cargar_historial()
        if df_ventas.empty: st.info("Aún no hay ventas registradas.")
        else:
            df_ventas['comentario'], df_ventas['metodo_envio'] = df_ventas['comentario'].fillna(""), df_ventas['metodo_envio'].fillna("")
            columnas_hist = ['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'subtotal_libros', 'valor_envio', 'monto_final', 'metodo_envio', 'comentario']
            for col in columnas_hist: 
                if col not in df_ventas.columns: df_ventas[col] = ""
            df_mostrar = df_ventas[columnas_hist].copy()
            if 'historial_original' not in st.session_state or not st.session_state.historial_original.equals(df_mostrar):
                st.session_state.historial_original = df_mostrar.copy()
            st.caption("Doble clic en celdas para modificar Envío, Monto, Método o Comentario.")
            df_editado = st.data_editor(df_mostrar, disabled=['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'subtotal_libros'], use_container_width=True, hide_index=True)
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Historial", type="primary"):
                    num = actualizar_historial_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} registros!"), st.rerun()

    with tab_anular:
        st.markdown("### 🚫 Anular Venta y Restaurar Stock")
        df_ventas = cargar_historial()
        if not df_ventas.empty:
            df_ventas['etiqueta_anular'] = df_ventas.apply(lambda row: f"ID: {row.get('venta_id','')} | {row.get('fecha_venta','')} | {row.get('libros_vendidos','')} | ${row.get('monto_final',0):,.0f}", axis=1)
            venta_sel = st.selectbox("Selecciona la venta:", [""] + df_ventas.sort_values('venta_id', ascending=False)['etiqueta_anular'].tolist())
            if venta_sel:
                venta_a_anular = df_ventas[df_ventas['etiqueta_anular'] == venta_sel].iloc[0]
                if st.button("🟥 CONFIRMAR ANULACIÓN", type="primary"):
                    exito, error = anular_venta(int(venta_a_anular['venta_id']), venta_a_anular['libros_vendidos'])
                    if exito: st.success("¡Venta anulada con éxito!"), st.rerun()
                    else: st.error(f"Error al anular: {error}")