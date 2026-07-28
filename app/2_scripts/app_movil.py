import streamlit as st
from streamlit_oauth import OAuth2Component
import os
import sys
import base64
import json
from dotenv import load_dotenv
import time

# --- ARQUITECTURA DE IMPORTACIÓN (Correcto) ---
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

# --- IMPORTACIÓN DE VISTAS (Correcto) ---
from vista_inventario import mostrar_inventario
from vista_caja import mostrar_caja
from vista_clientes import mostrar_clientes
from vista_asignaciones import mostrar_asignaciones
from vista_dashboard import mostrar_dashboard
from vista_herramientas import mostrar_herramientas
from vista_libreros import mostrar_importacion_libreros
from vista_creacion_masiva import mostrar_creacion_masiva
from vista_actualizacion_masiva import mostrar_actualizacion_masiva
from vista_reportes import mostrar_reportes 

# --- CONFIGURACIÓN Y AUTENTICACIÓN (Sin cambios) ---
st.set_page_config(page_title="Alba Librería Web", page_icon="📚", layout="wide")
load_dotenv()

# ... (Todo tu código de configuración de OAuth2, CORREOS_AUTORIZADOS, etc. va aquí sin cambios) ...

# --- LÓGICA PRINCIPAL ---
if "usuario_logeado" not in st.session_state:
    st.session_state["usuario_logeado"] = False

if not st.session_state["usuario_logeado"]:
    mostrar_login()
else:
    # --- 🛠️ MENÚ LATERAL OPTIMIZADO ---
    with st.sidebar:
        email_usuario = st.session_state.get('email_usuario', 'Usuario')
        st.markdown(f"""... Mensaje de bienvenida ...""", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### 🧭 NAVEGACIÓN")

        # Diccionario que mapea nombres de página a sus funciones
        paginas = {
            "📦 GESTIÓN DE INVENTARIO": mostrar_inventario,
            "🛒 CAJA / VENTAS RÁPIDAS": mostrar_caja,
            "👥 CLIENTES Y LIBRERO": mostrar_clientes,
            "📦 ASIGNACIONES SUSCRIPCIÓN": mostrar_asignaciones,
            "📊 DASHBOARD": mostrar_dashboard,
            "🛠️ HERRAMIENTAS Y SYNC": mostrar_herramientas,
            "📔 IMPORTAR LIBREROS": mostrar_importacion_libreros
        }
        
        # Inicializar la página actual
        if "pagina_actual" not in st.session_state:
            st.session_state.pagina_actual = "📦 GESTIÓN DE INVENTARIO"

        # Crear botones de navegación con un bucle
        for nombre_pagina in paginas.keys():
            if st.button(nombre_pagina, use_container_width=True, type="primary" if st.session_state.pagina_actual == nombre_pagina else "secondary"):
                st.session_state.pagina_actual = nombre_pagina
                st.rerun() # No se necesita sleep aquí

        st.markdown("---")
        st.markdown("### ⚙️ ADMIN AVANZADA")

        paginas_admin = {
            "📥 REPORTES Y DESCARGAS": mostrar_reportes,
            "✨ CREACIÓN MASIVA": mostrar_creacion_masiva,
            "⚡ ACTUALIZACIÓN MASIVA": mostrar_actualizacion_masiva
        }

        for nombre_pagina in paginas_admin.keys():
             if st.button(nombre_pagina, use_container_width=True, type="primary" if st.session_state.pagina_actual == nombre_pagina else "secondary"):
                st.session_state.pagina_actual = nombre_pagina
                st.rerun() # No se necesita sleep aquí

        # --- Botones de acción ---
        st.markdown("---")
        if st.button("🔄 Refrescar Toda la App", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.toast("✅ ¡Datos actualizados!", icon="🔄")
            time.sleep(1) # Sleep corto y justificado
            st.rerun()
        
        st.markdown("---")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun() # No se necesita sleep aquí

    # --- ÁREA PRINCIPAL PARA MOSTRAR LA PÁGINA ---
    # Unificamos todas las páginas en un solo diccionario para más limpieza
    todas_las_paginas = {**paginas, **paginas_admin}

    col_izq, col_central, col_der = st.columns([1, 8, 1])
    with col_central:
        # Ejecutamos la función de la página guardada en el estado
        if st.session_state.pagina_actual in todas_las_paginas:
            todas_las_paginas[st.session_state.pagina_actual]()
        else:
            # Fallback seguro si el estado se pierde
            mostrar_inventario()