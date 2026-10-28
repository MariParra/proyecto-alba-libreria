import streamlit as st
import pandas as pd
from utilidades import get_db_connection

def mostrar_buscalibre_scrapping():
    st.markdown("<h2 style='color: #4A4D7E;'>🔍 Buscalibre Price Tracker</h2>", unsafe_allow_html=True)
    
    # 4. CUADRO INFORMATIVO DE FUNCIONAMIENTO (UX)
    st.info(
        "💡 **¿Cómo funciona el Scraper?**\n\n"
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

    # Obtener catálogos existentes para autocompletado y selectores inteligentes (Punto 3)
    try:
        # Obtenemos libros para el selector de autocompletado (Punto 1)
        res_libros = conn.table("libros").select("*").order("titulo").execute()
        libros_data = res_libros.data if res_libros.data else []
        
        # Extraer valores únicos inteligentes de la base de datos (Punto 3)
        autores_existentes = sorted(list(set([l['autor'].strip() for l in libros_data if l.get('autor')])))
        editoriales_existentes = sorted(list(set([l['editorial'].strip() for l in libros_data if l.get('editorial')])))
        generos_existentes = sorted(list(set([l['genero'].strip() for l in libros_data if l.get('genero')])))
    except Exception:
        libros_data = []
        autores_existentes = []
        editoriales_existentes = []
        generos_existentes = []

    opciones_libros = {f"{l['titulo']} (ISBN: {l.get('isbn', 'N/A')})": l for l in libros_data}
    
    st.markdown("### 📌 Registrar Libro para Monitoreo")
    
    # 1. Selector autocompletable para buscar libros existentes
    libro_seleccionado = st.selectbox(
        "Autocompletar con un libro de la base de datos Alba:",
        options=list(opciones_libros.keys()),
        index=None,
        placeholder="Selecciona un libro de la base de datos...",
        key="sb_scra_libro"
    )

    # Inicialización de variables para autofill
    titulo_def = ""
    autor_def = ""
    isbn_def = ""
    editorial_def = ""
    genero_def = ""
    libro_db_id = None

    if libro_seleccionado:
        libro_db = opciones_libros[libro_seleccionado]
        titulo_def = libro_db.get("titulo") or ""
        autor_def = libro_db.get("autor") or ""
        isbn_def = libro_db.get("isbn") or ""
        editorial_def = libro_db.get("editorial") or ""
        genero_def = libro_db.get("genero") or ""
        libro_db_id = libro_db.get("libro_id")

    col1, col2 = st.columns(2)
    with col1:
        titulo = st.text_input("Título del libro (Obligatorio):", value=titulo_def, key="txt_scra_titulo")
        
        # 3. Selectores inteligentes / Campos de texto combinados para Autor, Editorial y Género
        autor_select = st.selectbox("Autor existente (Opcional si vas a escribir uno nuevo abajo):", 
                                    options=autores_existentes, index=None, placeholder="Elige un autor existente...", key="sb_autor_existente")
        autor = st.text_input("Escribir o corregir Autor (MANDATORIO):", value=autor_def if not autor_select else autor_select, key="txt_scra_autor")
        
        isbn = st.text_input("ISBN (MANDATORIO):", value=isbn_def, key="txt_scra_isbn")
        target_price = st.number_input("Precio Objetivo (CLP):", min_value=0, value=0, step=1000, key="num_scra_target")

    with col2:
        url_buscalibre = st.text_input("URL Buscalibre (MANDATORIO):", placeholder="https://www.buscalibre.cl/libro-...", key="txt_scra_buscalibre")
        
        editorial_select = st.selectbox("Editorial existente (Opcional si vas a escribir una nueva abajo):", 
                                        options=editoriales_existentes, index=None, placeholder="Elige una editorial existente...", key="sb_editorial_existente")
        editorial = st.text_input("Escribir o corregir Editorial (MANDATORIO):", value=editorial_def if not editorial_select else editorial_select, key="txt_scra_editorial")
        
        genero_select = st.selectbox("Género existente (Opcional si vas a escribir uno nuevo abajo):", 
                                     options=generos_existentes, index=None, placeholder="Elige un género existente...", key="sb_genero_existente")
        genero = st.text_input("Escribir o corregir Género / Categoría (Opcional):", value=genero_def if not genero_select else genero_select, key="txt_scra_genero")

    id_usuario_defecto = "00000000-0000-0000-0000-000000000000"

    if st.button("Agregar a la Wishlist", type="primary"):
        # 2. Validar campos obligatorios
        if not titulo:
            st.error("⚠️ El título del libro es obligatorio.")
            return
        if not autor:
            st.error("⚠️ El autor es obligatorio.")
            return
        if not editorial:
            st.error("⚠️ La editorial es obligatoria.")
            return
        if not isbn:
            st.error("⚠️ El ISBN es obligatorio.")
            return
        if not url_buscalibre:
            st.error("⚠️ La URL de Buscalibre es obligatoria.")
            return

        try:
            # 1. Si no existe en la tabla de libros de Alba, lo creamos de forma automática (Punto 1)
            if not libro_db_id:
                try:
                    insert_libro = conn.table("libros").insert({
                        "titulo": titulo,
                        "autor": autor,
                        "isbn": isbn,
                        "editorial": editorial,
                        "genero": genero if genero else None
                    }).execute()
                    if insert_libro.data:
                        st.toast(f"📖 ¡Libro '{titulo}' creado exitosamente en la base de datos Alba!")
                except Exception as db_err:
                    st.warning(f"Nota: No se pudo registrar en la tabla libros de forma automática ({db_err}), guardando directo en wishlist.")

            # 2. Registrar en la wishlist de precios
            wishlist_data = {
                "user_id": id_usuario_defecto,
                "title": titulo,
                "author": autor,
                "isbn": isbn,
                "store_url_buscalibre": url_buscalibre,
                "target_price": target_price if target_price > 0 else None,
                "editorial": editorial,
                "genre": genero if genero else None,
                "current_price": None,
                "alert_sent": False
            }
            conn.table("book_wishlist").insert(wishlist_data).execute()
            st.success(f"🎉 ¡Libro '{titulo}' agregado con éxito para monitoreo de precios!")
            
            # Limpieza de estados según directrices UX
            for key in ["sb_scra_libro", "txt_scra_titulo", "txt_scra_autor", "txt_scra_isbn", "num_scra_target", 
                        "txt_scra_buscalibre", "txt_scra_editorial", "txt_scra_genero", "sb_autor_existente", 
                        "sb_editorial_existente", "sb_genero_existente"]:
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

    if wishlist:
        for item in wishlist:
            with st.container(border=True):
                col_detalles, col_acciones = st.columns([4, 1])
                with col_detalles:
                    st.markdown(f"#### 📖 {item['title']}")
                    if item.get("author"):
                        st.markdown(f"**Autor:** {item['author']}")
                    st.write(f"**ISBN:** {item.get('isbn') or 'N/A'} | **Editorial:** {item.get('editorial') or 'N/A'} | **Género:** {item.get('genre') or 'N/A'}")
                    
                    target_price_val = item.get("target_price")
                    if target_price_val is not None:
                        target_price_str = f"${float(target_price_val):,.0f} CLP"
                    else:
                        target_price_str = "No definido"
                        
                    current_price_val = item.get("current_price")
                    if current_price_val is not None:
                        current_price_str = f"${float(current_price_val):,.0f} CLP"
                    else:
                        current_price_str = "Pendiente de Scraping"
                        
                    st.write(f"**Precio Objetivo:** {target_price_str}")
                    st.write(f"**Precio Actual:** {current_price_str}")
                    
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