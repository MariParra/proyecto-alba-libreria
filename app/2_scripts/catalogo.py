import streamlit as st
import pandas as pd
import urllib.parse
# from utilidades import get_db_connection
# from cache_utils import cargar_catalogo_publico, filtrar_solo_con_imagen

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

def load_css():
    """Carga todo el CSS personalizado en un solo lugar."""
    st.markdown("""
    <style>
        /* Tu CSS completo va aquí. Lo he omitido por brevedad, pero pégalo tal cual lo tenías. */
        @import url('https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,300;0,400;0,700;1,300&family=Dancing+Script:wght@400..700&display=swap');
        html, body, [class*="css"] { font-family: 'Lato', sans-serif; }
        h1, h2, h3, .banner-titulo { font-family: 'Dancing Script', cursive !important; color: #dc4990 !important; }
        .stApp { 
            background: linear-gradient(180deg, #fcf5f7 0%, #fcdce8 100%); 
            padding-top: 220px; /* Aumentado para dar más espacio a los filtros y buscador */
        }
        .navbar-fija {
            position: fixed; top: 0; left: 0; width: 100%; z-index: 9999;
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px);
            padding: 15px 20px; border-bottom: 2px solid #e790b3;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        .libro-card-container {
            background: rgba(255, 255, 255, 0.9); border: 1px solid #fcdce8; border-radius: 20px; 
            padding: 15px; margin-bottom: 15px; text-align: center; box-shadow: 0 4px 15px rgba(220, 73, 144, 0.08);
            transition: transform 0.3s ease, box-shadow 0.3s ease; display: flex; flex-direction: column;
            height: 100%; /* Asegura que todos los contenedores tengan la misma altura */
        }
        .libro-card-container:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(220, 73, 144, 0.2); }
        .libro-card-container img { width: 100%; border-radius: 8px; object-fit: contain; height: 200px; margin-bottom: 15px; }
        .libro-card-container h4 {
            font-family: 'Lato', sans-serif !important; color: #333333; font-weight: 700; font-size: 1.05rem;
            line-height: 1.3; margin: 10px 0 5px 0; min-height: 2.6em; flex-grow: 1;
        }
        /* Ajuste para que el botón "Lo Quiero" use el estilo del CSS */
        .stButton>button {
            background-color: #fcdce8 !important; color: #333333 !important; border: 1px solid #e790b3 !important;
            font-weight: bold !important; border-radius: 10px !important; width: 100%;
        }
        .stButton>button:hover { background-color: #e790b3 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

load_css()

# ====================================================
# 📦 GESTIÓN DEL CARRITO (LÓGICA)
# ====================================================

if 'carrito_publico' not in st.session_state:
    st.session_state.carrito_publico = {}

def agregar_al_carrito(libro_id, titulo, precio):
    """Añade un libro al carrito o incrementa su cantidad."""
    if libro_id in st.session_state.carrito_publico:
        st.session_state.carrito_publico[libro_id]['cantidad'] += 1
    else:
        st.session_state.carrito_publico[libro_id] = {'titulo': titulo, 'precio': precio, 'cantidad': 1}
    st.toast(f"✅ ¡'{titulo}' añadido a tu bolsa!")

def quitar_del_carrito(libro_id):
    """Quita un libro del carrito y refresca la app."""
    if libro_id in st.session_state.carrito_publico:
        del st.session_state.carrito_publico[libro_id]
        st.rerun()

def get_info_carrito():
    """Calcula totales y genera el mensaje y URL de WhatsApp."""
    carrito = st.session_state.get('carrito_publico', {})
    if not carrito:
        return 0, 0, "#"

    total_articulos = sum(item['cantidad'] for item in carrito.values())
    total_precio = sum(item['precio'] * item['cantidad'] for item in carrito.values())
    
    mensaje_wa = "¡Hola Alba Librería! 💖 Mi nombre es [TU NOMBRE] y me encantaría pedir estos libros:\n\n"
    for item in carrito.values():
        subtotal = item['precio'] * item['cantidad']
        mensaje_wa += f"📖 {item['cantidad']}x {item['titulo']} - ${subtotal:,.0f}\n"
    
    mensaje_wa += f"\n*Total Estimado: ${total_precio:,.0f}*\n\n"
    mensaje_wa += "⚠️ _Nota: Entiendo que deben confirmarme el stock y el valor final._\n\n¡Quedo atenta, gracias!"
    
    url_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP}?text={urllib.parse.quote(mensaje_wa)}"
    
    return total_articulos, total_precio, url_whatsapp

# ====================================================
# 🖼️ COMPONENTES DE LA INTERFAZ (UI)
# ====================================================

def mostrar_header_principal():
    st.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <img src="https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png" style="width: 55px; height: auto;">
        <h1>Alba Librería</h1>
        <p style='color: #dc4990; font-size: 1.2rem; font-weight: 600;'>Explora nuestro catálogo y haz tu pedido al instante.</p>
    </div>
    """, unsafe_allow_html=True)

