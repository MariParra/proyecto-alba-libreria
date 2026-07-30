import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import time
from utilidades import get_db_connection, limpiar_texto

def unificar_formatos_fecha(serie_fechas):
    def parsear_valor(val):
        if pd.isna(val) or str(val).strip() == '' or str(val).strip().lower() == 'nan':
            return pd.NaT
        val_str = str(val).strip()
        formatos_a_probar = [
            "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
            "%d-%m-%Y", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S",
            "%Y/%m/%d", "%Y/%m/%d %H:%M:%S"
        ]
        for fmt in formatos_a_probar:
            try: return datetime.strptime(val_str, fmt)
            except ValueError: continue
        try: return pd.to_datetime(val_str, errors='coerce', dayfirst=True)
        except Exception: return pd.NaT
    return serie_fechas.apply(parsear_valor)

def cargar_libros_caja():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, costo, stock").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        if not df.empty:
            df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0.0)
            df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0.0)
            df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e: 
        print(f"Error cargando libros caja: {e}")
        return pd.DataFrame()

def cargar_clientes_caja():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, email, telefono, status, rut, direccion").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: 
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'email', 'telefono', 'status', 'rut', 'direccion'])

def gestionar_cliente(nombre, correo, telefono, rut, direccion, cliente_id_existente=None):
    if not nombre: return None
    conn = get_db_connection()
    datos = {
        "nombre": limpiar_texto(nombre), 
        "email": limpiar_texto(correo), 
        "telefono": limpiar_texto(telefono),
        "rut": limpiar_texto(rut),
        "direccion": limpiar_texto(direccion)
    }
    
    try:
        if cliente_id_existente:
            conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
            return cliente_id_existente
        else:
            datos["status"] = "CLIENTE REGULAR"
            response = conn.table("clientes").insert(datos).execute()
            return response.data[0]['cliente_id']
    except Exception as e: 
        print(f"Error gestionando cliente: {e}")
        return None

def cargar_historial_completo():
    conn = get_db_connection()
    try:
        res_ventas = conn.table("registro_ventas").select("*").order("venta_id", desc=True).execute()
        if not res_ventas.data: return pd.DataFrame()
        df_ventas = pd.DataFrame(res_ventas.data)
        
        def formatear_libros(libros_data):
            if not isinstance(libros_data, str) or not libros_data.strip(): return "Sin Detalle"
            if libros_data.strip().startswith('['):
                try:
                    libros = json.loads(libros_data)
                    return " | ".join([f"{item.get('cantidad', 1)} x {item.get('titulo', 'N/A')}" for item in libros])
                except: return libros_data
            else: return libros_data
                
        df_ventas['libros_vendidos'] = df_ventas['libros_vendidos'].apply(formatear_libros)
        
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        if res_clientes.data:
            df_clientes = pd.DataFrame(res_clientes.data)
            df_ventas = df_ventas.merge(df_clientes, on='cliente_id', how='left')
            df_ventas.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
            df_ventas['nombre_cliente'] = df_ventas['nombre_cliente'].fillna('Cliente Eliminado')
        else: df_ventas['nombre_cliente'] = 'Sin Cliente'
        
        df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0)
        df_ventas['abono'] = pd.to_numeric(df_ventas.get('abono', 0), errors='coerce').fillna(0)
        df_ventas['costo_venta'] = pd.to_numeric(df_ventas.get('costo_venta', 0), errors='coerce').fillna(0)
        df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
        df_ventas['utilidad'] = df_ventas['monto_final'] - df_ventas['costo_venta']
        
        return df_ventas
    except Exception as e:
        st.error(f"Error cargando historial: {e}")
        return pd.DataFrame()

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
        return response.data[0]['libro_id']

