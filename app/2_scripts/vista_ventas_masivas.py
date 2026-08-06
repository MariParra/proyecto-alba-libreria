# vista_ventas_masivas.py

import streamlit as st
import pandas as pd
from datetime import datetime
import json
import time
from utilidades import get_db_connection, log_error

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=600)
def cargar_catalogo_libros_vm():
    """Carga el catálogo completo de libros para la selección."""
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
    """Carga el historial de todas las ventas masivas registradas."""
    conn = get_db_connection()
    try:
        res = conn.table("ventas_masivas").select("*").order("fecha_evento", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_historial_ventas_masivas", e)
        st.error("No se pudo cargar el historial de ventas masivas.")
        return pd.DataFrame()

def procesar_nueva_venta_masiva(datos_evento):
    """Inserta una nueva venta masiva y descuenta el stock si es necesario."""
    conn = get_db_connection()
    
    # 1. Descontar el stock si el usuario lo marcó
    if datos_evento.get("stock_descontado") and datos_evento.get("libros_implicados"):
        try:
            with st.spinner("Descontando stock de libros..."):
                for libro in datos_evento["libros_implicados"]:
                    if libro.get("libro_id") and libro.get("cantidad") > 0:
                        # Obtenemos el stock actual para evitar condiciones de carrera
                        res_stock = conn.table("libros").select("stock").eq("libro_id", libro["libro_id"]).single().execute()
                        stock_actual = res_stock.data.get('stock', 0)
                        nuevo_stock = stock_actual - libro["cantidad"]
                        
                        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro["libro_id"]).execute()
        except Exception as e:
            log_error("vista_ventas_masivas", "procesar_nueva_venta_masiva (descontar stock)", e)
            st.error(f"Error al descontar el stock del libro '{libro.get('titulo', 'ID desconocido')}'. La venta no se ha registrado. Detalle: {e}")
            return False, f"Error al descontar stock: {e}"

    # 2. Insertar el registro de la venta masiva
    try:
        with st.spinner("Registrando la venta masiva..."):
            # Convertimos la lista de libros a formato JSON
            if 'libros_implicados' in datos_evento:
                datos_evento['libros_implicados'] = json.dumps(datos_evento['libros_implicados'], ensure_ascii=False)

            conn.table("ventas_masivas").insert(datos_evento).execute()
        return True, ""
    except Exception as e:
        log_error("vista_ventas_masivas", "procesar_nueva_venta_masiva (insertar evento)", e)
        # Aquí podríamos añadir una lógica para "revertir" el stock si la inserción falla, pero es un caso muy raro.
        return False, f"Error al registrar el evento en la base de datos: {e}"