def mostrar_bolsa_compras():
    total_articulos, total_precio, url_whatsapp = get_info_carrito()
    titulo_bolsa = f"🛍️ Mi Bolsa ({total_articulos})" if total_articulos > 0 else "🛍️ Mi Bolsa"
    
    with st.expander(titulo_bolsa):
        if not st.session_state.get('carrito_publico'):
            st.info("Tu bolsa está vacía. ¡Añade libros mágicos!")
        else:
            for l_id, item in list(st.session_state.carrito_publico.items()):
                col_t, col_b = st.columns([4, 1])
                col_t.write(f"**{item['cantidad']}x** {item['titulo']}")
                col_b.button("❌", key=f"del_nav_{l_id}", help="Quitar", on_click=quitar_del_carrito, args=(l_id,))
            
            st.markdown("---")
            st.markdown(f"<h5 style='text-align: right;'>Total: ${total_precio:,.0f}</h5>", unsafe_allow_html=True)
            st.link_button("📲 ENVIAR PEDIDO", url_whatsapp, use_container_width=True)

def mostrar_tarjeta_libro(col, libro):
    with col:
        # Usamos un contenedor para aplicar la clase CSS y controlar el layout interno
        with st.container():
            st.markdown('<div class="libro-card-container">', unsafe_allow_html=True)
            
            libro_id = str(int(libro.get('libro_id', 0)))
            titulo = libro.get('titulo', "Sin título")
            precio = float(libro.get('precio', 0.0))
            
            st.markdown(f'<img src="{URL_BASE_SUPABASE}{libro_id}.jpg" onerror="this.onerror=null; this.src=\'https://via.placeholder.com/250x350?text=Sin+Portada\';">', unsafe_allow_html=True)
            st.markdown(f"<h4>{titulo}</h4>", unsafe_allow_html=True)
            st.markdown(f"<p style='color: #888; font-size: 0.9rem;'>por {libro.get('autor', 'Desconocido')}</p>", unsafe_allow_html=True)
            st.markdown(f"<div><span class='precio-normal'>${precio:,.0f}</span></div>", unsafe_allow_html=True)
            
            # El botón se crea fuera del markdown para que sea un widget real de Streamlit
            st.button("✨ Lo quiero", key=f"add_{libro_id}", on_click=agregar_al_carrito, args=(libro_id, titulo, precio), use_container_width=True)
            
            st.markdown('</div>', unsafe_allow_html=True)

# ====================================================
#  FLUJO PRINCIPAL DE LA APLICACIÓN
# ====================================================

# --- SIMULACIÓN DE CARGA DE DATOS ---
@st.cache_data
def cargar_datos_simulados():
    data = {'libro_id': range(1, 11), 'titulo': [f'Libro de Ejemplo {i}' for i in range(1, 11)], 'autor': [f'Autor {i}' for i in range(1, 11)], 'genero': ['Fantasía', 'Misterio'] * 5, 'editorial': ['Ed. Luna', 'Ed. Sol'] * 5, 'precio': [15000, 18000, 12500, 21000, 9990, 16500, 14000, 19990, 25000, 17000]}
    return pd.DataFrame(data)

# Reemplaza la línea de abajo con tus funciones reales `cargar_catalogo_publico` y `filtrar_solo_con_imagen`
with st.spinner("Acomodando los libros en la vitrina..."):
    df_catalogo = cargar_datos_simulados()

if df_catalogo.empty:
    st.warning("No hay libros disponibles por el momento.")
    st.stop()

# --- NAVBAR FIJA CON FILTROS Y BUSCADOR ---
st.markdown('<div class="navbar-fija">', unsafe_allow_html=True)
col_filtros, col_bolsa = st.columns([3.5, 1])

with col_filtros:
    c1, c2, c3 = st.columns(3)
    filtro_generos = c1.multiselect("📖 Géneros:", sorted(df_catalogo['genero'].unique()))
    filtro_autores = c2.multiselect("✍️ Autores:", sorted(df_catalogo['autor'].unique()))
    filtro_editoriales = c3.multiselect("🏢 Editorial:", sorted(df_catalogo['editorial'].unique()))
    busqueda_texto = st.text_input("🔍 Buscar por título o autor:", placeholder="Ej. El nombre de tu libro o autor favorito...")

with col_bolsa:
    mostrar_bolsa_compras()
st.markdown('</div>', unsafe_allow_html=True)

# --- APLICAR FILTROS Y BÚSQUEDA ---
df_filtrado = df_catalogo.copy()
if busqueda_texto:
    df_filtrado = df_filtrado[df_filtrado['titulo'].str.contains(busqueda_texto, case=False) | df_filtrado['autor'].str.contains(busqueda_texto, case=False)]
if filtro_generos: df_filtrado = df_filtrado[df_filtrado['genero'].isin(filtro_generos)]
if filtro_autores: df_filtrado = df_filtrado[df_filtrado['autor'].isin(filtro_autores)]
if filtro_editoriales: df_filtrado = df_filtrado[df_filtrado['editorial'].isin(filtro_editoriales)]

# --- HEADER Y CUADRÍCULA DE LIBROS ---
mostrar_header_principal()
st.markdown(f"<p style='color: #dc4990; font-weight: 600; text-align: center; font-size: 1.2rem;'>Mostrando {len(df_filtrado)} de {len(df_catalogo)} libros mágicos ✨</p>", unsafe_allow_html=True)

columnas = st.columns(4) # Puedes ajustar el número de columnas (ej. 3 o 4)
for index, libro in df_filtrado.iterrows():
    col = columnas[index % len(columnas)]
    mostrar_tarjeta_libro(col, libro)
