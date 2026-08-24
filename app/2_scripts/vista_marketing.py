import streamlit as st
import pandas as pd
import io 
import json
import os
import base64
import zipfile
from utilidades import limpiar_texto_para_busqueda
from generador_collage import generar_collage_marketing
import time

# Ruta física para la persistencia del archivo de configuración JSON
CONFIG_FILE = "assets/default_marketing_config.json"

def cargar_configuracion_marketing():
    """Carga los valores por defecto del archivo JSON si existe."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # Configuración por defecto elegante
    return {
        "font_family_header": "Montserrat",
        "font_family_books": "Montserrat",
        "bold_header": True,
        "italic_header": False,
        "tamanio_header": 45,
        "tamanio_libros": 20,
        "color_bg": "#FDE8F3",
        "color_card": "#FFFFFF",
        "color_shadow": "#F4CCD4",
        "color_primary_header": "#7C0C3F",
        "color_primary_books": "#7C0C3F",
        "color_accent": "#DB2777",
        "color_muted": "#BA96A5",
        "color_badge_bg": "#DB2777",
        "color_badge_text": "#FFFFFF",
        "color_header_rect_bg": "#FFFFFF",
        "color_header_rect_border": "#7C0C3F",
        "header_rect_border_width": 2,
        "header_rect_radius": 20,
        "header_pad_x": 40,
        "header_pad_y": 20,
        "libros_por_pagina": 12
    }

def guardar_configuracion_marketing(config):
    """Guarda persistentemente la configuración en el JSON de assets."""
    if not os.path.exists("assets"):
        os.makedirs("assets")
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        return False

@st.cache_data(ttl=60)
def cargar_libros_para_marketing():
    """
    Filtro Maestro (Requisito 1): Carga libros visibles, con precio > 0 y con portada en Supabase.
    Bypass seguro de 1000 registros ordenando obligatoriamente por la clave primaria: libro_id.
    """
    from utilidades import get_db_connection
    conn = get_db_connection()
    try:
        all_books = []
        chunk_size = 1000
        # Paginación dinámica segura
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

        # Carga física y paginada de portadas existentes en el Storage
        portadas_existentes = set()
        offset = 0
        while True:
            try:
                bloque = conn.storage.from_("portadas").list(path="", search_options={"limit": 100, "offset": offset})
            except TypeError:
                bloque = conn.storage.from_("portadas").list(path="", options={"limit": 100, "offset": offset})
            
            if not bloque:
                break
            
            for archivo in bloque:
                if archivo.get('name') is not None:
                    portadas_existentes.add(archivo.get('name').strip())
            offset += 100
        
        # Cruzamos y filtramos de forma segura libre de corchetes Markdown
        df_libros = df_libros.assign(portada_esperada = df_libros.libro_id.apply(lambda idx: f"{int(float(idx))}.jpg".strip()))
        df_libros = df_libros.assign(tiene_portada = df_libros.portada_esperada.isin(portadas_existentes))
        
        df_final = df_libros.query("tiene_portada == True").copy()
        df_final = df_final.drop(columns=list(("portada_esperada", "tiene_portada")))
        df_final.loc[:, 'precio'] = pd.to_numeric(df_final.precio, errors='coerce').fillna(0)
        df_final.loc[:, 'libro_id'] = df_final.libro_id.astype(str)
        
        return df_final
    except Exception as e:
        return pd.DataFrame()

def mostrar_generador_marketing():
    st.title("🎨 Generador de Catálogos Masivos")
    st.info("Genera imágenes personalizadas para tus Stories de Redes Sociales.")

    try:
        URL_BASE_SUPABASE = st.secrets.get("catalogo_publico", {}).get("supabase_portadas_url")
    except KeyError:
        st.error("🚨 Falta la clave 'supabase_portadas_url' en secrets.toml.")
        st.stop()

    # Cargar configuraciones guardadas o por defecto
    config_default = cargar_configuracion_marketing()

    df_libros = cargar_libros_para_marketing()
    if df_libros.empty:
        st.warning("No hay libros en el catálogo que cumplan las condiciones para marketing (visibles, con precio y con portada cargada).")
        return

    # =========================================================================
    # 🎨 PANEL INTERACTIVO DE PERSONALIZACIÓN COMPACTA Y SIMÉTRICA
    # =========================================================================
    with st.expander("🛠️ Personalizar Diseño, Colores y Retícula del Catálogo", expanded=False):
        st.markdown("#### 📐 Configuración de Cuadrícula")
        opciones_paginacion = tuple((1, 4, 8, 12))
        libros_por_pag = st.selectbox(
            "Cantidad de libros por página:", 
            options=opciones_paginacion, 
            index=opciones_paginacion.index(config_default.get("libros_por_pagina", 12)) if config_default.get("libros_por_pagina", 12) in opciones_paginacion else 3
        )
        
        st.markdown("---")
        st.markdown("#### 🔠 Tipografías y Textos (Google Fonts)")
        
        # Checkbox interactivo de ayuda de fuentes Google
        mostrar_ayuda_fuentes = st.checkbox("ℹ️ Mostrar ayuda de fuentes Google Fonts", value=False)
        if mostrar_ayuda_fuentes:
            st.info(
                "Las fuentes personalizables provienen del catálogo oficial de Google Fonts. "
                "Puedes revisar y buscar tipografías soportadas aquí: "
                "https://fonts.google.com/?preview.script=Latn"
            )
            
        listado_fuentes = tuple(("Montserrat", "Playfair Display", "Lobster", "Pacifico", "Roboto", "Oswald", "Lato", "Merriweather", "Dancing Script", "Escribir otra..."))
        
        # Persistencia de tipografía del género
        saved_font_h = config_default.get("font_family_header", "Montserrat")
        if saved_font_h in listado_fuentes[:-1]:
            default_index_h = listado_fuentes.index(saved_font_h)
            custom_value_h = "Montserrat"
        else:
            default_index_h = listado_fuentes.index("Escribir otra...")
            custom_value_h = saved_font_h

        font_h_sel = st.selectbox("Fuente del título (Género):", options=listado_fuentes, index=default_index_h)
        if font_h_sel == "Escribir otra...":
            font_h_sel = st.text_input("Ingresa el nombre exacto de la fuente de Google Fonts (Género):", value=custom_value_h, key="txt_fnh")

        # Persistencia de tipografía de libros
        saved_font_b = config_default.get("font_family_books", "Montserrat")
        if saved_font_b in listado_fuentes[:-1]:
            default_index_b = listado_fuentes.index(saved_font_b)
            custom_value_b = "Montserrat"
        else:
            default_index_b = listado_fuentes.index("Escribir otra...")
            custom_value_b = saved_font_b

        font_b_sel = st.selectbox("Fuente de los libros (Títulos/Precios):", options=listado_fuentes, index=default_index_b)
        if font_b_sel == "Escribir otra...":
            font_b_sel = st.text_input("Ingresa el nombre de la fuente para libros en Google Fonts:", value=custom_value_b, key="txt_fnb")

        c_font1, c_font2, c_font3, c_font4 = st.columns(4)
        bold_h = c_font1.checkbox("Aplicar Negrita (Bold) al Género", value=config_default.get("bold_header", True))
        italic_h = c_font2.checkbox("Aplicar Cursiva (Italic) al Género", value=config_default.get("italic_header", False))
        size_h = c_font3.slider("Tamaño Fuente Género:", 20, 100, int(config_default.get("tamanio_header", 45)))
        size_b = c_font4.slider("Tamaño Fuente Libros:", 12, 35, int(config_default.get("tamanio_libros", 20)))

        st.markdown("---")
        st.markdown("#### 📦 Rectángulo del Título (Género)")
        c_rect1, c_rect2, c_rect3, c_rect4 = st.columns(4)
        color_rect_bg = c_rect1.color_picker("Fondo del Recuadro:", value=config_default.get("color_header_rect_bg", "#FFFFFF"))
        color_rect_border = c_rect2.color_picker("Borde del Recuadro:", value=config_default.get("color_header_rect_border", "#7C0C3F"))
        border_w = c_rect3.slider("Grosor del Borde:", 0, 10, int(config_default.get("header_rect_border_width", 2)))
        radius_h = c_rect4.slider("Redondeo de Esquinas:", 0, 40, int(config_default.get("header_rect_radius", 20)))

        st.markdown("##### ↕️ Ajuste de Ancho y Alto de Rectángulo (Padding)")
        c_pad1, c_pad2 = st.columns(2)
        pad_x = c_pad1.slider("Ajuste Ancho (Padding X):", 10, 150, int(config_default.get("header_pad_x", 40)))
        pad_y = c_pad2.slider("Ajuste Alto (Padding Y):", 5, 80, int(config_default.get("header_pad_y", 20)))

        st.markdown("---")
        # 🌟 MEJORA UX: Alineación de Paleta de Colores en Cuadrícula 3x3 Perfecta con etiquetas concisas
        st.markdown("#### 🎨 Paleta de Colores (HEX)")
        
        # Fila 1: Lienzo y Tarjetas
        cc1, cc2, cc3 = st.columns(3)
        c_bg = cc1.color_picker("Fondo del Collage", value=config_default.get("color_bg", "#FDE8F3"))
        c_card = cc2.color_picker("Fondo de Tarjetas", value=config_default.get("color_card", "#FFFFFF"))
        c_shadow = cc3.color_picker("Sombra de Tarjetas", value=config_default.get("color_shadow", "#F4CCD4"))
        
        # Fila 2: Letras Principales
        cc4, cc5, cc6 = st.columns(3)
        c_primary_header = cc4.color_picker("Texto del Género", value=config_default.get("color_primary_header", "#7C0C3F"))
        c_primary_books = cc5.color_picker("Texto de Títulos", value=config_default.get("color_primary_books", "#7C0C3F"))
        c_accent = cc6.color_picker("Precio de Oferta", value=config_default.get("color_accent", "#DB2777"))
        
        # Fila 3: Precios Tachados y Etiquetas
        cc7, cc8, cc9 = st.columns(3)
        c_muted = cc7.color_picker("Precio Tachado", value=config_default.get("color_muted", "#BA96A5"))
        c_badge_bg = cc8.color_picker("Fondo de Etiqueta", value=config_default.get("color_badge_bg", "#DB2777"))
        c_badge_text = cc9.color_picker("Texto de Etiqueta", value=config_default.get("color_badge_text", "#FFFFFF"))

        config_diseno_final = {
            "font_family_header": font_h_sel,
            "font_family_books": font_b_sel,
            "bold_header": bold_h,
            "italic_header": italic_h,
            "tamanio_header": size_h,
            "tamanio_libros": size_b,
            "color_header_rect_bg": color_rect_bg,
            "color_header_rect_border": color_rect_border,
            "header_rect_border_width": border_w,
            "header_rect_radius": radius_h,
            "header_pad_x": pad_x,
            "header_pad_y": pad_y,
            "color_bg": c_bg,
            "color_card": c_card,
            "color_shadow": c_shadow,
            "color_primary_header": c_primary_header,
            "color_primary_books": c_primary_books,
            "color_accent": c_accent,
            "color_muted": c_muted,
            "color_badge_bg": c_badge_bg,
            "color_badge_text": c_badge_text,
            "libros_por_pagina": libros_por_pag
        }

        # =========================================================================
        # 🌟 PREVISUALIZADOR PREMIUM EN TIEMPO REAL (DISEÑO ALINEADO 3x3)
        # =========================================================================
        st.markdown("---")
        st.markdown("#### 👁️ Previsualización del Diseño en Tiempo Real")
        st.caption("Esta tarjeta simula en vivo cómo se renderizarán el género y los libros en tus collages finales con todos sus componentes.")
        
        import_font_h = font_h_sel.replace(" ", "+")
        import_font_b = font_b_sel.replace(" ", "+")
        
        preview_html = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family={import_font_h}:ital,wght@0,300;0,400;0,700;1,300;1,400;1,700&family={import_font_b}:ital,wght@0,300;0,400;0,700;1,300;1,400;1,700&display=swap');
        
        .preview-container {{
            background-color: {c_bg};
            padding: 40px 30px;
            border-radius: 15px;
            text-align: center;
            font-family: '{font_b_sel}', sans-serif;
            margin-bottom: 20px;
        }}
        .preview-header-rect {{
            background-color: {color_rect_bg};
            border: {border_w}px solid {color_rect_border};
            border-radius: {radius_h}px;
            padding: {pad_y}px {pad_x}px;
            display: inline-block;
            margin-bottom: 25px;
            box-shadow: 8px 8px 0px {c_shadow};
        }}
        .preview-header-text {{
            color: {c_primary_header};
            font-family: '{font_h_sel}', sans-serif;
            font-size: 24px;
            font-weight: {'bold' if bold_h else 'normal'};
            font-style: {'italic' if italic_h else 'normal'};
            margin: 0;
            text-transform: uppercase;
        }}
        .preview-card {{
            background-color: {c_card};
            border-radius: 20px;
            padding: 20px;
            display: inline-block;
            width: 250px;
            margin: 15px auto 10px auto;
            box-shadow: 10px 10px 0px {c_shadow};
            text-align: center;
            position: relative;
        }}
        .preview-badge {{
            background-color: {c_badge_bg};
            color: {c_badge_text};
            font-family: '{font_b_sel}', sans-serif;
            font-size: 10px;
            font-weight: bold;
            padding: 4px 12px;
            border-radius: 10px;
            position: absolute;
            top: -14px;
            left: 50%;
            transform: translateX(-50%);
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            white-space: nowrap;
        }}
        .preview-book-title {{
            color: {c_primary_books};
            font-weight: bold;
            font-size: 16px;
            margin-top: 15px;
            margin-bottom: 10px;
            text-transform: uppercase;
        }}
        .preview-book-price-orig {{
            color: {c_muted};
            font-size: 13px;
            text-decoration: line-through;
            margin-bottom: 2px;
            font-weight: bold;
        }}
        .preview-book-price {{
            color: {c_accent};
            font-weight: bold;
            font-size: 22px;
        }}
        </style>
        
        <div class="preview-container">
            <div class="preview-header-rect">
                <h2 class="preview-header-text">GÉNERO PREVIA</h2>
            </div>
            <br/>
            <div class="preview-card">
                <div class="preview-badge">DISPONIBLE</div>
                <div style="background-color: #F5EEF1; height: 145px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #888;">
                    📚 Portada
                </div>
                <div class="preview-book-title">Título del Libro</div>
                <div class="preview-book-price-orig">$14,000</div>
                <div class="preview-book-price">$13,300</div>
            </div>
        </div>
        """
        st.markdown(preview_html, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("💾 Guardar Ajustes como Predeterminados", type="primary", use_container_width=True):
            if guardar_configuracion_marketing(config_diseno_final):
                st.success("✅ ¡Ajustes guardados como predeterminados con éxito!")
            else:
                st.error("❌ No se pudieron guardar los ajustes.")

    # =========================================================================
    # 🖼️ CARGA DE ARCHIVO PARA IMAGEN DE FONDO SUPABASE
    # =========================================================================
    with st.expander("🖼️ Cargar y Cambiar Imagen de Fondo Oficial (Supabase base.png)", expanded=False):
        st.info("Subir una nueva imagen de fondo (idealmente 1080x1920) sobreescribirá la plantilla de Alba Librería en tiempo real.")
        img_fondo_subida = st.file_uploader("Sube tu archivo de fondo (PNG recomendado):", type=["png", "jpg", "jpeg"])
        
        if img_fondo_subida is not None:
            if st.button("🚀 Subir e Inyectar en Supabase", type="primary", use_container_width=True):
                with st.spinner("Subiendo imagen de fondo y sobrescribiendo plantilla..."):
                    try:
                        from utilidades import get_db_connection
                        conn = get_db_connection()
                        img_bytes = img_fondo_subida.getvalue()
                        
                        conn.storage.from_("grafica").upload(
                            path="base.png",
                            file=img_bytes,
                            file_options={"cache-control": "3600", "upsert": "true"}
                        )
                        st.success("🎉 ¡Fondo oficial actualizado con éxito en Supabase!")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error cargando imagen de fondo: {e}")

    # =========================================================================
    # RENDERIZADO COMÚN
    # =========================================================================
    with st.container(border=True):
        st.markdown("#### 1. Filtra y Selecciona")
        
        generos_disponibles = sorted(list(df_libros.genero.dropna().unique()))
        genero_seleccionado = st.selectbox("Filtrar por Género (opcional):", ["Todos"] + generos_disponibles)

        df_filtrado = df_libros
        if genero_seleccionado != "Todos":
            df_filtrado = df_libros.query(f"genero == '{genero_seleccionado}'").copy()

        df_filtrado = df_filtrado.assign(
            label_selectbox = df_filtrado.apply(lambda x: f"{x.titulo} (Sin Stock)" if int(x.get("stock", 0)) <= 0 else x.titulo, axis=1)
        )
        opciones_libros = dict(zip(df_filtrado.label_selectbox, df_filtrado.libro_id))

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

            df_final = df_libros.query(f"libro_id in {tuple(ids_seleccionados)}").copy() if len(ids_seleccionados) > 1 else df_libros.query(f"libro_id == '{ids_seleccionados[0]}'").copy()
            st.session_state.hojas_generadas = []

            # Libros por página dinámico desde la configuración
            libros_por_pagina = config_diseno_final.get("libros_por_pagina", 12)

            with st.spinner("Pintando hojas del catálogo... Aguarda un momento."):
                if agrupar_por_genero:
                    for genero, df_grupo in df_final.groupby('genero'):
                        titulo_base = str(genero).upper() if pd.notna(genero) else "OTROS"
                        lista_data = df_grupo.sort_values('titulo').to_dict('records')
                        chunks = [lista_data[i:i + libros_por_pagina] for i in range(0, len(lista_data), libros_por_pagina)]
                        for idx, chunk in enumerate(chunks):
                            titulo_hoja = titulo_base if len(chunks) == 1 else f"{titulo_base} ({idx + 1}/{len(chunks)})"
                            img_obj = generar_collage_marketing(chunk, URL_BASE_SUPABASE, titulo_hoja, config_diseno_final)
                            if img_obj: st.session_state.hojas_generadas.append((titulo_hoja, img_obj))
                else:
                    lista_data = df_final.sort_values('titulo').to_dict('records')
                    chunks = [lista_data[i:i + libros_por_pagina] for i in range(0, len(lista_data), libros_por_pagina)]
                    for idx, chunk in enumerate(chunks):
                        titulo_hoja = "NOVEDADES" if len(chunks) == 1 else f"NOVEDADES ({idx + 1}/{len(chunks)})"
                        img_obj = generar_collage_marketing(chunk, URL_BASE_SUPABASE, titulo_hoja, config_diseno_final)
                        if img_obj: st.session_state.hojas_generadas.append((titulo_hoja, img_obj))

    if 'hojas_generadas' in st.session_state and st.session_state.hojas_generadas:
        hojas = st.session_state.hojas_generadas
        st.success(f"¡Se generaron {len(hojas)} hojas con éxito!")
        
        # =========================================================================
        # 📥 DESCARGA MASIVA ZIP REUBICADA DEBAJO DE LAS IMÁGENES
        # =========================================================================
        with st.expander("Ver y Descargar las Hojas Generadas Individualmente", expanded=True):
            columnas_render = st.columns(3)
            for idx, (titulo_hoja, img_obj) in enumerate(hojas):
                col = columnas_render[idx % 3]
                with col:
                    buf = io.BytesIO()
                    img_obj.save(buf, format="PNG")
                    img_bytes = buf.getvalue()
                    
                    b64_img = base64.b64encode(img_bytes).decode("utf-8")
                    # Diseño CSS/HTML Premium
                    html_str = f"""
                    <div style="
                        text-align: center; 
                        margin-bottom: 12px; 
                        color: {config_diseno_final.get('color_primary_books', '#7C0C3F')}; 
                        font-family: 'Helvetica Neue', Arial, sans-serif;
                        font-size: 18px; 
                        font-weight: bold; 
                        letter-spacing: 1px;
                        text-transform: uppercase;
                        text-shadow: 1px 1px 2px rgba(0,0,0,0.08);
                        border-bottom: 2px solid {config_diseno_final.get('color_accent', '#DB2777')};
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
            
            # 🌟 NUEVA UBICACIÓN: Botón de descarga masiva ZIP al final del Expander
            st.markdown("---")
            st.markdown("#### 📦 Descarga Masiva del Catálogo Completo")
            st.caption("Usa este botón para descargar todas las hojas generadas comprimidas en un único archivo ZIP en un clic.")
            
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for t_hoja, i_obj in hojas:
                    buf_img = io.BytesIO()
                    i_obj.save(buf_img, format="PNG")
                    img_bytes = buf_img.getvalue()
                    file_name = f"Catalogo_{t_hoja.replace(' ', '_').replace('/', '-')}.png"
                    zip_file.writestr(file_name, img_bytes)
                    
            st.download_button(
                label="📥 Descargar Catálogo Completo (ZIP)",
                data=zip_buf.getvalue(),
                file_name="Catalogo_Completo_Alba_Libreria.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary"
            )