import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
from utilidades import get_db_connection, limpiar_texto
import time

# ==========================================
# --- FUNCIONES DE BASE DE DATOS ---
# ==========================================

def unificar_formatos_fecha(serie_fechas):
    """
    Analiza una serie de fechas en texto y las traduce a formato datetime 
    intentando múltiples patrones. No elimina datos.
    """
    def parsear_valor(val):
        if pd.isna(val) or str(val).strip() == '' or str(val).strip().lower() == 'nan':
            return pd.NaT
            
        val_str = str(val).strip()
        
        # Diccionario de formatos comunes esperados en importaciones (LATAM e ISO)
        formatos_a_probar = [
            "%Y-%m-%d",           # Ej: 2026-08-25
            "%Y-%m-%d %H:%M:%S",  # Ej: 2026-08-25 14:30:00
            "%Y-%m-%d %H:%M:%S.%f",
            "%d-%m-%Y",           # Ej: 25-08-2026
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y",           # Ej: 25/08/2026
            "%d/%m/%Y %H:%M:%S",
            "%Y/%m/%d",           # Ej: 2026/08/25
            "%Y/%m/%d %H:%M:%S"
        ]
        
        for fmt in formatos_a_probar:
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
                
        # Si todos los explícitos fallan, intenta con el parseo nativo de pandas asumiendo día primero
        try:
            return pd.to_datetime(val_str, errors='coerce', dayfirst=True)
        except Exception:
            return pd.NaT
            
    return serie_fechas.apply(parsear_valor)

@st.cache_data(ttl=60)
def cargar_libros_caja():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, costo, stock").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        
        if not df.empty:
            # 🔴 EL SECRETO: Forzamos matemáticamente a que los nulos sean 0.0 y no NaN
            df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0.0)
            df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0.0)
            df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0)
            
        return df
    except: 
        return pd.DataFrame()


@st.cache_data(ttl=60)
def cargar_clientes_caja():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, email, telefono, status").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: 
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'email', 'telefono', 'status'])

@st.cache_data(ttl=60)
def cargar_historial_completo():
    """
    Carga el historial de ventas, procesa los libros vendidos (texto/JSON),
    y calcula deuda y utilidad en tiempo real.
    """
    conn = get_db_connection()
    try:
        res_ventas = conn.table("registro_ventas").select("*").order("venta_id", desc=True).execute()
        if not res_ventas.data: 
            return pd.DataFrame()
        df_ventas = pd.DataFrame(res_ventas.data)
        
        # Formatear la columna de libros para visualización
        def formatear_libros(libros_data):
            if not isinstance(libros_data, str) or not libros_data.strip(): 
                return "Sin Detalle"
            if libros_data.strip().startswith('['):
                try:
                    libros = json.loads(libros_data)
                    return " | ".join([f"{item.get('cantidad', 1)} x {item.get('titulo', 'N/A')}" for item in libros])
                except: 
                    return libros_data
            else: 
                return libros_data
                
        df_ventas['libros_vendidos'] = df_ventas['libros_vendidos'].apply(formatear_libros)
        
        # Unir con nombres de clientes
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        if res_clientes.data:
            df_clientes = pd.DataFrame(res_clientes.data)
            df_ventas = df_ventas.merge(df_clientes, on='cliente_id', how='left')
            df_ventas.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
            df_ventas['nombre_cliente'] = df_ventas['nombre_cliente'].fillna('Cliente Eliminado')
        else:
            df_ventas['nombre_cliente'] = 'Sin Cliente'
        
        # Asegurar tipos numéricos para los cálculos
        df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0)
        df_ventas['abono'] = pd.to_numeric(df_ventas.get('abono', 0), errors='coerce').fillna(0)
        df_ventas['costo_venta'] = pd.to_numeric(df_ventas.get('costo_venta', 0), errors='coerce').fillna(0)
        
        # --- CÁLCULOS FINANCIEROS AL VUELO ---
        df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
        df_ventas['utilidad'] = df_ventas['monto_final'] - df_ventas['costo_venta']
        
        return df_ventas
    except Exception as e:
        st.error(f"Error cargando historial: {e}")
        return pd.DataFrame()

