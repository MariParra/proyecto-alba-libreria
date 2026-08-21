import streamlit as st
import pandas as pd
import io 
import base64
from utilidades import limpiar_texto_para_busqueda
from generador_collage import generar_collage_marketing

@st.cache_data(ttl=60)
def cargar_libros_para_marketing():
    """
    Filtro Maestro: Obtiene libros visibles, con precio > 0 y con portada en el bucket de Supabase.
    Bypass del límite de 1000 registros ordenando obligatoriamente por la clave primaria: libro_id.
    """
    from utilidades import get_db_connection
    conn = get_db_connection()
    try:
        all_books = []
        chunk_size = 1000
        # Paginación dinámica por bloques usando la clave de ordenación obligatoria: libro_id
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("libros")\
                .select("libro_id, titulo, autor, precio, precio_original, genero, stock")\
                .eq("visible_catalogo", True)\
                .gt("precio", 0)\
                .order("libro_id")\
                .range(start, end).execute()
            if res.data:
                all_books.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_books:
            return pd.DataFrame()
            
        df_libros = pd.DataFrame(all_books)

        # Cargar lista de portadas físicas existentes en el bucket de storage
        portadas_existentes = set()
        offset = 0
        while True:
            try:
                bloque = conn.storage.from_("portadas").list(path="", search_options={"limit": 100, "offset": offset})
            except TypeError:
                bloque = conn.storage.from_("portadas").list(path="", options={"limit": 100, "offset": offset})
            
            if not bloque:
                break
            
            # Limpiamos cada nombre de archivo al momento de añadirlo
            for archivo in bloque:
                if archivo['name'] is not None:
                    portadas_existentes.add(archivo['name'].strip())
            
            offset += 100
        
        # Validar y cruzar contra portadas reales
        df_libros['portada_esperada'] = df_libros['libro_id'].apply(lambda idx: f"{int(float(idx))}.jpg".strip())
        df_libros['tiene_portada'] = df_libros['portada_esperada'].isin(portadas_existentes)
        
        df_final = df_libros[df_libros['tiene_portada'] == True].copy()
        df_final.drop(columns=['portada_esperada', 'tiene_portada'], inplace=True)
        df_final['precio'] = pd.to_numeric(df_final['precio'], errors='coerce').fillna(0)
        df_final['libro_id'] = df_final['libro_id'].astype(str)
        
        return df_final
    except Exception as e:
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
        st.warning("No hay libros en el catálogo que cumplan las condiciones para marketing (visibles, con precio y con portada cargada).")
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
                    buf = io.BytesIO()
                    img_obj.save(buf, format="PNG")
                    img_bytes = buf.getvalue()
                    
                    b64_img = base64.b64encode(img_bytes).decode("utf-8")
                    # Diseño CSS/HTML Premium con letras atractivas y transiciones dinámicas
                    html_str = f"""
                    <div style="
                        text-align: center; 
                        margin-bottom: 12px; 
                        color: #4A4D7E; 
                        font-family: 'Helvetica Neue', Arial, sans-serif;
                        font-size: 18px; 
                        font-weight: bold; 
                        letter-spacing: 1px;
                        text-transform: uppercase;
                        text-shadow: 1px 1px 2px rgba(0,0,0,0.08);
                        border-bottom: 2px solid #C994C0;
                        padding-bottom: 6px;
                    ">
                        ✨ {titulo_hoja} ✨
                    </div>
                    <div style="
                        border-radius: 12px; 
                        box-shadow: 0 10px 25px rgba(0,0,0,0.15); 
                        overflow: hidden; 
                        margin-bottom: 15px;
                        transition: transform 0.3s ease-in-out;
                    " onmouseover="this.style.transform='scale(1.03)'" onmouseout="this.style.transform='scale(1)'">
                        <img src="data:image/png;base64,{b64_img}" style="width: 100%; display: block;">
                    </div>
                    """
                    st.markdown(html_str, unsafe_allow_html=True)
                    
                    st.download_button(
                        label=f"📥 Descargar {titulo_hoja}", data=img_bytes,
                        file_name=f"Catalogo_{titulo_hoja.replace(' ', '_').replace('/', '-')}.png",
                        mime="image/png", key=f"dl_btn_{idx}", use_container_width=True
                    )