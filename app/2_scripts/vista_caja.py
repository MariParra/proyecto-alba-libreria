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
    try:
        response = conn.table("clientes").select("*").execute()
        return pd.DataFrame(response.data)
    except:
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'correo', 'telefono'])

@st.cache_data(ttl=60)
def cargar_historial():
    conn = get_db_connection()
    try:
        response = conn.table("ventas").select("*, libros(titulo), clientes(nombre)").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['titulo_libro'] = df['libros'].apply(lambda x: x['titulo'] if isinstance(x, dict) else 'Desconocido')
            df['nombre_cliente'] = df['clientes'].apply(lambda x: x['nombre'] if isinstance(x, dict) else 'Desconocido')
        return df
    except:
        return pd.DataFrame(columns=['venta_id', 'fecha', 'cantidad', 'total', 'metodo_pago', 'modo_envio', 'titulo_libro', 'nombre_cliente'])

def gestionar_cliente(nombre, correo, telefono, cliente_id_existente=None):
    conn = get_db_connection()
    datos = {"nombre": limpiar_texto(nombre), "correo": limpiar_texto(correo), "telefono": limpiar_texto(telefono)}
    
    if cliente_id_existente:
        conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
        return cliente_id_existente
    else:
        response = conn.table("clientes").insert(datos).execute()
        return response.data[0]['cliente_id']

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
        return response.data[0]['libro_id']

def procesar_venta(libro_id, cliente_id, cantidad, total, metodo, envio, stock_actual):
    conn = get_db_connection()
    nuevo_stock = stock_actual - cantidad
    
    try:
        datos_venta = {
            "libro_id": libro_id,
            "cliente_id": cliente_id,
            "cantidad": cantidad,
            "total": total,
            "metodo_pago": metodo,
            "modo_envio": envio,  # <--- NUEVO CAMPO DE ENVÍO
            "fecha": datetime.now().isoformat()
        }
        conn.table("ventas").insert(datos_venta).execute()
        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro_id).execute()
        
        cargar_libros_caja.clear()
        cargar_clientes.clear()
        cargar_historial.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

