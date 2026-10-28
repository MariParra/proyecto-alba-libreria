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
    
    # 1. REGISTRAR LIBRO AHORA ES UN EXPANDER COLAPSABLE (Punto 1)
    with st.expander("📌 Registrar Libro para Monitoreo", expanded=True):
        
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
            # Normalizamos los valores usando limpiar_texto_para_busqueda
            titulo_clean = limpiar_texto_para_busqueda(titulo)
            autor_clean = limpiar_texto_para_busqueda(autor)
            editorial_clean = limpiar_texto_para_busqueda(editorial)
            isbn_clean = ''.join(filter(str.isdigit, str(isbn))) # Limpia guiones del ISBN
            encuader_clean = limpiar_texto_para_busqueda(encuader)
            genero_clean = limpiar_texto_para_busqueda(genero) if genero else None

            # Validar campos obligatorios (URL ES OPCIONAL AHORA GRACIAS AL AUTO-DISCOVERY)
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
                # 1. Crear libro si no existe (con datos 100% normalizados)
                existe_libro_db = any(limpiar_texto_para_busqueda(l.get('titulo', '')) == titulo_clean or (l.get('isbn') and l.get('isbn') == isbn_clean) for l in libros_data)
                
                if not existe_libro_db:
                    try:
                        insert_libro = conn.table("libros").insert({
                            "titulo": titulo_clean,
                            "autor": autor_clean,
                            "isbn": isbn_clean,
                            "editorial": editorial_clean,
                            "genero": genero_clean,
                            "encuadernacion": encuader_clean
                        }).execute()
                        if insert_libro.data:
                            st.toast(f"📖 ¡Libro '{titulo_clean}' creado exitosamente en la base de datos Alba!")
                    except Exception as db_err:
                        st.warning(f"Nota: No se pudo registrar en la tabla libros de forma automática ({db_err}), guardando directo en wishlist.")

                # 2. Registrar en la wishlist de precios (datos 100% normalizados)
                wishlist_data = {
                    "user_id": id_usuario_defecto,
                    "title": titulo_clean,
                    "author": autor_clean,
                    "isbn": isbn_clean,
                    "store_url_buscalibre": url_buscalibre if url_buscalibre else None,
                    "target_price": target_price if target_price > 0 else None,
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
                st.success(f"🎉 ¡Libro '{titulo_clean}' agregado con éxito para monitoreo de precios!")
                
                # Limpieza de estados según directrices UX
                for key in ["sb_scra_libro", "txt_scra_titulo", "txt_scra_autor", "txt_scra_isbn", "num_scra_target", 
                            "txt_scra_buscalibre", "txt_scra_editorial", "txt_scra_genero", "sb_autor_existente", 
                            "sb_editorial_existente", "sb_genero_existente", "sb_encuader_existente", "txt_scra_encuader"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar en book_wishlist: {e}")

    # Mostrar wishlist actual e historial de precios
    st.markdown("---")
    st.markdown("### 📋 Libros en Monitoreo")
    
    try:
        res_wish = conn.table("book_wishlist").select("*").order("title").execute()
        wishlist = res_wish.data if res_wish.data else []
    except Exception as e:
        st.warning(f"Error al cargar wishlist: {e}")
        wishlist = []

    # 2. AGREGAR FILTRO Y LUPA DE BÚSQUEDA
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

    if wishlist:
        for item in wishlist:
            with st.container(border=True):
                col_detalles, col_acciones = st.columns([4, 1])
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
                    
                    # 3. LÓGICA DE FLECHAS DE FLUCTUACIÓN DE PRECIO
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
                    
                    # Mostrar historial de precios de este item
                    try:
                        res_hist = conn.table("book_price_history").select("*").eq("wishlist_item_id", item["id"]).order("recorded_at", desc=True).limit(5).execute()
                        if res_hist.data:
                            hist_df = pd.DataFrame(res_hist.data)
                            hist_df['recorded_at'] = pd.to_datetime(hist_df['recorded_at']).dt.strftime('%Y-%m-%d %H:%M')
                            hist_df = hist_df.rename(columns={'price': 'Precio (CLP)', 'store_name': 'Tienda', 'recorded_at': 'Fecha'})
                            st.write("**Historial Reciente:**")
                            st.dataframe(hist_df[['Fecha', 'Tienda', 'Precio (CLP)']], use_container_width=True, hide_index=True)
                    except Exception:
                        pass
                        
                with col_acciones:
                    if st.button("Eliminar", key=f"del_{item['id']}", type="secondary"):
                        try:
                            conn.table("book_wishlist").delete().eq("id", item["id"]).execute()
                            st.toast(f"Monitoreo eliminado para {item['title']}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")
    else:
        st.info("No hay libros configurados en el tracker actualmente.")