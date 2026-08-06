import streamlit as st
import pandas as pd
from datetime import datetime
import json
import time
from utilidades import get_db_connection, log_error, limpiar_texto_para_busqueda

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=600)
def cargar_catalogo_libros_vm():
    # ... (Esta función no cambia)
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
    # ... (Esta función no cambia)
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
    
    # 0. Primero procesamos los libros NUEVOS para insertarlos en la tabla 'libros'
    if datos_evento.get("libros_implicados"):
        for libro in datos_evento["libros_implicados"]:
            if libro.get("es_nuevo"):
                try:
                    # ✅ MEJORA: Aplicamos la limpieza profunda (sin tildes/signos y a mayúsculas)
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
                    libro["libro_id"] = nuevo_id # Actualizamos el JSON con el ID real de la BD
                except Exception as e:
                    log_error("vista_ventas_masivas", "crear_libro_nuevo", f"Error al crear {libro.get('titulo')}: {e}")
                    # Importante: Detenemos la operación si no se puede crear el libro.
                    return False, f"Error al crear el libro nuevo '{libro.get('titulo')}' en el catálogo. La venta no se procesó. Detalle: {e}"

    # 1. Descontar el stock (lógica sin cambios)
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
            log_error("vista_ventas_masivas", "procesar_nueva_venta_masiva (descontar stock)", e)
            return False, f"Error al descontar stock. La venta NO se registró. Detalle: {e}"

    # 2. Insertar el registro de la venta masiva (lógica sin cambios)
    try:
        with st.spinner("Registrando la venta masiva..."):
            if 'libros_implicados' in datos_evento:
                datos_evento['libros_implicados'] = json.dumps(datos_evento['libros_implicados'], ensure_ascii=False)
            conn.table("ventas_masivas").insert(datos_evento).execute()
        return True, ""
    except Exception as e:
        log_error("vista_ventas_masivas", "procesar_nueva_venta_masiva (insertar evento)", e)
        return False, f"Error al registrar el evento en la base de datos: {e}"


def anular_venta_masiva(evento_id, stock_fue_descontado, libros_implicados_json):
    # ... (Esta función no cambia)
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
            log_error("vista_ventas_masivas", "anular_venta_masiva (restaurar stock)", e)
            st.error(f"No se pudo restaurar el stock por completo. Detalle: {e}")
    try:
        with st.spinner("Anulando el registro de la venta..."):
            conn.table("ventas_masivas").delete().eq("evento_id", evento_id).execute()
        return True, ""
    except Exception as e:
        log_error("vista_ventas_masivas", "anular_venta_masiva (eliminar evento)", e)
        return False, f"Error al anular la venta: {e}"

# --- VISTA PRINCIPAL ---