def anular_venta(venta_id, libro_id, cantidad_vendida):
    """Elimina la venta y restaura el stock del libro."""
    conn = get_db_connection()
    try:
        # 1. Devolver el stock al libro
        response = conn.table("libros").select("stock").eq("libro_id", libro_id).execute()
        stock_actual = response.data[0]['stock']
        nuevo_stock = stock_actual + cantidad_vendida
        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro_id).execute()

        # 2. Eliminar el registro de la venta
        conn.table("ventas").delete().eq("venta_id", venta_id).execute()
        
        cargar_libros_caja.clear()
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
        
        l_id, l_titulo, l_autor, l_precio_catalogo, l_stock_actual = None, "", "", 0.0, 0
        
        if modo_libro == "📚 Buscar Existente":
            if not df_libros.empty:
                lista_titulos_l = [""] + df_libros['titulo'].tolist()
                sel_libro = st.selectbox("Buscar libro por título:", lista_titulos_l)
                if sel_libro:
                    datos_l = df_libros[df_libros['titulo'] == sel_libro].iloc[0]
                    l_id = int(datos_l['libro_id'])
                    l_stock_actual = int(datos_l['stock'])
                    
                    with st.expander("✏️ Actualizar Catálogo (Opcional)", expanded=False):
                        st.caption("Modifica esto SOLO si quieres cambiar los datos permanentes del catálogo.")
                        l_titulo = st.text_input("Título:", value=datos_l['titulo'], disabled=True)
                        l_autor = st.text_input("Autor:", value=datos_l.get('autor', ''))
                        l_precio_catalogo = st.number_input("Precio Oficial en Catálogo ($):", value=float(datos_l['precio']), step=100.0)
                    
                    # Asignamos el precio del catálogo por defecto
                    l_precio_catalogo = float(datos_l['precio'])
                    l_titulo = datos_l['titulo']
            else:
                st.warning("El inventario está vacío.")
        else:
            with st.container(border=True):
                l_titulo = st.text_input("Título del libro:")
                l_autor = st.text_input("Autor (Opcional):")
                l_precio_catalogo = st.number_input("Precio ($):", min_value=0.0, step=100.0)
                l_stock_actual = 1 

        st.markdown("---")
        st.markdown("### 3️⃣ Detalle y Pago")
        
        # --- NUEVO: PRECIO ESPECIAL DE VENTA ---
        st.caption("Puedes aplicar un precio especial manualmente para esta venta.")
        precio_a_cobrar = st.number_input("Precio Unitario a Cobrar ($):", value=float(l_precio_catalogo), step=500.0)
        
        col5, col6, col7 = st.columns(3)
        cantidad = col5.number_input("Cantidad a vender:", min_value=1, max_value=max(1, l_stock_actual), step=1)
        metodo_pago = col6.selectbox("Método de Pago:", ["Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Transferencia"])
        
        # --- NUEVO: MODO DE ENVÍO ---
        modo_envio = col7.selectbox("Modo de Envío:", ["Retiro en tienda", "Despacho a domicilio", "Starken", "Chilexpress", "Correos de Chile", "Acordar con vendedor"])
        
        total_pagar = precio_a_cobrar * cantidad
        
        st.markdown(f"""
        <div style="background-color: #E6F3E6; border: 2px solid #4CAF50; padding: 15px; border-radius: 10px; text-align: center; margin-top: 10px;">
            <h2 style="color: #2E7D32; margin:0;">Total a Pagar: ${total_pagar:,.0f}</h2>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        
        if st.button("✅ CONFIRMAR VENTA", type="primary", use_container_width=True):
            if not c_nombre: st.error("⚠️ Falta el nombre del cliente.")
            elif not l_titulo: st.error("⚠️ Falta seleccionar un libro.")
            elif cantidad > l_stock_actual and modo_libro == "📚 Buscar Existente": st.error("⚠️ No hay suficiente stock.")
            else:
                with st.spinner("Procesando..."):
                    final_cliente_id = gestionar_cliente(c_nombre, c_correo, c_telefono, c_id)
                    final_libro_id = gestionar_libro(l_titulo, l_autor, l_precio_catalogo, cantidad, l_id)
                    
                    exito, err = procesar_venta(final_libro_id, final_cliente_id, cantidad, total_pagar, metodo_pago, modo_envio, l_stock_actual)
                    
                    if exito:
                        st.success("🎉 ¡Venta registrada con éxito!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"Error al registrar: {err}")

    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = cargar_historial()
        
        if df_ventas.empty:
            st.info("Aún no hay ventas registradas.")
        else:
            with st.expander("🔍 Filtros de Historial", expanded=False):
                col_h1, col_h2 = st.columns(2)
                f_cliente = col_h1.selectbox("Filtrar por Cliente:", ["Todos"] + df_ventas['nombre_cliente'].unique().tolist())
                f_metodo = col_h2.selectbox("Filtrar por Método:", ["Todos"] + df_ventas['metodo_pago'].unique().tolist())
                f_envio = st.selectbox("Filtrar por Envío:", ["Todos"] + df_ventas.get('modo_envio', pd.Series(["Retiro en tienda"])).unique().tolist())
            
            df_hist_filtrado = df_ventas.copy()
            if f_cliente != "Todos": df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['nombre_cliente'] == f_cliente]
            if f_metodo != "Todos": df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['metodo_pago'] == f_metodo]
            if f_envio != "Todos" and 'modo_envio' in df_hist_filtrado.columns: 
                df_hist_filtrado = df_hist_filtrado[df_hist_filtrado['modo_envio'] == f_envio]
            
            total_recaudado = df_hist_filtrado['total'].sum()
            total_libros_vendidos = df_hist_filtrado['cantidad'].sum()
            
            c_res1, c_res2 = st.columns(2)
            c_res1.metric("Recaudación", f"${total_recaudado:,.0f}")
            c_res2.metric("Libros Vendidos", total_libros_vendidos)
            
            st.markdown("---")
            # Ajustamos las columnas a mostrar para incluir el modo de envío
            columnas_mostrar = ['fecha', 'titulo_libro', 'nombre_cliente', 'cantidad', 'total', 'metodo_pago']
            if 'modo_envio' in df_hist_filtrado.columns:
                columnas_mostrar.append('modo_envio')
                
            df_hist_filtrado['fecha'] = pd.to_datetime(df_hist_filtrado['fecha']).dt.strftime('%d-%m-%Y %H:%M')
            st.dataframe(df_hist_filtrado[columnas_mostrar], hide_index=True, use_container_width=True)
            
    # --- NUEVA PESTAÑA PARA ANULAR VENTAS ---
    with tab_anular:
        st.markdown("### 🚫 Anular Venta y Restaurar Stock")
        st.warning("⚠️ Esta acción es irreversible. Al anular una venta, el registro se elimina y el stock del libro se restaura automáticamente.")
        
        if df_ventas.empty:
            st.info("No hay ventas para anular.")
        else:
            # Creamos una etiqueta legible para el selector
            df_ventas['etiqueta_anular'] = df_ventas.apply(
                lambda row: f"ID: {row['venta_id']} - {pd.to_datetime(row['fecha']).strftime('%d/%m')} - {row['titulo_libro']} -> {row['nombre_cliente']}",
                axis=1
            )
            lista_ventas_anular = [""] + df_ventas.sort_values('fecha', ascending=False)['etiqueta_anular'].tolist()
            
            venta_seleccionada = st.selectbox("Selecciona la venta a anular:", lista_ventas_anular)

            if venta_seleccionada:
                venta_a_anular = df_ventas[df_ventas['etiqueta_anular'] == venta_seleccionada].iloc[0]
                
                st.markdown("---")
                st.markdown("**Detalles de la Venta Seleccionada:**")
                st.json({
                    "ID Venta": int(venta_a_anular['venta_id']),
                    "Libro": venta_a_anular['titulo_libro'],
                    "Cliente": venta_a_anular['nombre_cliente'],
                    "Cantidad": int(venta_a_anular['cantidad']),
                    "Total Cobrado": f"${venta_a_anular['total']:,.0f}",
                    "Fecha": pd.to_datetime(venta_a_anular['fecha']).strftime('%d-%m-%Y %H:%M')
                })
                
                if st.button("🟥 CONFIRMAR ANULACIÓN DE ESTA VENTA", type="primary", use_container_width=True):
                    with st.spinner("Anulando venta y restaurando stock..."):
                        exito, error = anular_venta(
                            venta_id=int(venta_a_anular['venta_id']),
                            libro_id=int(venta_a_anular['libro_id']),
                            cantidad_vendida=int(venta_a_anular['cantidad'])
                        )
                        if exito:
                            st.success("¡Venta anulada y stock restaurado con éxito!")
                            st.rerun()
                        else:
                            st.error(f"Error al anular: {error}")