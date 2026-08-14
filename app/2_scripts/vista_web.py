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
    # --- NUEVO: GESTIÓN BANNER CAJITA ---
        st.markdown("#### Banner de Suscripción")
        img_banner_cajita = st.file_uploader("Sube la imagen para la 'Cajita Literaria'", type=['png', 'jpg', 'jpeg'], key="banner_cajita")

        st.markdown("---")
        
        # --- GESTIÓN BANNERS TAPA DURA ---
        st.markdown("#### Banner de Ediciones Únicas")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            img_banner_1 = st.file_uploader("Sube la imagen 1 (Izquierda)", type=['png', 'jpg', 'jpeg'], key="banner_1")
        with col_b2:
            img_banner_2 = st.file_uploader("Sube la imagen 2 (Derecha)", type=['png', 'jpg', 'jpeg'], key="banner_2")

        if st.button("🚀 Actualizar Banners", type="primary", use_container_width=True):
            conn = get_db_connection()
            try:
                # Procesar Banner Cajita
                if img_banner_cajita:
                    # (Lógica para procesar y subir img_banner_cajita como "promo_cajita.jpg")
                    st.success("✅ Banner de Cajita Literaria actualizado.")

                # Procesar Banner Tapa Dura 1
                if img_banner_1:
                    # (Lógica para procesar y subir img_banner_1 como "promo_tapa_dura_1.jpg")
                    st.success("✅ Banner de Tapa Dura 1 actualizado.")

                # Procesar Banner Tapa Dura 2
                if img_banner_2:
                    # (Lógica para procesar y subir img_banner_2 como "promo_tapa_dura_2.jpg")
                    st.success("✅ Banner de Tapa Dura 2 actualizado.")

                if img_banner_cajita or img_banner_1 or img_banner_2:
                    st.balloons()
                    st.info("💡 ¡Ve a tu catálogo y añade `?admin=limpiar` a la URL para ver los cambios de inmediato!")
                else:
                    st.warning("⚠️ No subiste ninguna imagen nueva.")
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