import streamlit as st
from streamlit_oauth import OAuth2Component
import os
import base64
import json
from dotenv import load_dotenv
import psycopg2
import pandas as pd
from packaging import version # <--- ¡LA LÍNEA QUE FALTABA!

# Configuración de página
st.set_page_config(page_title="Alba Librería Móvil", page_icon="📚", layout="centered")

# --- 0. MOSTRAR VERSIÓN PARA DEBUGGING ---
st.caption(f"Streamlit v{st.__version__}")

# --- 1. CARGAR VARIABLES DE ENTORNO ---
load_dotenv()
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- 2. LISTA DE CORREOS AUTORIZADOS ---
CORREOS_AUTORIZADOS = [
    "mariana96.parra@gmail.com", 
    "albalibreriadevelop@gmail.com",
    "develop.alba.libreria@gmail.com"
]

# --- 3. CONFIGURACIÓN DE GOOGLE OAUTH ---
oauth2 = OAuth2Component(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    authorize_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    refresh_token_endpoint="https://oauth2.googleapis.com/token",
)

# --- 4. FUNCIONES DE BASE DE DATOS (REFORZADAS) ---
@st.cache_resource
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

@st.cache_data(ttl=30)
def cargar_inventario():
    conn = get_db_connection()
    df = pd.read_sql("SELECT libro_id, titulo, autor, stock, precio FROM libros ORDER BY titulo", conn)
    return df

def ejecutar_query_escritura(query, params):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
        st.cache_data.clear()
        return True, None
    except psycopg2.Error as e:
        conn.rollback()
        return False, str(e)

