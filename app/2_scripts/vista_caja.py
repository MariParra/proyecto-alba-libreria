import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

def unificar_formatos_fecha(serie_fechas):
    def parsear_valor(val):
        if pd.isna(val) or str(val).strip() == '' or str(val).strip().lower() in ['nan', 'nat']:
            return pd.NaT
        val_str = str(val).strip()
        fecha_parseada = pd.to_datetime(val_str, dayfirst=True, errors='coerce')
        return fecha_parseada

    try:
        return serie_fechas.apply(parsear_valor)
    except Exception as e:
        log_error("vista_caja", "unificar_formatos_fecha", f"Error inesperado al parsear fechas. Detalle: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return pd.to_datetime(serie_fechas, errors='coerce')

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
        log_error("vista_caja", "cargar_libros_caja", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error("Error crítico: No se pudo cargar el catálogo de libros.")
        return pd.DataFrame()

def cargar_clientes_caja():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, email, telefono, status, rut, direccion").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_caja", "cargar_clientes_caja", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error("Error crítico: No se pudo cargar el listado de clientes.")
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'email', 'telefono', 'status', 'rut', 'direccion'])

def cargar_listas_desplegables_caja():
    """Obtiene Autores y Editoriales únicos para los desplegables de caja."""
    conn = get_db_connection()
    try:
        res_autores = conn.table("libros").select("autor").execute()
        res_editoriales = conn.table("libros").select("editorial").execute()
        
        autores = sorted(list(set([r['autor'] for r in res_autores.data if r.get('autor')]))) if res_autores.data else []
        editoriales = sorted(list(set([r['editorial'] for r in res_editoriales.data if r.get('editorial')]))) if res_editoriales.data else []
        
        return autores, editoriales
    except Exception as e:
        log_error("vista_caja", "cargar_listas_desplegables_caja", f"Error: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return [], []

def gestionar_cliente(nombre, correo, telefono, rut, direccion, cliente_id_existente=None):
    if not nombre: return None, "El nombre del cliente es obligatorio."
    conn = get_db_connection()
    
    nombre_limpio = limpiar_texto_para_busqueda(nombre)
    datos = {
        "nombre": nombre_limpio, 
        "email": limpiar_texto_para_busqueda(correo), 
        "telefono": limpiar_texto_para_busqueda(telefono),
        "rut": limpiar_texto_para_busqueda(rut),
        "direccion": limpiar_texto_para_busqueda(direccion)
    }
    
    try:
        if cliente_id_existente:
            conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
            return cliente_id_existente, ""
        else:
            # VALIDACIÓN ANTI-DUPLICADOS
            res_check = conn.table("clientes").select("cliente_id").eq("nombre", nombre_limpio).execute()
            if res_check.data:
                return None, f"¡DUPLICADO DETENIDO! Ya existe un cliente registrado con el nombre '{nombre_limpio}'."
                
            datos["status"] = "CLIENTE REGULAR"
            response = conn.table("clientes").insert(datos).execute()
            return response.data[0]['cliente_id'], ""
    except Exception as e: 
        log_error("vista_caja", "gestionar_cliente", f"Error: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return None, f"No se pudo {'actualizar' if cliente_id_existente else 'crear'} al cliente '{nombre}'. Detalle: {e}"

def cargar_historial_completo():
    conn = get_db_connection()
    try:
        # Traemos también los datos del cliente usando un JOIN
        res_ventas = conn.table("registro_ventas").select("*, cliente:clientes(cliente_id, nombre, rut, email, telefono)").order("venta_id", desc=True).execute()
        if not res_ventas.data: return pd.DataFrame()
        
        df_ventas = pd.DataFrame(res_ventas.data)
        
        # Aplanar los datos del cliente para que queden como columnas en la tabla
        if 'cliente' in df_ventas.columns:
            df_clientes_data = pd.json_normalize(df_ventas['cliente']).add_prefix('cliente_')
            df_ventas = pd.concat([df_ventas.drop(columns=['cliente']), df_clientes_data], axis=1)
            df_ventas['cliente_nombre'] = df_ventas['cliente_nombre'].fillna('Cliente Eliminado')
        else: 
            df_ventas['cliente_nombre'] = 'Sin Cliente'
            df_ventas['cliente_rut'] = ''
            df_ventas['cliente_email'] = ''
            df_ventas['cliente_telefono'] = ''
            df_ventas['cliente_id'] = None
            
        def formatear_libros(libros_data):
            if not isinstance(libros_data, str) or not libros_data.strip(): return "Sin Detalle"
            if libros_data.strip().startswith('['):
                try:
                    libros = json.loads(libros_data)
                    return " | ".join([f"{item.get('cantidad', 1)} x {item.get('titulo', 'N/A')}" for item in libros])
                except: return libros_data
            else: return libros_data
                
        df_ventas['libros_vendidos'] = df_ventas['libros_vendidos'].apply(formatear_libros)
        
        # Mantenemos el nombre_cliente antiguo para compatibilidad con código existente
        df_ventas['nombre_cliente'] = df_ventas['cliente_nombre']
        
        df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0)
        df_ventas['abono'] = pd.to_numeric(df_ventas.get('abono', 0), errors='coerce').fillna(0)
        df_ventas['costo_venta'] = pd.to_numeric(df_ventas.get('costo_venta', 0), errors='coerce').fillna(0)
        df_ventas['estado_pago'] = df_ventas.get('estado_pago', 'PENDIENTE').fillna('PENDIENTE')
        df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
        df_ventas['utilidad'] = df_ventas['monto_final'] - df_ventas['costo_venta']
        
        if 'fecha_pago' not in df_ventas.columns:
            df_ventas['fecha_pago'] = pd.NaT
        df_ventas['fecha_pago'] = pd.to_datetime(df_ventas['fecha_pago'], errors='coerce').dt.date
        
        return df_ventas
    except Exception as e:
        log_error("vista_caja", "cargar_historial_completo", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error(f"Error crítico al cargar el historial de ventas: {e}")
        return pd.DataFrame()

def gestionar_libro(titulo, autor, precio_catalogo, stock_a_sumar, libro_id_existente=None, encuadernacion="", editorial=""):
    conn = get_db_connection()
    datos = {
        "titulo": limpiar_texto_para_busqueda(titulo), 
        "autor": limpiar_texto_para_busqueda(autor), 
        "precio": float(precio_catalogo),
        "encuadernacion": limpiar_texto_para_busqueda(encuadernacion),
        "editorial": limpiar_texto_para_busqueda(editorial)
    }
    
    if libro_id_existente:
        datos_actualizar = {k: v for k, v in datos.items() if v}
        if datos_actualizar:
            conn.table("libros").update(datos_actualizar).eq("libro_id", libro_id_existente).execute()
        return libro_id_existente
    else:
        datos["stock"] = int(stock_a_sumar)
        datos["precio_original"] = float(precio_catalogo)
        response = conn.table("libros").insert(datos).execute()
        return response.data[0]['libro_id']

def procesar_venta_carrito(carrito, cliente_id, valor_envio, metodo_envio, metodo_pago, comentario, fecha_venta, estado_venta, estado_pago, fecha_pago, abono_venta, asignacion_id=None):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    
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
            "estado_pago": estado_pago, 
            "fecha_pago": fecha_pago.isoformat() if fecha_pago else None,
            "abono": float(abono_venta), "costo_venta": float(costo_total_venta) 
        }
        conn.table("registro_ventas").insert(datos_venta).execute()
        
        for item in carrito:
            l_id = item['libro_id']
            if item['es_nuevo']: 
                l_id = gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], item['cantidad'], None, item.get('encuadernacion', ''), item.get('editorial', ''))
            else:
                gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], 0, l_id)
                nuevo_stock = item['stock_actual'] - item['cantidad']
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
            
            if cliente_id and l_id:
                res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", l_id).execute()
                if not res_hist.data:
                    datos_historico = {"cliente_id": cliente_id, "libro_id": l_id, "autor_historico": limpiar_texto_para_busqueda(item['autor']), "origen": "VENTA CAJA"}
                    conn.table("librero_historico").insert(datos_historico).execute()

        if asignacion_id:
            try:
                res_asig = conn.table("asignaciones").select("extras, valor_extras").eq("asignacion_id", asignacion_id).execute()
                if res_asig.data:
                    asig_actual = res_asig.data[0]
                    extras_previos_raw = asig_actual.get('extras') or ""
                    valor_previo = float(asig_actual.get('valor_extras') or 0.0)
                    
                    lista_extras_previos = []
                    if extras_previos_raw:
                        items = extras_previos_raw.replace('\n', '|').split('|')
                        for item in items:
                            item_limpio = item.strip()
                            if '.' in item_limpio:
                                item_limpio = item_limpio.split('.', 1)[-1].strip()
                            if item_limpio:
                                lista_extras_previos.append(item_limpio.upper())
                                
                    nuevos_extras_list = [f"{item['cantidad']} x {item['titulo']}".upper() for item in carrito]
                    lista_completa = lista_extras_previos + nuevos_extras_list
                    extras_final_enumerado = "\n".join([f"{i+1}. {libro}" for i, libro in enumerate(lista_completa)])
                    valor_final = valor_previo + subtotal_libros
                    
                    conn.table("asignaciones").update({
                        "extras": extras_final_enumerado, 
                        "valor_extras": valor_final
                    }).eq("asignacion_id", asignacion_id).execute()
                    
            except Exception as ex_asig:
                log_error("vista_caja", "procesar_venta_carrito (actualizar extras)", f"Error {ex_asig}", email_usuario)
                st.warning(f"⚠️ Venta procesada, pero no se registraron extras en la suscripción. Detalle: {ex_asig}")

        return True, ""

    except Exception as e:
        error_detalle = f"Fallo crítico registrando venta. Detalle técnico: {e}"
        log_error("vista_caja", "procesar_venta_carrito", error_detalle, email_usuario)
        return False, str(e)

