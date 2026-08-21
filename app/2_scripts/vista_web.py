import streamlit as st
from PIL import Image
import io
import time
import urllib.request
from utilidades import get_db_connection

from vista_inventario import (
    cargar_datos_completos, 
    actualizar_destacados_batch, 
    actualizar_visibilidad_batch,
    limpiar_texto_para_busqueda
)


def leer_texto_remoto(nombre_archivo):
    """Descarga el texto actual desde Supabase para poder editarlo."""
    url = f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/{nombre_archivo}"
    try:
        # Añadimos un timestamp a la URL para saltarnos la caché al editar
        req = urllib.request.urlopen(f"{url}?t={time.time()}")
        return req.read().decode('utf-8')
    except:
        return "" # Si no existe aún, devuelve vacío

def procesar_y_subir_imagen(conn, uploaded_file, nombre_final):
    """Función reutilizable para procesar y subir una imagen a Supabase."""
    img = Image.open(uploaded_file)
    
    # Manejo de fondos transparentes (RGBA a RGB con fondo blanco)
    if img.mode in ("RGBA", "P"):
        fondo_blanco = Image.new("RGB", img.size, (255, 255, 255))
        fondo_blanco.paste(img, mask=img.convert('RGBA'))
        rgb_im = fondo_blanco
    else:
        rgb_im = img.convert('RGB')
    
    buf = io.BytesIO()
    rgb_im.save(buf, format='JPEG', quality=85)
    
    # Sube la imagen sobreescribiendo la anterior si existe (upsert=true)
    conn.storage.from_("grafica").upload(
        path=nombre_final, 
        file=buf.getvalue(), 
        file_options={"content-type": "image/jpeg", "upsert": "true"}
    )