def actualizar_libros_batch(df_editado):
    df_original = st.session_state.get('inventario_original')
    if df_original is None: return 0
    df_original_comp = df_original.set_index('libro_id')
    df_editado_comp = df_editado.set_index('libro_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    if filas_cambiadas.empty: return 0
    updates_count = 0
    for libro_id, row in filas_cambiadas.iterrows():
        try:
            query = "UPDATE libros SET stock = %s, precio = %s WHERE libro_id = %s"
            params = (int(row['stock']), float(row['precio']), libro_id)
            success, error = ejecutar_query_escritura(query, params)
            if success:
                updates_count += 1
            else:
                st.error(f"Error al actualizar libro ID {libro_id}: {error}")
        except (ValueError, KeyError):
            continue
    return updates_count

def crear_nuevo_libro(titulo, autor, stock, precio):
    query = "INSERT INTO libros (titulo, autor, stock, precio, precio_original) VALUES (%s, %s, %s, %s, %s)"
    params = (titulo.upper(), autor.upper(), stock, precio, precio)
    return ejecutar_query_escritura(query, params)

def eliminar_libro(libro_id):
    query = "DELETE FROM libros WHERE libro_id = %s"
    params = (libro_id,)
    return ejecutar_query_escritura(query, params)

# --- 5. FUNCIONES DE LA INTERFAZ ---
def decodificar_token(token):
    partes = token.split(".");
    if len(partes) != 3: return None
    payload = partes[1]; payload += "=" * ((4 - len(payload) % 4) % 4)
    return json.loads(base64.b64decode(payload).decode("utf-8")).get("email")

def mostrar_login():
    st.title("📚 Alba Librería"); st.markdown("### Acceso Restringido")
    st.write("Por favor, inicia sesión para continuar.")
    result = oauth2.authorize_button(
        name="Iniciar sesión con Google", icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI, scope="openid email profile", key="google_login", use_container_width=True
    )
    if result and "token" in result:
        email_usuario = decodificar_token(result["token"].get("id_token"))
        if email_usuario.lower() in [email.lower() for email in CORREOS_AUTORIZADOS]:
            st.session_state["usuario_logeado"] = True; st.session_state["email_usuario"] = email_usuario
            st.rerun()
        else:
            st.error(f"⛔ El correo {email_usuario} no está autorizado.")


def mostrar_app_principal():
    st.success(f"¡Bienvenida, {st.session_state['email_usuario']}!")
    st.title("📱 Panel Principal")
    
    menu = st.radio("¿Qué deseas hacer?", ["Inventario", "Caja / Ventas"], horizontal=True, label_visibility="collapsed")
    
    if menu == "Inventario":
        st.subheader("📚 Inventario de Libros")
        
        with st.expander("➕ Crear Nuevo Libro"):
            with st.form("form_nuevo_libro", clear_on_submit=True):
                nuevo_titulo = st.text_input("Título")
                nuevo_autor = st.text_input("Autor")
                col1, col2 = st.columns(2)
                nuevo_stock = col1.number_input("Stock", min_value=0, step=1)
                nuevo_precio = col2.number_input("Precio", min_value=0.0, format="%.2f")
                submitted = st.form_submit_button("Crear Libro")
                if submitted and nuevo_titulo:
                    success, error = crear_nuevo_libro(nuevo_titulo, nuevo_autor, nuevo_stock, nuevo_precio)
                    if success: st.success(f"¡'{nuevo_titulo}' creado!"); st.rerun()
                    else: st.error(f"No se pudo crear: {error}")

        df_inventario = cargar_inventario()
        if 'inventario_original' not in st.session_state:
            st.session_state.inventario_original = df_inventario.copy()
        
        st.info("Haz doble clic en 'stock' o 'precio' para editar.")
        
        # --- LÓGICA ADAPTATIVA ---
        usa_selection = False
        try:
            # Intenta usar la versión moderna
            df_editado = st.data_editor(
                df_inventario, 
                use_container_width=True, hide_index=True,
                disabled=["libro_id", "titulo", "autor"], 
                key="editor_inventario",
                on_select="rerun",
                selection_mode="single-row"
            )
            usa_selection = True
        except TypeError:
            # Si lanza error, usa la versión clásica de forma limpia
            df_editado = st.data_editor(
                df_inventario, 
                use_container_width=True, hide_index=True,
                disabled=["libro_id", "titulo", "autor"], 
                key="editor_inventario"
            )


        if not st.session_state.inventario_original.equals(df_editado):
            if st.button("💾 Guardar Cambios en la Tabla", type="primary"):
                with st.spinner("Actualizando..."):
                    num_actualizados = actualizar_libros_batch(df_editado)
                    st.success(f"¡Se actualizaron {num_actualizados} libros!")
                    st.session_state.inventario_original = df_editado.copy()
                    st.rerun()

        # --- LÓGICA DE ELIMINACIÓN ---
        st.write("---") 
        if usa_selection:
            # MÉTODO MODERNO
            seleccion = st.session_state.get("editor_inventario", {}).get("selection", {}).get("rows", [])
            if seleccion:
                libro_a_eliminar = df_inventario.iloc[seleccion[0]]
                libro_id_a_eliminar = int(libro_a_eliminar['libro_id'])
                st.warning(f"Libro seleccionado: **{libro_a_eliminar['titulo']}**")
                if st.button("🗑️ Eliminar libro seleccionado", type="secondary"):
                    success, error = eliminar_libro(libro_id_a_eliminar)
                    if success: st.success(f"'{libro_a_eliminar['titulo']}' eliminado."); st.rerun()
                    else: st.error(f"No se pudo eliminar: {error}")
        else:
            # MÉTODO ANTIGUO: Con un menú desplegable
            st.warning("Usa este menú para seleccionar un libro a eliminar:")
            lista_titulos = [""] + df_inventario['titulo'].tolist()
            titulo_a_eliminar = st.selectbox("Selecciona un libro:", lista_titulos)
            if titulo_a_eliminar:
                libro_id = int(df_inventario[df_inventario['titulo'] == titulo_a_eliminar].iloc[0]['libro_id'])
                if st.button(f"🗑️ Confirmar eliminación de '{titulo_a_eliminar}'", type="secondary"):
                    success, error = eliminar_libro(libro_id)
                    if success: st.success(f"'{titulo_a_eliminar}' eliminado."); st.rerun()
                    else: st.error(f"No se pudo eliminar: {error}")

    elif menu == "Caja / Ventas":
        st.write("🛒 (Próximamente) Formulario de ventas directas.")
        
    if st.button("Cerrar Sesión"):
        st.session_state.clear(); st.rerun()

# --- LÓGICA PRINCIPAL ---
if "usuario_logeado" not in st.session_state:
    st.session_state["usuario_logeado"] = False

if not st.session_state["usuario_logeado"]:
    mostrar_login()
else:
    mostrar_app_principal()
