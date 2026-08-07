import streamlit as st
import pandas as pd
from datetime import datetime
import json
import time
from utilidades import get_db_connection, log_error, limpiar_texto_para_busqueda

@st.cache_data(ttl=300)
def cargar_catalogo_libros_vm():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, stock").order("titulo").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_catalogo_libros_vm", e)
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_listas_desplegables():
    conn = get_db_connection()
    try:
        res_autores = conn.table("libros").select("autor").execute()
        res_generos = conn.table("libros").select("genero").execute()
        res_editoriales = conn.table("libros").select("editorial").execute()
        autores = sorted(list(set([r['autor'] for r in res_autores.data if r.get('autor')]))) if res_autores.data else []
        generos = sorted(list(set([r['genero'] for r in res_generos.data if r.get('genero')]))) if res_generos.data else []
        editoriales = sorted(list(set([r['editorial'] for r in res_editoriales.data if r.get('editorial')]))) if res_editoriales.data else []
        return autores, generos, editoriales
    except Exception:
        return [], [], []

@st.cache_data(ttl=300)
def cargar_historial_ventas_masivas():
    conn = get_db_connection()
    try:
        res = conn.table("ventas_masivas").select("*").order("fecha_evento", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_ventas_masivas", "cargar_historial_ventas_masivas", e)
        return pd.DataFrame()

def procesar_nueva_venta_masiva(datos_evento):
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
                    libro["libro_id"] = res.data[0]['libro_id'] 
                except Exception as e:
                    return False, f"Error al crear '{libro.get('titulo')}': {e}"

    if datos_evento.get("stock_descontado") and datos_evento.get("libros_implicados"):
        try:
            with st.spinner("Descontando stock..."):
                for libro in datos_evento["libros_implicados"]:
                    if libro.get("libro_id") and libro.get("cantidad") > 0:
                        res_stock = conn.table("libros").select("stock").eq("libro_id", libro["libro_id"]).single().execute()
                        nuevo_stock = res_stock.data.get('stock', 0) - libro["cantidad"]
                        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro["libro_id"]).execute()
        except Exception as e:
            return False, f"Error al descontar stock: {e}"

    try:
        if 'libros_implicados' in datos_evento:
            datos_evento['libros_implicados'] = json.dumps(datos_evento['libros_implicados'], ensure_ascii=False)
        conn.table("ventas_masivas").insert(datos_evento).execute()
        return True, ""
    except Exception as e:
        return False, f"Error al registrar evento: {e}"

