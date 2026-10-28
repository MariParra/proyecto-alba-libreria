import streamlit as st
import pandas as pd
from utilidades import get_db_connection

def mostrar_buscalibre_scrapping():
    st.markdown("<h2 style='color: #4A4D7E;'>🔍 Buscalibre Price Tracker</h2>", unsafe_allow_html=True)
    st.write("Gestiona la lista de deseos y monitorea precios en Buscalibre de forma automatizada.")

    try:
        conn = get_db_connection()
    except Exception as e:
        st.error(f"Error de conexión con la base de datos: {e}")
        return

    st.markdown("### 📌 Registrar Libro para Monitoreo")
    
    # Selector de libro existente en la base de datos de Alba para facilitar la carga
    try:
        res_libros = conn.table("libros").select("libro_id, titulo, isbn").order("libro_id").limit(100).execute()
        libros_data = res_libros.data if res_libros.data else []
    except Exception:
        libros_data = []

    opciones_libros = {f"{l['titulo']} (ISBN: {l.get('isbn', 'N/A')})": l for l in libros_data}
    
    libro_seleccionado = st.selectbox(
        "Autocompletar con un libro de la base de datos Alba:",
        options=list(opciones_libros.keys()),
        index=None,
        placeholder="Selecciona un libro (opcional)...",
        key="sb_scra_libro"
    )

    col1, col2 = st.columns(2)
    with col1:
        titulo_def = ""
        isbn_def = ""
        if libro_seleccionado:
            titulo_def = opciones_libros[libro_seleccionado]["titulo"]
            isbn_def = opciones_libros[libro_seleccionado].get("isbn") or ""
            
        titulo = st.text_input("Título del libro:", value=titulo_def, key="txt_scra_titulo")
        autor = st.text_input("Autor (Opcional):", key="txt_scra_autor")
        isbn = st.text_input("ISBN (Opcional):", value=isbn_def, key="txt_scra_isbn")
        target_price = st.number_input("Precio Objetivo (CLP):", min_value=0, value=0, step=1000, key="num_scra_target")

    with col2:
        url_buscalibre = st.text_input("URL Buscalibre:", placeholder="https://www.buscalibre.cl/libro-...", key="txt_scra_buscalibre")
        editorial = st.text_input("Editorial (Opcional):", key="txt_scra_editorial")
        genero = st.text_input("Género / Categoría (Opcional):", key="txt_scra_genero")

    id_usuario_defecto = "00000000-0000-0000-0000-000000000000"

    if st.button("Agregar a la Wishlist", type="primary"):
        if not titulo:
            st.error("⚠️ El título del libro es obligatorio.")
            return
        if not url_buscalibre:
            st.error("⚠️ Debes proporcionar la URL de Buscalibre para el monitoreo.")
            return

        try:
            wishlist_data = {
                "user_id": id_usuario_defecto,
                "title": titulo,
                "author": autor if autor else None,
                "isbn": isbn if isbn else None,
                "store_url_buscalibre": url_buscalibre,
                "target_price": target_price if target_price > 0 else None,
                "editorial": editorial if editorial else None,
                "genre": genero if genero else None,
                "current_price": None,
                "alert_sent": False
            }
            conn.table("book_wishlist").insert(wishlist_data).execute()
            st.success(f"🎉 ¡Libro '{titulo}' agregado con éxito para monitoreo!")
            
            # Limpieza de estados según directrices UX
            for key in ["sb_scra_libro", "txt_scra_titulo", "txt_scra_autor", "txt_scra_isbn", "num_scra_target", "txt_scra_buscalibre", "txt_scra_editorial", "txt_scra_genero"]:
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
                    
                    # Evitamos f-strings aninados complejos para compatibilidad absoluta
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