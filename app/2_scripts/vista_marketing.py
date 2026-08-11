import streamlit as st
import pandas as pd
from utilidades import limpiar_texto_para_busqueda
from generador_collage import generar_collage_marketing

@st.cache_data(ttl=60)
def cargar_libros_para_marketing():
    from utilidades import get_db_connection
    conn = get_db_connection()
    try:
        # --- CAMBIO: Añadimos 'stock' a la consulta y quitamos el .gt("stock", 0) ---
        res = conn.table("libros").select("libro_id, titulo, autor, precio, precio_original, genero, stock").order("titulo").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except:
        return pd.DataFrame()

def mostrar_generador_marketing():
    st.title("🎨 Generador de Collages para Marketing")
    st.info("Crea una imagen de 1080x1920 con varios libros para tus Stories de Instagram. Las etiquetas de stock se añadirán solas.")

    df_libros = cargar_libros_para_marketing()

    if df_libros.empty:
        st.warning("No hay libros en el catálogo.")
        return

    with st.container(border=True):
        st.markdown("#### 1. Selecciona los Libros para el Collage")
        
        generos = sorted(df_libros['genero'].dropna().unique())
        genero_sel = st.selectbox("Filtrar por Género (opcional):", ["Todos"] + generos)

        df_filtrado = df_libros
        if genero_sel != "Todos":
            df_filtrado = df_libros[df_libros['genero'] == genero_sel]

        # Añadimos un aviso visual en el selectbox si el libro no tiene stock
        df_filtrado['label_selectbox'] = df_filtrado.apply(
            lambda x: f"{x['titulo']} (Sin Stock)" if int(x.get('stock', 0)) <= 0 else x['titulo'], 
            axis=1
        )
        
        opciones_libros = dict(zip(df_filtrado['label_selectbox'], df_filtrado['libro_id']))
        libros_seleccionados = st.multiselect(
            "Selecciona hasta 8 libros:",
            options=opciones_libros.keys(),
            max_selections=8
        )

    if libros_seleccionados:
        st.markdown("---")
        st.markdown("#### 2. Previsualización y Descarga")

        ids_seleccionados = [opciones_libros[t] for t in libros_seleccionados]
        df_final = df_libros[df_libros['libro_id'].isin(ids_seleccionados)]
        lista_libros_data = df_final.to_dict('records')

        # --- ¡PEGA TU URL BASE AQUÍ! ---
        URL_BASE_SUPABASE = "https://TU_PROYECTO.supabase.co/storage/v1/object/public/portadas/"
        
        with st.spinner("Armando el collage y calculando stock..."):
            png_bytes = generar_collage_marketing(lista_libros_data, URL_BASE_SUPABASE)

        if png_bytes:
            st.image(png_bytes, caption="Previsualización del Collage", use_container_width=True)
            
            st.download_button(
                label="📥 Descargar Collage para Instagram",
                data=png_bytes,
                file_name=f"collage_novedades.png",
                mime="image/png",
                type="primary",
                use_container_width=True
            )
        else:
            st.error("Hubo un error generando la imagen. Revisa las fuentes o las URLs de las imágenes.")