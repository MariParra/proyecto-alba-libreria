import streamlit as st
import pandas as pd
from datetime import datetime
import json
import time
from utilidades import get_db_connection, log_error, limpiar_texto_para_busqueda

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=600)
def cargar_catalogo_libros_vm():
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        # Bucle seguro de rango amplio (hasta 100.000 libros)
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("libros")\
                .select("libro_id, titulo, autor, stock, genero, editorial")\
                .order("titulo")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_catalogo_libros_vm", e)
        st.error("No se pudo cargar el catálogo de libros.")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def cargar_listas_desplegables():
    """Obtiene los valores únicos existentes para Autor, Género y Editorial desde la BD."""
    try:
        # Reutilizamos la función cacheada y paginada para evitar 3 llamadas API pesadas
        df_libros = cargar_catalogo_libros_vm()
        if df_libros.empty:
            return [], [], []
        
        autores = sorted(list(set(df_libros['autor'].dropna().tolist())))
        generos = sorted(list(set(df_libros['genero'].dropna().tolist())))
        editoriales = sorted(list(set(df_libros['editorial'].dropna().tolist())))
        
        # Filtramos textos vacíos
        autores = [a for a in autores if str(a).strip()]
        generos = [g for g in generos if str(g).strip()]
        editoriales = [e for e in editoriales if str(e).strip()]
        
        return autores, generos, editoriales
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_listas_desplegables", e)
        return [], [], []

@st.cache_data(ttl=300)
def cargar_historial_ventas_masivas():
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        # Bucle dinámico (hasta 100.000 eventos de ventas masivas)
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("ventas_masivas")\
                .select("*")\
                .order("fecha_evento", desc=True)\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_historial_ventas_masivas", e)
        st.error("No se pudo cargar el historial de ventas masivas.")
        return pd.DataFrame()

def procesar_nueva_venta_masiva(datos_evento):
    """Inserta una nueva venta masiva, crea libros nuevos y descuenta el stock."""
    conn = get_db_connection()
    
    if datos_evento.get("libros_implicados"):
        for libro in datos_evento["libros_implicados"]:
            if libro.get("es_nuevo"):
                try:
                    datos_libro = {
                        "titulo": limpiar_texto_para_busqueda(libro["titulo"]),
                        "autor": limpiar_texto_para_busqueda(libro.get("autor", "")),
                        "genero": limpiar_texto_para_busqueda(libro.get("genero", "")),
                        "editorial": limpiar_texto_para_busqueda(libro.get("editorial", "")),
                        "encuadernacion": limpiar_texto_para_busqueda(libro.get("encuadernacion", "")),
                        "precio": float(libro.get("precio", 0)),
                        "precio_original": float(libro.get("precio", 0)),
                        "costo": float(libro.get("costo", 0)),
                        "stock": int(libro.get("stock_inicial", 0))
                    }
                    res = conn.table("libros").insert(datos_libro).execute()
                    nuevo_id = res.data[0]['libro_id']
                    libro["libro_id"] = nuevo_id 
                except Exception as e:
                    log_error("vista_ventas_masivas", "crear_libro_nuevo", f"Error al crear {libro.get('titulo')}: {e}")
                    return False, f"Error al crear el libro nuevo '{libro.get('titulo')}'. Detalle: {e}"

    if datos_evento.get("stock_descontado") and datos_evento.get("libros_implicados"):
        try:
            with st.spinner("Descontando stock de libros..."):
                for libro in datos_evento["libros_implicados"]:
                    if libro.get("libro_id") and libro.get("cantidad") > 0:
                        res_stock = conn.table("libros").select("stock").eq("libro_id", libro["libro_id"]).single().execute()
                        stock_actual = res_stock.data.get('stock', 0)
                        nuevo_stock = stock_actual - libro["cantidad"]
                        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro["libro_id"]).execute()
        except Exception as e:
            log_error("vista_ventas_masivas", "descontar_stock", e)
            return False, f"Error al descontar stock. La venta NO se registró. Detalle: {e}"

    try:
        with st.spinner("Registrando la venta masiva..."):
            if 'libros_implicados' in datos_evento:
                datos_evento['libros_implicados'] = json.dumps(datos_evento['libros_implicados'], ensure_ascii=False)
            conn.table("ventas_masivas").insert(datos_evento).execute()
        return True, ""
    except Exception as e:
        log_error("vista_ventas_masivas", "insertar_evento", e)
        return False, f"Error al registrar el evento: {e}"

