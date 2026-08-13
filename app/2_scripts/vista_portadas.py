import streamlit as st
import pandas as pd
import io
import os
import time
from PIL import Image
from utilidades import get_db_connection, log_error, limpiar_texto_para_busqueda

# --- FUNCIÓN DE LIMPIEZA ESTANDARIZADA ---
def normalizar_nombre_para_match(texto):
    if not isinstance(texto, str):
        return ""
    texto_limpio = limpiar_texto_para_busqueda(texto)
    return "".join(caracter for caracter in texto_limpio if caracter.isalnum())

def actualizar_portada_individual(libro_id, archivo_subido):
    conn = get_db_connection()
    try:
        img = Image.open(archivo_subido)
        rgb_im = img.convert('RGB')
        
        img_byte_arr = io.BytesIO()
        rgb_im.save(img_byte_arr, format='JPEG', quality=95)
        
        nombre_archivo = f"{libro_id}.jpg"
        
        try:
            conn.storage.from_("portadas").remove([nombre_archivo])
        except:
            pass 
            
        conn.storage.from_("portadas").upload(
            path=nombre_archivo,
            file=img_byte_arr.getvalue(),
            file_options={"content-type": "image/jpeg"}
        )
        
        conn.table("libros").update({
            "portada_last_updated": "now()"
        }).eq("libro_id", libro_id).execute()
        
        return True, ""
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(vista="vista_portadas", funcion="actualizar_portada_individual", error=str(e), email_usuario=email_usuario)
        return False, str(e)