def anular_venta_masiva(evento_id, stock_fue_descontado, libros_implicados_json):
    """Anula una venta masiva y restaura el stock si fue descontado."""
    conn = get_db_connection()

    # 1. Restaurar stock si corresponde
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
            st.error(f"No se pudo restaurar el stock. Por favor, revísalo manualmente. Detalle: {e}")
            # No detenemos el proceso, la anulación de la venta es más importante.

    # 2. Eliminar el registro de la venta masiva
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
    st.info("Utiliza esta sección para registrar ingresos y costos de eventos como ferias, rifas o ventas de bodega donde no hay un cliente único.")

    if 'carrito_libros_vm' not in st.session_state:
        st.session_state.carrito_libros_vm = []

    # Opciones predefinidas y personalizables
    tipos_evento_predefinidos = ["VENTA EN FERIA", "RIFA", "CLUB DE LECTURA", "EVENTO ESPECIAL", "VENTA DE BODEGA"]
    estados_evento = ["POR EMPEZAR", "EN CURSO", "FINALIZADO"]
    estados_pago = ["PENDIENTE", "PAGADO"]

    tab_nueva, tab_historial, tab_anular = st.tabs(["➕ Nueva Venta Masiva", "📜 Historial", "🚫 Anular"])

    with tab_nueva:
        st.markdown("### Registrar Nuevo Evento de Venta")
        
        with st.form("form_nueva_venta_masiva", clear_on_submit=True):
            # --- Detalles del Evento ---
            st.markdown("#### 1. Información General del Evento")
            col1, col2 = st.columns(2)
            nombre_evento = col1.text_input("Nombre o Descripción del Evento*", placeholder="Ej: Feria del Libro de Viña 2026")
            
            tipo_evento_input = col2.text_input("Tipo de Evento*", placeholder="Escribe o selecciona de la lista")
            tipo_evento_sel = st.selectbox("O usa un tipo predefinido:", [""] + tipos_evento_predefinidos, label_visibility="collapsed")
            tipo_evento_final = tipo_evento_input if tipo_evento_input else tipo_evento_sel
            
            fecha_evento = st.date_input("Fecha del Evento (Opcional)", value=None)

            # --- Datos Financieros ---
            st.markdown("#### 2. Datos Financieros")
            col_f1, col_f2 = st.columns(2)
            ingreso_total = col_f1.number_input("Ingreso Total Bruto ($)*", min_value=0.0, step=10000.0)
            costo_total = col_f2.number_input("Costo Total del Evento ($)", min_value=0.0, step=5000.0, help="Incluye costos de stand, traslados, etc.")

            # --- Libros Implicados y Stock ---
            st.markdown("#### 3. Libros y Gestión de Stock (Opcional)")
            descontar_stock = st.checkbox("Descontar stock de los libros asociados a este evento", value=False)
            
            df_libros_catalogo = cargar_catalogo_libros_vm()
            if not df_libros_catalogo.empty:
                libros_seleccionados = st.multiselect(
                    "Busca y selecciona los libros del catálogo:",
                    options=df_libros_catalogo['titulo'].tolist()
                )
                
                if libros_seleccionados:
                    for libro_titulo in libros_seleccionados:
                        # Si el libro ya está en el carrito, no lo volvemos a añadir
                        if not any(d['titulo'] == libro_titulo for d in st.session_state.carrito_libros_vm):
                            libro_data = df_libros_catalogo[df_libros_catalogo['titulo'] == libro_titulo].iloc[0]
                            st.session_state.carrito_libros_vm.append({
                                "libro_id": int(libro_data['libro_id']),
                                "titulo": libro_data['titulo'],
                                "cantidad": 1, # Por defecto
                                "es_nuevo": False
                            })
            
            # Editor para ajustar cantidades y añadir libros no catalogados
            if st.session_state.carrito_libros_vm:
                st.write("Ajusta las cantidades de los libros seleccionados:")
                df_carrito = pd.DataFrame(st.session_state.carrito_libros_vm)
                edited_df = st.data_editor(
                    df_carrito,
                    column_config={
                        "libro_id": st.column_config.NumberColumn("ID", disabled=True),
                        "titulo": st.column_config.TextColumn("Título"),
                        "cantidad": st.column_config.NumberColumn("Cantidad a descontar", min_value=1, step=1),
                        "es_nuevo": st.column_config.CheckboxColumn("¿Es Nuevo?", disabled=True)
                    },
                    hide_index=True,
                    num_rows="dynamic", # Permite añadir nuevas filas
                    key="editor_carrito_vm"
                )
                st.session_state.carrito_libros_vm = edited_df.to_dict('records')

            # --- Estado Final ---
            st.markdown("#### 4. Estado del Evento")
            col_e1, col_e2 = st.columns(2)
            estado_evento_sel = col_e1.selectbox("Estado del Evento", options=estados_evento, index=0)
            estado_pago_sel = col_e2.selectbox("Estado del Pago", options=estados_pago, index=0, help="Refleja si el ingreso total ya fue recibido.")
            
            comentarios = st.text_area("Comentarios Adicionales (Opcional)", placeholder="Anotaciones sobre la feria, contactos, etc.")
            
            # --- Botón de Envío ---
            submitted = st.form_submit_button("💾 Guardar Venta Masiva", type="primary", use_container_width=True)

            if submitted:
                if not nombre_evento or not tipo_evento_final:
                    st.error("El nombre y el tipo de evento son obligatorios.")
                else:
                    # Preparar el diccionario de datos para la inserción
                    datos_para_db = {
                        "nombre_evento": nombre_evento,
                        "tipo_evento": tipo_evento_final,
                        "fecha_evento": fecha_evento.isoformat() if fecha_evento else None,
                        "ingreso_total": ingreso_total,
                        "costo_total": costo_total,
                        "libros_implicados": st.session_state.carrito_libros_vm,
                        "stock_descontado": descontar_stock,
                        "estado_evento": estado_evento_sel,
                        "estado_pago": estado_pago_sel,
                        "comentarios": comentarios
                    }
                    
                    exito, error = procesar_nueva_venta_masiva(datos_para_db)
                    
                    if exito:
                        st.success(f"¡Venta masiva '{nombre_evento}' registrada con éxito!")
                        st.balloons()
                        # Limpiar carrito y recargar datos
                        st.session_state.carrito_libros_vm = []
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
            st.dataframe(
                df_historial,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ingreso_total": st.column_config.NumberColumn("Ingreso ($)", format="$%.0f"),
                    "costo_total": st.column_config.NumberColumn("Costo ($)", format="$%.0f"),
                    "utilidad_estimada": st.column_config.NumberColumn("Utilidad ($)", format="$%.0f"),
                    "fecha_evento": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                    "stock_descontado": st.column_config.CheckboxColumn("¿Stock Descontado?", disabled=True)
                }
            )

    with tab_anular:
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
                    exito, error = anular_venta_masiva(
                        evento_a_anular['evento_id'],
                        evento_a_anular.get('stock_descontado'),
                        evento_a_anular.get('libros_implicados')
                    )
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
    # Esta comprobación es útil si ejecutas el script localmente
    # st.set_page_config(layout="wide")
    mostrar_ventas_masivas()