def anular_venta_masiva(evento_id, stock_fue_descontado, libros_implicados_json):
    conn = get_db_connection()
    if stock_fue_descontated and libros_implicados_json:
        try:
            libros = json.loads(libros_implicados_json) if isinstance(libros_implicados_json, str) else libros_implicados_json
            with st.spinner("Restaurando stock al inventario..."):
                for libro in libros:
                    if libro.get("libro_id") and libro.get("cantidad", 0) > 0:
                        res_stock = conn.table("libros").select("stock").eq("libro_id", libro["libro_id"]).single().execute()
                        stock_actual = res_stock.data.get('stock', 0)
                        nuevo_stock = stock_actual + libro["cantidad"]
                        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro["libro_id"]).execute()
        except Exception as e:
            log_error("vista_ventas_masivas", "anular_venta_masiva", e)
            st.error(f"No se pudo restaurar el stock por completo. Detalle: {e}")
    try:
        with st.spinner("Anulando el registro de la venta..."):
            conn.table("ventas_masivas").delete().eq("evento_id", evento_id).execute()
        return True, ""
    except Exception as e:
        log_error("vista_ventas_masivas", "anular_venta_masiva (eliminar)", e)
        return False, f"Error al anular la venta: {e}"

# --- EVENTOS Y CALLBACKS ---

def on_estado_evento_change():
    """Si el estado cambia a FINALIZADO, fuerza el pago a PAGADO en tiempo real"""
    if st.session_state.vm_estado_evento == "FINALIZADO":
        st.session_state.vm_estado_pago = "PAGADO"

def anadir_nuevo_libro_carrito():
    """Callback que procesa, valida, añade al carrito y limpia los inputs de forma segura."""
    titulo = st.session_state.get('tmp_titulo', '').strip()
    
    # --- Resolver Selectboxes combinados desde memoria ---
    sel_autor = st.session_state.get('sel_autor')
    if sel_autor == "➕ Crear Nuevo Autor":
        autor = st.session_state.get('tmp_autor_nuevo', '').strip()
    elif sel_autor:
        autor = sel_autor
    else:
        autor = ""
        
    sel_gen = st.session_state.get('sel_genero')
    if sel_gen == "➕ Crear Nuevo Género":
        genero = st.session_state.get('tmp_genero_nuevo', '').strip()
    elif sel_gen:
        genero = sel_gen
    else:
        genero = ""
        
    sel_edit = st.session_state.get('sel_editorial')
    if sel_edit == "➕ Crear Nueva Editorial":
        editorial = st.session_state.get('tmp_editorial_nueva', '').strip()
    elif sel_edit:
        editorial = sel_edit
    else:
        editorial = ""

    encuadernacion = st.session_state.get('tmp_encuadernacion', '')
    precio = st.session_state.get('tmp_precio', 0.0)
    costo = st.session_state.get('tmp_costo', 0.0)
    stock = st.session_state.get('tmp_stock', 0)
    cant = st.session_state.get('tmp_cant', 1)
    
    if not titulo:
        st.session_state['vm_error_libro'] = "El Título es obligatorio."
        return
        
    titulo_limpio = limpiar_texto_para_busqueda(titulo)
    conn = get_db_connection()
    res_check = conn.table("libros").select("titulo").eq("titulo", titulo_limpio).execute()
    
    if res_check.data:
        st.session_state['vm_error_libro'] = f"🚫 DUPLICADO: Ya existe un libro con el título '{titulo_limpio}' en tu catálogo."
        return
        
    # Añadimos al carrito
    st.session_state.vm_carrito.append({
        "libro_id": None, "titulo": titulo.upper(), "cantidad": cant, 
        "stock_actual": stock, "es_nuevo": True, "autor": autor.upper() if autor else "", 
        "genero": genero.upper() if genero else "", "editorial": editorial.upper() if editorial else "", 
        "encuadernacion": encuadernacion, "precio": precio, 
        "costo": costo, "stock_inicial": stock
    })
    
    # Limpiamos todos los campos temporales
    st.session_state['vm_error_libro'] = ""
    keys_to_clear = [
        'tmp_titulo', 'sel_autor', 'tmp_autor_nuevo', 'sel_genero', 'tmp_genero_nuevo', 
        'sel_editorial', 'tmp_editorial_nueva', 'tmp_encuadernacion', 'tmp_precio', 
        'tmp_costo', 'tmp_stock', 'tmp_cant'
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]

