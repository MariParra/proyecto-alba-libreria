import streamlit as st
from streamlit_oauth import OAuth2Component
import os
import base64
import json
from dotenv import load_dotenv

# --- IMPORTACIÓN DE VISTAS ---
from vista_inventario import mostrar_inventario
from vista_caja import mostrar_caja
from vista_clientes import mostrar_clientes
from vista_asignaciones import mostrar_asignaciones
from vista_dashboard import mostrar_dashboard
from vista_herramientas import mostrar_herramientas
from vista_libreros import mostrar_importacion_libreros

# Nuevas importaciones añadidas
from vista_creacion_masiva import mostrar_creacion_masiva
from vista_actualizacion_masiva import mostrar_actualizacion_masiva
from vista_reportes import mostrar_reportes 

import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)
    
st.set_page_config(page_title="Alba Librería Web", page_icon="📚", layout="wide")
load_dotenv()

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
    
def get_image_as_base64(path):
    """Convierte una imagen local a una cadena de texto Base64."""
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/gif;base64,{data}"
    except IOError:
        return None # Devuelve None si no encuentra el archivo
    
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
        # 1. Construimos la ruta segura
        ruta_gif = os.path.join(script_dir, "pricono.gif")
        # 2. Convertimos el GIF a Base64
        gif_base64 = get_image_as_base64(ruta_gif)
        
        # 3. Si se pudo convertir, lo fijamos en la esquina con CSS
        if gif_base64:
            st.markdown(
                f'''
                <div style="position: fixed; bottom: 30px; right: 40px; z-index: 999;">
                    <img src="{gif_base64}" alt="animacion" width="400">
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
        ruta_logo = os.path.join(script_dir, "logo.png")
        try:
            st.sidebar.image(ruta_logo, use_container_width=True)
        except Exception:
            st.sidebar.warning("Logo no encontrado")
        st.sidebar.title("📚 Panel de Control")
        st.sidebar.info("Selecciona un módulo para gestionar tu negocio.")
        
        if "pagina_actual" not in st.session_state:
            st.session_state.pagina_actual = "📦 GESTIÓN DE INVENTARIO"
            
        if st.button("📦 GESTIÓN DE INVENTARIO", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📦 GESTIÓN DE INVENTARIO" else "secondary"):
            st.session_state.pagina_actual = "📦 GESTIÓN DE INVENTARIO"
            st.rerun()
            
        if st.button("🛒 CAJA / VENTAS RÁPIDAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🛒 CAJA / VENTAS RÁPIDAS" else "secondary"):
            st.session_state.pagina_actual = "🛒 CAJA / VENTAS RÁPIDAS"
            st.rerun()
            
        if st.button("👥 CLIENTES Y LIBRERO", use_container_width=True, type="primary" if st.session_state.pagina_actual == "👥 CLIENTES Y LIBRERO" else "secondary"):
            st.session_state.pagina_actual = "👥 CLIENTES Y LIBRERO"
            st.rerun()
        
        if st.button("📦 ASIGNACIONES SUSCRIPCIÓN", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📦 ASIGNACIONES SUSCRIPCIÓN" else "secondary"):
            st.session_state.pagina_actual = "📦 ASIGNACIONES SUSCRIPCIÓN"
            st.rerun()
            
        if st.button("📊 DASHBOARD", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📊 DASHBOARD" else "secondary"):
            st.session_state.pagina_actual = "📊 DASHBOARD"
            st.rerun()
            
        if st.button("🛠️ HERRAMIENTAS Y SYNC", use_container_width=True, type="primary" if st.session_state.pagina_actual == "🛠️ HERRAMIENTAS Y SYNC" else "secondary"):
            st.session_state.pagina_actual = "🛠️ HERRAMIENTAS Y SYNC"
            st.rerun()
            
        if st.button("📔 IMPORTAR LIBREROS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📔 IMPORTAR LIBREROS" else "secondary"):
            st.session_state.pagina_actual = "📔 IMPORTAR LIBREROS"
            st.rerun()

        st.markdown("---")
        st.markdown("### ⚙️ ADMIN AVANZADA")
        
        if st.button("📥 REPORTES Y DESCARGAS", use_container_width=True, type="primary" if st.session_state.pagina_actual == "📥 REPORTES Y DESCARGAS" else "secondary"):
            st.session_state.pagina_actual = "📥 REPORTES Y DESCARGAS"
            st.rerun()

        if st.button("✨ CREACIÓN MASIVA", use_container_width=True, type="primary" if st.session_state.pagina_actual == "✨ CREACIÓN MASIVA" else "secondary"):
            st.session_state.pagina_actual = "✨ CREACIÓN MASIVA"
            st.rerun()
            
        if st.button("⚡ ACTUALIZACIÓN MASIVA", use_container_width=True, type="primary" if st.session_state.pagina_actual == "⚡ ACTUALIZACIÓN MASIVA" else "secondary"):
            st.session_state.pagina_actual = "⚡ ACTUALIZACIÓN MASIVA"
            st.rerun()

        st.markdown("---")
        if st.button("🔄 Refrescar Toda la App", type="secondary", use_container_width=True):
            # 1. Limpiamos la caché de datos
            st.cache_data.clear()
            
            # 2. Mostramos el mensaje de confirmación
            st.toast("✅ ¡Datos actualizados! La aplicación ha sido refrescada.", icon="🔄")
            
            # 3. Esperamos un instante para que el mensaje sea visible antes de recargar
            import time
            time.sleep(1) 
            
            # 4. Recargamos la página
            st.rerun()
        
        st.markdown("---")
        
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # ================= ÁREA PRINCIPAL =================
    col_izq, col_central, col_der = st.columns([1, 8, 1])
    with col_central:
        if st.session_state.pagina_actual == "📦 GESTIÓN DE INVENTARIO":
            mostrar_inventario() 
        elif st.session_state.pagina_actual == "🛒 CAJA / VENTAS RÁPIDAS":
            mostrar_caja()
        elif st.session_state.pagina_actual == "👥 CLIENTES Y LIBRERO":
            mostrar_clientes()
        elif st.session_state.pagina_actual == "📦 ASIGNACIONES SUSCRIPCIÓN":
            mostrar_asignaciones()
        elif st.session_state.pagina_actual == "📊 DASHBOARD":
            mostrar_dashboard()
        elif st.session_state.pagina_actual == "🛠️ HERRAMIENTAS Y SYNC":
            mostrar_herramientas()
        elif st.session_state.pagina_actual == "📔 IMPORTAR LIBREROS":
            mostrar_importacion_libreros()
            
        # --- NUEVAS RUTAS AÑADIDAS ---
        elif st.session_state.pagina_actual == "📥 REPORTES Y DESCARGAS":
            mostrar_reportes()
        elif st.session_state.pagina_actual == "✨ CREACIÓN MASIVA":
            mostrar_creacion_masiva()
        elif st.session_state.pagina_actual == "⚡ ACTUALIZACIÓN MASIVA":
            mostrar_actualizacion_masiva()