def mostrar_gestion_web():
    st.markdown("## 🎨 Gestión de la Tienda Web y Catálogo Redes Sociales")
    
    # Dividimos en pestañas para mayor orden
    tab_banners, tab_textos, tab_destacados = st.tabs([
        "🖼️ Banners", "📝 Textos Legales", "⭐ Destacados y Visibilidad"
    ])
    
    # ==========================================
    # PESTAÑA 1: BANNERS
    # ==========================================
    with tab_banners:
        st.info("Sube las imágenes para actualizar los banners promocionales del catálogo.")
        
        st.markdown("#### Banner de Suscripción")
        img_banner_cajita = st.file_uploader("Sube la imagen para la 'Cajita Literaria'", type=['png', 'jpg', 'jpeg'], key="banner_cajita")

        st.markdown("---")
        
        st.markdown("#### Banner de Ediciones Únicas")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            img_banner_1 = st.file_uploader("Sube la imagen 1 (Izquierda)", type=['png', 'jpg', 'jpeg'], key="banner_1")
        with col_b2:
            img_banner_2 = st.file_uploader("Sube la imagen 2 (Derecha)", type=['png', 'jpg', 'jpeg'], key="banner_2")

        if st.button("🚀 Actualizar Banners", type="primary", use_container_width=True):
            conn = get_db_connection()
            imagenes_subidas = False
            
            with st.spinner("Procesando y subiendo imágenes a Supabase..."):
                try:
                    # 1. Subir Banner de Cajita
                    if img_banner_cajita:
                        procesar_y_subir_imagen(conn, img_banner_cajita, "promo_cajita.jpg")
                        st.success("✅ Banner de Cajita Literaria actualizado.")
                        imagenes_subidas = True

                    # 2. Subir Banner Tapa Dura 1
                    if img_banner_1:
                        procesar_y_subir_imagen(conn, img_banner_1, "promo_tapa_dura_1.jpg")
                        st.success("✅ Banner de Tapa Dura 1 actualizado.")
                        imagenes_subidas = True

                    # 3. Subir Banner Tapa Dura 2
                    if img_banner_2:
                        procesar_y_subir_imagen(conn, img_banner_2, "promo_tapa_dura_2.jpg")
                        st.success("✅ Banner de Tapa Dura 2 actualizado.")
                        imagenes_subidas = True

                    # Mensaje final
                    if imagenes_subidas:
                        st.balloons()
                        st.info("💡 ¡Ve a tu catálogo y añade `?admin=limpiar` a la URL para ver los cambios de inmediato!")
                    else:
                        st.warning("⚠️ No seleccionaste ninguna imagen nueva para subir.")

                except Exception as e:
                    st.error(f"Ocurrió un error al subir los banners: {e}")
    # PESTAÑA 2: TEXTOS LEGALES
    # ==========================================
    with tab_textos:
        st.info("Edita el texto de tus páginas. **Tip:** Puedes usar [Markdown](https://www.markdownguide.org/cheat-sheet/) para poner **negritas** (usando `**texto**`), listas, etc.")
        
        # Descargamos el texto actual (si existe)
        texto_terminos_actual = leer_texto_remoto("terminos.txt")
        texto_envios_actual = leer_texto_remoto("envios.txt")
        
        # Campos de texto gigantes
        texto_terminos = st.text_area("📄 Términos y Condiciones:", value=texto_terminos_actual, height=300)
        texto_envios = st.text_area("🚚 Condiciones de Envío:", value=texto_envios_actual, height=300)
        
        if st.button("💾 Guardar Textos Legales", type="primary", use_container_width=True):
            conn = get_db_connection()
            with st.spinner("Guardando textos en la nube..."):
                try:
                    # Guardamos los textos en el bucket como archivos .txt
                    conn.storage.from_("grafica").upload(
                        path="terminos.txt", 
                        file=texto_terminos.encode("utf-8"), 
                        file_options={"content-type": "text/plain", "upsert": "true"}
                    )
                    conn.storage.from_("grafica").upload(
                        path="envios.txt", 
                        file=texto_envios.encode("utf-8"), 
                        file_options={"content-type": "text/plain", "upsert": "true"}
                    )
                    st.success("✅ ¡Textos guardados con éxito!")
                    st.balloons()
                    st.info("💡 Recuerda ir a tu catálogo y añadir `?admin=limpiar` a la URL para ver los cambios de inmediato.")
                except Exception as e:
                    st.error(f"Error al guardar los textos: {e}")
    # ==========================================
    # PESTAÑA 3: DESTACADOS Y VISIBILIDAD (NUEVA)
    # ==========================================
    with tab_destacados:
        st.markdown("### ⭐ Destacados y Visibilidad en la Web")
        st.caption("Administra qué libros se muestran en la página pública y cuáles aparecen en el carrusel principal.")

        # Cargar catálogo completo
        df_web = cargar_datos_completos()

        if df_web.empty:
            st.warning("⚠️ No se pudieron cargar los libros del catálogo.")
        else:
            # Buscador integrado para facilitar la gestión
            busqueda_web = st.text_input("🔍 Buscar libro por título o autor:", placeholder="Ej: El Principito / J.K. Rowling", key="busqueda_destacados_web")
            
            df_filtrado_web = df_web.copy()
            if busqueda_web:
                busqueda_limpia = limpiar_texto_para_busqueda(busqueda_web)
                df_filtrado_web = df_filtrado_web[
                    df_filtrado_web['titulo'].apply(limpiar_texto_para_busqueda).str.contains(busqueda_limpia, case=False, na=False) |
                    df_filtrado_web['autor'].apply(limpiar_texto_para_busqueda).str.contains(busqueda_limpia, case=False, na=False)
                ]

            st.write(f"Mostrando **{len(df_filtrado_web)}** libros.")

            col_dest1, col_dest2 = st.columns(2)
            
            # --- COLUMNA 1: CARRUSEL DE DESTACADOS ---
            with col_dest1:
                st.markdown("##### ⭐ Carrusel de Destacados")
                st.caption("Libros en el carrusel de inicio de la web.")
                columnas_destacados = ['libro_id', 'titulo', 'destacado']
                
                if 'destacado' not in df_filtrado_web.columns:
                    st.error("Columna 'destacado' no encontrada.")
                else:
                    df_para_editar_dest = df_filtrado_web[columnas_destacados].copy().reset_index(drop=True)
                    df_editado_dest = st.data_editor(
                        df_para_editar_dest,
                        key="editor_destacados_web_view",
                        hide_index=True,
                        use_container_width=True,
                        disabled=['libro_id', 'titulo'],
                        column_config={
                            "libro_id": st.column_config.NumberColumn("ID", format="%d"),
                            "titulo": st.column_config.TextColumn("Título"),
                            "destacado": st.column_config.CheckboxColumn("¿Destacado? ⭐", default=False)
                        }
                    )
                    cambios_dest = df_para_editar_dest['destacado'] != df_editado_dest['destacado']
                    hay_cambios_dest = cambios_dest.any()
                    
                    if st.button("💾 Guardar Destacados", type="primary", use_container_width=True, disabled=not hay_cambios_dest, key="btn_save_dest_web"):
                        df_final_dest = df_editado_dest[cambios_dest]
                        num_act = actualizar_destacados_batch(df_final_dest)
                        if num_act > 0:
                            st.success(f"¡Se actualizaron {num_act} destacados!")
                            st.balloons()
                            time.sleep(1.5)
                            st.rerun()

    # --- COLUMNA 2: VISIBILIDAD EN CATÁLOGO ---
    with col_dest2:
        st.markdown("##### 👁️ Visibilidad en Catálogo")
        st.caption("Define qué libros se muestran al público general.")
        columnas_visibilidad = ['libro_id', 'titulo', 'visible_catalogo']
        
        if 'visible_catalogo' not in df_filtrado_web.columns:
            st.error("Columna 'visible_catalogo' no encontrada.")
        else:
            df_para_editar_vis = df_filtrado_web[columnas_visibilidad].copy().reset_index(drop=True)
            df_editado_vis = st.data_editor(
                df_para_editar_vis,
                key="editor_visibilidad_web_view",
                hide_index=True,
                use_container_width=True,
                disabled=['libro_id', 'titulo'],
                column_config={
                    "libro_id": st.column_config.NumberColumn("ID", format="%d"),
                    "titulo": st.column_config.TextColumn("Título"),
                    "visible_catalogo": st.column_config.CheckboxColumn("¿Visible? 👁️", default=True)
                }
            )
            cambios_vis = df_para_editar_vis['visible_catalogo'] != df_editado_vis['visible_catalogo']
            hay_cambios_vis = cambios_vis.any()
            
            if st.button("💾 Guardar Visibilidad", type="primary", use_container_width=True, disabled=not hay_cambios_vis, key="btn_save_vis_web"):
                df_final_vis = df_editado_vis[cambios_vis]
                num_act = actualizar_visibilidad_batch(df_final_vis)
                if num_act > 0:
                    st.success(f"¡Se actualizó la visibilidad de {num_act} libros!")
                    st.balloons()
                    time.sleep(1.5)
                    st.rerun()