def mostrar_gestion_portadas():
    st.markdown("<h2 style='color: #4A4D7E;'>🖼️ Gestión de Portadas</h2>", unsafe_allow_html=True)
    st.write("Sube imágenes para tus libros. El sistema las optimizará a JPG y forzará a la web pública a mostrar la nueva versión.")
    
    # Obtenemos la base de datos una sola vez
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo").order("titulo").execute()
        if not res.data:
            st.warning("No hay libros en el catálogo.")
            return
        df_libros = pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Error al cargar la lista de libros: {e}")
        return

    # Tabs para separar la lógica
    tab_individual, tab_masiva = st.tabs(["🎯 Subida Individual", "🚀 Subida Masiva (Emparejamiento Automático)"])

    # ==========================================
    # PESTAÑA 1: INDIVIDUAL
    # ==========================================
    with tab_individual:
        dict_libros = dict(zip(df_libros['libro_id'], df_libros['titulo']))
        opciones_ids = [None] + list(dict_libros.keys())
        
        col1, col2 = st.columns()
        
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
                    if st.button("🚀 Optimizar y Subir Portada", type="primary", use_container_width=True):
                        with st.spinner("Procesando imagen, subiendo a la nube y actualizando caché..."):
                            exito, error = actualizar_portada_individual(libro_id_seleccionado, archivo_img)
                            if exito:
                                st.success("✨ ¡Portada actualizada con éxito!")
                                st.snow()
                                time.sleep(2)
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"❌ Ocurrió un error: {error}")
                                
        with col2:
            if libro_id_seleccionado and 'archivo_img' in locals() and archivo_img is not None:
                st.markdown("### Vista Previa")
                st.image(archivo_img, caption="Así se verá la nueva portada", use_container_width=True)
            elif libro_id_seleccionado:
                st.markdown("### Portada Actual en BD")
                URL_BASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
                st.image(f"{URL_BASE}{libro_id_seleccionado}.jpg", caption="Portada actual", use_container_width=True)

    # ==========================================
    # PESTAÑA 2: MASIVA
    # ==========================================
    with tab_masiva:
        st.markdown("### 📦 Subir múltiples portadas a la vez")
        st.info("💡 **Tip:** Asegúrate de que el nombre de cada archivo coincida con el **título del libro** o sea el **ID exacto**. El sistema ignorará tildes y mayúsculas para hacer el emparejamiento.")
        
        # --- NUEVO: OPCIÓN PARA SOBREESCRIBIR ---
        sobreescribir = st.toggle(
            "🔄 Sobreescribir portadas existentes en la nube", 
            value=False, 
            help="Si está APAGADO, el sistema saltará los libros que ya tengan portada. Si lo ENCIENDES, reemplazará las portadas viejas por las nuevas que estás subiendo."
        )
        
        archivos_multiples = st.file_uploader(
            "Arrastra aquí todas las portadas (JPG, PNG, WEBP):", 
            type=['jpg', 'jpeg', 'png', 'webp'], 
            accept_multiple_files=True,
            key="up_portadas_masivas"
        )
        
        if archivos_multiples:
            st.write(f"Has seleccionado **{len(archivos_multiples)}** imágenes.")
            
            if st.button("⚡ Procesar Subida Masiva", type="primary", use_container_width=True):
                # Crear mapas de búsqueda rápida
                mapa_titulos = {normalizar_nombre_para_match(row['titulo']): str(row['libro_id']) for _, row in df_libros.iterrows()}
                
                portadas_existentes = set()
                
                # Si NO queremos sobreescribir, necesitamos saber qué hay en la nube
                if not sobreescribir:
                    with st.spinner("Consultando qué portadas ya existen en la nube..."):
                        try:
                            offset = 0
                            while True:
                                try:
                                    bloque = conn.storage.from_("portadas").list(path="", search_options={"limit": 100, "offset": offset})
                                except TypeError:
                                    bloque = conn.storage.from_("portadas").list(path="", options={"limit": 100, "offset": offset})
                                    
                                if not bloque:
                                    break
                                for b in bloque:
                                    if b['name'] != '.emptyFolderPlaceholder':
                                        portadas_existentes.add(b['name'])
                                offset += 100
                        except Exception as e:
                            st.warning(f"No se pudo verificar la nube, se intentará subir todo. Error: {e}")

                exitos = 0
                omitidos = 0
                no_encontrados = []
                errores = []
                
                barra_progreso = st.progress(0, text="Iniciando procesamiento masivo...")
                
                for idx, archivo in enumerate(archivos_multiples):
                    barra_progreso.progress((idx + 1) / len(archivos_multiples), text=f"Procesando {archivo.name}...")
                    
                    nombre_sin_ext, _ = os.path.splitext(archivo.name)
                    nombre_limpio = normalizar_nombre_para_match(nombre_sin_ext)
                    
                    libro_id_match = None
                    
                    # 1. Intentar buscar por Título Limpio
                    if nombre_limpio in mapa_titulos:
                        libro_id_match = mapa_titulos[nombre_limpio]
                    # 2. Intentar buscar por ID directo
                    elif nombre_sin_ext.isdigit() and int(nombre_sin_ext) in df_libros['libro_id'].values:
                        libro_id_match = nombre_sin_ext
                        
                    if libro_id_match:
                        nuevo_nombre_archivo = f"{libro_id_match}.jpg"
                        
                        # --- LÓGICA DE OMITIR ---
                        if not sobreescribir and nuevo_nombre_archivo in portadas_existentes:
                            omitidos += 1
                            continue
                            
                        # Subir y romper caché
                        exito, error = actualizar_portada_individual(libro_id_match, archivo)
                        if exito:
                            exitos += 1
                        else:
                            errores.append(f"{archivo.name}: {error}")
                    else:
                        no_encontrados.append(archivo.name)
                
                barra_progreso.progress(1.0, text="¡Procesamiento finalizado!")
                
                # Resumen
                st.markdown("---")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("✅ Subidas", exitos)
                c2.metric("⏭️ Omitidas (Ya existían)", omitidos)
                c3.metric("⚠️ Sin Match", len(no_encontrados))
                c4.metric("❌ Errores", len(errores))
                
                if exitos > 0:
                    st.balloons()
                    st.success("¡Las portadas han sido procesadas! El catálogo público se actualizará de inmediato.")
                    st.cache_data.clear()
                    
                if no_encontrados:
                    with st.expander("Ver portadas que no hicieron match con ningún libro"):
                        for ne in no_encontrados:
                            st.write(f"- {ne}")
                            
                if errores:
                    with st.expander("Ver errores de subida"):
                        for err in errores:
                            st.write(f"- {err}")