import streamlit as st
import pandas as pd
import io 
import base64 # <-- Nueva librería para el truco HTML
from utilidades import limpiar_texto_para_busqueda
from generador_collage import generar_collage_marketing

@st.cache_data(ttl=60)
def cargar_libros_para_marketing():
    from utilidades import get_db_connection
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, precio_original, genero, stock").order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        if not df.empty:
            df.dropna(subset=['libro_id', 'titulo'], inplace=True)
            df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0)
            df['libro_id'] = df['libro_id'].astype(str)
        return df
    except:
        return pd.DataFrame()

def mostrar_generador_marketing():
    st.title("🎨 Generador de Catálogos Masivos")
    st.info("Genera imágenes para tus Stories (12 libros por página).")

    try:
        URL_BASE_SUPABASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
    except KeyError:
        st.error("🚨 Falta la clave 'supabase_portadas_url' en secrets.toml.")
        st.stop()

    df_libros = cargar_libros_para_marketing()
    if df_libros.empty:
        st.warning("No hay libros en el catálogo para generar marketing.")
        return

    with st.container(border=True):
        st.markdown("#### 1. Filtra y Selecciona")
        
        generos_disponibles = sorted(df_libros['genero'].dropna().unique())
        genero_seleccionado = st.selectbox("Filtrar por Género (opcional):", ["Todos"] + generos_disponibles)

        df_filtrado = df_libros
        if genero_seleccionado != "Todos":
            df_filtrado = df_libros[df_libros['genero'] == genero_seleccionado]

        df_filtrado['label_selectbox'] = df_filtrado.apply(
            lambda x: f"{x['titulo']} (Sin Stock)" if int(x.get('stock', 0)) <= 0 else x['titulo'], axis=1
        )
        opciones_libros = dict(zip(df_filtrado['label_selectbox'], df_filtrado['libro_id']))

        seleccionar_todos = st.checkbox(f"✅ Seleccionar TODOS los libros filtrados ({len(df_filtrado)} libros)")
        
        libros_seleccionados = []
        if seleccionar_todos:
            libros_seleccionados = list(opciones_libros.keys())
        else:
            libros_seleccionados = st.multiselect("O selecciona manualmente:", options=opciones_libros.keys())

    if libros_seleccionados:
        st.markdown("---")
        st.markdown("#### 2. Configuración y Generación")
        agrupar_por_genero = st.checkbox("🗂️ Agrupar y titular hojas por Género", value=True)

        if st.button("🚀 Generar Catálogo Completo", type="primary", use_container_width=True):
            ids_seleccionados = [opciones_libros[t] for t in libros_seleccionados if t in opciones_libros]
            if not ids_seleccionados:
                st.warning("No se seleccionaron libros válidos.")
                st.stop()

            df_final = df_libros[df_libros['libro_id'].isin(ids_seleccionados)].copy()
            st.session_state.hojas_generadas = []

            with st.spinner("Pintando hojas del catálogo... Aguarda un momento."):
                if agrupar_por_genero:
                    for genero, df_grupo in df_final.groupby('genero'):
                        titulo_base = str(genero).upper() if pd.notna(genero) else "OTROS"
                        lista_data = df_grupo.sort_values('titulo').to_dict('records')
                        chunks = [lista_data[i:i + 12] for i in range(0, len(lista_data), 12)]
                        for idx, chunk in enumerate(chunks):
                            titulo_hoja = titulo_base if len(chunks) == 1 else f"{titulo_base} ({idx + 1}/{len(chunks)})"
                            img_obj = generar_collage_marketing(chunk, URL_BASE_SUPABASE, titulo_hoja)
                            if img_obj: st.session_state.hojas_generadas.append((titulo_hoja, img_obj))
                else:
                    lista_data = df_final.sort_values('titulo').to_dict('records')
                    chunks = [lista_data[i:i + 12] for i in range(0, len(lista_data), 12)]
                    for idx, chunk in enumerate(chunks):
                        titulo_hoja = "NOVEDADES" if len(chunks) == 1 else f"NOVEDADES ({idx + 1}/{len(chunks)})"
                        img_obj = generar_collage_marketing(chunk, URL_BASE_SUPABASE, titulo_hoja)
                        if img_obj: st.session_state.hojas_generadas.append((titulo_hoja, img_obj))

    if 'hojas_generadas' in st.session_state and st.session_state.hojas_generadas:
        hojas = st.session_state.hojas_generadas
        st.success(f"¡Se generaron {len(hojas)} hojas con éxito!")
        
        with st.expander("Ver y Descargar las Hojas Generadas", expanded=True):
            columnas_render = st.columns(3)
            for idx, (titulo_hoja, img_obj) in enumerate(hojas):
                col = columnas_render[idx % 3]
                with col:
                    # 1. Obtenemos los bytes de la imagen para la descarga
                    buf = io.BytesIO()
                    img_obj.save(buf, format="PNG")
                    img_bytes = buf.getvalue()
                    
                    # 2. EL TRUCO HTML: Codificamos en Base64 para saltarnos st.image()
                    b64_img = base64.b64encode(img_bytes).decode("utf-8")
                    html_str = f"""
                    <div style="text-align: center; margin-bottom: 5px; color: #4A4D7E; font-weight: bold;">{titulo_hoja}</div>
                    <img src="data:image/png;base64,{b64_img}" style="width: 100%; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 10px;">
                    """
                    st.markdown(html_str, unsafe_allow_html=True)
                    
                    # 3. El botón de descarga usa los bytes crudos (esto siempre funcionó bien)
                    st.download_button(
                        label=f"📥 Descargar {titulo_hoja}", data=img_bytes,
                        file_name=f"Catalogo_{titulo_hoja.replace(' ', '_').replace('/', '-')}.png",
                        mime="image/png", key=f"dl_btn_{idx}", use_container_width=True
                    )