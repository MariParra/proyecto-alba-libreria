import streamlit as st
from streamlit_oauth import OAuth2Component
import os
import base64
import json
from dotenv import load_dotenv
import time
from utilidades import get_db_connection
from datetime import datetime     

# --- IMPORTACIÓN DE VISTAS ---
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
from vista_kanban import mostrar_kanban
from vista_rollback import mostrar_rollback
from vista_ventas_masivas import mostrar_ventas_masivas
from vista_marketing import mostrar_generador_marketing
from vista_portadas import mostrar_gestion_portadas
from vista_web import mostrar_gestion_web
from vista_alertas_prioritarias import mostrar_alertas_prioritarias
from vista_pizarra import mostrar_pizarra
from vista_costos import mostrar_costos


import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)
    
# --- 1. CONFIGURACIÓN DE LA PÁGINA (¡SIEMPRE PRIMERO!) ---
st.set_page_config(page_title="Alba Librería Web", page_icon="📚", layout="wide")
load_dotenv()

# --- INYECCIÓN DE CSS PARA BARRA LATERAL FIJA (PC Y MÓVIL) ---
st.markdown("""
    <style>
        /* Contenedor principal de la barra lateral */
        [data-testid="stSidebar"] {
            /* Asegura que el contenido interno que se desborde permita hacer scroll */
            overflow-y: auto;
        }

        /* Cabecera de la barra lateral (donde está la X o flecha) */
        [data-testid="stSidebarHeader"] {
            position: sticky; /* La clave: se pega al borde superior */
            top: 0;
            z-index: 100; /* Se asegura de que esté por encima del contenido */
            /* Usa la variable de color de Streamlit para que coincida con el tema */
            background-color: var(--secondary-background-color);
            border-bottom: 1px solid rgba(49, 51, 63, 0.2); /* Línea sutil de separación */
            padding-bottom: 10px; /* Un poco de espacio extra */
        }
    </style>
""", unsafe_allow_html=True)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Lee la lista de correos desde los secretos de Streamlit
CORREOS_AUTORIZADOS = st.secrets.get("authorization", {}).get("authorized_emails", [])

if not CORREOS_AUTORIZADOS:
    st.error("Error de configuración: No se encontró la lista de correos autorizados en los secretos de la plataforma.")
    st.stop()
    
if CLIENT_ID and CLIENT_SECRET:
    oauth2 = OAuth2Component(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        authorize_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        refresh_token_endpoint="https://oauth2.googleapis.com/token",
    )
else:
    oauth2 = None

@st.cache_data
def get_image_as_base64(path):
    """Convierte una imagen local a una cadena de texto Base64 de forma instantánea."""
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/gif;base64,{data}"
    except IOError:
        return None
    
def decodificar_token(token):
    partes = token.split(".")
    if len(partes) != 3: return None
    payload = partes[1]; payload += "=" * ((4 - len(payload) % 4) % 4)
    return json.loads(base64.b64decode(payload).decode("utf-8")).get("email")

