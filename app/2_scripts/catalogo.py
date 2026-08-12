import streamlit as st
import pandas as pd
import urllib.parse

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Catálogo | Alba Librería",
    page_icon="https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png",
    layout="wide"
)

# ====================================================
# ⚙️ CARGA SEGURA DE CONFIGURACIÓN Y ESTILOS
# ====================================================
try:
    NUMERO_WHATSAPP = st.secrets["catalogo_publico"]["whatsapp_numero"]
    URL_BASE_SUPABASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
except (KeyError, FileNotFoundError):
    st.error("🚨 Error de configuración: Faltan claves en los secretos de Streamlit (secrets.toml).")
    st.stop()

# --- CSS: Se pega tu CSS original sin cambios ---
st.markdown("""
    <style>
        /* ========================================================= */
        /* AQUÍ PEGAS EXACTAMENTE EL MISMO CSS QUE TENÍAS EN TU APP  */
        /* Lo he omitido por brevedad, pero debe ser el tuyo.       */
        /* ========================================================= */
        @import url('https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,300;0,400;0,700;1,300&family=Dancing+Script:wght@400..700&display=swap');
        html, body, [class*="css"] { font-family: 'Lato', sans-serif; }
        h1, h2, h3, .banner-titulo { font-family: 'Dancing Script', cursive !important; color: #dc4990 !important; }
        .stApp { 
            background: linear-gradient(180deg, #fcf5f7 0%, #fcdce8 100%); 
            padding-top: 220px; /* Espacio para la navbar fija de 2 filas */
        }
        .navbar-fija {
            position: fixed; top: 0; left: 0; width: 100%; z-index: 9999;
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px);
            padding: 15px 20px; border-bottom: 2px solid #e790b3;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        .libro-card {
            background: rgba(255, 255, 255, 0.9); border: 1px solid #fcdce8; border-radius: 20px; 
            padding: 15px; margin-bottom: 15px; text-align: center; box-shadow: 0 4px 15px rgba(220, 73, 144, 0.08);
            transition: transform 0.3s ease, box-shadow 0.3s ease; display: flex; flex-direction: column;
            min-height: 430px; height: 100%;
        }
        .libro-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(220, 73, 144, 0.2); }
        .libro-card img { width: 100%; border-radius: 8px; object-fit: contain; height: 200px; margin-bottom: 15px; }
        .libro-card h4 {
            font-family: 'Lato', sans-serif !important; color: #333333; font-weight: 700; font-size: 1.05rem;
            line-height: 1.3; margin-top: 10px; margin-bottom: 5px; min-height: 2.6em;
        }
        .info-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: flex-end; }
        .precio-normal { color: #e471a4; font-weight: 700; font-size: 1.2rem; }
        [data-testid="stButton"] > button {
            background-color: #fcdce8 !important; color: #333333 !important; border: 1px solid #e790b3 !important; font-weight: bold !important; border-radius: 10px !important; width: 100%;
        }
        [data-testid="stButton"] > button:hover { background-color: #e790b3 !important; color: white !important; }
        /* ... y el resto de tu CSS ... */
    </style>
""", unsafe_allow_html=True)


# ====================================================
# 📦 GESTIÓN DEL CARRITO (LÓGICA) - Sin cambios
# ====================================================
if 'carrito_publico' not in st.session_state:
    st.session_state.carrito_publico = {}

def agregar_al_carrito(libro_id, titulo, precio):
    if libro_id in st.session_state.carrito_publico:
        st.session_state.carrito_publico[libro_id]['cantidad'] += 1
    else:
        st.session_state.carrito_publico[libro_id] = {'titulo': titulo, 'precio': precio, 'cantidad': 1}
    st.toast(f"✅ ¡'{titulo}' añadido a tu bolsa!")

# ... (resto de funciones de lógica sin cambios)

# ====================================================
#  FLUJO PRINCIPAL DE LA APLICACIÓN
# ====================================================

# --- SIMULACIÓN DE CARGA DE DATOS ---
@st.cache_data
def cargar_datos_simulados():
    data = {'libro_id': range(1, 11), 'titulo': [f'Libro de Ejemplo {i}' for i in range(1, 11)], 'autor': [f'Autor {i}' for i in range(1, 11)], 'genero': ['Fantasía', 'Misterio'] * 5, 'editorial': ['Ed. Luna', 'Ed. Sol'] * 5, 'precio': [15000, 18000, 12500, 21000, 9990, 16500, 14000, 19990, 25000, 17000]}
    return pd.DataFrame(data)

# Reemplaza la línea de abajo con tus funciones reales
with st.spinner("Acomodando los libros en la vitrina..."):
    df_catalogo = cargar_datos_simulados()

# --- NAVBAR FIJA (LA LÓGICA ESTABA BIEN) ---
# ... (tu código de la navbar con los filtros y la bolsa va aquí)

# --- CUADRÍCULA PRINCIPAL DE LIBROS ---
st.markdown("<h2 style='text-align:center;'>Nuestros Libros</h2>", unsafe_allow_html=True)

columnas = st.columns(4) # O 3, como prefieras
for index, row in df_catalogo.iterrows():
    col = columnas[index % len(columnas)]
    with col:
        # TÉCNICA HÍBRIDA: Usamos st.markdown para crear la estructura que tu CSS espera,
        # pero dejamos un marcador de posición para el botón.
        
        libro_id_limpio = str(int(row.get('libro_id', 0)))
        url_imagen = f"{URL_BASE_SUPABASE}{libro_id_limpio}.jpg" if 'URL_BASE_SUPABASE' in locals() else ""
        titulo_seguro = row.get('titulo', "Sin título")
        autor_seguro = row.get('autor', 'Desconocido')
        precio = float(row.get('precio', 0.0))

        # Reconstruimos tu tarjeta HTML original
        html_card = f"""
        <div class="libro-card">
            <img src="{url_imagen}" onerror="this.onerror=null; this.src='https://via.placeholder.com/250x350?text=Sin+Portada';">
            <div class="info-container">
                <h4>{titulo_seguro}</h4>
                <p style='color: #888888; font-size: 0.9rem; margin-top: 0; margin-bottom: 15px;'>por {autor_seguro}</p>
                <div><span class='precio-normal'>${precio:,.0f}</span></div>
            </div>
        </div>
        """
        
        # Renderizamos el contenedor de la tarjeta
        st.markdown(html_card, unsafe_allow_html=True)
        
        # **LA MAGIA:** Creamos el botón de Streamlit por separado.
        # Streamlit lo colocará justo después del último st.markdown.
        # Por el flujo natural del layout, aparecerá al final de la tarjeta.
        # Tu CSS para [data-testid="stButton"] > button se encargará de darle el estilo.
        st.button(
            "✨ Lo quiero", 
            key=f"add_{libro_id_limpio}", 
            use_container_width=True, 
            on_click=agregar_al_carrito, 
            args=(libro_id_limpio, titulo_seguro, precio)
        )