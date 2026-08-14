import streamlit as st
from PIL import Image
import io
import time
import urllib.request
from utilidades import get_db_connection

def leer_texto_remoto(nombre_archivo):
    """Descarga el texto actual desde Supabase para poder editarlo."""
    url = f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/{nombre_archivo}"
    try:
        req = urllib.request.urlopen(f"{url}?t={time.time()}")
        return req.read().decode('utf-8')
    except:
        return ""

def procesar_y_subir_imagen(conn, uploaded_file, nombre_final):
    """Función reutilizable para procesar y subir una imagen a Supabase."""
    img = Image.open(uploaded_file)
    # Manejo de fondos transparentes
    if img.mode in ("RGBA", "P"):
        fondo_blanco = Image.new("RGB", img.size, (255, 255, 255))
        fondo_blanco.paste(img, mask=img.convert('RGBA'))
        rgb_im = fondo_blanco
    else:
        rgb_im = img.convert('RGB')
    
    buf = io.BytesIO()
    rgb_im.save(buf, format='JPEG', quality=85)
    
    # Sube la imagen sobreescribiendo la anterior
    conn.storage.from_("grafica").upload(
        path=nombre_final, 
        file=buf.getvalue(), 
        file_options={"content-type": "image/jpeg", "upsert": "true"}
    )

def mostrar_gestion_web():
    st.markdown("## 🎨 Gestión de la Tienda Web")
    
    tab_banners, tab_textos = st.tabs(["🖼️ Banners", "📝 Textos Legales"])
    
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
            with st.spinner("Procesando y subiendo imágenes..."):
                try:
                    # --- LÓGICA CORREGIDA ---
                    if img_banner_cajita:
                        procesar_y_subir_imagen(conn, img_banner_cajita, "promo_cajita.jpg")
                        st.success("✅ Banner de Cajita Literaria actualizado.")
                        imagenes_subidas = True

                    if img_banner_1:
                        procesar_y_subir_imagen(conn, img_banner_1, "promo_tapa_dura_1.jpg")
                        st.success("✅ Banner de Tapa Dura 1 actualizado.")
                        imagenes_subidas = True

                    if img_banner_2:
                        procesar_y_subir_imagen(conn, img_banner_2, "promo_tapa_dura_2.jpg")
                        st.success("✅ Banner de Tapa Dura 2 actualizado.")
                        imagenes_subidas = True

                    if imagenes_subidas:
                        st.balloons()
                        st.info("💡 ¡Ve a tu catálogo y añade `?admin=limpiar` a la URL para ver los cambios de inmediato!")
                    else:
                        st.warning("⚠️ No seleccionaste ninguna imagen nueva para subir.")

                except Exception as e:
                    st.error(f"Ocurrió un error al subir los banners: {e}")
    # ==========================================
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