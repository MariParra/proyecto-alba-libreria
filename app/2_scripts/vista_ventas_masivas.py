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
        res = conn.table("libros").select("libro_id, titulo, autor, stock").order("titulo").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_catalogo_libros_vm", e)
        st.error("No se pudo cargar el catálogo de libros.")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_historial_ventas_masivas():
    conn = get_db_connection()
    try:
        res = conn.table("ventas_masivas").select("*").order("fecha_evento", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_historial_ventas_masivas", e)
        st.error("No se pudo cargar el historial de ventas masivas.")
        return pd.DataFrame()

def procesar_nueva_venta_masiva(datos_evento):
    """Inserta una nueva venta masiva, crea libros nuevos (limpios y en mayúsculas) y descuenta el stock."""
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
    if stock_fue_descontado and libros_implicados_json:
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

# --- EVENTOS ON_CHANGE ---

def on_estado_evento_change():
    """Si el estado cambia a FINALIZADO, fuerza el pago a PAGADO en tiempo real"""
    if st.session_state.vm_estado_evento == "FINALIZADO":
        st.session_state.vm_estado_pago = "PAGADO"

# --- VISTA PRINCIPAL ---

def mostrar_ventas_masivas():
    st.title("📈 Ventas Masivas y Eventos")
    st.info("Utiliza esta sección para registrar ingresos y costos de eventos como ferias, rifas o ventas de bodega donde no hay un cliente único.")

    # --- 1. INICIALIZACIÓN ESTRICTA DE MEMORIA ---
    # Variables de la venta
    vm_keys = ['vm_carrito', 'vm_nombre_evento', 'vm_tipo_sel', 'vm_tipo_pers', 'vm_fecha_evento', 
               'vm_ingreso', 'vm_costo', 'vm_descontar_stock', 'vm_estado_evento', 'vm_estado_pago', 
               'vm_comentarios', 'vm_modo_libro']
    defaults = {
        'vm_carrito': [], 'vm_nombre_evento': "", 'vm_tipo_sel': "", 'vm_tipo_pers': "", 
        'vm_fecha_evento': None, 'vm_ingreso': 0.0, 'vm_costo': 0.0, 'vm_descontar_stock': False, 
        'vm_estado_evento': "POR EMPEZAR", 'vm_estado_pago': "PENDIENTE", 'vm_comentarios': "", 
        'vm_modo_libro': "📚 Existente en Catálogo"
    }
    for key in vm_keys:
        if key not in st.session_state:
            st.session_state[key] = defaults[key]
            
    # Variables temporales para crear un libro nuevo (sin que se borre el resto)
    tmp_keys = ['tmp_titulo', 'tmp_autor', 'tmp_genero', 'tmp_editorial', 'tmp_encuadernacion', 
                'tmp_precio', 'tmp_costo', 'tmp_stock', 'tmp_cant']
    tmp_defaults = {
        'tmp_titulo': "", 'tmp_autor': "", 'tmp_genero': "", 'tmp_editorial': "", 'tmp_encuadernacion': "",
        'tmp_precio': 0.0, 'tmp_costo': 0.0, 'tmp_stock': 0, 'tmp_cant': 1
    }
    for key in tmp_keys:
        if key not in st.session_state:
            st.session_state[key] = tmp_defaults[key]

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
                    col_b1, col_b2 = st.columns([2, 1])
                    sel_libro_label = col_b1.selectbox("Busca un libro:", [""] + df_libros_catalogo['label_busqueda'].tolist())
                    cant_descontar = col_b2.number_input("Cantidad implicada:", min_value=1, step=1, value=1)
                    
                    if st.button("➕ Añadir a la lista", type="secondary"):
                        if sel_libro_label:
                            libro_data = df_libros_catalogo[df_libros_catalogo['label_busqueda'] == sel_libro_label].iloc[0]
                            if not any(d['titulo'] == libro_data['titulo'] for d in st.session_state.vm_carrito):
                                st.session_state.vm_carrito.append({
                                    "libro_id": int(libro_data['libro_id']), "titulo": libro_data['titulo'], 
                                    "cantidad": cant_descontar, "stock_actual": int(libro_data['stock']), "es_nuevo": False
                                })
                                st.rerun()
                            else:
                                st.warning("El libro ya está en la lista. Ajusta la cantidad en la tabla de abajo.")
                        else:
                            st.error("Debes seleccionar un libro.")
                else:
                    st.warning("El catálogo está vacío.")
                    
            elif st.session_state.vm_modo_libro == "➕ Crear Nuevo Libro":
                # AQUI ELIMINAMOS EL ST.FORM PARA QUE SEA 100% ESTABLE
                st.info("💡 Este libro se creará en el catálogo general. Todos los textos se guardarán en mayúsculas y sin tildes.")
                col_n1, col_n2 = st.columns(2)
                col_n1.text_input("Título*", key="tmp_titulo")
                col_n2.text_input("Autor", key="tmp_autor")
                
                col_n3, col_n4, col_n5 = st.columns(3)
                col_n3.text_input("Género", key="tmp_genero")
                col_n4.text_input("Editorial", key="tmp_editorial")
                col_n5.selectbox("Encuadernación", ["", "TAPA BLANDA", "TAPA DURA", "ESPIRAL"], key="tmp_encuadernacion")
                
                col_n6, col_n7, col_n8, col_n9 = st.columns(4)
                col_n6.number_input("Precio Oficial ($)*", min_value=0.0, step=500.0, key="tmp_precio")
                col_n7.number_input("Costo ($)", min_value=0.0, step=500.0, key="tmp_costo")
                col_n8.number_input("Stock Inicial Total*", min_value=0, step=1, key="tmp_stock")
                col_n9.number_input("Cant. Implicada*", min_value=1, step=1, key="tmp_cant")
                
                if st.button("➕ Crear y Añadir a la lista", type="secondary"):
                    if not st.session_state.tmp_titulo:
                        st.error("El Título es obligatorio.")
                    else:
                        titulo_limpio = limpiar_texto_para_busqueda(st.session_state.tmp_titulo)
                        conn = get_db_connection()
                        res_check = conn.table("libros").select("titulo").eq("titulo", titulo_limpio).execute()
                        
                        if res_check.data:
                            st.error(f"🚫 DUPLICADO: Ya existe un libro con el título '{titulo_limpio}'. Búscalo en 'Catálogo'.")
                        else:
                            st.session_state.vm_carrito.append({
                                "libro_id": None, "titulo": st.session_state.tmp_titulo, "cantidad": st.session_state.tmp_cant, 
                                "stock_actual": st.session_state.tmp_stock, "es_nuevo": True, "autor": st.session_state.tmp_autor, 
                                "genero": st.session_state.tmp_genero, "editorial": st.session_state.tmp_editorial, 
                                "encuadernacion": st.session_state.tmp_encuadernacion, "precio": st.session_state.tmp_precio, 
                                "costo": st.session_state.tmp_costo, "stock_inicial": st.session_state.tmp_stock
                            })
                            # Limpieza manual de los campos temporales
                            for k in tmp_keys:
                                st.session_state[k] = tmp_defaults[k]
                            st.rerun()

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
        
        # Usamos on_change para la automatización del pago
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
                    
                    # Limpiamos la memoria completa 
                    keys_to_clear = [k for k in st.session_state.keys() if k.startswith('vm_') or k.startswith('tmp_')]
                    for k in keys_to_clear:
                        del st.session_state[k]
                            
                    cargar_historial_ventas_masivas.clear()
                    cargar_catalogo_libros_vm.clear()
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
            def formatear_libros_vm(lista):
                if not isinstance(lista, str): return "Ninguno"
                try:
                    js = json.loads(lista)
                    return " | ".join([f"{item.get('cantidad', 1)}x {item.get('titulo', '')}" for item in js])
                except: return "Error leyendo libros"
                
            df_historial['libros_resumen'] = df_historial['libros_implicados'].apply(formatear_libros_vm)
            
            st.dataframe(
                df_historial[['evento_id', 'fecha_evento', 'nombre_evento', 'tipo_evento', 'ingreso_total', 'costo_total', 'utilidad_estimada', 'estado_evento', 'estado_pago', 'stock_descontado', 'libros_resumen', 'comentarios']],
                use_container_width=True, hide_index=True, 
                column_config={
                    "ingreso_total": st.column_config.NumberColumn("Ingreso ($)", format="$%.0f"), 
                    "costo_total": st.column_config.NumberColumn("Costo ($)", format="$%.0f"), 
                    "utilidad_estimada": st.column_config.NumberColumn("Utilidad ($)", format="$%.0f"), 
                    "fecha_evento": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"), 
                    "stock_descontado": st.column_config.CheckboxColumn("Stock Descontado", disabled=True)
                }
            )

    with tab_anular:
        st.markdown("### 🚫 Anular Venta Masiva y Restaurar Stock")
        st.warning("⚠️ ¡Atención! Anular una venta masiva eliminará el registro financiero y, si fue marcado, restaurará el stock de los libros asociados.")
        df_historial_anular = cargar_historial_ventas_masivas()
        
        if not df_historial_anular.empty:
            opciones_anular = {f"#{row['evento_id']} - {row['nombre_evento']} ({row.get('fecha_evento', 'Sin fecha')})": row for index, row in df_historial_anular.iterrows()}
            sel_anular_label = st.selectbox("Selecciona el evento a anular:", [""] + list(opciones_anular.keys()))
            
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