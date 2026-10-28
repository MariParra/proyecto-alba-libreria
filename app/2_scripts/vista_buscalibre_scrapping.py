import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto_para_busqueda

def mostrar_buscalibre_scrapping():
    st.markdown("<h2 style='color: #4A4D7E;'>🔍 Buscalibre Price Tracker</h2>", unsafe_allow_html=True)
    
    # 1. CUADRO INFORMATIVO COLAPSABLE (UX)
    with st.expander("💡 ¿Cómo funciona el Scraper y el Valor Objetivo?", expanded=False):
        st.write(
            "1. **Monitoreo Diario:** El script alojado en *Alwaysdata* revisa de forma automática los precios de Buscalibre cada día.\n"
            "2. **Historial de Precios:** Cada consulta guarda un registro histórico en la base de datos para mostrar las tendencias de precios de cada libro.\n"
            "3. **Valor Objetivo (Precio Alerta):** Si el precio de Buscalibre cae por debajo o igual al **Precio Objetivo** configurado "
            "(con un margen a favor de hasta **+$1.000 CLP**), el sistema encola una alerta.\n"
            "4. **Notificación Consolidada:** Al terminar de revisar todos los libros, el sistema despacha un único correo resumido con "
            "todas las ofertas vigentes a la lista de correos autorizados."
        )

    try:
        conn = get_db_connection()
    except Exception as e:
        st.error(f"Error de conexión con la base de datos: {e}")
        return

    # Obtener catálogos existentes para autocompletado y selectores inteligentes
    try:
        res_libros = conn.table("libros").select("*").order("titulo").execute()
        libros_data = res_libros.data if res_libros.data else []
        
        # Extraer valores únicos inteligentes de la base de datos (Normalizados en MAYÚSCULAS)
        autores_existentes = sorted(list(set([limpiar_texto_para_busqueda(l['autor']) for l in libros_data if l.get('autor')])))
        editoriales_existentes = sorted(list(set([limpiar_texto_para_busqueda(l['editorial']) for l in libros_data if l.get('editorial')])))
        generos_existentes = sorted(list(set([limpiar_texto_para_busqueda(l['genero']) for l in libros_data if l.get('genero')])))
        encuader_existentes = sorted(list(set([limpiar_texto_para_busqueda(l['encuadernacion']) for l in libros_data if l.get('encuadernacion')])))
    except Exception:
        libros_data = []
        autores_existentes = []
        editoriales_existentes = []
        generos_existentes = []
        encuader_existentes = []

    opciones_libros = {f"{limpiar_texto_para_busqueda(l['titulo'])} (ISBN: {l.get('isbn', 'N/A')}):": l for l in libros_data}
    
    # --- PESTAÑAS ADMINISTRATIVAS PARA MEJORAR LA ORGANIZACIÓN (UX) ---
    tab_gestion, tab_actualizacion_masiva = st.tabs(["📌 Registrar y Buscar", "⚡ Actualización Masiva de Precios"])
    
    # =====================================================================
    # PESTAÑA 1: REGISTRO Y GESTIÓN DE LIBROS INDIVIDUALES
    # =====================================================================
    with tab_gestion:
        # Registrar libro colapsable
        with st.expander("📌 Registrar Nuevo Libro para Monitoreo", expanded=True):
            # Selector autocompletable para buscar libros existentes
            libro_seleccionado = st.selectbox(
                "Autocompletar con un libro de la base de datos Alba:",
                options=list(opciones_libros.keys()),
                index=None,
                placeholder="Selecciona un libro de la base de datos...",
                key="sb_scra_libro"
            )

            # --- CONTROL INTELIGENTE DE ESTADO (SYNC) ---
            if "previo_libro_seleccionado" not in st.session_state:
                st.session_state.previo_libro_seleccionado = None

            if libro_seleccionado != st.session_state.previo_libro_seleccionado:
                st.session_state.previo_libro_seleccionado = libro_seleccionado
                if libro_seleccionado:
                    libro_db = opciones_libros[libro_seleccionado]
                    st.session_state["txt_scra_titulo"] = libro_db.get("titulo") or ""
                    st.session_state["txt_scra_isbn"] = libro_db.get("isbn") or ""
                    
                    # Autores
                    autor_val = libro_db.get("autor") or ""
                    if autor_val in autores_existentes:
                        st.session_state["sb_autor_existente"] = autor_val
                    else:
                        st.session_state["sb_autor_existente"] = "OTRO (Escribir nuevo...)"
                        st.session_state["txt_scra_autor"] = autor_val

                    # Editoriales
                    edit_val = libro_db.get("editorial") or ""
                    if edit_val in editoriales_existentes:
                        st.session_state["sb_editorial_existente"] = edit_val
                    else:
                        st.session_state["sb_editorial_existente"] = "OTRO (Escribir nuevo...)"
                        st.session_state["txt_scra_editorial"] = edit_val

                    # Géneros
                    gen_val = libro_db.get("genero") or ""
                    if gen_val in generos_existentes:
                        st.session_state["sb_genero_existente"] = gen_val
                    else:
                        st.session_state["sb_genero_existente"] = "OTRO (Escribir nuevo...)"
                        st.session_state["txt_scra_genero"] = gen_val

                    # Encuadernación
                    enc_val = libro_db.get("encuadernacion") or ""
                    if enc_val in encuader_existentes:
                        st.session_state["sb_encuader_existente"] = enc_val
                    else:
                        st.session_state["sb_encuader_existente"] = "OTRO (Escribir nuevo...)"
                        st.session_state["txt_scra_encuader"] = enc_val
                else:
                    for k in ["txt_scra_titulo", "txt_scra_isbn", "sb_autor_existente", "txt_scra_autor", 
                              "sb_editorial_existente", "txt_scra_editorial", "sb_genero_existente", "txt_scra_genero",
                              "sb_encuader_existente", "txt_scra_encuader"]:
                        st.session_state[k] = "" if "txt" in k else None

            col1, col2 = st.columns(2)
            with col1:
                titulo = st.text_input("Título del libro (Obligatorio):", key="txt_scra_titulo")
                
                # --- AUTOR (DInámico con opción OTRO) ---
                opciones_autores = autores_existentes + ["OTRO (Escribir nuevo...)"]
                autor_select = st.selectbox("Autor:", options=opciones_autores, index=None, placeholder="Elige un autor...", key="sb_autor_existente")
                
                if autor_select == "OTRO (Escribir nuevo...)" or (not autores_existentes and autor_select is None):
                    autor = st.text_input("Escribir nuevo Autor (MANDATORIO):", key="txt_scra_autor")
                else:
                    autor = autor_select
                    
                isbn = st.text_input("ISBN (MANDATORIO):", key="txt_scra_isbn")
                
                # --- ENCUADERNACIÓN (Dinámico con opción OTRO) ---
                opciones_encuader = encuader_existentes + ["OTRO (Escribir nuevo...)"]
                encuader_select = st.selectbox("Encuadernación:", options=opciones_encuader, index=None, placeholder="Elige tipo encuadernación...", key="sb_encuader_existente")
                
                if encuader_select == "OTRO (Escribir nuevo...)" or (not encuader_existentes and encuader_select is None):
                    encuader = st.text_input("Escribir nueva Encuadernación (MANDATORIO):", key="txt_scra_encuader")
                else:
                    encuader = encuader_select

        with col2:
            url_buscalibre = st.text_input("URL Buscalibre (Opcional - El Scrapper la buscará si se deja vacía):", placeholder="https://www.buscalibre.cl/libro-...", key="txt_scra_buscalibre")
            
            # --- EDITORIAL (Dinámico con opción OTRO) ---
            opciones_editoriales = editoriales_existentes + ["OTRO (Escribir nuevo...)"]
            editorial_select = st.selectbox("Editorial:", options=opciones_editoriales, index=None, placeholder="Elige editorial...", key="sb_editorial_existente")
            
            if editorial_select == "OTRO (Escribir nuevo...)" or (not editoriales_existentes and editorial_select is None):
                editorial = st.text_input("Escribir nueva Editorial (MANDATORIO):", key="txt_scra_editorial")
            else:
                editorial = editorial_select
            
            # --- GÉNERO (Dinámico con opción OTRO) ---
            opciones_generos = generos_existentes + ["OTRO (Escribir nuevo...)"]
            genero_select = st.selectbox("Género:", options=opciones_generos, index=None, placeholder="Elige género...", key="sb_genero_existente")
            
            if genero_select == "OTRO (Escribir nuevo...)" or (not generos_existentes and genero_select is None):
                genero = st.text_input("Escribir nuevo Género / Categoría (Opcional):", key="txt_scra_genero")
            else:
                genero = genero_select
            
            target_price = st.number_input("Precio Objetivo (CLP):", min_value=0, value=0, step=1000, key="num_scra_target")

        id_usuario_defecto = "00000000-0000-0000-0000-000000000000"

        if st.button("Agregar a la Wishlist", type="primary"):
            titulo_clean = limpiar_texto_para_busqueda(titulo)
            autor_clean = limpiar_texto_para_busqueda(autor)
            editorial_clean = limpiar_texto_para_busqueda(editorial)
            isbn_clean = ''.join(filter(str.isdigit, str(isbn)))
            encuader_clean = limpiar_texto_para_busqueda(encuader)
            genero_clean = limpiar_texto_para_busqueda(genero) if genero else None

            if not titulo_clean:
                st.error("⚠️ El título del libro es obligatorio.")
                return
            if not autor_clean:
                st.error("⚠️ El autor es obligatorio.")
                return
            if not editorial_clean:
                st.error("⚠️ La editorial es obligatoria.")
                return
            if not isbn_clean:
                st.error("⚠️ El ISBN es obligatorio.")
                return
            if not encuader_clean:
                st.error("⚠️ La encuadernación es obligatoria.")
                return

            try:
                # 1. Crear libro si no existe
                existe_libro_db = any(limpiar_texto_para_busqueda(l.get('titulo', '')) == titulo_clean or (l.get('isbn') and l.get('isbn') == isbn_clean) for l in libros_data)
                
                if not existe_libro_db:
                    try:
                        conn.table("libros").insert({
                            "titulo": titulo_clean,
                            "autor": autor_clean,
                            "isbn": isbn_clean,
                            "editorial": editorial_clean,
                            "genero": genero_clean,
                            "encuadernacion": encuader_clean
                        }).execute()
                        st.toast(f"📖 ¡Libro '{titulo_clean}' creado en la base de datos!")
                    except Exception as db_err:
                        st.warning(f"Nota: {db_err}")

                # 2. Registrar en la wishlist
                target_val_final = target_price
                if target_price == 0:
                    if encuader_clean == "TAPA DURA":
                        target_val_final = 15000
                    elif encuader_clean == "TAPA BLANDA":
                        target_val_final = 11000

                wishlist_data = {
                    "user_id": id_usuario_defecto,
                    "title": titulo_clean,
                    "author": autor_clean,
                    "isbn": isbn_clean,
                    "store_url_buscalibre": url_buscalibre if url_buscalibre else None,
                    "target_price": target_val_final if target_val_final > 0 else None,
                    "editorial": editorial_clean,
                    "genre": genero_clean,
                    "current_price": None,
                    "alert_sent": False,
                    "encuadernacion": encuader_clean
                }
                
                try:
                    conn.table("book_wishlist").insert(wishlist_data).execute()
                except Exception as insert_err:
                    if "encuadernacion" in str(insert_err):
                        wishlist_data.pop("encuadernacion", None)
                        conn.table("book_wishlist").insert(wishlist_data).execute()
                    else:
                        raise insert_err
                st.success(f"🎉 ¡Libro '{titulo_clean}' agregado con éxito para monitoreo!")
                
                for key in ["sb_scra_libro", "txt_scra_titulo", "txt_scra_autor", "txt_scra_isbn", "num_scra_target", 
                            "txt_scra_buscalibre", "txt_scra_editorial", "txt_scra_genero", "sb_autor_existente", 
                            "sb_editorial_existente", "sb_genero_existente", "sb_encuader_existente", "txt_scra_encuader"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")

        # Mostrar wishlist actual e historial de precios
        st.markdown("---")
        st.markdown("### 📋 Libros Destacados en Monitoreo (Máx. 3)")
        
        try:
            res_wish = conn.table("book_wishlist").select("*").execute()
            wishlist = res_wish.data if res_wish.data else []
        except Exception as e:
            st.warning(f"Error al cargar wishlist: {e}")
            wishlist = []

        # AGREGAR FILTRO Y LUPA DE BÚSQUEDA
        search_query = st.text_input("🔍 Buscar en libros de monitoreo (Título, Autor, ISBN, Editorial):", value="", placeholder="Escribe para filtrar tu wishlist...")

        # Filtrado en memoria
        if search_query:
            q = limpiar_texto_para_busqueda(search_query).lower()
            wishlist = [
                item for item in wishlist 
                if q in (item.get('title') or '').lower() 
                or q in (item.get('author') or '').lower() 
                or q in (item.get('isbn') or '').lower() 
                or q in (item.get('editorial') or '').lower()
            ]

        # Lógica de Ordenación: Prioridad ofertas bajadas de precio
        def sort_prioridad_oferta(item):
            curr = item.get("current_price")
            prev = item.get("previous_price")
            if curr is not None and prev is not None:
                diff = float(curr) - float(prev)
                if diff < 0:
                    return (0, diff) 
                elif diff == 0:
                    return (1, 0)    
                else:
                    return (2, diff) 
            return (3, 0)            

        wishlist = sorted(wishlist, key=sort_prioridad_oferta)
        total_encontrados = len(wishlist)
        wishlist_sliced = wishlist[:3]

        if wishlist_sliced:
            if search_query:
                st.write(f"🔍 *Mostrando los {len(wishlist_sliced)} resultados prioritarios (de {total_encontrados} encontrados):*")
            else:
                st.write(f"💡 *Mostrando los {len(wishlist_sliced)} libros prioritarios con mayor descuento:*")
                
            for item in wishlist_sliced:
                with st.container(border=True):
                    col_detalles, col_acciones = st.columns([3, 1.5])
                    with col_detalles:
                        st.markdown(f"#### 📖 {item['title']}")
                        if item.get("author"):
                            st.markdown(f"**Autor:** {item['author']}")
                        
                        encuad_str = f" | **Encuadernación:** {item['encuadernacion']}" if item.get('encuadernacion') else ""
                        st.write(f"**ISBN:** {item.get('isbn') or 'N/A'} | **Editorial:** {item.get('editorial') or 'N/A'} | **Género:** {item.get('genre') or 'N/A'}{encuad_str}")
                        
                        # Formato de precios
                        target_price_val = item.get("target_price")
                        target_price_str = f"${float(target_price_val):,.0f} CLP" if target_price_val is not None else "No definido"
                        
                        current_price_val = item.get("current_price")
                        previous_price_val = item.get("previous_price")
                        
                        tendencia_str = ""
                        if current_price_val is not None:
                            current_price_str = f"${float(current_price_val):,.0f} CLP"
                            if previous_price_val is not None:
                                diff = float(current_price_val) - float(previous_price_val)
                                if diff < 0:
                                    tendencia_str = f" 🟢 ⬇️ **Bajó de precio! (-${abs(diff):,.0f} CLP)**"
                                elif diff > 0:
                                    tendencia_str = f" 🔴 ⬆️ **Subió de precio (+${diff:,.0f} CLP)**"
                                else:
                                    tendencia_str = " 🟡 ➡️ **Sin cambios**"
                        else:
                            current_price_str = "Pendiente de Scraping"
                            
                        st.write(f"**Precio Objetivo:** {target_price_str}")
                        st.write(f"**Precio Actual:** {current_price_str}{tendencia_str}")
                        
                        if item.get("store_url_buscalibre"):
                            st.markdown(f"🔗 Enlace: [Ver en Buscalibre]({item['store_url_buscalibre']})")
                        
                    with col_acciones:
                        # --- EDICIÓN INDIVIDUAL DE PRECIO OBJETIVO (Punto 1) ---
                        st.markdown("**⚡ Edición Rápida**")
                        # Cargamos el precio actual del modelo
                        nuevo_precio_obj_indiv = st.number_input(
                            "Editar Precio Objetivo:", 
                            min_value=0, 
                            value=int(item['target_price']) if item.get('target_price') else 0,
                            step=1000, 
                            key=f"edit_indiv_{item['id']}"
                        )
                        # Renderizamos los botones de forma vertical consecutiva para evitar anidamiento de columnas prohibido
                        if st.button("Guardar", key=f"save_indiv_{item['id']}", use_container_width=True, type="primary"):
                            try:
                                conn.table("book_wishlist").update({"target_price": nuevo_precio_obj_indiv}).eq("id", item["id"]).execute()
                                st.toast("✅ ¡Precio Objetivo guardado!")
                                st.rerun()
                            except Exception as err:
                                st.error(f"Error: {err}")
                        if st.button("Eliminar", key=f"del_{item['id']}", use_container_width=True, type="secondary"):
                            try:
                                conn.table("book_wishlist").delete().eq("id", item["id"]).execute()
                                st.toast(f"Monitoreo eliminado")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                                    
                    # Historial reciente de precios
                    try:
                        res_hist = conn.table("book_price_history").select("*").eq("wishlist_item_id", item["id"]).order("recorded_at", desc=True).limit(5).execute()
                        if res_hist.data:
                            hist_df = pd.DataFrame(res_hist.data)
                            hist_df['recorded_at'] = pd.to_datetime(hist_df['recorded_at']).dt.strftime('%Y-%m-%d %H:%M')
                            hist_df = hist_df.rename(columns={'price': 'Precio (CLP)', 'store_name': 'Tienda', 'recorded_at': 'Fecha'})
                            with st.expander("📊 Ver Historial Completo de fluctuaciones", expanded=False):
                                st.dataframe(hist_df[['Fecha', 'Tienda', 'Precio (CLP)']], use_container_width=True, hide_index=True)
                    except Exception:
                        pass
        else:
            st.info("No hay libros que coincidan con la búsqueda en el tracker actualmente.")

    # =====================================================================
    # PESTAÑA 2: ACTUALIZACIÓN MASIVA / ADMINISTRACIÓN POR LOTES (Punto 2)
    # =====================================================================
    with tab_actualizacion_masiva:
        st.markdown("<h3 style='color: #4A4D7E;'>⚡ Actualización de Precios por Lotes</h3>", unsafe_allow_html=True)
        st.write("Aplica reglas masivas de precios de forma inmediata para grupos enteros de libros (ej. Editoriales o Encuadernación).")
        
        # Filtros de Agrupación para actualizar
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            editorial_masiva = st.selectbox(
                "Filtrar por Editorial:", 
                options=["TODAS"] + editoriales_existentes, 
                index=0, 
                key="sb_masivo_editorial"
            )
            
        with col_f2:
            encuader_masiva = st.selectbox(
                "Filtrar por Encuadernación:", 
                options=["TODAS"] + encuader_existentes, 
                index=0, 
                key="sb_masivo_encuader"
            )
            
        col_f3, col_f4 = st.columns(2)
        with col_f3:
            genero_masiva = st.selectbox(
                "Filtrar por Género / Categoría:", 
                options=["TODOS"] + generos_existentes, 
                index=0, 
                key="sb_masivo_genero"
            )
            
        with col_f4:
            nuevo_precio_masivo = st.number_input(
                "Nuevo Precio Objetivo a Asignar (CLP):", 
                min_value=0, 
                value=0, 
                step=1000, 
                key="num_masivo_precio"
            )
            
        # Simulación de cuántos registros se verán afectados por el filtro
        try:
            query_test = conn.table("book_wishlist").select("id", count="exact")
            if editorial_masiva != "TODAS":
                query_test = query_test.eq("editorial", editorial_masiva)
            if encuader_masiva != "TODAS":
                query_test = query_test.eq("encuadernacion", encuader_masiva)
            if genero_masiva != "TODOS":
                query_test = query_test.eq("genre", genero_masiva)
            
            res_test = query_test.execute()
            registros_afectados = res_test.count if res_test.count is not None else 0
            
            st.warning(f"👉 Esta acción actualizará de forma masiva a **{registros_afectados}** libros de tu wishlist de monitoreo.")
        except Exception:
            registros_afectados = 0
            
        if st.button("Aplicar Actualización Masiva", type="primary", use_container_width=True):
            if nuevo_precio_masivo == 0:
                st.error("⚠️ El precio objetivo debe ser mayor a $0 CLP.")
                return
                
            try:
                # Construir el update condicional de Supabase de manera quirúrgica
                update_query = conn.table("book_wishlist").update({"target_price": nuevo_precio_masivo})
                
                # Aplicamos filtros condicionales según lo seleccionado por el usuario
                if editorial_masiva != "TODAS":
                    update_query = update_query.eq("editorial", editorial_masiva)
                if encuader_masiva != "TODAS":
                    update_query = update_query.eq("encuadernacion", encuader_masiva)
                if genero_masiva != "TODOS":
                    update_query = update_query.eq("genre", genero_masiva)
                    
                update_query.execute()
                
                st.success(f"🎉 ¡Éxito! Se actualizaron correctamente {registros_afectados} libros al precio de ${nuevo_precio_masivo:,.0f} CLP.")
                st.rerun()
            except Exception as masivo_err:
                st.error(f"Error al aplicar actualización masiva: {masivo_err}")