import streamlit as st
import pandas as pd
import urllib.parse
import requests
import concurrent.futures
from utilidades import get_db_connection

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Catálogo | Alba Librería", page_icon="📖", layout="wide")

# ====================================================
# ⚙️ CARGA SEGURA DE CONFIGURACIÓN DESDE st.secrets
# ====================================================
try:
    NUMERO_WHATSAPP = st.secrets["catalogo_publico"]["whatsapp_numero"]
    URL_BASE_SUPABASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
except KeyError:
    st.error("🚨 Error de configuración: Faltan claves en secrets.toml.")
    st.stop()

# --- CSS CON LA PALETA OFICIAL, NUEVAS FUENTES Y NAVBAR FIJA ---
st.markdown("""
    <style>
        /* 1. IMPORTAR DANCING SCRIPT */
        @import url('https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,300;0,400;0,700;1,300&family=Dancing+Script:wght@400..700&display=swap');
        
        html, body, [class*="css"] { 
            font-family: 'Lato', sans-serif; 
        }
        
        /* Títulos principales con la fuente Dancing Script */
        h1, h2, h3, .banner-titulo { 
            font-family: 'Dancing Script', cursive !important; 
            color: #dc4990 !important;
        }
        
        /* Fondo general */
        .stApp { 
            background: linear-gradient(180deg, #fcf5f7 0%, #fcdce8 100%); 
        }

        /* 🎨 DISEÑO DE LOS EXPANDERS / BOLSAS */
        [data-testid="stExpander"] {
            background-color: #ffffff !important;
            border-radius: 15px !important;
            border: 2px solid #e790b3 !important; 
            box-shadow: 0 4px 12px rgba(220, 73, 144, 0.1) !important;
            margin-bottom: 10px;
        }
        [data-testid="stExpander"] summary {
            background-color: #fcf5f7 !important; 
            border-radius: 12px !important;
        }
        [data-testid="stExpander"] summary p {
            font-size: 1.15rem !important;
            font-weight: 700 !important;
            color: #dc4990 !important; 
        }

        /* 📌 NAVBAR SUPERIOR FIJA (Reemplaza a Sidebar) */
        [data-testid="stSidebar"] {
            display: none !important; /* Ocultamos el sidebar original */
        }
        .navbar-fija {
            position: sticky;
            top: 2.8rem; /* Se ancla justo debajo de la cabecera de Streamlit */
            z-index: 999;
            background: rgba(252, 245, 247, 0.95);
            backdrop-filter: blur(10px);
            padding: 10px 0;
            border-bottom: 2px solid #fcdce8;
            margin-bottom: 20px;
        }

        /* 🎠 ESTILOS PARA EL CARRUSEL */
        .carrusel-container {
            display: flex; overflow-x: auto; scroll-behavior: smooth;
            gap: 15px; padding: 10px 5px 20px 5px;
            scrollbar-width: thin; scrollbar-color: #e790b3 #fcf5f7;
        }
        .carrusel-container::-webkit-scrollbar { height: 8px; }
        .carrusel-container::-webkit-scrollbar-track { background: #fcf5f7; border-radius: 10px; }
        .carrusel-container::-webkit-scrollbar-thumb { background-color: #e790b3; border-radius: 10px; }
        .carrusel-item {
            flex: 0 0 200px;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid #fcdce8;
            border-radius: 15px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(220, 73, 144, 0.08);
            transition: transform 0.2s ease;
        }
        .carrusel-item:hover { transform: translateY(-4px); }
        .carrusel-item img { width: 100%; height: 180px; object-fit: contain; border-radius: 8px; margin-bottom: 10px; }

        /* 🎨 TARJETAS DE LIBROS UNIFORMES */
        .libro-card {
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(10px);
            border: 1px solid #fcdce8;
            border-radius: 20px; 
            padding: 20px;
            margin-bottom: 15px; 
            text-align: center; 
            box-shadow: 0 8px 25px rgba(220, 73, 144, 0.08);
            transition: transform 0.3s ease, box-shadow 0.3s ease; 
            /* 2. FORZAMOS EL MISMO ALTO PARA TODAS */
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 480px;
            height: 100%;
        }
        .libro-card:hover { 
            transform: translateY(-8px) scale(1.02); 
            box-shadow: 0 15px 30px rgba(220, 73, 144, 0.2);
        }
        .libro-card img {
            width: 100%; border-radius: 12px; object-fit: contain;
            height: 220px; margin-bottom: 15px;
            transition: transform 0.3s ease;
        }
        .libro-card:hover img { transform: scale(1.03); }
        
        .libro-card h4 {
            font-family: 'Lato', sans-serif !important;
            color: #333333; font-weight: 700; font-size: 1.1rem;
            line-height: 1.3; margin-bottom: 5px; margin-top: 0;
            /* Limita el título a 2 líneas exactas para evitar desniveles */
            display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
            overflow: hidden; text-overflow: ellipsis; height: 2.6em;
        }
        .info-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: flex-end; }

        .precio-tachado { color: #9CA3AF; text-decoration: line-through; font-size: 1rem; }
        .precio-oferta { color: #dc4990; font-weight: 700; font-size: 1.4rem; }
        .precio-normal { color: #e471a4; font-weight: 700; font-size: 1.3rem; }
        
        /* 3. BOTÓN "LO QUIERO" CON NUEVO COLOR */
        [data-testid="stButton"] button {
            background-color: #fcdce8 !important;
            color: #333333 !important;
            border: 1px solid #e790b3 !important;
            font-weight: bold !important;
            border-radius: 10px !important;
        }
        [data-testid="stButton"] button:hover {
            background-color: #e790b3 !important;
            color: white !important;
        }

        /* Botón WhatsApp Flotante */
        .whatsapp-float {
            position: fixed; bottom: 40px; right: 40px; background-color: #25D366;
            color: white !important; border-radius: 50px; padding: 15px 30px;
            font-size: 18px; font-weight: 700; box-shadow: 0 4px 20px rgba(37, 211, 102, 0.4);
            z-index: 1000; text-decoration: none; display: flex; align-items: center; justify-content: center;
        }
        .whatsapp-float:hover { background-color: #128C7E; }
        @media (max-width: 768px) { .whatsapp-float { bottom: 20px; right: 20px; padding: 12px 20px; font-size: 15px; } }
        
        /* Título con ícono */
        .header-container { display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 5px; }
        .header-icono { width: 55px; height: auto; }
        .header-container h1 { margin: 0; font-size: 3.2rem; }
    </style>
""", unsafe_allow_html=True)