def verificar_estado_cliente(cliente_id):
    conn = get_db_connection()
    try:
        res = conn.table("suscripciones").select("suscripcion_id").eq("cliente_id", cliente_id).execute()
        if res.data and len(res.data) > 0: 
            return "SUSCRITO"
        return "CLIENTE REGULAR"
    except: 
        return "CLIENTE REGULAR"

def gestionar_cliente(nombre, correo, telefono, cliente_id_existente=None):
    if not nombre: return None
    conn = get_db_connection()
    datos = {
        "nombre": limpiar_texto(nombre), 
        "email": limpiar_texto(correo), 
        "telefono": limpiar_texto(telefono)
    }
    try:
        if cliente_id_existente:
            datos["status"] = verificar_estado_cliente(cliente_id_existente)
            conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
            return cliente_id_existente
        else:
            datos["status"] = "CLIENTE REGULAR"
            response = conn.table("clientes").insert(datos).execute()
            cargar_clientes_caja.clear()
            return response.data[0]['cliente_id']
    except: 
        return None

def gestionar_libro(titulo, autor, precio_catalogo, stock_a_sumar, libro_id_existente=None):
    conn = get_db_connection()
    datos = {
        "titulo": limpiar_texto(titulo), 
        "autor": limpiar_texto(autor), 
        "precio": float(precio_catalogo)
    }
    if libro_id_existente:
        conn.table("libros").update(datos).eq("libro_id", libro_id_existente).execute()
        return libro_id_existente
    else:
        datos["stock"] = int(stock_a_sumar)
        datos["precio_original"] = float(precio_catalogo)
        response = conn.table("libros").insert(datos).execute()
        cargar_libros_caja.clear()
        return response.data[0]['libro_id']

def procesar_venta_carrito(carrito, cliente_id, valor_envio, metodo_envio, metodo_pago, comentario, fecha_venta, estado_venta, abono_venta):
    conn = get_db_connection()
    
    # Preparamos los datos para guardar en JSON y el costo total
    libros_para_json = []
    costo_total_venta = 0.0
    
    for item in carrito:
        libros_para_json.append({
            "libro_id": item['libro_id'], 
            "titulo": item['titulo'], 
            "autor": item['autor'],
            "cantidad": item['cantidad'], 
            "precio": item['precio_cobrado']
        })
        # Sumamos el costo de cada libro (costo unitario * cantidad)
        costo_total_venta += item.get('costo', 0.0) * item['cantidad']
    subtotal_libros = sum([item['subtotal'] for item in carrito])
    monto_final = subtotal_libros + valor_envio
    try:
        datos_venta = {
            "cliente_id": cliente_id, 
            "fecha_venta": fecha_venta.strftime("%Y-%m-%d %H:%M:%S"),
            "libros_vendidos": json.dumps(libros_para_json, ensure_ascii=False), 
            "subtotal_libros": float(subtotal_libros),
            "valor_envio": float(valor_envio), 
            "monto_final": float(monto_final),
            "metodo_envio": metodo_envio, 
            "comentario": f"Pago: {metodo_pago}. {comentario}".strip(),
            "estado": estado_venta,
            "abono": float(abono_venta),
            "costo_venta": float(costo_total_venta)
        }
        conn.table("registro_ventas").insert(datos_venta).execute()
        for item in carrito:
            l_id = item['libro_id'] # Se define l_id para la interacción
            if item['es_nuevo']: 
                l_id = gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], item['cantidad'], None)
            else:
                gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], 0, l_id)
                nuevo_stock = item['stock_actual'] - item['cantidad']
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
            
            # Registrar en el historial del cliente
            if cliente_id and l_id:
                res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", l_id).execute()
                if not res_hist.data:
                    datos_historico = {"cliente_id": cliente_id, "libro_id": l_id, "autor_historico": limpiar_texto(item['autor']), "origen": "VENTA CAJA"}
                    conn.table("librero_historico").insert(datos_historico).execute()
        
        # Limpiamos el carrito y las cachés
        st.session_state.carrito_caja = []
        cargar_libros_caja.clear()
        cargar_clientes_caja.clear()
        cargar_historial_completo.clear()
        return True, ""
    except Exception as e: 
        return False, str(e)

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
        cargar_historial_completo.clear()
        cargar_libros_caja.clear()
        return True, ""
    except Exception as e: 
        return False, str(e)

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
            datos = {
                "valor_envio": float(row['valor_envio']), 
                "monto_final": float(row['monto_final']), 
                "metodo_envio": str(row['metodo_envio']), 
                "comentario": str(row['comentario']),
                "estado": str(row.get('estado', 'FINALIZADO')),
                "abono": float(row.get('abono', 0)),
                "costo_venta": float(row.get('costo_venta', 0))
            }
            conn.table("registro_ventas").update(datos).eq("venta_id", venta_id).execute()
            updates += 1
        except: 
            continue
            
    if updates > 0: 
        cargar_historial_completo.clear()
    return updates