def mostrar_login():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center; color: #4A4D7E; margin-bottom: 0;'>📚 Alba Librería</h1>", unsafe_allow_html=True)
            st.markdown("<h4 style='text-align: center; color: #666; margin-top: 0;'>Portal Administrativo</h4>", unsafe_allow_html=True)
            st.markdown("---")
            st.markdown("<p style='text-align: center; font-size: 1.1em;'>Bienvenida al sistema integral de gestión de inventario, ventas y suscripciones.</p>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            if not oauth2:
                st.error("⚠️ Faltan las credenciales de Google en los secretos.")
                return
                
            try:
                result = oauth2.authorize_button(
                    name="Continuar con Google", 
                    icon="https://www.google.com/favicon.ico",
                    redirect_uri=REDIRECT_URI, 
                    scope="openid email profile", 
                    key="google_login", 
                    use_container_width=True
                )
                
                if result and "token" in result:
                    email = decodificar_token(result["token"].get("id_token"))
                    if email and email.lower() in [e.lower() for e in CORREOS_AUTORIZADOS]:
                        st.session_state["usuario_logeado"] = True
                        st.session_state["email_usuario"] = email
                        st.rerun()
                    else:
                        st.error(f"⛔ Acceso denegado: El correo {email} no tiene permisos.")
            except Exception as e:
                # SI HAY UN ERROR DE URL VIEJA, LO ATRAPAMOS AQUÍ Y LIMPIAMOS
                st.warning("🔄 Sesión caducada o enlace antiguo. Limpiando caché...")
                st.query_params.clear()
                import time
                time.sleep(1)
                st.rerun()
        
        st.markdown("<p style='text-align: center; color: #999; font-size: 12px; margin-top: 15px;'>🔒 Sistema protegido con autenticación de Google OAuth 2.0</p>", unsafe_allow_html=True)
    with col3:
        enlace_directo_gif = "https://raw.githubusercontent.com/MariParra/proyecto-alba-libreria/refs/heads/main/app/2_scripts/pricono.gif"
        
        st.markdown(
            f'''
            <style>
                /* DISEÑO POR DEFECTO: PC */
                .gif-bienvenida {{
                    position: fixed;
                    bottom: 30px;
                    right: 40px;
                    width: 300px;
                    z-index: 999;
                }}

                /* DISEÑO EN MÓVILES */
                @media (max-width: 768px) {{
                    .gif-bienvenida {{
                        position: relative;
                        display: block;
                        margin: 20px auto 0 auto;
                        bottom: auto;
                        right: auto;
                        width: 200px;
                    }}
                }}
            </style>
            <div class="gif-bienvenida">
                <img src="{enlace_directo_gif}" alt="animacion" style="width: 100%;">
            </div>
            ''',
            unsafe_allow_html=True,
        )

# --- LÓGICA PRINCIPAL ---
if "usuario_logeado" not in st.session_state:
    st.session_state["usuario_logeado"] = False

if not st.session_state["usuario_logeado"]:
    mostrar_login()
else:
    # ================= MENÚ LATERAL MEJORADO =================
    with st.sidebar:
        email_usuario = st.session_state.get('email_usuario', 'Usuario')
        
        mensaje_bienvenida_html = f"""
        <div style="background-color: #F3E6F3; border: 1px solid #C994C0; color: #4A4D7E; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; text-align: center;">
            <span style="font-weight: bold; font-size: 1.1em;">¡Bienvenida!</span><br>
            {email_usuario}
        </div>
        """
        st.markdown(mensaje_bienvenida_html, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### 🧭 NAVEGACIÓN")
        
        st.sidebar.title("📚 Panel de Control")
        st.sidebar.info("Selecciona un módulo para gestionar tu negocio.")
        
        if "pagina_actual" not in st.session_state:
            st.session_state.pagina_actual = "🚨 ALERTAS PRIORITARIAS"
            
        # Definición de grupos de vistas para la apertura dinámica de los expanders
        grupo_general = ["🚨 ALERTAS PRIORITARIAS", "📌 PIZARRA DE NOTAS", "📋 TABLERO KANBAN", "📊 DASHBOARD"]
        grupo_ventas = ["🛒 CAJA / VENTAS RÁPIDAS", "🎡 VENTAS MASIVAS", "📦 GESTIÓN DE SUSCRIPCIÓN", "👥 CLIENTES Y LIBRERO", "💸 GASTOS"]
        grupo_catalogo = ["📦 GESTIÓN DE INVENTARIO", "🖼️ GESTIÓN DE PORTADAS", "🎨 GENERADOR CATÁLOGO IG", "🌐 GESTIÓN WEB"]
        grupo_datos = ["🛠️ SINCRONIZACIÓN GOOGLE SHEET", "📔 IMPORTAR LIBREROS", "📥 REPORTES Y DESCARGAS"]
        grupo_soporte = ["✨ CREACIÓN MASIVA", "⚡ ACTUALIZACIÓN MASIVA", "⏪ ROLLBACK BD"]

        # --- SECCIÓN 1: GENERAL & MONITOREO ---
        with st.expander("📢 General & Monitoreo", expanded=st.session_state.pagina_actual in grupo_general):
            if st.button("🚨 ALERTAS PRIORITARIAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🚨 ALERTAS PRIORITARIAS" else "secondary"):
                st.session_state.pagina_actual = "🚨 ALERTAS PRIORITARIAS"
                st.rerun()
            
            if st.button("📌 PIZARRA DE NOTAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📌 PIZARRA DE NOTAS" else "secondary"):
                st.session_state.pagina_actual = "📌 PIZARRA DE NOTAS"
                st.rerun()
                
            if st.button("📋 TABLERO KANBAN", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📋 TABLERO KANBAN" else "secondary"):
                st.session_state.pagina_actual = "📋 TABLERO KANBAN"
                st.rerun()

            if st.button("📊 DASHBOARD", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📊 DASHBOARD" else "secondary"):
                st.session_state.pagina_actual = "📊 DASHBOARD"
                st.rerun()

        # --- SECCIÓN 2: GESTIÓN DE VENTAS Y CLIENTES ---
        with st.expander("💰 Ventas & Clientes", expanded=st.session_state.pagina_actual in grupo_ventas):
            if st.button("🛒 CAJA / VENTAS RÁPIDAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🛒 CAJA / VENTAS RÁPIDAS" else "secondary"):
                st.session_state.pagina_actual = "🛒 CAJA / VENTAS RÁPIDAS"
                st.rerun()
                
            if st.button("🎡 VENTAS MASIVAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🎡 VENTAS MASIVAS" else "secondary"):
                st.session_state.pagina_actual = "🎡 VENTAS MASIVAS" 
                st.rerun()

            if st.button("📦 GESTIÓN DE SUSCRIPCIÓN", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📦 GESTIÓN DE SUSCRIPCIÓN" else "secondary"):
                st.session_state.pagina_actual = "📦 GESTIÓN DE SUSCRIPCIÓN"
                st.rerun()

            if st.button("👥 CLIENTES Y LIBRERO", use_container_width=True, type="primary" if st.session_state.pagina_actual == "👥 CLIENTES Y LIBRERO" else "secondary"):
                st.session_state.pagina_actual = "👥 CLIENTES Y LIBRERO"
                st.rerun()
                
            if st.button("💸 GASTOS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "💸 GASTOS" else "secondary"):
                st.session_state.pagina_actual = "💸 GASTOS"
                st.rerun()

        # --- SECCIÓN 3: CATÁLOGO & INVENTARIO ---
        with st.expander("📦 Catálogo & Inventario", expanded=st.session_state.pagina_actual in grupo_catalogo):
            if st.button("📦 GESTIÓN DE INVENTARIO", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📦 GESTIÓN DE INVENTARIO" else "secondary"):
                st.session_state.pagina_actual = "📦 GESTIÓN DE INVENTARIO"
                st.rerun()

            if st.button("🖼️ GESTIÓN DE PORTADAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🖼️ GESTIÓN DE PORTADAS" else "secondary"):
                st.session_state.pagina_actual = "🖼️ GESTIÓN DE PORTADAS"
                st.rerun()
                
            if st.button("🎨 GENERADOR CATÁLOGO IG", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🎨 GENERADOR CATÁLOGO IG" else "secondary"):
                st.session_state.pagina_actual = "🎨 GENERADOR CATÁLOGO IG"
                st.rerun()
                
            if st.button("🌐 GESTIÓN WEB", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🌐 GESTIÓN WEB" else "secondary"):
                st.session_state.pagina_actual = "🌐 GESTIÓN WEB"
                st.rerun()

        # --- SECCIÓN 4: DATOS & INTEGRACIONES ---
        with st.expander("⚙️ Datos & Integraciones", expanded=st.session_state.pagina_actual in grupo_datos):
            if st.button("🛠️ SINCRONIZACIÓN GOOGLE SHEET", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🛠️ SINCRONIZACIÓN GOOGLE SHEET" else "secondary"):
                st.session_state.pagina_actual = "🛠️ SINCRONIZACIÓN GOOGLE SHEET"
                st.rerun()
                
            if st.button("📔 IMPORTAR LIBREROS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📔 IMPORTAR LIBREROS" else "secondary"):
                st.session_state.pagina_actual = "📔 IMPORTAR LIBREROS"
                st.rerun()

            if st.button("📥 REPORTES Y DESCARGAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📥 REPORTES Y DESCARGAS" else "secondary"):
                st.session_state.pagina_actual = "📥 REPORTES Y DESCARGAS"
                st.rerun()

        # --- SECCIÓN 5: SOPORTE & ADMIN AVANZADA ---
        with st.expander("🛠️ Soporte & Admin Avanzada", expanded=st.session_state.pagina_actual in grupo_soporte):
            if st.button("✨ CREACIÓN MASIVA", use_container_width=True, type="primary" if st.session_state.pagina_actual == "✨ CREACIÓN MASIVA" else "secondary"):
                st.session_state.pagina_actual = "✨ CREACIÓN MASIVA"
                st.rerun()
                
            if st.button("⚡ ACTUALIZACIÓN MASIVA", use_container_width=True, type="primary" if st.session_state.pagina_actual == "⚡ ACTUALIZACIÓN MASIVA" else "secondary"):
                st.session_state.pagina_actual = "⚡ ACTUALIZACIÓN MASIVA"
                st.rerun()
                
            if st.button("⏪ ROLLBACK BD", use_container_width=True, type="primary" if st.session_state.pagina_actual == "⏪ ROLLBACK BD" else "secondary"):
                st.session_state.pagina_actual = "⏪ ROLLBACK BD"
                st.rerun()

        st.markdown("---")
        if st.button("🔄 Refrescar Toda la App", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.toast("✅ ¡Datos actualizados! La aplicación ha sido refrescada.", icon="🔄")
            import time
            time.sleep(1) 
            st.rerun()
        
        st.markdown("---")
        
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        with st.expander("🛠️ Auditoría de Sistema (Versiones)"):
            import pandas as pd
            import pytz
            import gspread
            import openpyxl
            import xlsxwriter
            
            try:
                import starlette
                version_starlette = starlette.__version__
            except:
                version_starlette = "No instalada o versión oculta"
                
            try:
                import streamlit_oauth
                version_oauth = streamlit_oauth.__version__
            except:
                version_oauth = "No instalada o versión oculta"

            st.markdown("##### Librerías Instaladas")
            st.write(f"🟢 **Streamlit:** `{st.__version__}`")
            st.write(f"🟢 **Pandas:** `{pd.__version__}`")
            st.write(f"🟢 **Pytz:** `{pytz.__version__}`")
            st.write(f"🟢 **Gspread:** `{gspread.__version__}`")
            st.write(f"🟢 **Openpyxl:** `{openpyxl.__version__}`")
            st.write(f"🟢 **Xlsxwriter:** `{xlsxwriter.__version__}`")
            st.write(f"🟢 **Starlette:** `{version_starlette}`")
            st.write(f"🟢 **Streamlit-OAuth:** `{version_oauth}`")

    # ================= ÁREA PRINCIPAL =================
    col_izq, col_central, col_der = st.columns([1, 8, 1])
    with col_central:
        if st.session_state.pagina_actual == "🚨 ALERTAS PRIORITARIAS":
            mostrar_alertas_prioritarias()
        elif st.session_state.pagina_actual == "📌 PIZARRA DE NOTAS":
            mostrar_pizarra()
        
        # Mantenemos tu estructura condicional exacta para el renderizado
        if st.session_state.pagina_actual == "📦 GESTIÓN DE INVENTARIO":
            mostrar_inventario() 
        elif st.session_state.pagina_actual == "🛒 CAJA / VENTAS RÁPIDAS":
            mostrar_caja()
        elif st.session_state.pagina_actual == '🎡 VENTAS MASIVAS':
            mostrar_ventas_masivas()
        elif st.session_state.pagina_actual == "👥 CLIENTES Y LIBRERO":
            mostrar_clientes()
        elif st.session_state.pagina_actual == "💸 GASTOS":
            mostrar_costos()
        elif st.session_state.pagina_actual == "📦 GESTIÓN DE SUSCRIPCIÓN":
            mostrar_asignaciones()
        elif st.session_state.pagina_actual == "🎨 GENERADOR CATÁLOGO IG":
            mostrar_generador_marketing()
        elif st.session_state.pagina_actual == "📊 DASHBOARD":
            mostrar_dashboard()
        elif st.session_state.pagina_actual == "🛠️ SINCRONIZACIÓN GOOGLE SHEET":
            mostrar_herramientas()
        elif st.session_state.pagina_actual == "📔 IMPORTAR LIBREROS":
            mostrar_importacion_libreros()
        elif st.session_state.pagina_actual == "🖼️ GESTIÓN DE PORTADAS":
            mostrar_gestion_portadas()
        elif st.session_state.pagina_actual == "🌐 GESTIÓN WEB":
            mostrar_gestion_web()
        elif st.session_state.pagina_actual == "📥 REPORTES Y DESCARGAS":
            mostrar_reportes()
        elif st.session_state.pagina_actual == "✨ CREACIÓN MASIVA":
            mostrar_creacion_masiva()
        elif st.session_state.pagina_actual == "⚡ ACTUALIZACIÓN MASIVA":
            mostrar_actualizacion_masiva()
        elif st.session_state.pagina_actual == "📋 TABLERO KANBAN":
            mostrar_kanban()
        elif st.session_state.pagina_actual == "⏪ ROLLBACK BD": 
            mostrar_rollback()