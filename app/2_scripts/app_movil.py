import streamlit as st
from streamlit_oauth import OAuth2Component
import os
import base64
import json
from dotenv import load_dotenv

from vista_inventario import mostrar_inventario
from vista_caja import mostrar_caja
from vista_clientes import mostrar_clientes
from vista_asignaciones import mostrar_asignaciones

st.set_page_config(page_title="Alba Librería Web", page_icon="📚", layout="wide")

load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

CORREOS_AUTORIZADOS = [
    "mariana96.parra@gmail.com", 
    "albalibreriadevelop@gmail.com",
    "develop.alba.libreria@gmail.com",
    "albalibreriachile@gmail.com",
    "ividalavello@gmail.com"
]

if CLIENT_ID and CLIENT_SECRET:
    oauth2 = OAuth2Component(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        authorize_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        refresh_token_endpoint="https://oauth2.googleapis.com/token",
    )
else:
    oauth2 = None

def decodificar_token(token):
    partes = token.split(".")
    if len(partes) != 3: return None
    payload = partes[1]; payload += "=" * ((4 - len(payload) % 4) % 4)
    return json.loads(base64.b64decode(payload).decode("utf-8")).get("email")

def mostrar_login():
    st.title("📚 Alba Librería")
    st.markdown("### Acceso Restringido")
    if not oauth2:
        st.error("Faltan las credenciales de Google.")
        return
        
    result = oauth2.authorize_button(
        name="Iniciar sesión con Google", icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI, scope="openid email profile", key="google_login", use_container_width=True
    )
    if result and "token" in result:
        email = decodificar_token(result["token"].get("id_token"))
        if email and email.lower() in [e.lower() for e in CORREOS_AUTORIZADOS]:
            st.session_state["usuario_logeado"] = True; st.session_state["email_usuario"] = email
            st.rerun()
        else:
            st.error(f"⛔ El correo {email} no está autorizado.")

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
        st.markdown("## 🧭 NAVEGACIÓN")
        
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