def unificar_formatos_fecha(serie_fechas):
    """
    Función de parseo de fechas a prueba de balas, capaz de interpretar
    múltiples formatos y de remover de forma segura zonas horarias (Timezones).
    """
    def parsear_valor(val):
        if pd.isna(val) or not str(val).strip() or str(val).strip().lower() in ['nan', 'nat']:
            return pd.NaT
        val_str = str(val).strip()
        try:
            if 't' in val_str.lower() or '+' in val_str:
                return pd.to_datetime(val_str).tz_localize(None)
            if len(val_str.split('-')[0]) == 4 or len(val_str.split('/')[0]) == 4:
                return pd.to_datetime(val_str, dayfirst=False, errors='coerce').tz_localize(None)
            else:
                return pd.to_datetime(val_str, dayfirst=True, errors='coerce').tz_localize(None)
        except Exception:
            try:
                return pd.to_datetime(val_str, errors='coerce').tz_localize(None)
            except Exception:
                return pd.NaT
    try:
        return serie_fechas.apply(parsear_valor)
    except Exception:
        return pd.to_datetime(serie_fechas, errors='coerce').dt.tz_localize(None)

# --- VISTA PRINCIPAL ---

def mostrar_ventas_masivas():
    st.title("📈 Ventas Masivas y Eventos")
    st.info("Utiliza esta sección para registrar ingresos y costos de eventos como ferias, rifas o ventas de bodega donde no hay un cliente único.")

    # --- INICIALIZACIÓN DE MEMORIA (Solo variables troncales) ---
    defaults = {
        'vm_carrito': [], 'vm_nombre_evento': "", 'vm_tipo_sel': "VENTA EN FERIA", 'vm_tipo_pers': "", 
        'vm_fecha_evento': None, 'vm_ingreso': 0.0, 'vm_costo': 0.0, 'vm_descontar_stock': False, 
        'vm_estado_evento': "POR EMPEZAR", 'vm_estado_pago': "PENDIENTE", 'vm_comentarios': "", 
        'vm_modo_libro': "📚 Existente en Catálogo", 'vm_error_libro': "", 'vm_limit_view': 50
    }
    for key in defaults:
        if key not in st.session_state:
            st.session_state[key] = defaults[key]

    tipos_evento_predefinidos = ["VENTA EN FERIA", "RIFA", "CLUB DE LECTURA", "EVENTO ESPECIAL", "VENTA DE BODEGA", "OTRO"]
    estados_evento = ["POR EMPEZAR", "EN CURSO", "FINALIZADO"]
    estados_pago = ["PENDIENTE", "PAGADO"]
    
    tab_nueva, tab_historial, tab_anular = st.tabs(["➕ Nueva Venta Masiva", "📜 Historial", "🚫 Anular"])

    with tab_nueva:
        st.markdown("### Registrar Nuevo Evento de Venta")
        
        # --- Información General ---
        st.markdown("#### 1. Información General del Evento")
        col1, col2 = st.columns(2)
        col1.text_input("Nombre o Descripción del Evento*", placeholder="Ej: FERIA DEL LIBRO DE VIÑA 2026", key="vm_nombre_evento")
        col2.selectbox("Tipo de Evento*", options=[""] + tipos_evento_predefinidos, key="vm_tipo_sel")
        
        if st.session_state.vm_tipo_sel == "OTRO":
            col2.text_input("Si elegiste 'OTRO', escríbelo aquí:", placeholder="Ej: DONACIÓN A COLEGIO", key="vm_tipo_pers")
            
        st.date_input("Fecha del Evento (Opcional)", key="vm_fecha_evento")

        # --- Datos Financieros ---
        st.markdown("#### 2. Datos Financieros")
        col_f1, col_f2 = st.columns(2)
        col_f1.number_input("Ingreso Total Bruto ($)*", min_value=0.0, step=10000.0, key="vm_ingreso")
        col_f2.number_input("Costo Total del Evento ($)", min_value=0.0, step=5000.0, help="Incluye costos de stand, traslados, etc.", key="vm_costo")

        # --- Gestión de Libros y Stock ---
        st.markdown("#### 3. Libros y Gestión de Stock (Opcional)")
        st.checkbox("Descontar stock de los libros asociados a este evento", key="vm_descontar_stock")
        
        with st.container(border=True):
            st.radio("Añadir libro a la lista:", ["📚 Existente en Catálogo", "➕ Crear Nuevo Libro"], horizontal=True, label_visibility="collapsed", key="vm_modo_libro")
            
            if st.session_state.vm_modo_libro == "📚 Existente en Catálogo":
                df_libros_catalogo = cargar_catalogo_libros_vm()
                if not df_libros_catalogo.empty:
                    df_libros_catalogo['label_busqueda'] = df_libros_catalogo.apply(lambda r: f"{r['titulo']} (Stock actual: {r['stock']})", axis=1)
                    col_b1, col_b2 = st.columns([3, 1])
                    
                    sel_libro_label = col_b1.selectbox(
                        "Busca un libro:", 
                        options=df_libros_catalogo['label_busqueda'].tolist(),
                        index=None,
                        placeholder="📚 Busca o selecciona un libro...",
                        key="sel_libro_vm"
                    )
                    
                    cant_descontar = col_b2.number_input("Cantidad implicada:", min_value=1, step=1, value=1)
                    
                    if st.button("➕ Añadir a la lista", type="secondary"):
                        if sel_libro_label:
                            libro_data = df_libros_catalogo[df_libros_catalogo['label_busqueda'] == sel_libro_label].iloc[0]
                            if not any(d['titulo'] == libro_data['titulo'] for d in st.session_state.vm_carrito):
                                st.session_state.vm_carrito.append({
                                    "libro_id": int(libro_data['libro_id']), "titulo": libro_data['titulo'], 
                                    "cantidad": cant_descontar, "stock_actual": int(libro_data['stock']), "es_nuevo": False
                                })
                                
                                if 'sel_libro_vm' in st.session_state:
                                    del st.session_state.sel_libro_vm
                                
                                st.success(f"'{libro_data['titulo']}' añadido al carrito.")
                                time.sleep(1)
                            else:
                                st.warning("El libro ya está en la lista. Ajusta la cantidad en la tabla de abajo.")
                        else:
                            st.error("Debes seleccionar un libro.")
                else:
                    st.warning("El catálogo está vacío.")
                    
            elif st.session_state.vm_modo_libro == "➕ Crear Nuevo Libro":
                st.info("💡 Este libro se creará en el catálogo general. Todos los textos se guardarán en mayúsculas y sin tildes.")
                
                # Cargamos listas inteligentes de la BD (Optimizadas sin múltiples llamadas API)
                autores_db, generos_db, editoriales_db = cargar_listas_desplegables()
                
                # Desplegamos errores generados desde el callback
                if st.session_state.get('vm_error_libro'):
                    st.error(st.session_state['vm_error_libro'])
                
                st.text_input("Título*", key="tmp_titulo")
                
                col_n1, col_n2, col_n3 = st.columns(3)
                
                # Selector de Autor Inteligente
                opciones_autor = ["➕ Crear Nuevo Autor"] + autores_db
                sel_autor = col_n1.selectbox("Autor", options=opciones_autor, key="sel_autor", index=None, placeholder="Busca o selecciona...")
                if sel_autor == "➕ Crear Nuevo Autor":
                    col_n1.text_input("Nombre del nuevo autor", key="tmp_autor_nuevo")
                    
                # Selector de Género Inteligente
                opciones_genero = ["➕ Crear Nuevo Género"] + generos_db
                sel_gen = col_n2.selectbox("Género", options=opciones_genero, key="sel_genero", index=None, placeholder="Busca o selecciona...")
                if sel_gen == "➕ Crear Nuevo Género":
                    col_n2.text_input("Nombre del nuevo género", key="tmp_genero_nuevo")
                    
                # Selector de Editorial Inteligente
                opciones_editorial = ["➕ Crear Nueva Editorial"] + editoriales_db
                sel_edit = col_n3.selectbox("Editorial", options=opciones_editorial, key="sel_editorial", index=None, placeholder="Busca o selecciona...")
                if sel_edit == "➕ Crear Nueva Editorial":
                    col_n3.text_input("Nombre de la nueva editorial", key="tmp_editorial_nueva")
                
                col_n4, col_n5, col_n6, col_n7, col_n8 = st.columns(5)
                col_n4.selectbox("Encuadernación", ["", "TAPA BLANDA", "TAPA DURA", "ESPIRAL"], key="tmp_encuadernacion")
                col_n5.number_input("Precio Oficial ($)*", min_value=0.0, step=500.0, key="tmp_precio")
                col_n6.number_input("Costo ($)", min_value=0.0, step=500.0, key="tmp_costo")
                col_n7.number_input("Stock Inicial Total*", min_value=0, step=1, key="tmp_stock")
                col_n8.number_input("Cant. Implicada*", min_value=1, step=1, key="tmp_cant")
                
                # BOTÓN CONECTADO AL CALLBACK
                st.button("➕ Crear y Añadir a la lista", type="secondary", on_click=anadir_nuevo_libro_carrito)

        # --- Visualización del Carrito ---
        if st.session_state.vm_carrito:
            st.write("📋 **Lista de Libros Implicados:**")
            df_carrito = pd.DataFrame(st.session_state.vm_carrito)
            df_carrito.insert(0, 'Quitar', False)
            cols_to_show = ['Quitar', 'titulo', 'cantidad', 'stock_actual', 'es_nuevo']
            
            df_editado = st.data_editor(
                df_carrito[cols_to_show], 
                column_config={
                    "Quitar": st.column_config.CheckboxColumn("Quitar ❌", default=False), 
                    "titulo": st.column_config.TextColumn("Título", disabled=True), 
                    "cantidad": st.column_config.NumberColumn("Cant. Implicada", min_value=1, step=1), 
                    "stock_actual": st.column_config.NumberColumn("Stock en BD", disabled=True), 
                    "es_nuevo": st.column_config.CheckboxColumn("¿Nuevo?", disabled=True)
                }, 
                hide_index=True, use_container_width=True, key="editor_carrito_vm"
            )
            
            for i, row in df_editado.iterrows():
                st.session_state.vm_carrito[i]['cantidad'] = row['cantidad']
                
            if st.button("🗑️ Quitar Seleccionados de la Lista"):
                indices_a_quitar = df_editado[df_editado['Quitar'] == True].index.tolist()
                if indices_a_quitar:
                    for i in sorted(indices_a_quitar, reverse=True):
                        st.session_state.vm_carrito.pop(i)
                    st.rerun()
                else:
                    st.warning("Marca la casilla 'Quitar ❌' en los libros que desees eliminar.")

        st.markdown("---")
        
        # --- 4. Estado Final ---
        st.markdown("#### 4. Estado del Evento")
        col_e1, col_e2 = st.columns(2)
        
        col_e1.selectbox("Estado del Evento", options=estados_evento, key="vm_estado_evento", on_change=on_estado_evento_change)
        
        if st.session_state.vm_estado_evento == "FINALIZADO":
            st.info("💡 Evento FINALIZADO: El estado del pago se ha establecido automáticamente en PAGADO.")
            
        col_e2.selectbox("Estado del Pago", options=estados_pago, key="vm_estado_pago")
        st.text_area("Comentarios Adicionales (Opcional)", key="vm_comentarios")
        
        # --- BOTÓN FINAL DE GUARDADO ---
        if st.button("💾 GUARDAR VENTA MASIVA TOTAL", type="primary", use_container_width=True):
            nombre_limpio = st.session_state.vm_nombre_evento.upper().strip()
            comentarios_limpios = st.session_state.vm_comentarios.upper().strip()
            tipo_final = (st.session_state.vm_tipo_pers.upper().strip() if st.session_state.vm_tipo_sel == "OTRO" else st.session_state.vm_tipo_sel)

            if not nombre_limpio or not tipo_final:
                st.error("El nombre y el tipo de evento son obligatorios.")
            else:
                datos_para_db = {
                    "nombre_evento": nombre_limpio, 
                    "tipo_evento": tipo_final,
                    "fecha_evento": st.session_state.vm_fecha_evento.isoformat() if st.session_state.vm_fecha_evento else None,
                    "ingreso_total": st.session_state.vm_ingreso, 
                    "costo_total": st.session_state.vm_costo,
                    "libros_implicados": st.session_state.vm_carrito,
                    "stock_descontado": st.session_state.vm_descontar_stock,
                    "estado_evento": st.session_state.vm_estado_evento,
                    "estado_pago": st.session_state.vm_estado_pago,
                    "comentarios": comentarios_limpios
                }
                
                with st.spinner("Procesando evento masivo..."):
                    exito, error = procesar_nueva_venta_masiva(datos_para_db)
                    
                if exito:
                    st.success(f"¡Venta masiva '{nombre_limpio}' registrada con éxito!")
                    st.balloons()
                    
                    # Limpiamos la memoria completa respetando el ciclo de Streamlit
                    keys_to_clear = [k for k in st.session_state.keys() if k.startswith('vm_') or k.startswith('tmp_') or k.startswith('sel_')]
                    for k in keys_to_clear:
                        del st.session_state[k]
                            
                    cargar_historial_ventas_masivas.clear()
                    cargar_catalogo_libros_vm.clear()
                    cargar_listas_desplegables.clear()
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"No se pudo registrar la venta. Detalle: {error}")

    with tab_historial:
        st.markdown("### 📜 Historial de Ventas Masivas")
        df_historial = cargar_historial_ventas_masivas()
        
        if df_historial.empty:
            st.info("Aún no se han registrado ventas masivas.")
        else:
            # 1. Procesamiento y normalización de fechas
            df_historial['fecha_limpia'] = unificar_formatos_fecha(df_historial['fecha_evento'])
            
            # 2. Despliegue de Filtros Interactivos
            with st.expander("🔍 Filtros del Historial"):
                df_fechas_validas = df_historial.dropna(subset=['fecha_limpia'])
                opciones_mes = ["Ver Todo"]
                mapa_inverso_mes = {}
                
                if not df_fechas_validas.empty:
                    df_fechas_validas['mes_ano_str'] = df_fechas_validas['fecha_limpia'].dt.strftime('%Y-%m')
                    meses_unicos = sorted(df_fechas_validas['mes_ano_str'].unique(), reverse=True)
                    
                    month_map_es = {
                        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril', '05': 'Mayo', '06': 'Junio',
                        '07': 'Julio', '08': 'Agosto', '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
                    }
                    
                    for mes_str in meses_unicos:
                        ano, mes_num = mes_str.split('-')
                        nombre_amigable = f"{month_map_es.get(mes_num, '')} {ano}"
                        opciones_mes.append(nombre_amigable)
                        mapa_inverso_mes[nombre_amigable] = mes_str

                # Seleccionar por defecto el mes actual en el combo
                hoy = datetime.now()
                nombre_mes_actual = f"{month_map_es.get(hoy.strftime('%m'), '')} {hoy.year}"
                default_index = opciones_mes.index(nombre_mes_actual) if nombre_mes_actual in opciones_mes else 0

                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                mes_seleccionado = col_f1.selectbox("Filtrar por Mes:", options=opciones_mes, index=default_index, key="vm_filtro_mes")
                
                tipos_existentes = ["Todos"] + sorted(df_historial['tipo_evento'].unique().tolist())
                tipo_filtro = col_f2.selectbox("Tipo de Evento:", options=tipos_existentes, key="vm_filtro_tipo")
                
                estados_existentes = ["Todos"] + sorted(df_historial['estado_evento'].unique().tolist())
                estado_filtro = col_f3.selectbox("Estado del Evento:", options=estados_existentes, key="vm_filtro_estado")
                
                pagos_existentes = ["Todos"] + sorted(df_historial['estado_pago'].unique().tolist())
                pago_filtro = col_f4.selectbox("Estado del Pago:", options=pagos_existentes, key="vm_filtro_pago")

            # 3. Aplicar Filtros sobre el DataFrame
            df_filtrado_vm = df_historial.copy()
            
            if mes_seleccionado != "Ver Todo":
                mes_str_buscar = mapa_inverso_mes.get(mes_seleccionado)
                if mes_str_buscar:
                    df_filtrado_fechas_validas = df_filtrado_vm.dropna(subset=['fecha_limpia'])
                    df_filtrado_vm = df_filtrado_fechas_validas[df_filtrado_fechas_validas['fecha_limpia'].dt.strftime('%Y-%m') == mes_str_buscar]

            if tipo_filtro != "Todos":
                df_filtrado_vm = df_filtrado_vm[df_filtrado_vm['tipo_evento'] == tipo_filtro]
            if estado_filtro != "Todos":
                df_filtrado_vm = df_filtrado_vm[df_filtrado_vm['estado_evento'] == estado_filtro]
            if pago_filtro != "Todos":
                df_filtrado_vm = df_filtrado_vm[df_filtrado_vm['estado_pago'] == pago_filtro]

            # 4. Formateador de libros implicados
            def formatear_libros_vm(lista):
                if not isinstance(lista, str): return "Ninguno"
                try:
                    js = json.loads(lista)
                    return " | ".join([f"{item.get('cantidad', 1)}x {item.get('titulo', '')}" for item in js])
                except: return "Error leyendo libros"
                
            df_filtrado_vm['libros_resumen'] = df_filtrado_vm['libros_implicados'].apply(formatear_libros_vm)

            # Convertir campos financieros a numéricos para cálculos de métricas
            df_filtrado_vm['ingreso_total'] = pd.to_numeric(df_filtrado_vm['ingreso_total'], errors='coerce').fillna(0.0)
            df_filtrado_vm['costo_total'] = pd.to_numeric(df_filtrado_vm['costo_total'], errors='coerce').fillna(0.0)
            df_filtrado_vm['utilidad_estimada'] = pd.to_numeric(df_filtrado_vm['utilidad_estimada'], errors='coerce').fillna(0.0)

            # 5. Renderizado de Métricas
            st.markdown("#### 📊 Resumen Financiero del Período Filtrado")
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 Ingresos Totales", f"${df_filtrado_vm['ingreso_total'].sum():,.0f}")
            m2.metric("📦 Costos de Evento", f"${df_filtrado_vm['costo_total'].sum():,.0f}")
            m3.metric("📈 Utilidad Estimada", f"${df_filtrado_vm['utilidad_estimada'].sum():,.0f}")
            st.markdown("---")

            # --- Slicing visual progresivo ---
            limite_actual = st.session_state.vm_limit_view
            total_eventos_filtrados = len(df_filtrado_vm)
            df_paginado = df_filtrado_vm.head(limite_actual)

            st.caption(f"Mostrando los **{len(df_paginado)}** eventos más recientes de un total de **{total_eventos_filtrados}** encontrados.")

            # 6. Despliegue de la Tabla de Datos filtrada
            st.dataframe(
                df_paginado[['evento_id', 'fecha_evento', 'nombre_evento', 'tipo_evento', 'ingreso_total', 'costo_total', 'utilidad_estimada', 'estado_evento', 'estado_pago', 'stock_descontado', 'libros_resumen', 'comentarios']],
                use_container_width=True, hide_index=True, 
                column_config={
                    "evento_id": "ID",
                    "nombre_evento": "Nombre Evento",
                    "tipo_evento": "Tipo",
                    "ingreso_total": st.column_config.NumberColumn("Ingreso ($)", format="$%.0f"), 
                    "costo_total": st.column_config.NumberColumn("Costo ($)", format="$%.0f"), 
                    "utilidad_estimada": st.column_config.NumberColumn("Utilidad ($)", format="$%.0f"), 
                    "fecha_evento": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"), 
                    "stock_descontado": st.column_config.CheckboxColumn("Stock Descontado", disabled=True),
                    "estado_evento": "Estado Evento",
                    "estado_pago": "Estado Pago",
                    "libros_resumen": "Libros implicados",
                    "comentarios": "Comentarios"
                }
            )

            # Botón dinámico de paginación progresiva para el historial de ventas masivas
            if total_eventos_filtrados > limite_actual:
                st.write("")
                col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
                with col_pag2:
                    if st.button(f"🔄 Cargar más eventos (+50) — Quedan {total_eventos_filtrados - limite_actual} por ver", use_container_width=True, key="btn_load_more_vm"):
                        st.session_state.vm_limit_view += 50
                        st.rerun()

    with tab_anular:
        st.markdown("### 🚫 Anular Venta Masiva y Restaurar Stock")
        st.warning("⚠️ ¡Atención! Anular una venta masiva eliminará el registro financiero y, si fue marcado, restaurará el stock de los libros asociados.")
        df_historial_anular = cargar_historial_ventas_masivas()
        
        if not df_historial_anular.empty:
            opciones_anular = {f"#{row['evento_id']} - {row['nombre_evento']} ({row.get('fecha_evento', 'Sin fecha')})": row for index, row in df_historial_anular.iterrows()}
            sel_anular_label = st.selectbox(
                "Selecciona el evento a anular:", 
                options=list(opciones_anular.keys()),
                index=None,
                placeholder="🔍 Selecciona el evento a anular...",
                key="sel_anular_vm"
            )
            
            if sel_anular_label:
                evento_a_anular = opciones_anular[sel_anular_label]
                st.error(f"Estás a punto de anular el evento: **{evento_a_anular['nombre_evento']}**")
                
                if evento_a_anular.get('stock_descontado'):
                    st.warning("Este evento descontó stock del inventario. La anulación **intentará restaurarlo automáticamente**.")
                    
                confirmacion = st.checkbox("Estoy segura de que quiero anular este evento permanentemente.")
                
                if st.button("🟥 ANULAR EVENTO DEFINITIVAMENTE", disabled=not confirmacion, type="primary"):
                    exito, error = anular_venta_masiva(evento_a_anular['evento_id'], evento_a_anular.get('stock_descontado'), evento_a_anular.get('libros_implicados'))
                    if exito:
                        st.success("¡Evento anulado con éxito!")
                        if 'sel_anular_vm' in st.session_state: 
                                del st.session_state.sel_anular_vm
                        cargar_historial_ventas_masivas.clear()
                        cargar_catalogo_libros_vm.clear()
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"No se pudo anular el evento. Detalle: {error}")
        else:
            st.info("No hay eventos en el historial para anular.")

if __name__ == "__main__":
    mostrar_ventas_masivas()