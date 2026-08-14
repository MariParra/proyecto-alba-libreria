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
        # Añadimos un timestamp a la URL para saltarnos la caché al editar
        req = urllib.request.urlopen(f"{url}?t={time.time()}")
        return req.read().decode('utf-8')
    except:
        return "" # Si no existe aún, devuelve vacío

def mostrar_gestion_web():
    st.markdown("## 🎨 Gestión de la Tienda Web")
    
    # Dividimos en pestañas para mayor orden
    tab_banners, tab_textos = st.tabs(["🖼️ Banners", "📝 Textos Legales"])
    
    # ==========================================
    # PESTAÑA 1: BANNERS
    # ==========================================
    with tab_banners:
        st.info("Sube las imágenes para actualizar los libros que se muestran en el banner de 'Ediciones Únicas'.")

        col_b1, col_b2 = st.columns(2)

        with col_b1:
            st.markdown("**Banner Tapa Dura 1 (Izquierda)**")
            img_banner_1 = st.file_uploader("Sube la imagen 1", type=['png', 'jpg', 'jpeg'], key="banner_1")

        with col_b2:
            st.markdown("**Banner Tapa Dura 2 (Derecha)**")
            img_banner_2 = st.file_uploader("Sube la imagen 2", type=['png', 'jpg', 'jpeg'], key="banner_2")

        if st.button("🚀 Actualizar Banners", type="primary", use_container_width=True):
            conn = get_db_connection()
            try:
                # Procesar Banner 1
                if img_banner_1:
                    img1 = Image.open(img_banner_1)
                    if img1.mode in ("RGBA", "P"):
                        fondo_blanco = Image.new("RGB", img1.size, (255, 255, 255))
                        fondo_blanco.paste(img1, mask=img1.convert('RGBA'))
                        rgb_im1 = fondo_blanco
                    else:
                        rgb_im1 = img1.convert('RGB')
                    
                    buf1 = io.BytesIO()
                    rgb_im1.save(buf1, format='JPEG', quality=85)
                    
                    conn.storage.from_("grafica").upload(
                        path="promo_tapa_dura_1.jpg", 
                        file=buf1.getvalue(), 
                        file_options={"content-type": "image/jpeg", "upsert": "true"}
                    )
                    st.success("✅ Banner 1 actualizado con éxito.")

                # Procesar Banner 2
                if img_banner_2:
                    img2 = Image.open(img_banner_2)
                    if img2.mode in ("RGBA", "P"):
                        fondo_blanco = Image.new("RGB", img2.size, (255, 255, 255))
                        fondo_blanco.paste(img2, mask=img2.convert('RGBA'))
                        rgb_im2 = fondo_blanco
                    else:
                        rgb_im2 = img2.convert('RGB')
                    
                    buf2 = io.BytesIO()
                    rgb_im2.save(buf2, format='JPEG', quality=85)
                    
                    conn.storage.from_("grafica").upload(
                        path="promo_tapa_dura_2.jpg", 
                        file=buf2.getvalue(), 
                        file_options={"content-type": "image/jpeg", "upsert": "true"}
                    )
                    st.success("✅ Banner 2 actualizado con éxito.")

                if img_banner_1 or img_banner_2:
                    st.balloons()
                    st.info("💡 ¡Ve a tu catálogo y añade `?admin=limpiar` a la URL para ver los cambios de inmediato!")
                else:
                    st.warning("⚠️ No subiste ninguna imagen.")

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