# ==========================================
# --- VISTA PRINCIPAL (CAJA) ---
# ==========================================
def mostrar_caja():
    if 'carrito_caja' not in st.session_state:
        st.session_state.carrito_caja = []
        
    st.title("🛒 Caja y Ventas Rápidas")
    
    df_libros = cargar_libros_caja()
    df_clientes = cargar_clientes_caja()
    
    tab_venta, tab_historial, tab_cobranza, tab_anular = st.tabs(["🛒 Nueva Venta", "📜 Historial Editable", "💸 Cuentas por Cobrar", "🚫 Anular Venta"])
    
    # --- PESTAÑA 1: NUEVA VENTA ---
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
            else: 
                st.warning("No hay clientes registrados.")
        else:
            with st.container(border=True):
                c_nombre = st.text_input("Nombre del nuevo cliente:")
                c_correo = st.text_input("Correo (Opcional):")
                c_telefono = st.text_input("Teléfono (Opcional):")
                
        st.markdown("---")
        
        st.markdown("### 2️⃣ Añadir Libros al Carrito")
        with st.container(border=True):
            modo_libro = st.radio("Libro:", ["📚 Buscar Existente", "➕ Rápido (No en catálogo)"], horizontal=True, label_visibility="collapsed")
            l_id, l_titulo, l_autor, l_precio_catalogo, l_stock_actual, l_costo, es_nuevo = None, "", "", 0.0, 0, 0.0, False
            
            if modo_libro == "📚 Buscar Existente":
                if not df_libros.empty:
                    sel_libro = st.selectbox("Buscar libro:", [""] + df_libros['titulo'].tolist())
                    if sel_libro:
                        datos_l = df_libros[df_libros['titulo'] == sel_libro].iloc[0]
                        l_id = int(datos_l['libro_id'])
                        l_stock_actual = int(datos_l['stock'])
                        l_titulo = datos_l['titulo']
                        l_precio_catalogo = float(datos_l['precio'])
                        l_costo = float(datos_l['costo']) 
                        l_autor = datos_l.get('autor', '')
                        
                        with st.expander("✏️ Actualizar Catálogo (Opcional)", expanded=False):
                            l_autor = st.text_input("Autor:", value=l_autor)
                            l_precio_catalogo = st.number_input("Precio Oficial ($):", value=l_precio_catalogo, step=100.0)
                else: 
                    st.warning("El inventario está vacío.")
            else:
                es_nuevo = True
                l_titulo = st.text_input("Título del libro:")
                l_autor = st.text_input("Autor (Opcional):")
                l_precio_catalogo = st.number_input("Precio Oficial ($):", min_value=0.0, step=100.0)
                l_costo = st.number_input("Costo del libro nuevo ($):", min_value=0.0, step=100.0)
                l_stock_actual = 999 
            
            st.markdown("👇 **Precio Especial y Cantidad para esta venta**")
            col_c1, col_c2 = st.columns(2)
            precio_a_cobrar = col_c1.number_input("Precio a Cobrar ($):", value=float(l_precio_catalogo), step=500.0)
            cantidad = col_c2.number_input("Cantidad:", min_value=1, max_value=max(1, l_stock_actual), step=1)
            
            libro_sin_stock = l_stock_actual <= 0 and not es_nuevo
            if libro_sin_stock:
                st.warning("⚠️ Atención: Estás vendiendo un libro sin stock físico (venta por encargo).")
            
            if st.button("➕ AÑADIR AL CARRITO", use_container_width=True):
                if not l_titulo: 
                    st.error("Debes seleccionar un libro.")
                else:
                    st.session_state.carrito_caja.append({
                        'libro_id': l_id, 'titulo': l_titulo, 'autor': l_autor, 
                        'precio_catalogo': l_precio_catalogo, 'precio_cobrado': precio_a_cobrar, 
                        'cantidad': cantidad, 'subtotal': precio_a_cobrar * cantidad,
                        'stock_actual': l_stock_actual, 'costo': l_costo, 'es_nuevo': es_nuevo
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
        
        st.markdown("---")
        st.markdown("#### ⚙️ Estado y Abono (Opcional)")
        
        col_abono1, col_abono2 = st.columns(2)
        estados_posibles = ["NO COMENZADO", "PENDIENTE STOCK", "PENDIENTE ARMADO PAQUETE", "PAQUETE LISTO","PENDIENTE PAGO", "FINALIZADO"]
        estado_venta_sel = col_abono1.selectbox("Estado de la Venta:", estados_posibles, index=3) # Por defecto FINALIZADO
        abono_inicial = col_abono2.number_input("Abono Inicial ($):", min_value=0.0, step=1000.0)
        
        monto_final = subtotal_carrito + valor_envio
        st.markdown(f"<div style='background-color:#E6F3E6; border:2px solid #4CAF50; padding:15px; border-radius:10px; text-align:center;'><p style='color:#2E7D32; margin:0;'>Subtotal Libros: ${subtotal_carrito:,.0f} | Envío: ${valor_envio:,.0f}</p><h2 style='color:#2E7D32; margin:0;'>MONTO FINAL: ${monto_final:,.0f}</h2></div>", unsafe_allow_html=True)
        st.write("")
        
        if st.button("✅ CONFIRMAR VENTA TOTAL", type="primary", use_container_width=True):
            if not c_nombre: 
                st.error("⚠️ Falta el cliente.")
            elif len(st.session_state.carrito_caja) == 0: 
                st.error("⚠️ El carrito está vacío.")
            else:
                with st.spinner("Procesando Venta..."):
                    final_cliente_id = gestionar_cliente(c_nombre, c_correo, c_telefono, c_id)
                    exito, err = procesar_venta_carrito(
                        st.session_state.carrito_caja, final_cliente_id, valor_envio, 
                        modo_envio, metodo_pago, comentario_venta, fecha_venta_manual,
                        estado_venta_sel, abono_inicial
                    )
                    if exito: 
                        st.success("🎉 ¡Venta registrada!")
                        st.balloons()
                        st.rerun()
                    else: 
                        st.error(f"Error: {err}")

        # --- PESTAÑA 2: HISTORIAL EDITABLE ---
    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = cargar_historial_completo()
        
        if df_ventas.empty: 
            st.info("Aún no hay ventas registradas.")
        else:
            # 1. Creamos una columna sanitizada usando tu función unificadora de fechas
            df_ventas['fecha_limpia'] = unificar_formatos_fecha(df_ventas['fecha_venta'])
            
            # Alerta UX responsiva en caso de que existan fechas corruptas
            fechas_invalidas = df_ventas['fecha_limpia'].isna()
            if fechas_invalidas.any():
                with st.expander(f"⚠️ Atención: {fechas_invalidas.sum()} ventas tienen fechas con formato ilegible"):
                    st.warning("Estos registros siguen en el sistema pero no se pueden filtrar temporalmente. Revisa el formato original.")
                    st.dataframe(df_ventas[fechas_invalidas][['venta_id', 'fecha_venta', 'nombre_cliente']], hide_index=True)

            with st.expander("🔍 Filtros del Historial"):
                col_f1, col_f2, col_f3 = st.columns(3)
                
                # Usamos la columna ya parseada para extraer los límites de fechas
                df_fechas_validas = df_ventas.dropna(subset=['fecha_limpia'])
                
                if not df_fechas_validas.empty:
                    fecha_min = df_fechas_validas['fecha_limpia'].min().date()
                    fecha_max = df_fechas_validas['fecha_limpia'].max().date()
                    
                    rango_fechas = col_f1.date_input(
                        "Filtrar por Fecha:", 
                        value=(fecha_min, fecha_max), 
                        min_value=fecha_min, max_value=fecha_max
                    )
                else:
                    rango_fechas = col_f1.date_input("Filtrar por Fecha:", value=(), disabled=True)
                
                clientes_hist = ["Todos"] + sorted(df_ventas['nombre_cliente'].unique().tolist())
                cliente_filtro = col_f2.selectbox("Filtrar por Cliente:", clientes_hist)
                
                estados_hist = ["Todos"] + sorted(df_ventas['estado'].unique().tolist())
                estado_filtro = col_f3.selectbox("Filtrar por Estado:", estados_hist)
                
                # 🔴 NUEVO FILTRO RÁPIDO PARA AUDITORÍA DE COSTOS
                st.markdown("---")
                solo_costo_cero = st.checkbox("⚠️ Mostrar solo ventas pendientes de asignar Costo (Costo = $0)", value=False)
                
            df_filtrado = df_ventas.copy()
            
            # Filtrado seguro
            if len(rango_fechas) == 2:
                df_filtrado = df_filtrado[
                    (df_filtrado['fecha_limpia'].dt.date >= rango_fechas[0]) & 
                    (df_filtrado['fecha_limpia'].dt.date <= rango_fechas[1])
                ]
                
            if cliente_filtro != "Todos":
                df_filtrado = df_filtrado[df_filtrado['nombre_cliente'] == cliente_filtro]
            if estado_filtro != "Todos":
                df_filtrado = df_filtrado[df_filtrado['estado'] == estado_filtro]
                
            # Aplicar filtro de costo cero si la casilla está marcada
            if solo_costo_cero:
                df_filtrado = df_filtrado[df_filtrado['costo_venta'] == 0]
            
            # Panel de métricas para sumar costos y utilidades del período
            st.markdown("#### 📊 Resumen del período filtrado")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("💰 Ventas Totales", f"${df_filtrado['monto_final'].sum():,.0f}")
            m2.metric("💳 Total Abonado", f"${df_filtrado['abono'].sum():,.0f}")
            m3.metric("📦 Costos Totales", f"${df_filtrado['costo_venta'].sum():,.0f}")
            m4.metric("📈 Utilidad Estimada", f"${df_filtrado['utilidad'].sum():,.0f}")
            st.markdown("---")
            
            columnas_hist = ['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'monto_final', 'abono', 'deuda', 'utilidad', 'costo_venta', 'estado', 'metodo_envio', 'comentario']
            for col in columnas_hist: 
                if col not in df_filtrado.columns: df_filtrado[col] = ""
                
            df_mostrar = df_filtrado[columnas_hist].copy()
            
            if 'historial_original' not in st.session_state or not st.session_state.historial_original.equals(df_mostrar):
                st.session_state.historial_original = df_mostrar.copy()
                
            st.caption("Doble clic en celdas para modificar. Los campos financieros (Costo Venta, Estado, Abono) pueden editarse directamente aquí.")
            
            config_cols_hist = {
                "monto_final": st.column_config.NumberColumn("Monto Final", format="$%.0f"),
                "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                "deuda": st.column_config.NumberColumn("Deuda", format="$%.0f"),
                "utilidad": st.column_config.NumberColumn("Utilidad", format="$%.0f"),
                "costo_venta": st.column_config.NumberColumn("Costo Venta", format="$%.0f"),
                "estado": st.column_config.SelectboxColumn("Estado", options=["PENDIENTE STOCK", "PENDIENTE ARMADO PAQUETE", "LISTO / PENDIENTE PAGO", "FINALIZADO"]),
            }
            
            # 🔴 NUEVA ALERTA VISUAL: Pinta de rojo si el costo es 0
            df_estilizado = df_mostrar.style.apply(
                lambda s: ['background-color: #ffebee; color: #c62828; font-weight: bold;' if v == 0 else '' for v in s],
                subset=['costo_venta']
            )
            
            df_editado = st.data_editor(
                df_estilizado, # Usamos el DataFrame estilizado
                disabled=['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'deuda', 'utilidad'], 
                use_container_width=True, 
                hide_index=True,
                column_config=config_cols_hist
            )
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Historial", type="primary"):
                    num = actualizar_historial_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} registros!")
                    time.sleep(1.5) 
                    st.rerun()

    # --- PESTAÑA 3: CUENTAS POR COBRAR ---
    with tab_cobranza:
        st.markdown("### 💸 Cuentas por Cobrar")
        st.caption("Lista de todas las ventas con deuda pendiente (Deuda > 0).")
        
        df_ventas_cobranza = cargar_historial_completo()
        if not df_ventas_cobranza.empty:
            df_deudores = df_ventas_cobranza[df_ventas_cobranza['deuda'] > 0].copy()
            
            if df_deudores.empty:
                st.success("🎉 ¡Felicidades! No hay deudas pendientes.")
            else:
                config_deuda = {
                    "monto_final": st.column_config.NumberColumn("Monto Venta", format="$%.0f"),
                    "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                    "deuda": st.column_config.NumberColumn("Deuda Pendiente", format="$%.0f")
                }
                st.dataframe(
                    df_deudores[['fecha_venta', 'nombre_cliente', 'monto_final', 'abono', 'deuda', 'estado']],
                    hide_index=True, use_container_width=True, column_config=config_deuda
                )
                
                total_por_cobrar = df_deudores['deuda'].sum()
                st.markdown(f"#### 💰 Total por Cobrar: **${total_por_cobrar:,.0f}**")
        else:
            st.info("No hay ventas registradas.")

    # --- PESTAÑA 4: ANULAR VENTA ---
    with tab_anular:
        st.markdown("### 🚫 Anular Venta y Restaurar Stock")
        df_ventas_anular = cargar_historial_completo()
        if not df_ventas_anular.empty:
            df_ventas_anular['etiqueta_anular'] = df_ventas_anular.apply(lambda row: f"ID: {row.get('venta_id','')} | {row.get('fecha_venta','')} | {row.get('libros_vendidos','')} | ${row.get('monto_final',0):,.0f}", axis=1)
            venta_sel = st.selectbox("Selecciona la venta:", [""] + df_ventas_anular.sort_values('venta_id', ascending=False)['etiqueta_anular'].tolist())
            
            if venta_sel:
                venta_a_anular = df_ventas_anular[df_ventas_anular['etiqueta_anular'] == venta_sel].iloc[0]
                if st.button("🟥 CONFIRMAR ANULACIÓN", type="primary"):
                    exito, error = anular_venta(int(venta_a_anular['venta_id']), venta_a_anular['libros_vendidos'])
                    if exito: 
                        st.success("¡Venta anulada con éxito!")
                        st.rerun()
                    else: 
                        st.error(f"Error al anular: {error}")

if __name__ == "__main__":
    mostrar_caja()