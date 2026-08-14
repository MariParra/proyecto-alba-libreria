import streamlit as st
import pandas as pd
import urllib.parse
import urllib.request
import time
from cache_utils import obtener_libros_publicables

# --- PUERTA SECRETA PARA ADMINISTRADORES ---
if st.query_params.get("admin") == "limpiar":
    st.cache_data.clear()
    st.toast("🧹 Caché de la tienda limpiada con éxito al instante.")
    st.query_params.clear() # Limpia la URL para que no se siga borrando en cada clic

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Catálogo | Alba Librería", 
    page_icon="https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png", 
    layout="wide"
)

# ====================================================
# ⚙️ CARGA SEGURA DE CONFIGURACIÓN
# ====================================================
try:
    NUMERO_WHATSAPP = st.secrets["catalogo_publico"]["whatsapp_numero"]
    URL_BASE_SUPABASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
except KeyError:
    st.error("🚨 Error de configuración: Faltan claves en secrets.toml.")
    st.stop()

# --- CSS BASE Y MEJORADO ---

html_scroll_indicator = """
    <div class="scroll-indicator" onclick="window.parent.scrollBy({ top: 500, behavior: 'smooth' });" title="Bajar">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <path d="M0 0h24v24H0V0z" fill="none"/>
            <path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/>
        </svg>
    </div>
"""

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,300;0,400;0,700;1,300&family=Dancing+Script:wght@400..700&display=swap');
        
        html, body, [class*="css"] { font-family: 'Lato', sans-serif; }
        h1, h2, h3 { color: #dc4990 !important; }
        
        /* OCULTAR HEADER BLANCO NATIVO DE STREAMLIT */
        header[data-testid="stHeader"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        .block-container { padding-top: 1rem !important; }
        
        .stApp { 
            background: linear-gradient(180deg, #fcf5f7 0%, #fcdce8 100%); 
        }

        /* --- NAVBAR LEGAL (FLUYE NATURALMENTE, DESAPARECE AL BAJAR) --- */
        .navbar-legal {
            width: 100%; text-align: right; padding: 5px 15px 15px 0px;
        }
        .navbar-legal a {
            color: #b38dac; text-decoration: none; font-size: 0.9rem;
            margin-left: 25px; font-weight: 700; transition: color 0.2s ease;
        }
        .navbar-legal a:hover { color: #dc4990; text-decoration: underline; }

        /* DISEÑO EXPANDERS (BOLSA) */
        [data-testid="stExpander"] {
            background-color: #ffffff !important; border-radius: 15px !important;
            border: 2px solid #e790b3 !important; box-shadow: 0 4px 12px rgba(220, 73, 144, 0.1) !important; margin-bottom: 10px;
        }
        [data-testid="stExpander"] summary { background-color: #fcf5f7 !important; border-radius: 12px !important; }
        [data-testid="stExpander"] summary p { font-size: 1.15rem !important; font-weight: 700 !important; color: #dc4990 !important; }

        /* NUEVOS FILTROS */
        [data-testid="stMultiSelect"] { border: 2px solid #FBCFE8 !important; background-color: #ffffff !important; border-radius: 10px !important; }
        [data-testid="stMultiSelect"] .st-c5 {
            background-color: #FBCFE8 !important; color: #9D174D !important; border: 1px solid #F472B6 !important;
            border-radius: 6px !important; font-weight: bold !important;
        }
        [data-testid="stMultiSelect"] .st-c5 svg { fill: #9D174D !important; }
        [data-testid="stSelectbox"] > div[data-baseweb="select"] { border: 2px solid #FBCFE8 !important; background-color: #ffffff !important; border-radius: 10px !important; }
        
        .stTextInput { margin-bottom: 0px !important; }
        
        /* --- TARJETAS DE LIBROS ALINEADAS --- */
        .libro-card {
            background: #fdf1f1; border: 1px solid #fcdce8; border-radius: 20px; 
            padding: 15px; margin-bottom: 5px; text-align: center; box-shadow: 0 4px 15px rgba(220, 73, 144, 0.08);
            transition: transform 0.3s ease, box-shadow 0.3s ease; 
            display: flex; flex-direction: column; justify-content: space-between;
            height: 430px; 
        }
        .libro-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(220, 73, 144, 0.2); }
        .libro-card img { width: 100%; border-radius: 8px; object-fit: contain; height: 180px; margin-bottom: 10px; transition: transform 0.3s ease; }
        .libro-card:hover img { transform: scale(1.03); }
        .libro-card h4 {
            font-family: 'Lato', sans-serif !important; color: #333333; font-weight: 700; font-size: 1.05rem;
            line-height: 1.3; margin-top: 10px; margin-bottom: 5px; 
            display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
            min-height: 3.9em; 
        }
        .info-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: flex-end; }
        .precio-tachado { color: #9CA3AF; text-decoration: line-through; font-size: 0.9rem; }
        .precio-oferta { color: #dc4990; font-weight: 700; font-size: 1.3rem; }
        .precio-normal { color: #e471a4; font-weight: 700; font-size: 1.2rem; }
        
        /* BOTÓN "LO QUIERO" (Se alinea perfecto debajo del markdown fijo) */
        [data-testid="stButton"] button {
            background-color: #fcdce8 !important; color: #333333 !important; border: 1px solid #e790b3 !important; 
            font-weight: bold !important; border-radius: 10px !important; width: 100%; margin-top: -10px; margin-bottom: 20px;
        }
        [data-testid="stButton"] button:hover { background-color: #e790b3 !important; color: white !important; }

        /* Botón WhatsApp Flotante */
        .whatsapp-float {
            position: fixed; bottom: 40px; right: 40px; background-color: #25D366; color: white !important; border-radius: 50px; padding: 15px 30px;
            font-size: 18px; font-weight: 700; box-shadow: 0 4px 20px rgba(37, 211, 102, 0.4); z-index: 1000; text-decoration: none; display: flex; align-items: center; justify-content: center; transition: background-color 0.3s ease;
        }
        .whatsapp-float:hover { background-color: #128C7E; }
        @media (max-width: 768px) { .whatsapp-float { bottom: 20px; right: 20px; padding: 12px 20px; font-size: 15px; } }
        
        .header-container { display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 5px; }
        .header-icono { width: 55px; height: auto; }
        .header-container h1 { margin: 0; font-size: 3.2rem; font-family: 'Dancing Script', cursive; }
        
        /* --- BANNERS --- */
        .mega-carrusel-wrapper {
            display: grid; grid-template-columns: 1fr; gap: 15px; padding: 20px 0; width: 100%;
        }
        @media (min-width: 900px) { .mega-carrusel-wrapper { grid-template-columns: repeat(4, 1fr); } }
        
        .banner-promo {
            border-radius: 20px; padding: 20px 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            display: flex; align-items: center; justify-content: space-between;
            text-decoration: none !important; width: 100%; box-sizing: border-box;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .banner-promo:hover { transform: translateY(-5px); box-shadow: 0 12px 30px rgba(0,0,0,0.2); }
        
        .bg-cajita { background: linear-gradient(135deg, #fcdce8 0%, #e790b3 100%); }
        .bg-destacados { background: linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%); }
        .bg-ofertas { background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); }
        
        /* DEGRADADO MORADO PARA TAPA DURA */
        .bg-tapa-dura {
            background: linear-gradient(135deg, #d2b4de 0%, #884ea0 100%);
        }
        .banner-multi-img-container img {
            max-width: 100px; /* Un poco más grandes */
            transform: rotate(8deg); /* Inclinadas */
        }
        .banner-texto { flex: 1; padding-right: 5px; }
        .banner-titulo { font-family: 'Dancing Script', cursive !important; color: #ffffff !important; font-size: 1.8rem; margin-bottom: 5px; line-height: 1.1; }
        .banner-subtitulo { color: #ffffff; font-size: 0.85rem; margin-bottom: 12px; font-weight: 500; line-height: 1.2; }
        
        .banner-btn { background-color: #ffffff; padding: 6px 15px; border-radius: 50px; font-weight: 700; font-size: 0.8rem; display: inline-block; box-shadow: 0 4px 15px rgba(0,0,0,0.1); transition: transform 0.2s ease; text-decoration: none !important; }
        .banner-btn:hover { transform: scale(1.05); }
        
        .banner-img-container { flex: 0.45; text-align: right; }
        .banner-img-container img { width: 100%; max-width: 90px; height: auto; border-radius: 12px; transform: rotate(5deg); }
        .img-icono { transform: rotate(0deg) !important; max-width: 75px !important; box-shadow: none !important; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.1));}
        
        /* BANNER TAPA DURA MULTI IMG */
        .banner-multi-img-container { display: flex; gap: 5px; align-items: center; justify-content: flex-end; flex: 0.7; }
        .banner-multi-img-container img { width: 48%; max-width: 70px; border-radius: 8px; transform: rotate(0deg); box-shadow: 0 4px 10px rgba(0,0,0,0.15); }
        
        /* TÍTULOS DE SUBPÁGINAS VISIBLES */
        .titulo-seccion {
            font-family: 'Dancing Script', cursive !important;
            color: #dc4990 !important; 
            text-align: center;
            font-size: 3.5rem;
            margin-top: 10px;
        }

        /* ANIMACIÓN SCROLL - FLOTANTE FIJA */
        .scroll-indicator {
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 999;
            display: flex;
            justify-content: center;
            background-color: rgba(255, 255, 255, 0.8);
            padding: 8px;
            border-radius: 50%;
            box-shadow: 0 4px 15px rgba(220, 73, 144, 0.3);
            animation: bounce 2.5s infinite;
            cursor: pointer;
        }
        .scroll-indicator {
            display: flex; justify-content: center; width: 100%;
            margin-top: 25px; margin-bottom: 25px;
            cursor: pointer;
            animation: bounce 2.5s infinite;
        }
        .scroll-indicator svg { width: 45px; height: 45px; fill: #dc4990; }
        @keyframes bounce {
            0%, 20%, 50%, 80%, 100% { transform: translateX(-50%) translateY(0); }
            40% { transform: translateX(-50%) translateY(-10px); }
            60% { transform: translateX(-50%) translateY(-5px); }
        }
    </style>
""", unsafe_allow_html=True)

# --- NAVBAR SUPERIOR PARA PÁGINAS LEGALES ---
st.markdown("""
<div class="navbar-legal">
    <a href="?seccion=terminos" target="_self">Términos y Condiciones</a>
    <a href="?seccion=envios" target="_self">Condiciones de Envío</a>
</div>
""", unsafe_allow_html=True)

# --- ENRUTADOR DE PÁGINAS LEGALES ---
@st.cache_data(ttl=1800) # Guarda en caché por media hora (igual que los libros)
def obtener_texto_legal(archivo):
    url = f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/{archivo}"
    try:
        req = urllib.request.urlopen(url)
        return req.read().decode('utf-8')
    except:
        return "El texto aún no ha sido configurado. Visita el panel de administración."

seccion_actual = st.query_params.get("seccion", "inicio")

if seccion_actual == "terminos":
    st.markdown("<h2 class='titulo-seccion'>Términos y Condiciones</h2>", unsafe_allow_html=True)
    st.markdown("---")
    # Llama a la nueva función
    st.markdown(obtener_texto_legal("terminos.txt"))
    st.html("<div style='text-align:center; margin-top: 50px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    st.stop()

elif seccion_actual == "envios":
    st.markdown("<h2 class='titulo-seccion'>Condiciones de Envío</h2>", unsafe_allow_html=True)
    st.markdown("---")
    # Llama a la nueva función
    st.markdown(obtener_texto_legal("envios.txt"))
    st.html("<div style='text-align:center; margin-top: 50px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    st.stop()


# --- INICIALIZAR CARRITO ---
if 'carrito_publico' not in st.session_state:
    st.session_state.carrito_publico = {}

def agregar_al_carrito(libro_id, titulo, precio):
    if libro_id in st.session_state.carrito_publico:
        st.session_state.carrito_publico[libro_id]['cantidad'] += 1
    else:
        st.session_state.carrito_publico[libro_id] = {'titulo': titulo, 'precio': precio, 'cantidad': 1}
    st.toast(f"✅ ¡Añadido a tu bolsa: '{titulo}'!")

def quitar_del_carrito(libro_id):
    if libro_id in st.session_state.carrito_publico:
        del st.session_state.carrito_publico[libro_id]

# --- CABECERA PRINCIPAL CON ICONO ---
st.markdown("""
<div class="header-container">
    <img src="https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png" class="header-icono" alt="Icono Librería">
    <h1>Alba Librería</h1>
</div>
<p style='text-align: center; color: #dc4990; font-size: 1.2rem; margin-top: 0px; font-weight: 600;'>Explora nuestro catálogo y haz tu pedido al instante.</p>
""", unsafe_allow_html=True)

# =====================================================================
# CARGA DE DATOS
# =====================================================================
with st.spinner("Acomodando los libros en la vitrina..."):
    df_catalogo = obtener_libros_publicables()

if df_catalogo.empty:
    st.warning("No hay libros disponibles por el momento. ¡Vuelve pronto!")
    st.stop()
    
generos_disp = sorted(df_catalogo['genero'].dropna().unique()) if 'genero' in df_catalogo.columns else []
autores_disp = sorted(df_catalogo['autor'].dropna().unique()) if 'autor' in df_catalogo.columns else []
editoriales_disp = sorted(df_catalogo['editorial'].dropna().unique()) if 'editorial' in df_catalogo.columns else []

st.write("---")

# =====================================================================
# FILTROS Y CARRITO (En el flujo normal de la página)
# =====================================================================
col_filtros, col_bolsa = st.columns([3,1])

with col_filtros:
    cf1, cf2, cf3 = st.columns(3)
    with cf1:
        filtro_generos = st.multiselect("📖 Géneros:", generos_disp, placeholder="Géneros...")
    with cf2:
        filtro_autores = st.multiselect("✍️ Autores:", autores_disp, placeholder="Autores...")
    with cf3:
        filtro_editoriales = st.multiselect("🏢 Editorial:", editoriales_disp, placeholder="Editoriales...") if editoriales_disp else []

with col_bolsa:
    total_articulos = sum(item['cantidad'] for item in st.session_state.get('carrito_publico', {}).values())
    titulo_bolsa = f"🛍️ Mi Bolsa ({total_articulos})" if total_articulos > 0 else "🛍️ Mi Bolsa"
    
    with st.expander(titulo_bolsa, expanded=False):
        if not st.session_state.get('carrito_publico'):
            st.write("Tu bolsa está vacía.")
        else:
            total_carrito = 0
            mensaje_wa = "¡Hola Alba Librería! Mi nombre es [ESCRIBE TU NOMBRE AQUÍ] y me encantaría pedir estos libros:\n\n"
            for l_id, item in list(st.session_state.carrito_publico.items()):
                subtotal = item['precio'] * item['cantidad']
                total_carrito += subtotal
                mensaje_wa += f"📖 {item['cantidad']}x {item['titulo']} - ${subtotal:,.0f}\n"
                
                col_t, col_b = st.columns([3,1])
                with col_t: st.write(f"**{item['cantidad']}x** {item['titulo']}")
                with col_b: st.button("❌", key=f"del_nav_{l_id}", help="Quitar", on_click=quitar_del_carrito, args=(l_id,))
                        
            st.markdown("---")
            st.markdown(f"**Total:** ${total_carrito:,.0f}")
            mensaje_wa += f"\n*Total Estimado a pagar: ${total_carrito:,.0f}*\n\n⚠️ _Nota: Entiendo que deben confirmarme el stock disponible y el valor final antes de realizar el pago._\n\n¡Quedo atenta, muchas gracias!"
            
            st.session_state.url_wa_flotante = f"https://wa.me/{NUMERO_WHATSAPP}?text={urllib.parse.quote(mensaje_wa)}"
            st.markdown(f'<a href="{st.session_state.url_wa_flotante}" target="_blank" style="display: block; text-align: center; background-color: #25D366; color: white; padding: 10px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-bottom:10px;">📲 ENVIAR PEDIDO</a>', unsafe_allow_html=True)

# --- BARRA DE BÚSQUEDA Y ORDENAMIENTO ---
col_busqueda, col_orden = st.columns([3,1])
with col_busqueda:
    busqueda_texto = st.text_input("🔍 Buscar:", placeholder="Ej. Fantasía, amor, o el nombre de tu autor favorito...", label_visibility="collapsed")
with col_orden:
    orden_seleccionado = st.selectbox(
        "Ordenar", 
        ["⭐ Relevancia / Destacados", "🔤 Título: A - Z", "🔤 Título: Z - A", "💸 Precio: Menor a Mayor", "💰 Precio: Mayor a Menor", "✍️ Autor: A - Z", "🏢 Editorial: A - Z"],
        label_visibility="collapsed"
    )


# =====================================================================
# 🎪 MEGA CARRUSEL DE BANNERS Y SECCIONES
# =====================================================================

if seccion_actual == "inicio":
    LINK_FORMULARIO_SUSCRIPCION = "https://docs.google.com/forms/d/e/1FAIpQLSc8FpBSwizmcinCdemJo31APqa24fU_Xw837mHJU2VJW2xNNg/viewform"
    URL_ICONO = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png"
    
    version_banner = int(time.time() / 3600) 
    URL_FOTO_CAJITA = f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/promo_cajita.jpg?v={version_banner}"
    URL_TAPA_DURA_1 = f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/promo_tapa_dura_1.jpg?v={version_banner}" 
    URL_TAPA_DURA_2 = f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/promo_tapa_dura_2.jpg?v={version_banner}"

    html_mega_carrusel = f"""
    <div class="mega-carrusel-wrapper">
        <a href="?seccion=ofertas" target="_self" class="banner-promo bg-ofertas">
            <div class="banner-texto">
                <h2 class="banner-titulo">Ofertas 🔥</h2>
                <p class="banner-subtitulo">Descuentos mágicos en nuestro catálogo.</p>
                <span class="banner-btn" style="color: #e88c71 !important;">💸 VER OFERTAS</span>
            </div>
            <div class="banner-img-container"><img src="{URL_ICONO}" class="img-icono"></div>
        </a>

        <a href="{LINK_FORMULARIO_SUSCRIPCION}" target="_blank" class="banner-promo bg-cajita">
            <div class="banner-texto">
                <h2 class="banner-titulo">Cajita Literaria ✨</h2>
                <p class="banner-subtitulo">Libro sorpresa, regalitos y magia mensual.</p>
                <span class="banner-btn" style="color: #dc4990 !important;">📝 SUSCRIBIRME</span>
            </div>
            <div class="banner-img-container"><img src="{URL_FOTO_CAJITA}"></div>
        </a>

        <a href="?seccion=destacados" target="_self" class="banner-promo bg-destacados">
            <div class="banner-texto">
                <h2 class="banner-titulo">Destacados ⭐</h2>
                <p class="banner-subtitulo">Las mejores historias seleccionadas para ti.</p>
                <span class="banner-btn" style="color: #9283e0 !important;">📚 VER LIBROS</span>
            </div>
            <div class="banner-img-container"><img src="{URL_ICONO}" class="img-icono"></div>
        </a>
        
        <a href="?seccion=tapa-dura" target="_self" class="banner-promo bg-tapa-dura">
            <div class="banner-texto">
                <h2 class="banner-titulo">Ediciones Únicas</h2>
                <p class="banner-subtitulo">Libros en Tapa Dura y formatos especiales.</p>
                <span class="banner-btn" style="color: #8e44ad !important;">💎 VER JOYITAS</span>
            </div>
            <div class="banner-multi-img-container">
                <img src="{URL_TAPA_DURA_1}">
                <img src="{URL_TAPA_DURA_2}">
            </div>
        </a>
    </div>
    """
    st.html(html_mega_carrusel)
    
    # FLECHA DE SCROLL
    st.markdown(html_scroll_indicator, unsafe_allow_html=True)
    
    st.write("---")
    df_base = df_catalogo.copy()

elif seccion_actual == "destacados":
    st.markdown("<h2 class='titulo-seccion'>⭐ Libros Destacados</h2>", unsafe_allow_html=True)
    st.html("<div style='text-align:center; margin-bottom: 20px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    st.markdown(html_scroll_indicator, unsafe_allow_html=True)
    
    if 'destacado' in df_catalogo.columns:
        df_base = df_catalogo[df_catalogo['destacado'] == True]
    else:
        df_base = df_catalogo.head(0) 

elif seccion_actual == "ofertas":
    st.markdown("<h2 class='titulo-seccion'>🔥 Libros en Oferta</h2>", unsafe_allow_html=True)
    st.html("<div style='text-align:center; margin-bottom: 20px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    st.markdown(html_scroll_indicator, unsafe_allow_html=True)
    
    if 'precio_original' in df_catalogo.columns and 'precio' in df_catalogo.columns:
        df_base = df_catalogo[df_catalogo['precio'] < df_catalogo['precio_original']]
    else:
        df_base = df_catalogo.head(0)

elif seccion_actual == "tapa-dura":
    st.markdown("<h2 class='titulo-seccion'>💎 Ediciones en Tapa Dura</h2>", unsafe_allow_html=True)
    st.html("<div style='text-align:center; margin-bottom: 20px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    st.markdown(html_scroll_indicator, unsafe_allow_html=True)
    
    if 'encuadernacion' in df_catalogo.columns:
        df_base = df_catalogo[df_catalogo['encuadernacion'].str.upper() == 'TAPA DURA']
    else:
        df_base = df_catalogo.head(0)

# =====================================================================
# --- APLICAR FILTROS Y BÚSQUEDA ---
# =====================================================================
df_filtrado = df_base.copy()

if busqueda_texto:
    texto_limpio = busqueda_texto.strip().lower()
    df_filtrado = df_filtrado[
        df_filtrado['titulo'].str.lower().str.contains(texto_limpio, na=False) | 
        df_filtrado['autor'].str.lower().str.contains(texto_limpio, na=False)
    ]

try:
    if filtro_generos: df_filtrado = df_filtrado[df_filtrado['genero'].isin(filtro_generos)]
    if filtro_autores: df_filtrado = df_filtrado[df_filtrado['autor'].isin(filtro_autores)]
    if filtro_editoriales: df_filtrado = df_filtrado[df_filtrado['editorial'].isin(filtro_editoriales)]
except NameError:
    pass 

# =====================================================================
# --- APLICAR ORDENAMIENTO DE LIBROS ---
# =====================================================================
if not df_filtrado.empty:
    if orden_seleccionado == "🔤 Título: A - Z":
        df_filtrado = df_filtrado.sort_values(by="titulo", ascending=True)
    elif orden_seleccionado == "🔤 Título: Z - A":
        df_filtrado = df_filtrado.sort_values(by="titulo", ascending=False)
    elif orden_seleccionado == "💸 Precio: Menor a Mayor":
        df_filtrado = df_filtrado.sort_values(by="precio", ascending=True)
    elif orden_seleccionado == "💰 Precio: Mayor a Menor":
        df_filtrado = df_filtrado.sort_values(by="precio", ascending=False)
    elif orden_seleccionado == "✍️ Autor: A - Z":
        if 'autor' in df_filtrado.columns:
            df_filtrado = df_filtrado.sort_values(by="autor", ascending=True)
    elif orden_seleccionado == "🏢 Editorial: A - Z":
        if 'editorial' in df_filtrado.columns:
            df_filtrado = df_filtrado.sort_values(by="editorial", ascending=True)
    else:
        if 'destacado' in df_filtrado.columns:
            df_filtrado = df_filtrado.sort_values(by=["destacado", "titulo"], ascending=[False, True])
        else:
            df_filtrado = df_filtrado.sort_values(by="titulo", ascending=True)

if df_filtrado.empty:
    st.info("No encontramos libros con esos filtros. ¡Intenta con otra búsqueda! 🪄")
else:
    st.markdown(f"<p style='color: #dc4990; font-weight: 600; text-align: center; font-size: 1.2rem;'>Mostrando {len(df_filtrado)} libros mágicos ✨</p>", unsafe_allow_html=True)

    # --- CUADRÍCULA PRINCIPAL DE LIBROS ---
    columnas = st.columns(3)
    for index, row in df_filtrado.reset_index(drop=True).iterrows():
        col = columnas[index % 3]
        with col:
            libro_id_limpio = str(int(float(row.get('libro_id', 0))))
            
            timestamp_str = row.get('portada_last_updated', '') 
            version_cache = ""
            if timestamp_str and not pd.isna(timestamp_str):
                try:
                    dt_obj = pd.to_datetime(timestamp_str)
                    version_cache = f"?v={int(dt_obj.timestamp())}"
                except:
                    pass

            url_imagen = f"{URL_BASE_SUPABASE}{libro_id_limpio}.jpg{version_cache}"
            
            titulo_seguro = row.get('titulo', "Sin título")
            autor_seguro = row.get('autor', 'Desconocido')
            editorial_segura = row.get('editorial', 'No especificada')
            precio = float(row.get('precio', 0.0))
            precio_orig = float(row.get('precio_original', precio))

            html_card = f"""
            <div class="libro-card">
                <img src="{url_imagen}" onerror="this.onerror=null; this.src='https://via.placeholder.com/250x350?text=Sin+Portada';">
                <div class="info-container">
                    <h4>{titulo_seguro}</h4>
                    <p style='color: #888888; font-size: 0.9rem; margin-top: 0; margin-bottom: 2px;'>por {autor_seguro}</p>
                    <p style='color: #b38dac; font-size: 0.85rem; font-weight: 600; margin-top: 0; margin-bottom: 15px;'>Editorial: {editorial_segura}</p>
            """
            
            if not pd.isna(row.get('precio_original')) and precio < precio_orig:
                html_card += f"<div><span class='precio-tachado'>${precio_orig:,.0f}</span><br><span class='precio-oferta'>${precio:,.0f}</span></div>"
            else:
                html_card += f"<div><span class='precio-normal'>${precio:,.0f}</span></div>"
                
            html_card += "</div></div>" 
            
            st.markdown(html_card, unsafe_allow_html=True)
            st.button("✨ Lo quiero", key=f"add_{libro_id_limpio}", use_container_width=True, on_click=agregar_al_carrito, args=(libro_id_limpio, titulo_seguro, precio))

# --- BOTÓN FLOTANTE DE WHATSAPP ---
if st.session_state.get('carrito_publico'):
    url_flotante = st.session_state.get('url_wa_flotante', '#')
    btn_html = f"""
    <a href="{url_flotante}" target="_blank" class="whatsapp-float">
        💬 ENVIAR PEDIDO
    </a>
    """
    st.markdown(btn_html, unsafe_allow_html=True)