def anular_venta(venta_id, texto_libros_vendidos):
    conn = get_db_connection()
    try:
        items = texto_libros_vendidos.split(" | ")
        for item in items:
            partes = item.split(" x ", 1)
            if len(partes) == 2:
                try:
                    cantidad_devuelta = int(partes[0].strip())
                    titulo_libro = partes[1].strip()
                except ValueError:
                    continue
                res_l = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_libro).execute()
                if res_l.data:
                    l_id, nuevo_stock = res_l.data[0]['libro_id'], res_l.data[0]['stock'] + cantidad_devuelta
                    conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
                    
        conn.table("registro_ventas").delete().eq("venta_id", venta_id).execute()
        return True, ""
    except Exception as e:
        log_error("vista_caja", "anular_venta", e, st.session_state.get('email_usuario', 'Desconocido'))
        return False, str(e)

def actualizar_historial_caja(df_editado):
    df_original = st.session_state.get('historial_original', pd.DataFrame())
    if df_original.empty: return 0

    # ✅ CORRECCIÓN: Convertimos todo a string antes de comparar para evitar errores de tipo
    # Esto hace que las diferencias de formato (ej. None vs NaT) se ignoren
    df_original_str = df_original.astype(str)
    df_editado_str = df_editado.astype(str)

    # Comparamos las versiones en texto
    diff_mask = df_original_str.ne(df_editado_str).any(axis=1)
    filas_cambiadas = df_editado[diff_mask]
    
    if filas_cambiadas.empty:
        st.info("No se detectaron cambios para guardar.")
        return 0

    conn = get_db_connection()
    updates = 0
    for venta_id, row in filas_cambiadas.iterrows():
        try:
            # 1. DATOS DEL CLIENTE
            cliente_id = row.get('cliente_cliente_id') # El ID viene con prefijo del JOIN
            if cliente_id and pd.notna(cliente_id):
                datos_cliente = {
                    'nombre': limpiar_texto_para_busqueda(row.get('cliente_nombre')),
                    'rut': limpiar_texto_para_busqueda(row.get('cliente_rut')),
                    'email': limpiar_texto_para_busqueda(row.get('cliente_email')),
                    'telefono': limpiar_texto_para_busqueda(row.get('cliente_telefono'))
                }
                datos_cliente_limpios = {k: v for k, v in datos_cliente.items() if pd.notna(v) and v != 'nan'}
                if datos_cliente_limpios:
                    conn.table("clientes").update(datos_cliente_limpios).eq("cliente_id", int(cliente_id)).execute()

            # 2. DATOS DE LA VENTA
            datos_venta_raw = {k: v for k, v in row.items() if not k.startswith('cliente_')}
            
            monto_final_actual = float(row.get('monto_final', df_original.loc[venta_id, 'monto_final']))
            if datos_venta_raw.get('estado') == 'FINALIZADO' or datos_venta_raw.get('estado_pago') == 'PAGADO':
                datos_venta_raw['estado_pago'] = 'PAGADO'
                datos_venta_raw['abono'] = monto_final_actual

            datos_venta_final = {}
            columnas_venta_validas = ['monto_final', 'abono', 'costo_venta', 'estado', 'estado_pago', 'fecha_pago', 'metodo_envio', 'comentario']
            for col in columnas_venta_validas:
                if col in datos_venta_raw:
                    valor = datos_venta_raw[col]
                    if col == 'fecha_pago':
                        datos_venta_final[col] = pd.to_datetime(valor).isoformat() if pd.notna(valor) else None
                    else:
                        datos_venta_final[col] = valor

            if datos_venta_final:
                conn.table("registro_ventas").update(datos_venta_final).eq("venta_id", venta_id).execute()
            
            updates += 1
        except Exception as e:
            log_error("vista_caja", "actualizar_historial_caja", f"Error en venta #{venta_id}: {e}", st.session_state.get('email_usuario', 'Desconocido'))
            st.warning(f"No se pudo guardar la fila de la venta #{venta_id}.")
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
                    st.sidebar.warning(f"👤 **{row['cliente_nombre']}**\n💰 Deuda: ${row['deuda']:,.0f}\n⏳ {row['dias_mora']} días")
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
            l_id, l_titulo, l_autor, l_precio_catalogo, l_stock_actual, l_costo, es_nuevo, l_encuadernacion = None, "", "", 0.0, 0, 0.0, False, ""
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
                        l_editorial = datos_l.get('editorial', '') 
                        with st.expander("✏️ Actualizar Catálogo (Opcional)", expanded=False):
                            l_autor = st.text_input("Autor:", value=l_autor)
                            l_precio_catalogo = st.number_input("Precio Oficial ($):", value=l_precio_catalogo, step=100.0)
                else: st.warning("El inventario está vacío.")
            else:
                es_nuevo = True
                autores_db, editoriales_db = cargar_listas_desplegables_caja()
                
                l_titulo = st.text_input("Título del libro:")
                
                col_rap1, col_rap2 = st.columns(2)
                
                opciones_autor = ["➕ Crear Nuevo Autor"] + autores_db
                sel_autor = col_rap1.selectbox("Autor:", options=opciones_autor, placeholder="Busca o selecciona un autor...", index=None)

                if sel_autor == "➕ Crear Nuevo Autor":
                    l_autor = col_rap1.text_input("Nombre del nuevo autor:", key="nuevo_autor_caja") # Usamos una key única
                elif sel_autor: # Si se seleccionó algo
                    l_autor = sel_autor
                else: # Si no se seleccionó nada
                    l_autor = ""
                    
                opciones_editorial = ["➕ Crear Nueva Editorial"] + editoriales_db
                sel_edit = col_rap2.selectbox("Editorial:", options=opciones_editorial, placeholder="Busca o selecciona una editorial...", index=None)

                if sel_edit == "➕ Crear Nueva Editorial":
                    l_editorial = col_rap2.text_input("Nombre de la nueva editorial:", key="nueva_editorial_caja") # Usamos una key única
                elif sel_edit: # Si se seleccionó algo
                    l_editorial = sel_edit
                else: # Si no se seleccionó nada
                    l_editorial = ""

                l_encuadernacion = st.selectbox("Encuadernación:", ["", "TAPA BLANDA", "TAPA DURA", "BOLSILLO"])
                
                col_num1, col_num2 = st.columns(2)
                l_precio_catalogo = col_num1.number_input("Precio Oficial ($):", min_value=0.0, step=100.0)
                l_costo = col_num2.number_input("Costo del libro nuevo ($):", min_value=0.0, step=100.0)
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
                        'libro_id': l_id, 'titulo': l_titulo, 'autor': l_autor, 'editorial': l_editorial,
                        'precio_catalogo': l_precio_catalogo, 'precio_cobrado': precio_a_cobrar, 
                        'cantidad': cantidad, 'subtotal': precio_a_cobrar * cantidad,
                        'stock_actual': l_stock_actual, 'costo': l_costo, 'es_nuevo': es_nuevo,
                        'encuadernacion': l_encuadernacion
                    })
                    st.success(f"{l_titulo} añadido.")
                    st.rerun()
                    
        subtotal_carrito = 0
        if len(st.session_state.carrito_caja) > 0:
            st.markdown("#### 🛒 Tu Carrito Actual")
            df_carrito = pd.DataFrame(st.session_state.carrito_caja)
            df_carrito.insert(0, 'Quitar', False)
            
            df_editado_carrito = st.data_editor(
                df_carrito[['Quitar', 'cantidad', 'titulo', 'precio_cobrado', 'subtotal']], 
                hide_index=True, 
                use_container_width=True,
                column_config={"Quitar": st.column_config.CheckboxColumn("Quitar ❌", default=False)}
            )
            
            subtotal_carrito = df_carrito['subtotal'].sum()
            
            col_cart1, col_cart2 = st.columns(2)
            if col_cart1.button("🗑️ Quitar Seleccionados"):
                indices_a_quitar = df_editado_carrito[df_editado_carrito['Quitar'] == True].index.tolist()
                if indices_a_quitar:
                    for i in sorted(indices_a_quitar, reverse=True):
                        st.session_state.carrito_caja.pop(i)
                    st.rerun()
                else:
                    st.warning("Marca la casilla 'Quitar ❌' en los libros que desees eliminar.")
                    
            if col_cart2.button("🗑️ Vaciar Todo el Carrito"):
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
                res_cajas = conn.table("asignaciones").select("asignacion_id, mes, estado_envio").eq("cliente_id", c_id).execute()
                cajas_abiertas = [c for c in res_cajas.data if c.get('estado_envio', '') not in ["ENVIADO", "ENTREGADO/RETIRADO", "RETIRADO"]]
                if cajas_abiertas:
                    opciones_cajas = [f"Suscripción {c['mes']} - {c.get('estado_envio','')} (ID: {c['asignacion_id']})" for c in cajas_abiertas]
                    caja_sel = col_e2.selectbox("Caja de Suscripción abierta:", opciones_cajas)
                    asignacion_id_target = int(caja_sel.split("(ID: ")[1].strip(")"))
                    metodo_envio_final = f"Agregado a {caja_sel.split(' -')[0]}"
                    st.info("Los libros se agregarán como Extras a la caja seleccionada (Envío $0).")
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
        st.markdown("#### ⚙️ Estado y Abono")
        col_abono1, col_abono2, col_abono3, col_abono4 = st.columns(4)
        
        estado_venta_sel = col_abono1.selectbox("Estado de la Venta:", estados_posibles, index=0)
        estado_pago_sel = col_abono2.selectbox("Estado del Pago:", ["PENDIENTE", "PAGADO"], index=0)
        fecha_pago_sel = col_abono3.date_input("Fecha de Pago:", value=None)
        
        monto_final = subtotal_carrito + valor_envio
        abono_default = 0.0
        mensaje_exito = ""

        if estado_venta_sel == "FINALIZADO" or estado_pago_sel == "PAGADO":
            abono_default = monto_final
            estado_pago_sel = "PAGADO"
            mensaje_exito = "💡 Venta FINALIZADA/PAGADA: El abono se iguala al monto total."

        abono_inicial = col_abono4.number_input("Abono Inicial ($):", min_value=0.0, step=1000.0, value=abono_default)

        if mensaje_exito:
            st.success(mensaje_exito)

        st.markdown(f"<div style='background-color:#E6F3E6; border:2px solid #4CAF50; padding:15px; border-radius:10px; text-align:center;'><p style='color:#2E7D32; margin:0;'>Subtotal Libros: ${subtotal_carrito:,.0f} | Envío: ${valor_envio:,.0f}</p><h2 style='color:#2E7D32; margin:0;'>MONTO FINAL: ${monto_final:,.0f}</h2><p style='color:#1B5E20; margin:0; font-weight:bold;'>Abono Registrado: ${abono_inicial:,.0f} | Deuda: ${(monto_final - abono_inicial):,.0f}</p></div>", unsafe_allow_html=True)
        st.write("")
        
        desactivar_boton = not c_nombre or len(st.session_state.carrito_caja) == 0 or bloquear_venta
        
        if st.button("✅ CONFIRMAR VENTA TOTAL", type="primary", use_container_width=True, disabled=desactivar_boton):
            with st.spinner("Procesando Venta..."):
                final_cliente_id, error_cliente = gestionar_cliente(c_nombre, c_correo, c_telefono, c_rut, c_direccion, c_id)
                
                if error_cliente:
                    st.error(error_cliente)
                else:
                    exito, err = procesar_venta_carrito(
                        st.session_state.carrito_caja, final_cliente_id, valor_envio, 
                        metodo_envio_final, metodo_pago, comentario_venta, fecha_venta_manual,
                        estado_venta_sel, estado_pago_sel, fecha_pago_sel, abono_inicial, asignacion_id_target
                    )
                    if exito: 
                        st.success("🎉 ¡Venta registrada y extras agregados (si aplica)!")
                        st.balloons()
                        time.sleep(2)
                        st.session_state.carrito_caja = []
                        st.rerun()
                    else: 
                        st.error(f"Error: {err}")
                    
    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        df_ventas = df_ventas_global.copy()
        
        if df_ventas.empty: 
            st.info("Aún no hay ventas registradas.")
        else:
            fechas_invalidas = df_ventas['fecha_limpia'].isna()
            if fechas_invalidas.any():
                with st.expander(f"⚠️ Atención: {fechas_invalidas.sum()} ventas tienen fechas ilegibles"):
                    st.dataframe(df_ventas[fechas_invalidas][['venta_id', 'fecha_venta', 'cliente_nombre']], hide_index=True)
            with st.expander("🔍 Filtros del Historial"):
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
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
                
                clientes_hist = ["Todos"] + sorted(df_ventas['cliente_nombre'].unique().tolist())
                cliente_filtro = col_f2.selectbox("Filtrar Cliente:", clientes_hist)
                estados_hist = ["Todos"] + sorted(df_ventas['estado'].unique().tolist())
                estado_filtro = col_f3.selectbox("Filtrar Estado:", estados_hist)
                estado_pago_filtro = col_f4.selectbox("Filtrar Pago:", ["Todos", "PAGADO", "PENDIENTE"])
                
                st.markdown("---")
                col_chk1, col_chk2 = st.columns(2)
                mes_en_curso = col_chk1.checkbox("📅 Mostrar rápido: Solo este mes", value=False)
                solo_costo_cero = col_chk2.checkbox("⚠️ Mostrar rápido: Ventas sin costo asignado ($0)", value=False)
                st.markdown("---")
                columnas_hist_todas = ['venta_id', 'fecha_venta', 'fecha_pago', 'cliente_nombre', 'cliente_rut', 'cliente_email', 'cliente_telefono', 'libros_vendidos', 'monto_final', 'abono', 'deuda', 'utilidad', 'costo_venta', 'estado', 'estado_pago', 'metodo_envio', 'comentario']
                columnas_por_defecto = ['venta_id', 'fecha_venta', 'cliente_nombre', 'libros_vendidos', 'monto_final', 'abono', 'deuda', 'estado', 'estado_pago', 'fecha_pago']
                columnas_a_mostrar = st.multiselect("👀 Mostrar / Ocultar Columnas en Tabla", columnas_hist_todas, default=columnas_por_defecto)
                
            df_filtrado_general = df_ventas.copy()
            if mes_en_curso:
                df_filtrado_general = df_filtrado_general[(df_filtrado_general['fecha_limpia'].dt.date >= primer_dia_mes) & (df_filtrado_general['fecha_limpia'].dt.date <= limite_max)]
            elif len(rango_fechas) == 2:
                df_filtrado_general = df_filtrado_general[(df_filtrado_general['fecha_limpia'].dt.date >= rango_fechas[0]) & (df_filtrado_general['fecha_limpia'].dt.date <= rango_fechas[1])]
                
            if cliente_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['cliente_nombre'] == cliente_filtro]
            if estado_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['estado'] == estado_filtro]
            if estado_pago_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['estado_pago'] == estado_pago_filtro]
                
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
                "deuda": st.column_config.NumberColumn("Deuda", format="$%.0f", disabled=True),
                "utilidad": st.column_config.NumberColumn("Utilidad", format="$%.0f", disabled=True),
                "costo_venta": st.column_config.NumberColumn("Costo Venta", format="$%.0f"),
                "estado": st.column_config.SelectboxColumn("Estado Venta", options=estados_posibles),
                "estado_pago": st.column_config.SelectboxColumn("Estado Pago", options=["PENDIENTE", "PAGADO"]),
                "fecha_pago": st.column_config.DateColumn("Fecha Pago", format="DD/MM/YYYY"),
                "cliente_nombre": st.column_config.TextColumn("Nombre Cliente"),
                "cliente_rut": st.column_config.TextColumn("RUT Cliente"),
                "cliente_email": st.column_config.TextColumn("Email Cliente"),
                "cliente_telefono": st.column_config.TextColumn("Teléfono Cliente")
            }
            
            if 'costo_venta' in df_mostrar.columns:
                df_estilizado = df_mostrar.style.apply(lambda s: ['background-color: #ffebee; color: #c62828; font-weight: bold;' if v == 0 else '' for v in s], subset=['costo_venta'])
            else: df_estilizado = df_mostrar
                
            disabled_cols = ['venta_id', 'fecha_venta', 'libros_vendidos', 'deuda', 'utilidad']
            disabled_cols_active = [c for c in disabled_cols if c in columnas_a_mostrar]
            
            df_editado = st.data_editor(df_estilizado, disabled=disabled_cols_active, use_container_width=True, hide_index=True, column_config=config_cols_hist)
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Historial", type="primary"):
                    num = actualizar_historial_caja(df_editado)
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
                    clientes_cob = ["Todos"] + sorted(df_deudores['cliente_nombre'].unique().tolist())
                    cliente_filtro_c = col_c2.selectbox("Filtrar por Cliente:", clientes_cob, key="cliente_cob")
                if len(rango_fechas_c) == 2:
                    df_deudores = df_deudores[(df_deudores['fecha_limpia'].dt.date >= rango_fechas_c[0]) & (df_deudores['fecha_limpia'].dt.date <= rango_fechas_c[1])]
                if cliente_filtro_c != "Todos":
                    df_deudores = df_deudores[df_deudores['cliente_nombre'] == cliente_filtro_c]
                if df_deudores.empty: st.info("No hay deudas que coincidan con los filtros actuales.")
                else:
                    st.markdown(f"#### 💰 Total por Cobrar (Filtrado): **${df_deudores['deuda'].sum():,.0f}**")
                    df_deudores['Nivel Mora'] = df_deudores['dias_mora'].apply(lambda x: "🔴 Crítico (>14 días)" if x > 14 else ("🟡 Medio (7-14 días)" if x > 7 else "🟢 Normal"))
                    columnas_mostrar_cob = ['fecha_venta', 'cliente_nombre', 'monto_final', 'abono', 'deuda', 'Nivel Mora', 'estado', 'estado_pago']
                    st.dataframe(df_deudores[columnas_mostrar_cob], hide_index=True, use_container_width=True, 
                        column_config={
                            "monto_final": st.column_config.NumberColumn("Monto Venta", format="$%.0f"),
                            "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                            "deuda": st.column_config.NumberColumn("Deuda Pendiente", format="$%.0f"),
                            "cliente_nombre": st.column_config.TextColumn("Nombre Cliente")
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