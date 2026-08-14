import streamlit as st
from PIL import Image
import io

st.markdown("### 🖼️ Gestión de Banners del Catálogo")
st.info("Sube las imágenes para actualizar los libros que se muestran en el banner de 'Ediciones Únicas'.")

col_b1, col_b2 = st.columns(2)

with col_b1:
    st.markdown("**Banner Tapa Dura 1 (Izquierda)**")
    img_banner_1 = st.file_uploader("Sube la imagen 1", type=['png', 'jpg', 'jpeg'], key="banner_1")

with col_b2:
    st.markdown("**Banner Tapa Dura 2 (Derecha)**")
    img_banner_2 = st.file_uploader("Sube la imagen 2", type=['png', 'jpg', 'jpeg'], key="banner_2")

if st.button("🚀 Actualizar Banners en la Web", type="primary", use_container_width=True):
    conn = get_db_connection()
    try:
        # Procesar Banner 1
        if img_banner_1:
            img1 = Image.open(img_banner_1)
            # Manejo de fondos transparentes
            if img1.mode in ("RGBA", "P"):
                fondo_blanco = Image.new("RGB", img1.size, (255, 255, 255))
                fondo_blanco.paste(img1, mask=img1.convert('RGBA'))
                rgb_im1 = fondo_blanco
            else:
                rgb_im1 = img1.convert('RGB')
            
            buf1 = io.BytesIO()
            rgb_im1.save(buf1, format='JPEG', quality=85)
            
            # El parámetro upsert=true sobreescribe la imagen anterior
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