def mostrar_ventas_masivas():
    st.title("📈 Ventas Masivas y Eventos")
    # ... (código inicial sin cambios)
    st.info("Utiliza esta sección para registrar ingresos y costos de eventos como ferias, rifas o ventas de bodega donde no hay un cliente único.")
    if 'carrito_libros_vm' not in st.session_state:
        st.session_state.carrito_libros_vm = []
    tipos_evento_predefinidos = ["VENTA EN FERIA", "RIFA", "CLUB DE LECTURA", "EVENTO ESPECIAL", "VENTA DE BODEGA", "OTRO"]
    estados_evento = ["POR EMPEZAR", "EN CURSO", "FINALIZADO"]
    estados_pago = ["PENDIENTE", "PAGADO"]
    
    tab_nueva, tab_historial, tab_anular = st.tabs(["➕ Nueva Venta Masiva", "📜 Historial", "🚫 Anular"])

    with tab_nueva:
        st.markdown("### Registrar Nuevo Evento de Venta")
        
        # --- 1. Detalles del Evento ---
        st.markdown("#### 1. Información General del Evento")
        col1, col2 = st.columns(2)
        nombre_evento = col1.text_input("Nombre o Descripción del Evento*", placeholder="Ej: FERIA DEL LIBRO DE VIÑA 2026")
        tipo_evento_sel = col2.selectbox("Tipo de Evento*", options=[""] + tipos_evento_predefinidos)
        tipo_evento_personalizado = ""
        if tipo_evento_sel == "OTRO":
            tipo_evento_personalizado = col2.text_input("Si elegiste 'OTRO', escríbelo aquí:", placeholder="Ej: DONACIÓN A COLEGIO")
        fecha_evento = st.date_input("Fecha del Evento (Opcional)", value=None)

        # --- 2. Datos Financieros ---
        st.markdown("#### 2. Datos Financieros")
        col_f1, col_f2 = st.columns(2)
        ingreso_total = col_f1.number_input("Ingreso Total Bruto ($)*", min_value=0.0, step=10000.0)
        costo_total = col_f2.number_input("Costo Total del Evento ($)", min_value=0.0, step=5000.0, help="Incluye costos de stand, traslados, etc.")

        # ... (Sección 3 de Libros sin cambios en la UI, solo en la lógica de guardado)
        # --- 3. Libros y Gestión de Stock ---
        st.markdown("#### 3. Libros y Gestión de Stock (Opcional)")
        descontar_stock = st.checkbox("Descontar stock de los libros asociados a este evento", value=False)
        with st.container(border=True):
            modo_libro = st.radio("Añadir libro a la lista:", ["📚 Existente en Catálogo", "➕ Crear Nuevo Libro"], horizontal=True, label_visibility="collapsed")
            if modo_libro == "📚 Existente en Catálogo":
                df_libros_catalogo = cargar_catalogo_libros_vm()
                if not df_libros_catalogo.empty:
                    df_libros_catalogo['label_busqueda'] = df_libros_catalogo.apply(lambda row: f"{row['titulo']} (Stock actual: {row['stock']})", axis=1)
                    col_b1, col_b2 = st.columns([2, 1])
                    sel_libro_label = col_b1.selectbox("Busca un libro:", [""] + df_libros_catalogo['label_busqueda'].tolist())
                    cant_descontar = col_b2.number_input("Cantidad implicada:", min_value=1, step=1)
                    if st.button("➕ Añadir a la lista", key="btn_add_existente"):
                        if sel_libro_label:
                            libro_data = df_libros_catalogo[df_libros_catalogo['label_busqueda'] == sel_libro_label].iloc[0]
                            if not any(d['titulo'] == libro_data['titulo'] for d in st.session_state.carrito_libros_vm):
                                st.session_state.carrito_libros_vm.append({"libro_id": int(libro_data['libro_id']), "titulo": libro_data['titulo'], "cantidad": cant_descontar, "stock_actual": int(libro_data['stock']), "es_nuevo": False})
                                st.success(f"{libro_data['titulo']} añadido a la lista.")
                                st.rerun()
                            else:
                                st.warning("El libro ya está en la lista. Ajusta la cantidad en la tabla de abajo.")
                        else:
                            st.error("Debes seleccionar un libro.")
                else:
                    st.warning("El catálogo está vacío.")
            else: # modo_libro == "➕ Crear Nuevo Libro"
                st.info("💡 Este libro se creará en el catálogo. Si marcaste 'Descontar stock', se le restará la 'Cant. Implicada' al 'Stock Inicial'.")
                col_n1, col_n2 = st.columns(2)
                n_titulo = col_n1.text_input("Título*")
                n_autor = col_n2.text_input("Autor")
                col_n3, col_n4, col_n5 = st.columns(3)
                n_genero = col_n3.text_input("Género")
                n_editorial = col_n4.text_input("Editorial")
                n_encuadernacion = col_n5.selectbox("Encuadernación", ["", "TAPA BLANDA", "TAPA DURA", "ESPIRAL"])
                col_n6, col_n7, col_n8, col_n9 = st.columns(4)
                n_precio = col_n6.number_input("Precio Oficial ($)*", min_value=0.0, step=500.0)
                n_costo = col_n7.number_input("Costo ($)", min_value=0.0, step=500.0)
                n_stock_inicial = col_n8.number_input("Stock Inicial Total*", min_value=0, step=1)
                n_cant_implicada = col_n9.number_input("Cant. Implicada*", min_value=1, max_value=max(1, n_stock_inicial), step=1)
                if st.button("➕ Crear y Añadir a la lista", key="btn_add_nuevo"):
                    if not n_titulo:
                        st.error("El Título es obligatorio.")
                    else:
                        # ✅ PASO 1: Limpiamos el título para la validación
                        titulo_limpio_para_validar = limpiar_texto_para_busqueda(n_titulo)

                        # ✅ PASO 2: Revisamos si ya existe en la base de datos
                        conn = get_db_connection()
                        res_check = conn.table("libros").select("titulo").eq("titulo", titulo_limpio_para_validar).execute()

                        if res_check.data:
                            # ¡DUPLICADO ENCONTRADO!
                            st.error(f"🚫 ¡DUPLICADO DETENIDO! Ya existe un libro en el catálogo con el título '{titulo_limpio_para_validar}'. Búscalo en la pestaña 'Existente en Catálogo'.")
                        else:
                            # ✅ PASO 3: Si no existe, lo añadimos a la lista local
                            st.session_state.carrito_libros_vm.append({
                                "libro_id": None,
                                "titulo": n_titulo, # Guardamos el original para mostrarlo, se limpiará al guardar
                                "cantidad": n_cant_implicada,
                                "stock_actual": n_stock_inicial,
                                "es_nuevo": True,
                                # Guardamos los demás datos que llenaste
                                "autor": n_autor,
                                "genero": n_genero,
                                "editorial": n_editorial,
                                "encuadernacion": n_encuadernacion,
                                "precio": n_precio,
                                "costo": n_costo,
                                "stock_inicial": n_stock_inicial
                            })
                            st.success(f"'{n_titulo}' añadido a la lista como libro nuevo.")
                            st.rerun()

        if st.session_state.carrito_libros_vm:
            st.write("📋 **Lista de Libros Implicados:**")
            df_carrito = pd.DataFrame(st.session_state.carrito_libros_vm)
            df_carrito.insert(0, 'Quitar', False)
            cols_to_show = ['Quitar', 'titulo', 'cantidad', 'stock_actual', 'es_nuevo']
            df_editado = st.data_editor(df_carrito[cols_to_show], column_config={"Quitar": st.column_config.CheckboxColumn("Quitar ❌", default=False), "titulo": st.column_config.TextColumn("Título", disabled=True), "cantidad": st.column_config.NumberColumn("Cant. Implicada", min_value=1, step=1), "stock_actual": st.column_config.NumberColumn("Stock en BD", disabled=True), "es_nuevo": st.column_config.CheckboxColumn("¿Nuevo?", disabled=True)}, hide_index=True, use_container_width=True, key="editor_carrito_vm")
            for i, row in df_editado.iterrows():
                st.session_state.carrito_libros_vm[i]['cantidad'] = row['cantidad']
            if st.button("🗑️ Quitar Seleccionados de la Lista"):
                indices = df_editado[df_editado['Quitar'] == True].index.tolist()
                if indices:
                    for i in sorted(indices, reverse=True):
                        st.session_state.carrito_libros_vm.pop(i)
                    st.rerun()
                else:
                    st.warning("Marca la casilla 'Quitar ❌' en los libros que desees eliminar.")

        st.markdown("---")
        
        # --- 4. Estado Final ---
        st.markdown("#### 4. Estado del Evento")
        col_e1, col_e2 = st.columns(2)
        estado_evento_sel = col_e1.selectbox("Estado del Evento", options=estados_evento, index=0)
        
        # ✅ MEJORA: Lógica de Auto-Pago
        pago_index = 0 # Por defecto es PENDIENTE
        if estado_evento_sel == "FINALIZADO":
            pago_index = 1 # Cambia a PAGADO
            st.info("💡 Evento FINALIZADO: El estado del pago se establecerá en PAGADO.")
            
        estado_pago_sel = col_e2.selectbox("Estado del Pago", options=estados_pago, index=pago_index)
        
        comentarios = st.text_area("Comentarios Adicionales (Opcional)", placeholder="Anotaciones sobre la feria, contactos, etc.")
        
        # --- BOTÓN FINAL DE GUARDADO ---
        if st.button("💾 GUARDAR VENTA MASIVA TOTAL", type="primary", use_container_width=True):
            # ... (resto de la lógica de guardado, ahora respeta las mayúsculas y el estado de pago)
            nombre_evento_limpio = nombre_evento.upper().strip() if nombre_evento else ""
            comentarios_limpios = comentarios.upper().strip() if comentarios else ""
            if tipo_evento_sel == "OTRO":
                tipo_evento_final = tipo_evento_personalizado.upper().strip() if tipo_evento_personalizado else ""
            else:
                tipo_evento_final = tipo_evento_sel.upper().strip() if tipo_evento_sel else ""

            if not nombre_evento_limpio or not tipo_evento_final:
                st.error("El nombre y el tipo de evento son obligatorios (si elegiste 'OTRO', debes escribirlo).")
            else:
                # Si el evento está finalizado, nos aseguramos que el pago también lo esté
                if estado_evento_sel == "FINALIZADO":
                    estado_pago_sel = "PAGADO"

                datos_para_db = {"nombre_evento": nombre_evento_limpio, "tipo_evento": tipo_evento_final, "fecha_evento": fecha_evento.isoformat() if fecha_evento else None, "ingreso_total": ingreso_total, "costo_total": costo_total, "libros_implicados": st.session_state.carrito_libros_vm, "stock_descontado": descontar_stock, "estado_evento": estado_evento_sel, "estado_pago": estado_pago_sel, "comentarios": comentarios_limpios}
                with st.spinner("Procesando evento masivo..."):
                    exito, error = procesar_nueva_venta_masiva(datos_para_db)
                if exito:
                    st.success(f"¡Venta masiva '{nombre_evento_limpio}' registrada con éxito!")
                    st.balloons()
                    st.session_state.carrito_libros_vm = []
                    cargar_historial_ventas_masivas.clear()
                    cargar_catalogo_libros_vm.clear()
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"No se pudo registrar la venta. Detalle: {error}")

    with tab_historial:
        # ... (código de la pestaña historial no cambia)
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
            st.dataframe(df_historial[['evento_id', 'fecha_evento', 'nombre_evento', 'tipo_evento', 'ingreso_total', 'costo_total', 'utilidad_estimada', 'estado_evento', 'estado_pago', 'stock_descontado', 'libros_resumen', 'comentarios']], use_container_width=True, hide_index=True, column_config={"ingreso_total": st.column_config.NumberColumn("Ingreso ($)", format="$%.0f"), "costo_total": st.column_config.NumberColumn("Costo ($)", format="$%.0f"), "utilidad_estimada": st.column_config.NumberColumn("Utilidad ($)", format="$%.0f"), "fecha_evento": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"), "stock_descontado": st.column_config.CheckboxColumn("Stock Descontado", disabled=True)})

    with tab_anular:
        # ... (código de la pestaña anular no cambia)
        st.markdown("### 🚫 Anular Venta Masiva y Restaurar Stock")
        st.warning("⚠️ ¡Atención! Anular una venta masiva eliminará el registro financiero y, si fue marcado, restaurará el stock de los libros asociados.")
        df_historial_anular = cargar_historial_ventas_masivas()
        if not df_historial_anular.empty:
            opciones_anular = {f"#{row['evento_id']} - {row['nombre_evento']} ({row['fecha_evento']})": row for index, row in df_historial_anular.iterrows()}
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