def anular_venta_masiva(evento_id, stock_fue_descontado, libros_implicados_json):
    conn = get_db_connection()
    if stock_fue_descontado and libros_implicados_json:
        try:
            libros = json.loads(libros_implicados_json) if isinstance(libros_implicados_json, str) else libros_implicados_json
            for libro in libros:
                if libro.get("libro_id") and libro.get("cantidad", 0) > 0:
                    res_stock = conn.table("libros").select("stock").eq("libro_id", libro["libro_id"]).single().execute()
                    nuevo_stock = res_stock.data.get('stock', 0) + libro["cantidad"]
                    conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", libro["libro_id"]).execute()
        except Exception as e:
            st.error(f"Error restaurando stock: {e}")
    try:
        conn.table("ventas_masivas").delete().eq("evento_id", evento_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Error anulando: {e}"

def on_estado_evento_change():
    if st.session_state.vm_estado_evento == "FINALIZADO":
        st.session_state.vm_estado_pago = "PAGADO"

def anadir_nuevo_libro_carrito():
    titulo = st.session_state.get('tmp_titulo', '').strip()
    
    sel_autor = st.session_state.get('sel_autor')
    if sel_autor == "➕ Crear Nuevo Autor": autor = st.session_state.get('tmp_autor_nuevo', '').strip()
    elif sel_autor == "Selecciona o busca...": autor = ""
    else: autor = sel_autor or ""
        
    sel_gen = st.session_state.get('sel_genero')
    if sel_gen == "➕ Crear Nuevo Género": genero = st.session_state.get('tmp_genero_nuevo', '').strip()
    elif sel_gen == "Selecciona o busca...": genero = ""
    else: genero = sel_gen or ""
        
    sel_edit = st.session_state.get('sel_editorial')
    if sel_edit == "➕ Crear Nueva Editorial": editorial = st.session_state.get('tmp_editorial_nueva', '').strip()
    elif sel_edit == "Selecciona o busca...": editorial = ""
    else: editorial = sel_edit or ""

    if not titulo:
        st.session_state['vm_error_libro'] = "El Título es obligatorio."
        return
        
    titulo_limpio = limpiar_texto_para_busqueda(titulo)
    conn = get_db_connection()
    if conn.table("libros").select("titulo").eq("titulo", titulo_limpio).execute().data:
        st.session_state['vm_error_libro'] = f"🚫 DUPLICADO: Ya existe un libro con título '{titulo_limpio}'."
        return
        
    st.session_state.vm_carrito.append({
        "libro_id": None, "titulo": titulo.upper(), "cantidad": st.session_state.get('tmp_cant', 1), 
        "stock_actual": st.session_state.get('tmp_stock', 0), "es_nuevo": True, "autor": autor.upper() if autor else "", 
        "genero": genero.upper() if genero else "", "editorial": editorial.upper() if editorial else "", 
        "encuadernacion": st.session_state.get('tmp_encuadernacion', ''), "precio": st.session_state.get('tmp_precio', 0.0), 
        "costo": st.session_state.get('tmp_costo', 0.0), "stock_inicial": st.session_state.get('tmp_stock', 0)
    })
    
    st.session_state['vm_error_libro'] = ""
    for k in ['tmp_titulo', 'sel_autor', 'tmp_autor_nuevo', 'sel_genero', 'tmp_genero_nuevo', 'sel_editorial', 'tmp_editorial_nueva', 'tmp_encuadernacion', 'tmp_precio', 'tmp_costo', 'tmp_stock', 'tmp_cant']:
        if k in st.session_state: del st.session_state[k]

def mostrar_ventas_masivas():
    st.title("📈 Ventas Masivas y Eventos")
    defaults = {
        'vm_carrito': [], 'vm_nombre_evento': "", 'vm_tipo_sel': "VENTA EN FERIA", 'vm_tipo_pers': "", 
        'vm_fecha_evento': None, 'vm_ingreso': 0.0, 'vm_costo': 0.0, 'vm_descontar_stock': False, 
        'vm_estado_evento': "POR EMPEZAR", 'vm_estado_pago': "PENDIENTE", 'vm_comentarios': "", 
        'vm_modo_libro': "📚 Existente en Catálogo", 'vm_error_libro': ""
    }
    for key in defaults:
        if key not in st.session_state: st.session_state[key] = defaults[key]

    tab_nueva, tab_historial, tab_anular = st.tabs(["➕ Nueva Venta Masiva", "📜 Historial", "🚫 Anular"])

    with tab_nueva:
        st.markdown("#### 1. Información General del Evento")
        col1, col2 = st.columns(2)
        col1.text_input("Nombre o Descripción*", key="vm_nombre_evento")
        col2.selectbox("Tipo de Evento*", ["", "VENTA EN FERIA", "RIFA", "CLUB DE LECTURA", "EVENTO ESPECIAL", "VENTA DE BODEGA", "OTRO"], key="vm_tipo_sel")
        if st.session_state.vm_tipo_sel == "OTRO": col2.text_input("Especificar OTRO:", key="vm_tipo_pers")
        st.date_input("Fecha del Evento (Opcional)", key="vm_fecha_evento")

        st.markdown("#### 2. Datos Financieros")
        col_f1, col_f2 = st.columns(2)
        col_f1.number_input("Ingreso Total Bruto ($)*", min_value=0.0, step=10000.0, key="vm_ingreso")
        col_f2.number_input("Costo Total del Evento ($)", min_value=0.0, step=5000.0, key="vm_costo")

        st.markdown("#### 3. Libros y Gestión de Stock")
        st.checkbox("Descontar stock de los libros asociados", key="vm_descontar_stock")
        
        with st.container(border=True):
            st.radio("Añadir libro:", ["📚 Existente en Catálogo", "➕ Crear Nuevo Libro"], horizontal=True, label_visibility="collapsed", key="vm_modo_libro")
            
            if st.session_state.vm_modo_libro == "📚 Existente en Catálogo":
                df_libros_catalogo = cargar_catalogo_libros_vm()
                if not df_libros_catalogo.empty:
                    df_libros_catalogo['label_busqueda'] = df_libros_catalogo.apply(lambda r: f"{r['titulo']} (Stock: {r['stock']})", axis=1)
                    col_b1, col_b2 = st.columns([3, 1])
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
                            else: st.warning("El libro ya está en la lista.")
                        else: st.error("Selecciona un libro.")
                else: st.warning("Catálogo vacío.")
                    
            elif st.session_state.vm_modo_libro == "➕ Crear Nuevo Libro":
                autores_db, generos_db, editoriales_db = cargar_listas_desplegables()
                if st.session_state.get('vm_error_libro'): st.error(st.session_state['vm_error_libro'])
                
                st.text_input("Título*", key="tmp_titulo")
                col_n1, col_n2, col_n3 = st.columns(3)
                
                sel_autor = col_n1.selectbox("Autor", ["Selecciona o busca...", "➕ Crear Nuevo Autor"] + autores_db, key="sel_autor")
                if sel_autor == "➕ Crear Nuevo Autor": col_n1.text_input("Nombre autor", key="tmp_autor_nuevo")
                    
                sel_gen = col_n2.selectbox("Género", ["Selecciona o busca...", "➕ Crear Nuevo Género"] + generos_db, key="sel_genero")
                if sel_gen == "➕ Crear Nuevo Género": col_n2.text_input("Nombre género", key="tmp_genero_nuevo")
                    
                sel_edit = col_n3.selectbox("Editorial", ["Selecciona o busca...", "➕ Crear Nueva Editorial"] + editoriales_db, key="sel_editorial")
                if sel_edit == "➕ Crear Nueva Editorial": col_n3.text_input("Nombre editorial", key="tmp_editorial_nueva")
                
                col_n4, col_n5, col_n6, col_n7, col_n8 = st.columns(5)
                col_n4.selectbox("Encuadernación", ["", "TAPA BLANDA", "TAPA DURA", "ESPIRAL"], key="tmp_encuadernacion")
                col_n5.number_input("Precio Oficial*", min_value=0.0, step=500.0, key="tmp_precio")
                col_n6.number_input("Costo*", min_value=0.0, step=500.0, key="tmp_costo")
                col_n7.number_input("Stock Inicial*", min_value=0, step=1, key="tmp_stock")
                col_n8.number_input("Cant. Implicada*", min_value=1, step=1, key="tmp_cant")
                
                st.button("➕ Crear y Añadir a la lista", type="secondary", on_click=anadir_nuevo_libro_carrito)

        if st.session_state.vm_carrito:
            st.write("📋 **Lista de Libros Implicados:**")
            df_carrito = pd.DataFrame(st.session_state.vm_carrito)
            df_carrito.insert(0, 'Quitar', False)
            df_editado = st.data_editor(
                df_carrito[['Quitar', 'titulo', 'cantidad', 'stock_actual', 'es_nuevo']], 
                column_config={"Quitar": st.column_config.CheckboxColumn("Quitar ❌", default=False)}, 
                hide_index=True, use_container_width=True
            )
            for i, row in df_editado.iterrows(): st.session_state.vm_carrito[i]['cantidad'] = row['cantidad']
            if st.button("🗑️ Quitar Seleccionados"):
                indices_a_quitar = df_editado[df_editado['Quitar'] == True].index.tolist()
                for i in sorted(indices_a_quitar, reverse=True): st.session_state.vm_carrito.pop(i)
                st.rerun()

        st.markdown("#### 4. Estado del Evento")
        col_e1, col_e2 = st.columns(2)
        col_e1.selectbox("Estado del Evento", ["POR EMPEZAR", "EN CURSO", "FINALIZADO"], key="vm_estado_evento", on_change=on_estado_evento_change)
        col_e2.selectbox("Estado del Pago", ["PENDIENTE", "PAGADO"], key="vm_estado_pago")
        st.text_area("Comentarios Adicionales (Opcional)", key="vm_comentarios")
        
        if st.button("💾 GUARDAR VENTA MASIVA TOTAL", type="primary", use_container_width=True):
            nombre_limpio = st.session_state.vm_nombre_evento.upper().strip()
            tipo_final = (st.session_state.vm_tipo_pers.upper().strip() if st.session_state.vm_tipo_sel == "OTRO" else st.session_state.vm_tipo_sel)
            if not nombre_limpio or not tipo_final:
                st.error("El nombre y el tipo son obligatorios.")
            else:
                datos_para_db = {
                    "nombre_evento": nombre_limpio, "tipo_evento": tipo_final,
                    "fecha_evento": st.session_state.vm_fecha_evento.isoformat() if st.session_state.vm_fecha_evento else None,
                    "ingreso_total": st.session_state.vm_ingreso, "costo_total": st.session_state.vm_costo,
                    "libros_implicados": st.session_state.vm_carrito, "stock_descontado": st.session_state.vm_descontar_stock,
                    "estado_evento": st.session_state.vm_estado_evento, "estado_pago": st.session_state.vm_estado_pago,
                    "comentarios": st.session_state.vm_comentarios.upper().strip()
                }
                with st.spinner("Procesando evento masivo..."):
                    exito, error = procesar_nueva_venta_masiva(datos_para_db)
                if exito:
                    st.success("¡Venta masiva registrada con éxito!")
                    keys_to_clear = [k for k in st.session_state.keys() if k.startswith('vm_') or k.startswith('tmp_') or k.startswith('sel_')]
                    for k in keys_to_clear: del st.session_state[k]
                    time.sleep(2)
                    st.rerun()
                else: st.error(f"Error: {error}")

    with tab_historial:
        st.markdown("### 📜 Historial de Ventas Masivas")
        df_historial = cargar_historial_ventas_masivas()
        if df_historial.empty: st.info("No hay ventas masivas.")
        else:
            def form_libros(x):
                try: return " | ".join([f"{i.get('cantidad',1)}x {i.get('titulo','')}" for i in json.loads(x)]) if isinstance(x, str) else "Ninguno"
                except: return "Error leyendo"
            df_historial['libros_resumen'] = df_historial['libros_implicados'].apply(form_libros)
            st.dataframe(df_historial[['evento_id', 'fecha_evento', 'nombre_evento', 'tipo_evento', 'ingreso_total', 'costo_total', 'estado_evento', 'estado_pago', 'libros_resumen']], use_container_width=True, hide_index=True)

    with tab_anular:
        st.markdown("### 🚫 Anular Venta Masiva")
        df_historial_anular = cargar_historial_ventas_masivas()
        if not df_historial_anular.empty:
            opciones_anular = {f"#{r['evento_id']} - {r['nombre_evento']}": r for _, r in df_historial_anular.iterrows()}
            sel_anular = st.selectbox("Evento a anular:", [""] + list(opciones_anular.keys()))
            if sel_anular:
                ev = opciones_anular[sel_anular]
                confirm = st.checkbox("Confirmar anulación permanentemente.")
                if st.button("🟥 ANULAR EVENTO", disabled=not confirm, type="primary"):
                    exito, error = anular_venta_masiva(ev['evento_id'], ev.get('stock_descontado'), ev.get('libros_implicados'))
                    if exito: 
                        st.success("Evento anulado.")
                        time.sleep(2); st.rerun()
                    else: st.error(f"Error: {error}")
        else: st.info("No hay eventos para anular.")

if __name__ == "__main__":
    mostrar_ventas_masivas()
