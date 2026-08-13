import streamlit as st
import pandas as pd
import io
import time
from PIL import Image
from utilidades import get_db_connection, log_error

def actualizar_portada_individual(libro_id, archivo_subido):
    """
    Procesa la imagen, la sube a Supabase y actualiza la fecha de modificación
    para invalidar la caché pública.
    """
    conn = get_db_connection()
    try:
        # 1. Abrir la imagen y convertirla a RGB (para eliminar transparencias y optimizar)
        img = Image.open(archivo_subido)
        rgb_im = img.convert('RGB')
        
        # 2. Guardarla en la memoria temporal del servidor como JPG
        img_byte_arr = io.BytesIO()
        rgb_im.save(img_byte_arr, format='JPEG', quality=95)
        
        nombre_archivo = f"{libro_id}.jpg"
        
        # 3. Borrar la portada anterior en Supabase (si existe) para evitar conflictos
        try:
            conn.storage.from_("portadas").remove([nombre_archivo])
        except:
            pass # Si no existía, ignoramos el error y seguimos
            
        # 4. Subir la nueva portada optimizada
        conn.storage.from_("portadas").upload(
            path=nombre_archivo,
            file=img_byte_arr.getvalue(),
            file_options={"content-type": "image/jpeg"}
        )
        
        # 5. ¡LA CLAVE! Actualizar la fecha para romper la caché de los clientes
        conn.table("libros").update({
            "portada_last_updated": "now()"
        }).eq("libro_id", libro_id).execute()
        
        return True, ""
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(vista="vista_portadas", funcion="actualizar_portada_individual", error=str(e), email_usuario=email_usuario)
        return False, str(e)

def mostrar_gestion_portadas():
    st.markdown("<h2 style='color: #4A4D7E;'>🖼️ Gestión Individual de Portadas</h2>", unsafe_allow_html=True)
    st.write("Busca un libro y actualiza su portada al instante. El sistema la optimizará a JPG y forzará a la web pública a mostrar la nueva versión.")
    
    st.markdown("---")
    
    # Obtener la lista de libros directamente de la base de datos
    conn = get_db_connection()
    try:
        # Traemos solo lo necesario para el buscador para que sea muy rápido
        res = conn.table("libros").select("libro_id, titulo").order("titulo").execute()
        if not res.data:
            st.warning("No hay libros en el catálogo.")
            return
            
        df_libros = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Error al cargar la lista de libros: {e}")
        return

    # Crear el diccionario para el buscador
    dict_libros = dict(zip(df_libros['libro_id'], df_libros['titulo']))
    opciones_ids = [None] + list(dict_libros.keys())
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("### 1. Selecciona el Libro")
        libro_id_seleccionado = st.selectbox(
            "Escribe para buscar (título):", 
            options=opciones_ids,
            format_func=lambda x: "" if x is None else f"{dict_libros[x]} (ID: {x})",
            key="sel_portada_individual"
        )
        
        if libro_id_seleccionado:
            st.markdown("### 2. Sube la Nueva Imagen")
            archivo_img = st.file_uploader(
                "Formatos soportados: JPG, PNG, WEBP", 
                type=['jpg', 'jpeg', 'png', 'webp'], 
                key="up_portada_img"
            )
            
            if archivo_img:
                st.info("💡 Haz clic en el botón de abajo para aplicar los cambios.")
                if st.button("🚀 Optimizar y Subir Portada", type="primary", use_container_width=True):
                    with st.spinner("Procesando imagen, subiendo a la nube y actualizando caché..."):
                        exito, error = actualizar_portada_individual(libro_id_seleccionado, archivo_img)
                        
                        if exito:
                            st.success("✨ ¡Portada actualizada con éxito! Ya es visible en el catálogo público.")
                            st.snow()
                            time.sleep(2)
                            # Limpiamos caché global por si acaso y recargamos
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"❌ Ocurrió un error: {error}")
                            
    with col2:
        # Columna decorativa / Vista previa
        if libro_id_seleccionado and 'archivo_img' in locals() and archivo_img is not None:
            st.markdown("### Vista Previa")
            st.image(archivo_img, caption="Así se verá la nueva portada", use_container_width=True)
        elif libro_id_seleccionado:
            # Mostrar la portada actual si existe
            st.markdown("### Portada Actual en BD")
            URL_BASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
            st.image(f"{URL_BASE}{libro_id_seleccionado}.jpg", caption="Portada actual (puede tardar en actualizar si tu navegador tiene caché)", use_container_width=True)