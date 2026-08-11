import streamlit as st
import pandas as pd
from utilidades import limpiar_texto_para_busqueda
from generador_collage import generar_collage_marketing

@st.cache_data(ttl=60)
def cargar_libros_para_marketing():
    from utilidades import get_db_connection
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, precio_original, genero, stock").order("titulo").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except:
        return pd.DataFrame()

def mostrar_generador_marketing():
    st.title("🎨 Generador de Catálogos Masivos")
    st.info("Genera imágenes para tus Stories. Si eliges muchos libros, el sistema creará varias hojas automáticamente.")

    try:
        URL_BASE_SUPABASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
    except KeyError:
        st.error("🚨 Falta la clave 'supabase_portadas_url' en secrets.toml.")
        st.stop()

    df_libros = cargar_libros_para_marketing()
    if df_libros.empty:
        st.warning("No hay libros en el catálogo.")
        return

    with st.container(border=True):
        st.markdown("#### 1. Filtra y Selecciona")
        
        generos = sorted(df_libros['genero'].dropna().unique())
        genero_sel = st.selectbox("Filtrar por Género (opcional):", ["Todos"] + generos)

        df_filtrado = df_libros
        if genero_sel != "Todos":
            df_filtrado = df_libros[df_libros['genero'] == genero_sel]

        # Etiquetas con aviso de stock
        df_filtrado['label_selectbox'] = df_filtrado.apply(
            lambda x: f"{x['titulo']} (Sin Stock)" if int(x.get('stock', 0)) <= 0 else x['titulo'], axis=1
        )
        opciones_libros = dict(zip(df_filtrado['label_selectbox'], df_filtrado['libro_id']))

        # --- SELECCIÓN MASIVA ---
        seleccionar_todos = st.checkbox(f"✅ Seleccionar TODOS los libros filtrados ({len(df_filtrado)} libros)")
        
        if seleccionar_todos:
            libros_seleccionados = list(opciones_libros.keys())
        else:
            libros_seleccionados = st.multiselect(
                "O selecciona manualmente (sin límite):",
                options=opciones_libros.keys()
            )

    # --- GENERACIÓN DE IMÁGENES PAGINADAS ---
    if libros_seleccionados:
        st.markdown("---")
        st.markdown("#### 2. Configuración y Previsualización")
        
        agrupar_por_genero = st.checkbox("🗂️ Agrupar y titular hojas por Género (Recomendado)", value=True)

        if st.button("🚀 Generar Catálogo Completo", type="primary", use_container_width=True):
            
            ids_seleccionados = [opciones_libros[t] for t in libros_seleccionados]
            df_final = df_libros[df_libros['libro_id'].isin(ids_seleccionados)]

            with st.spinner("Pintando hojas del catálogo..."):
                hojas_generadas = [] # Guardaremos tuplas: (titulo_hoja, bytes_imagen)

                # Si agrupamos por género, iteramos sobre cada grupo
                if agrupar_por_genero:
                    grupos = df_final.groupby('genero')
                    for genero, df_grupo in grupos:
                        titulo_base = str(genero).upper() if pd.notna(genero) else "OTROS"
                        
                        # Ordenamos por título y convertimos a lista de diccionarios
                        lista_data = df_grupo.sort_values('titulo').to_dict('records')
                        
                        # Partimos la lista en trozos (chunks) de máximo 8 libros
                        chunks = [lista_data[i:i + 8] for i in range(0, len(lista_data), 8)]
                        
                        for idx, chunk in enumerate(chunks):
                            # Si hay más de 1 hoja para este género, le añadimos (1/2), (2/2)
                            titulo_hoja = titulo_base
                            if len(chunks) > 1:
                                titulo_hoja += f" ({idx + 1}/{len(chunks)})"
                            
                            img_bytes = generar_collage_marketing(chunk, URL_BASE_SUPABASE, titulo_hoja)
                            if img_bytes: hojas_generadas.append((titulo_hoja, img_bytes))

                # Si no agrupamos, simplemente partimos todo el bulto en bloques de 8
                else:
                    titulo_base = "NOVEDADES"
                    lista_data = df_final.sort_values('titulo').to_dict('records')
                    chunks = [lista_data[i:i + 8] for i in range(0, len(lista_data), 8)]
                    
                    for idx, chunk in enumerate(chunks):
                        titulo_hoja = titulo_base if len(chunks) == 1 else f"{titulo_base} ({idx + 1}/{len(chunks)})"
                        img_bytes = generar_collage_marketing(chunk, URL_BASE_SUPABASE, titulo_hoja)
                        if img_bytes: hojas_generadas.append((titulo_hoja, img_bytes))

            # --- RENDERIZADO EN PANTALLA ---
            if not hojas_generadas:
                st.error("No se pudo generar ninguna imagen. Revisa las configuraciones.")
            else:
                st.success(f"¡Se generaron {len(hojas_generadas)} hojas con éxito!")
                
                # Mostramos cada hoja generada en una columna para que se vea ordenado
                columnas_render = st.columns(2)
                for idx, (titulo_hoja, img_bytes) in enumerate(hojas_generadas):
                    col = columnas_render[idx % 2]
                    with col:
                        st.image(img_bytes, caption=titulo_hoja, use_container_width=True)
                        st.download_button(
                            label=f"📥 Descargar {titulo_hoja}",
                            data=img_bytes,
                            file_name=f"Catalogo_{titulo_hoja.replace(' ', '_').replace('/', '-')}.png",
                            mime="image/png",
                            key=f"dl_btn_{idx}", # Clave única obligatoria para Streamlit
                            use_container_width=True
                        )