# --- LÓGICA DE DATOS Y RADAR ---
@st.cache_data(ttl=120)
def cargar_catalogo_publico():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, editorial, precio, precio_original, genero, stock").gt("stock", 0).gt("precio", 0).order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, precio_original, genero, stock").gt("stock", 0).gt("precio", 0).order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        
    if not df.empty:
        df['precio'] = pd.to_numeric(df['precio'], errors='coerce')
        if 'precio_original' in df.columns:
            df['precio_original'] = pd.to_numeric(df['precio_original'], errors='coerce')
        df.dropna(subset=['libro_id', 'titulo', 'precio'], inplace=True)
        df = df[df['precio'] > 0] 
    return df

@st.cache_data(ttl=300)
def filtrar_solo_con_imagen(df):
    def check_url(row):
        try:
            libro_id = str(int(float(row.get('libro_id', 0))))
            url = f"{URL_BASE_SUPABASE}{libro_id}.jpg"
            return requests.head(url, timeout=2).status_code == 200
        except:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        resultados = list(executor.map(check_url, df.to_dict('records')))
    return df[resultados]

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

# --- 6. CABECERA PRINCIPAL CON ICONO PERSONALIZADO ---
st.markdown("""
<div class="header-container">
    <img src="https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png" class="header-icono" alt="Icono Librería">
    <h1>Alba Librería</h1>
</div>
""", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #e790b3; font-size: 1.1rem; margin-top: 5px; font-weight: 600;'>Explora nuestro catálogo y haz tu pedido al instante.</p>", unsafe_allow_html=True)

df_bruto = cargar_catalogo_publico()
if df_bruto.empty:
    st.info("Estamos actualizando las estanterías. ¡Vuelve pronto!")
    st.stop()

with st.spinner("Acomodando los libros en la vitrina..."):
    df_catalogo = filtrar_solo_con_imagen(df_bruto)

if df_catalogo.empty:
    st.warning("No hay libros con portadas disponibles por el momento.")
    st.stop()

# =====================================================================
# 5. NAVBAR FIJA SUPERIOR (Reemplaza a Sidebar)
# =====================================================================
st.markdown('<div class="navbar-fija">', unsafe_allow_html=True)
# Aquí corregimos el error anterior: st.columns(2)
col_nav1, col_nav2 = st.columns(2)

with col_nav1:
    busqueda_texto = st.text_input("🔍 Buscar:", placeholder="Ej. Fantasía, amor...", label_visibility="collapsed")
    
with col_nav2:
    total_articulos = sum(item['cantidad'] for item in st.session_state.get('carrito_publico', {}).values())
    titulo_bolsa = f"🛍️ Mi Bolsa ({total_articulos}) | 🔎 Filtros" if total_articulos > 0 else "🛍️ Mi Bolsa | 🔎 Filtros"
    
    with st.expander(titulo_bolsa, expanded=False):
        # Sección Bolsa
        st.markdown("#### 🛍️ Mi Bolsa")
        if not st.session_state.get('carrito_publico'):
            st.write("Aún no has seleccionado libros.")
        else:
            total_carrito = 0
            mensaje_wa = "¡Hola Alba Librería! 💖 Mi nombre es [ESCRIBE TU NOMBRE AQUÍ] y me encantaría pedir estos libros:\n\n"
            
            for l_id, item in list(st.session_state.carrito_publico.items()):
                subtotal = item['precio'] * item['cantidad']
                total_carrito += subtotal
                mensaje_wa += f"📖 {item['cantidad']}x {item['titulo']} - ${subtotal:,.0f}\n"
                
                col_t, col_b = st.columns([3, 1])
                with col_t:
                    st.write(f"**{item['cantidad']}x** {item['titulo']}")
                with col_b:
                    if st.button("❌", key=f"del_{l_id}", help="Quitar"):
                        quitar_del_carrito(l_id)
                        st.rerun()
                        
            st.markdown(f"**Total:** ${total_carrito:,.0f}")
            mensaje_wa += f"\n*Total Estimado a pagar: ${total_carrito:,.0f}*\n\n"
            mensaje_wa += "⚠️ _Nota: Entiendo que deben confirmarme el stock disponible y el valor final antes de realizar el pago._\n\n"
            mensaje_wa += "¡Quedo atenta, muchas gracias!"
            
            mensaje_wa_encoded = urllib.parse.quote(mensaje_wa)
            st.session_state.url_wa_flotante = f"https://wa.me/{NUMERO_WHATSAPP}?text={mensaje_wa_encoded}"
            st.link_button("📲 ENVIAR PEDIDO", st.session_state.url_wa_flotante, type="primary", use_container_width=True)

        st.markdown("---")
        
        # Sección Filtros
        st.markdown("#### 🔎 Filtros")
        generos_disp = sorted(df_catalogo['genero'].dropna().unique())
        autores_disp = sorted(df_catalogo['autor'].dropna().unique())
        
        filtro_generos = st.multiselect("📖 Géneros:", generos_disp)
        filtro_autores = st.multiselect("✍️ Autores:", autores_disp)
        
        filtro_editoriales = []
        if 'editorial' in df_catalogo.columns:
            editoriales_disp = sorted(df_catalogo['editorial'].dropna().unique())
            if editoriales_disp:
                filtro_editoriales = st.multiselect("🏢 Editorial:", editoriales_disp)
st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================
# 7. BANNER DE CAJITA LITERARIA CON NUEVA IMAGEN
# =====================================================================
LINK_FORMULARIO_SUSCRIPCION = "https://docs.google.com/forms/d/e/1FAIpQLSc8FpBSwizmcinCdemJo31APqa24fU_Xw837mHJU2VJW2xNNg/viewform"
URL_FOTO_CAJITA = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/caja_referencia.png"

st.markdown(f"""
    <style>
        .banner-cajita {{
            display: flex; align-items: center; justify-content: space-between;
            background: linear-gradient(135deg, #fcdce8 0%, #e790b3 100%);
            border-radius: 20px; padding: 30px 40px; margin-bottom: 30px;
            box-shadow: 0 10px 25px rgba(220, 73, 144, 0.15);
        }}
        .banner-texto {{ flex: 1; padding-right: 20px; }}
        .banner-titulo {{ font-family: 'Dancing Script', cursive !important; color: #ffffff !important; font-size: 2.2rem; margin-bottom: 10px; line-height: 1.4; }}
        .banner-subtitulo {{ color: #fcf5f7; font-size: 1.1rem; margin-bottom: 25px; font-weight: 500; }}
        .banner-btn {{
            background-color: #dc4990; color: white !important; padding: 12px 30px;
            border-radius: 50px; text-decoration: none; font-weight: 700; font-size: 1.1rem;
            box-shadow: 0 4px 15px rgba(220, 73, 144, 0.3); display: inline-block; transition: transform 0.2s ease;
        }}
        .banner-btn:hover {{ transform: scale(1.05); background-color: #e471a4; }}
        .banner-img-container {{ flex: 0.8; text-align: right; }}
        .banner-img {{ width: 100%; max-width: 150px; ; border-radius: 15px; transform: rotate(3deg); box-shadow: 0 8px 20px rgba(0,0,0,0.15); }}
        @media (max-width: 150px) {{
            .banner-cajita {{ flex-direction: column; text-align: center; padding: 25px 20px; }}
            .banner-texto {{ padding-right: 0; margin-bottom: 25px; }}
            .banner-titulo {{ font-size: 1.8rem; }}
            .banner-img-container {{ text-align: center; }}
            .banner-img {{ transform: rotate(0deg); }}
        }}
    </style>
    <div class="banner-cajita">
        <div class="banner-texto">
            <h2 class="banner-titulo">Pide hoy tu cajita literaria ✨</h2>
            <p class="banner-subtitulo">Recibe cada mes un libro sorpresa, regalitos y mucha magia directa a tu puerta.</p>
            <a href="{LINK_FORMULARIO_SUSCRIPCION}" target="_blank" class="banner-btn">📝 ¡SUSCRIBIRME!</a>
        </div>
        <div class="banner-img-container">
            <img src="{URL_FOTO_CAJITA}" class="banner-img" alt="Cajita Literaria Alba">
        </div>
    </div>
""", unsafe_allow_html=True)
st.write("---") 

# =====================================================================
# 🎠 CARRUSEL DE DESTACADOS / NOVEDADES 
# =====================================================================
st.markdown("<h3 style='text-align: center; margin-bottom: 10px;'>✨ Destacados del Mes</h3>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 0.9rem; margin-bottom: 15px;'>Desliza hacia la derecha para ver más novedades ➔</p>", unsafe_allow_html=True)

if 'precio_original' in df_catalogo.columns:
    df_destacados = df_catalogo[df_catalogo['precio'] < df_catalogo['precio_original']].dropna(subset=['precio_original'])
else:
    df_destacados = pd.DataFrame()

if len(df_destacados) < 4:
    df_destacados = df_catalogo.head(8)

html_carrusel = '<div class="carrusel-container">'
for _, row in df_destacados.iterrows():
    c_id = str(int(float(row.get('libro_id', 0))))
    c_url = f"{URL_BASE_SUPABASE}{c_id}.jpg"
    c_titulo = str(row.get('titulo', 'Sin título'))
    c_precio = float(row.get('precio', 0))
    
    html_carrusel += f"""
    <div class="carrusel-item">
        <img src="{c_url}" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x200?text=Sin+Portada';">
        <p style="font-weight: 700; ...">{c_titulo}</p>
        <p style="color: #dc4990; ...">${c_precio:,.0f}</p>
    </div>
    """
html_carrusel += '</div>'
st.markdown(html_carrusel, unsafe_allow_html=True)
st.write("---")

# =====================================================================
# --- APLICAR FILTROS Y BÚSQUEDA ---
# =====================================================================
df_filtrado = df_catalogo.copy()

if busqueda_texto:
    texto_limpio = busqueda_texto.strip().lower()
    df_filtrado = df_filtrado[
        df_filtrado['titulo'].str.lower().str.contains(texto_limpio, na=False) | 
        df_filtrado['autor'].str.lower().str.contains(texto_limpio, na=False)
    ]

if filtro_generos: df_filtrado = df_filtrado[df_filtrado['genero'].isin(filtro_generos)]
if filtro_autores: df_filtrado = df_filtrado[df_filtrado['autor'].isin(filtro_autores)]
if filtro_editoriales: df_filtrado = df_filtrado[df_filtrado['editorial'].isin(filtro_editoriales)]

st.markdown(f"<p style='color: #e790b3; font-weight: 600; text-align: center;'>Mostrando {len(df_filtrado)} libros mágicos ✨</p>", unsafe_allow_html=True)

# --- CUADRÍCULA PRINCIPAL DE LIBROS ---
columnas = st.columns(3)
for index, row in df_filtrado.reset_index(drop=True).iterrows():
    col = columnas[index % 3]
    with col:
        libro_id_limpio = str(int(float(row.get('libro_id', 0))))
        url_imagen = f"{URL_BASE_SUPABASE}{libro_id_limpio}.jpg"
        titulo_seguro = row.get('titulo', "Sin título")
        autor_seguro = row.get('autor', 'Desconocido')
        precio = float(row.get('precio', 0.0))
        precio_orig = float(row.get('precio_original', precio))

        html_card = f"""
        <div class="libro-card">
            <img src="{url_imagen}" onerror="this.onerror=null; this.src='https://via.placeholder.com/250x350?text=Sin+Portada';">
            <h4>{titulo_seguro}</h4>
            <div class="info-container">
                <p style='color: #888888; font-size: 0.9rem; margin-top: 0; margin-bottom: 10px;'>por {autor_seguro}</p>
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