def procesar_venta_carrito(carrito, cliente_id, valor_envio, metodo_envio, metodo_pago, comentario, fecha_venta, estado_venta, abono_venta, asignacion_id=None):
    conn = get_db_connection()
    libros_para_json = []
    costo_total_venta = 0.0
    
    for item in carrito:
        libros_para_json.append({
            "libro_id": item['libro_id'], "titulo": item['titulo'], "autor": item['autor'],
            "cantidad": item['cantidad'], "precio": item['precio_cobrado']
        })
        costo_unitario = item.get('costo', 0.0)
        if pd.isna(costo_unitario) or costo_unitario is None: costo_unitario = 0.0
        costo_total_venta += float(costo_unitario) * int(item['cantidad'])
    subtotal_libros = sum([item['subtotal'] for item in carrito])
    monto_final = subtotal_libros + valor_envio
    
    try:
        datos_venta = {
            "cliente_id": cliente_id, "fecha_venta": fecha_venta.strftime("%Y-%m-%d %H:%M:%S"),
            "libros_vendidos": json.dumps(libros_para_json, ensure_ascii=False), 
            "subtotal_libros": float(subtotal_libros), "valor_envio": float(valor_envio), 
            "monto_final": float(monto_final), "metodo_envio": metodo_envio, 
            "comentario": f"Pago: {metodo_pago}. {comentario}".strip(), "estado": estado_venta,
            "abono": float(abono_venta), "costo_venta": float(costo_total_venta) 
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
        
        # 🔴 INYECCIÓN AUTOMÁTICA DE EXTRAS EN ASIGNACIONES (CORREGIDO)
        if asignacion_id:
            try:
                # Corregimos 'id' a 'asignacion_id'
                res_asig = conn.table("asignaciones").select("extras, valor_extras").eq("asignacion_id", asignacion_id).execute()
                if res_asig.data:
                    asig_actual = res_asig.data[0]
                    extras_previos = asig_actual.get('extras') or ""
                    valor_previo = float(asig_actual.get('valor_extras') or 0.0)
                    
                    nuevos_extras_str = " | ".join([f"{item['cantidad']} x {item['titulo']}" for item in carrito])
                    extras_final = f"{extras_previos} | {nuevos_extras_str}".strip(" |")
                    valor_final = valor_previo + subtotal_libros
                    
                    # Corregimos 'estado' a 'estado_envio' y 'id' a 'asignacion_id'
                    conn.table("asignaciones").update({
                        "extras": extras_final,
                        "valor_extras": valor_final,
                        "estado_envio": "EXTRAS AÑADIDOS"
                    }).eq("asignacion_id", asignacion_id).execute()
            except Exception as ex:
                print(f"Error inyectando extras en asignacion: {ex}")
                
        st.session_state.carrito_caja = []
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
            datos = {}
            if 'monto_final' in row: datos['monto_final'] = float(row['monto_final'])
            if 'metodo_envio' in row: datos['metodo_envio'] = str(row['metodo_envio'])
            if 'comentario' in row: datos['comentario'] = str(row['comentario'])
            if 'estado' in row: datos['estado'] = str(row['estado'])
            if 'abono' in row: datos['abono'] = float(row['abono'])
            if 'costo_venta' in row: datos['costo_venta'] = float(row['costo_venta'])
            if datos:
                conn.table("registro_ventas").update(datos).eq("venta_id", venta_id).execute()
                updates += 1
        except Exception as e: 
            print(f"Error actualizando venta {venta_id}: {e}")
            continue
    return updates

# ==========================================
# --- VISTA PRINCIPAL (CAJA) ---
# ==========================================
def mostrar_caja():
    if 'carrito_caja' not in st.session_state: st.session_state.carrito_caja = []
        
    st.title("🛒 Caja y Ventas Rápidas")
    
    df_libros = cargar_libros_caja()
    df_clientes = cargar_clientes_caja()
    estados_posibles = ["NO COMENZADO", "PENDIENTE STOCK", "PENDIENTE ARMADO PAQUETE", "PAQUETE LISTO", "PENDIENTE PAGO", "FINALIZADO"]
    
    df_ventas_global_raw = cargar_historial_completo()
    df_ventas_global = df_ventas_global_raw.copy() if not df_ventas_global_raw.empty else pd.DataFrame()
    df_deudores_global = pd.DataFrame()
    
    if not df_ventas_global.empty:
        df_ventas_global['fecha_limpia'] = unificar_formatos_fecha(df_ventas_global['fecha_venta'])
        df_deudores_global = df_ventas_global[df_ventas_global['deuda'] > 0].copy()
        if not df_deudores_global.empty:
            df_deudores_global = df_deudores_global.dropna(subset=['fecha_limpia'])
            hoy_global = datetime.now().date()
            df_deudores_global['dias_mora'] = df_deudores_global['fecha_limpia'].apply(lambda x: (hoy_global - x.date()).days if pd.notna(x) else 0)
            deudas_criticas = df_deudores_global[df_deudores_global['dias_mora'] > 14]
            if not deudas_criticas.empty:
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 🚨 ALERTAS DE COBRANZA")
                st.sidebar.error(f"Tienes **{len(deudas_criticas)}** deudas con más de 2 semanas.")
                for _, row in deudas_criticas.iterrows():
                    st.sidebar.warning(f"👤 **{row['nombre_cliente']}**\n💰 Deuda: ${row['deuda']:,.0f}\n⏳ {row['dias_mora']} días")
                st.error(f"🚨 **¡ATENCIÓN!** Tienes {len(deudas_criticas)} cuenta(s) crítica(s) con más de 14 días de mora.")
    
    tab_venta, tab_historial, tab_cobranza, tab_anular = st.tabs(["🛒 Nueva Venta", "📜 Historial", "💸 Cobranza", "🚫 Anular"])
    
    with tab_venta:
        st.markdown("### 1️⃣ Datos del Cliente")
        modo_cliente = st.radio("Cliente:", ["👤 Buscar Existente", "➕ Nuevo"], horizontal=True, label_visibility="collapsed")
        
        c_id, c_nombre, c_correo, c_telefono, c_rut, c_direccion = None, "", "", "", "", ""
        
        if modo_cliente == "👤 Buscar Existente":
            if not df_clientes.empty:
                sel_cliente = st.selectbox("Buscar cliente:", [""] + df_clientes['nombre'].tolist())
                if sel_cliente:
                    datos_c = df_clientes[df_clientes['nombre'] == sel_cliente].iloc[0]
                    c_id = int(datos_c['cliente_id'])
                    c_nombre = datos_c['nombre']
                    c_correo = datos_c.get('email', '')
                    c_telefono = datos_c.get('telefono', '')
                    c_rut = datos_c.get('rut', '')
                    c_direccion = datos_c.get('direccion', '')
                    
                    with st.expander(f"✏️ Ver/Editar datos (Status: {datos_c.get('status', 'REGULAR')})", expanded=False):
                        col_cd1, col_cd2 = st.columns(2)
                        c_nombre = col_cd1.text_input("Nombre:", value=c_nombre)
                        c_rut = col_cd2.text_input("RUT:", value=c_rut)
                        c_correo = col_cd1.text_input("Correo:", value=c_correo)
                        c_telefono = col_cd2.text_input("Teléfono:", value=c_telefono)
                        c_direccion = st.text_input("Dirección de Despacho:", value=c_direccion)
            else: 
                st.warning("No hay clientes registrados.")
        else:
            with st.container(border=True):
                col_cn1, col_cn2 = st.columns(2)
                c_nombre = col_cn1.text_input("Nombre del nuevo cliente:")
                c_rut = col_cn2.text_input("RUT (Opcional):")
                c_correo = col_cn1.text_input("Correo (Opcional):")
                c_telefono = col_cn2.text_input("Teléfono (Opcional):")
                c_direccion = st.text_input("Dirección de Despacho (Opcional):")
                
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
                else: st.warning("El inventario está vacío.")
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
            
            if l_stock_actual <= 0 and not es_nuevo:
                st.warning("⚠️ Atención: Estás vendiendo un libro sin stock físico.")
            
            if st.button("➕ AÑADIR AL CARRITO", use_container_width=True):
                if not l_titulo: st.error("Debes seleccionar un libro.")
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
        opciones_envio = ["Retiro en tienda", "Despacho a domicilio", "Starken", "Chilexpress", "Correos de Chile", "Acordar con vendedor", "Añadir a compra anterior", "Añadir a caja de suscripción"]
        modo_envio = col_e1.selectbox("Modo de Envío:", opciones_envio)
        
        valor_envio = 0.0
        metodo_envio_final = modo_envio
        bloquear_venta = False 
        asignacion_id_target = None
        
        if modo_envio == "Añadir a caja de suscripción":
            if c_id is not None:
                conn = get_db_connection()
                # 🔴 CORRECCIÓN: Buscamos 'asignacion_id' y 'estado_envio'
                res_cajas = conn.table("asignaciones").select("asignacion_id, mes, estado_envio").eq("cliente_id", c_id).execute()
                cajas_abiertas = [c for c in res_cajas.data if c.get('estado_envio', '') not in ["ENVIADO", "ENTREGADO/RETIRADO", "RETIRADO"]]
                if cajas_abiertas:
                    opciones_cajas = [f"Suscripción {c['mes']} - {c.get('estado_envio','')} (ID: {c['asignacion_id']})" for c in cajas_abiertas]
                    caja_sel = col_e2.selectbox("Caja de Suscripción abierta:", opciones_cajas)
                    asignacion_id_target = int(caja_sel.split("(ID: ")[1].strip(")"))
                    metodo_envio_final = f"Inyectado a {caja_sel.split(' -')[0]}"
                    st.info("Los libros se inyectarán como Extras a la caja seleccionada (Envío $0).")
                else:
                    col_e2.warning("El cliente no tiene cajas de suscripción abiertas para añadir.")
                    bloquear_venta = True
            else:
                col_e2.error("Selecciona un cliente existente primero.")
                bloquear_venta = True
                
        elif modo_envio == "Añadir a compra anterior":
            if c_id is not None:
                ventas_abiertas = [v for v in df_ventas_global.to_dict('records') if v['cliente_id'] == c_id and v.get('estado', '') not in ["PAQUETE LISTO", "FINALIZADO"]]
                if ventas_abiertas:
                    opciones_ventas = [f"Venta #{v['venta_id']} ({v['fecha_venta']}) - {v.get('estado', 'Sin Estado')}" for v in ventas_abiertas]
                    venta_asociada_str = col_e2.selectbox("Compra asociada (No Finalizadas):", opciones_ventas)
                    v_id_asociada = venta_asociada_str.split("#")[1].split(" ")[0]
                    metodo_envio_final = f"Añadido a Venta #{v_id_asociada}"
                    st.info(f"El envío será gratuito. Esta compra se anexará a la Venta #{v_id_asociada}.")
                else:
                    col_e2.warning("No hay compras anteriores abiertas para anexar.")
                    bloquear_venta = True
            else:
                col_e2.error("Selecciona un cliente primero.")
                bloquear_venta = True
                
        elif modo_envio != "Retiro en tienda":
            valor_envio = col_e2.number_input("Costo de Envío ($):", min_value=0.0, step=500.0)
            
        metodo_pago = st.selectbox("Método de Pago:", ["Transferencia", "Efectivo", "Tarjeta Débito", "Tarjeta Crédito"])
        comentario_venta = st.text_area("Comentario (Opcional):", placeholder="Ej: Entregar por conserjería...")
        
        st.markdown("---")
        st.markdown("#### ⚙️ Estado y Abono (Opcional)")
        col_abono1, col_abono2 = st.columns(2)
        estado_venta_sel = col_abono1.selectbox("Estado de la Venta:", estados_posibles, index=0)
        abono_inicial = col_abono2.number_input("Abono Inicial ($):", min_value=0.0, step=1000.0)
        
        monto_final = subtotal_carrito + valor_envio
        st.markdown(f"<div style='background-color:#E6F3E6; border:2px solid #4CAF50; padding:15px; border-radius:10px; text-align:center;'><p style='color:#2E7D32; margin:0;'>Subtotal Libros: ${subtotal_carrito:,.0f} | Envío: ${valor_envio:,.0f}</p><h2 style='color:#2E7D32; margin:0;'>MONTO FINAL: ${monto_final:,.0f}</h2></div>", unsafe_allow_html=True)
        st.write("")
        
        desactivar_boton = not c_nombre or len(st.session_state.carrito_caja) == 0 or bloquear_venta
        
        if st.button("✅ CONFIRMAR VENTA TOTAL", type="primary", use_container_width=True, disabled=desactivar_boton):
            with st.spinner("Procesando Venta..."):
                final_cliente_id = gestionar_cliente(c_nombre, c_correo, c_telefono, c_rut, c_direccion, c_id)
                exito, err = procesar_venta_carrito(
                    st.session_state.carrito_caja, final_cliente_id, valor_envio, 
                    metodo_envio_final, metodo_pago, comentario_venta, fecha_venta_manual,
                    estado_venta_sel, abono_inicial, asignacion_id_target
                )
                if exito: 
                    st.success("🎉 ¡Venta registrada y extras inyectados (si aplica)!")
                    st.balloons()
                    time.sleep(2)
                    st.rerun()
                else: 
                    st.error(f"Error: {err}")
                    
    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = df_ventas_global.copy()
        
        if df_ventas.empty: st.info("Aún no hay ventas registradas.")
        else:
            fechas_invalidas = df_ventas['fecha_limpia'].isna()
            if fechas_invalidas.any():
                with st.expander(f"⚠️ Atención: {fechas_invalidas.sum()} ventas tienen fechas ilegibles"):
                    st.dataframe(df_ventas[fechas_invalidas][['venta_id', 'fecha_venta', 'nombre_cliente']], hide_index=True)
            with st.expander("🔍 Filtros del Historial"):
                col_f1, col_f2, col_f3 = st.columns(3)
                df_fechas_validas = df_ventas.dropna(subset=['fecha_limpia'])
                hoy = datetime.now().date()
                primer_dia_mes = hoy.replace(day=1)
                if not df_fechas_validas.empty:
                    fecha_min = df_fechas_validas['fecha_limpia'].min().date()
                    fecha_max = df_fechas_validas['fecha_limpia'].max().date()
                    limite_min = min(fecha_min, hoy)
                    limite_max = max(fecha_max, hoy)
                    rango_fechas = col_f1.date_input("Rango personalizado:", value=(limite_min, limite_max), min_value=limite_min, max_value=limite_max)
                else: rango_fechas = col_f1.date_input("Rango personalizado:", value=(), disabled=True)
                
                clientes_hist = ["Todos"] + sorted(df_ventas['nombre_cliente'].unique().tolist())
                cliente_filtro = col_f2.selectbox("Filtrar por Cliente:", clientes_hist)
                estados_hist = ["Todos"] + sorted(df_ventas['estado'].unique().tolist())
                estado_filtro = col_f3.selectbox("Filtrar por Estado:", estados_hist)
                
                st.markdown("---")
                col_chk1, col_chk2 = st.columns(2)
                mes_en_curso = col_chk1.checkbox("📅 Mostrar rápido: Solo este mes", value=False)
                solo_costo_cero = col_chk2.checkbox("⚠️ Mostrar rápido: Ventas sin costo asignado ($0)", value=False)
                st.markdown("---")
                columnas_hist_todas = ['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'monto_final', 'abono', 'deuda', 'utilidad', 'costo_venta', 'estado', 'metodo_envio', 'comentario']
                columnas_por_defecto = ['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'monto_final', 'utilidad', 'costo_venta', 'estado']
                columnas_a_mostrar = st.multiselect("👀 Mostrar / Ocultar Columnas en Tabla", columnas_hist_todas, default=columnas_por_defecto)
                
            df_filtrado_general = df_ventas.copy()
            if mes_en_curso:
                df_filtrado_general = df_filtrado_general[(df_filtrado_general['fecha_limpia'].dt.date >= primer_dia_mes) & (df_filtrado_general['fecha_limpia'].dt.date <= limite_max)]
            elif len(rango_fechas) == 2:
                df_filtrado_general = df_filtrado_general[(df_filtrado_general['fecha_limpia'].dt.date >= rango_fechas[0]) & (df_filtrado_general['fecha_limpia'].dt.date <= rango_fechas[1])]
                
            if cliente_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['nombre_cliente'] == cliente_filtro]
            if estado_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['estado'] == estado_filtro]
                
            st.markdown("#### 📊 Resumen del período filtrado")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("💰 Ventas Totales", f"${df_filtrado_general['monto_final'].sum():,.0f}")
            m2.metric("💳 Total Abonado", f"${df_filtrado_general['abono'].sum():,.0f}")
            m3.metric("📦 Costos Totales", f"${df_filtrado_general['costo_venta'].sum():,.0f}")
            m4.metric("📈 Utilidad Estimada", f"${df_filtrado_general['utilidad'].sum():,.0f}")
            st.markdown("---")
            
            df_mostrar = df_filtrado_general.copy()
            if solo_costo_cero: df_mostrar = df_mostrar[df_mostrar['costo_venta'] == 0]
            df_mostrar = df_mostrar[columnas_a_mostrar].copy()
            st.session_state.historial_original = df_mostrar.copy()
            config_cols_hist = {
                "monto_final": st.column_config.NumberColumn("Monto Final", format="$%.0f"),
                "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                "deuda": st.column_config.NumberColumn("Deuda", format="$%.0f"),
                "utilidad": st.column_config.NumberColumn("Utilidad", format="$%.0f"),
                "costo_venta": st.column_config.NumberColumn("Costo Venta", format="$%.0f"),
                "estado": st.column_config.SelectboxColumn("Estado", options=estados_posibles),
            }
            
            if 'costo_venta' in df_mostrar.columns:
                df_estilizado = df_mostrar.style.apply(lambda s: ['background-color: #ffebee; color: #c62828; font-weight: bold;' if v == 0 else '' for v in s], subset=['costo_venta'])
            else: df_estilizado = df_mostrar
                
            disabled_cols = ['venta_id', 'fecha_venta', 'nombre_cliente', 'libros_vendidos', 'deuda', 'utilidad']
            disabled_cols_active = [c for c in disabled_cols if c in columnas_a_mostrar]
            
            df_editado = st.data_editor(df_estilizado, disabled=disabled_cols_active, use_container_width=True, hide_index=True, column_config=config_cols_hist)
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Historial", type="primary"):
                    num = actualizar_historial_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} registros!")
                    time.sleep(1.5); st.rerun()
                    
    with tab_cobranza:
        st.markdown("### 💸 Cuentas por Cobrar")
        if not df_ventas_global.empty:
            df_deudores = df_deudores_global.copy()
            if df_deudores.empty: st.success("🎉 ¡Felicidades! No hay deudas pendientes.")
            else:
                with st.expander("🔍 Filtros de Cobranza", expanded=True):
                    col_c1, col_c2 = st.columns(2)
                    fecha_min_c = df_deudores['fecha_limpia'].min().date()
                    fecha_max_c = df_deudores['fecha_limpia'].max().date()
                    rango_fechas_c = col_c1.date_input("Filtrar por Fecha de Venta:", value=(fecha_min_c, fecha_max_c), min_value=fecha_min_c, max_value=fecha_max_c, key="rango_cob")
                    clientes_cob = ["Todos"] + sorted(df_deudores['nombre_cliente'].unique().tolist())
                    cliente_filtro_c = col_c2.selectbox("Filtrar por Cliente:", clientes_cob, key="cliente_cob")
                if len(rango_fechas_c) == 2:
                    df_deudores = df_deudores[(df_deudores['fecha_limpia'].dt.date >= rango_fechas_c[0]) & (df_deudores['fecha_limpia'].dt.date <= rango_fechas_c[1])]
                if cliente_filtro_c != "Todos":
                    df_deudores = df_deudores[df_deudores['nombre_cliente'] == cliente_filtro_c]
                if df_deudores.empty: st.info("No hay deudas que coincidan con los filtros actuales.")
                else:
                    st.markdown(f"#### 💰 Total por Cobrar (Filtrado): **${df_deudores['deuda'].sum():,.0f}**")
                    df_deudores['Nivel Mora'] = df_deudores['dias_mora'].apply(lambda x: "🔴 Crítico (>14 días)" if x > 14 else ("🟡 Medio (7-14 días)" if x > 7 else "🟢 Normal"))
                    columnas_mostrar_cob = ['fecha_venta', 'nombre_cliente', 'monto_final', 'abono', 'deuda', 'Nivel Mora', 'estado']
                    st.dataframe(df_deudores[columnas_mostrar_cob], hide_index=True, use_container_width=True, 
                        column_config={
                            "monto_final": st.column_config.NumberColumn("Monto Venta", format="$%.0f"),
                            "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                            "deuda": st.column_config.NumberColumn("Deuda Pendiente", format="$%.0f")
                        }
                    )
        else: st.info("No hay deudas registradas.")
        
    with tab_anular:
        st.markdown("### 🚫 Anular Venta y Restaurar Stock")
        df_ventas_anular = df_ventas_global.copy()
        if not df_ventas_anular.empty:
            df_ventas_anular['etiqueta_anular'] = df_ventas_anular.apply(lambda row: f"ID: {row.get('venta_id','')} | {row.get('fecha_venta','')} | {row.get('libros_vendidos','')} | ${row.get('monto_final',0):,.0f}", axis=1)
            venta_sel = st.selectbox("Selecciona la venta:", [""] + df_ventas_anular.sort_values('venta_id', ascending=False)['etiqueta_anular'].tolist())
            if venta_sel:
                venta_a_anular = df_ventas_anular[df_ventas_anular['etiqueta_anular'] == venta_sel].iloc[0]
                if st.button("🟥 CONFIRMAR ANULACIÓN", type="primary"):
                    exito, error = anular_venta(int(venta_a_anular['venta_id']), venta_a_anular['libros_vendidos'])
                    if exito: 
                        st.success("¡Venta anulada con éxito!")
                        time.sleep(1.5); st.rerun()
                    else: st.error(f"Error al anular: {error}")

if __name__ == "__main__":
    mostrar_caja()