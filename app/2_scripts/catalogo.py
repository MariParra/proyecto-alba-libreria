import streamlit as st
import pandas as pd
import urllib.parse
from utilidades import get_db_connection
from cache_utils import cargar_catalogo_publico, filtrar_solo_con_imagen

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

# --- CSS BASE ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,300;0,400;0,700;1,300&family=Dancing+Script:wght@400..700&display=swap');
        
        html, body, [class*="css"] { font-family: 'Lato', sans-serif; }
        
        h1, h2, h3, .banner-titulo { font-family: 'Dancing Script', cursive !important; color: #dc4990 !important; }
        
        .stApp { 
            background: linear-gradient(180deg, #fcf5f7 0%, #fcdce8 100%); 
            padding-top: 180px; /* ESPACIO PARA LA NAVBAR DE 2 FILAS */
        }

        /* DISEÑO EXPANDERS (BOLSA) */
        [data-testid="stExpander"] {
            background-color: #ffffff !important; border-radius: 15px !important;
            border: 2px solid #e790b3 !important; box-shadow: 0 4px 12px rgba(220, 73, 144, 0.1) !important; margin-bottom: 10px;
        }
        [data-testid="stExpander"] summary { background-color: #fcf5f7 !important; border-radius: 12px !important; }
        [data-testid="stExpander"] summary p { font-size: 1.15rem !important; font-weight: 700 !important; color: #dc4990 !important; }

        /* --- INICIO CAMBIO: NUEVOS COLORES PARA FILTROS --- */
        [data-testid="stMultiSelect"] { 
            border: 2px solid #FBCFE8 !important; /* Rosa muy suave */
            background-color: #ffffff !important; 
            border-radius: 10px !important; 
        }
        [data-testid="stMultiSelect"] .st-d5 { color: #D1D5DB !important; font-style: italic !important; } /* Placeholder */
        [data-testid="stMultiSelect"] .st-c5 {
            background-color: #FBCFE8 !important; /* Rosa muy suave */
            color: #9D174D !important; /* Texto fucsia oscuro para contraste */
            border: 1px solid #F472B6 !important;
            border-radius: 6px !important; 
            font-weight: bold !important;
        }
        [data-testid="stMultiSelect"] .st-c5 svg { fill: #9D174D !important; }
        /* --- FIN CAMBIO --- */

        [data-testid="stSidebar"] { display: none !important; }

        /* NAVBAR SUPERIOR FIJA */
        .navbar-fija {
            position: fixed; top: 0; left: 0; width: 100%; z-index: 9999;
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px);
            padding: 15px 20px 15px 20px; border-bottom: 2px solid #e790b3;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        
        .stTextInput { margin-bottom: 0px !important; }
        
        /* --- INICIO CAMBIO: NUEVO COLOR PARA TARJETAS DE LIBROS --- */
        .libro-card {
            background: #fdf1f1; /* Tu nuevo color rosa suave */
            border: 1px solid #fcdce8; border-radius: 20px; 
            padding: 15px; margin-bottom: 5px; text-align: center; box-shadow: 0 4px 15px rgba(220, 73, 144, 0.08);
            transition: transform 0.3s ease, box-shadow 0.3s ease; display: flex; flex-direction: column; justify-content: space-between;
            min-height: 400px; height: 100%;
        }
        /* --- FIN CAMBIO --- */

        .libro-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(220, 73, 144, 0.2); }
        .libro-card img { width: 100%; border-radius: 8px; object-fit: contain; height: 200px; margin-bottom: 15px; transition: transform 0.3s ease; }
        .libro-card:hover img { transform: scale(1.03); }
        .libro-card h4 {
            font-family: 'Lato', sans-serif !important; color: #333333; font-weight: 700; font-size: 1.05rem;
            line-height: 1.3; margin-top: 10px; margin-bottom: 5px; min-height: 2.6em;
        }
        .info-container { flex-grow: 1; display: flex; flex-direction: column; justify-content: flex-end; }
        .precio-tachado { color: #9CA3AF; text-decoration: line-through; font-size: 0.9rem; }
        .precio-oferta { color: #dc4990; font-weight: 700; font-size: 1.3rem; }
        .precio-normal { color: #e471a4; font-weight: 700; font-size: 1.2rem; }
        
        /* BOTÓN "LO QUIERO" */
        [data-testid="stButton"] button {
            background-color: #fcdce8 !important; color: #333333 !important; border: 1px solid #e790b3 !important; font-weight: bold !important; border-radius: 10px !important; width: 100%; margin-bottom: 25px;
        }
        [data-testid="stButton"] button:hover { background-color: #e790b3 !important; color: white !important; }

        /* Botón WhatsApp Flotante */
        .whatsapp-float {
            position: fixed; bottom: 40px; right: 40px; background-color: #25D366; color: white !important; border-radius: 50px; padding: 15px 30px;
            font-size: 18px; font-weight: 700; box-shadow: 0 4px 20px rgba(37, 211, 102, 0.4); z-index: 1000; text-decoration: none; display: flex; align-items: center; justify-content: center; transition: background-color 0.3s ease;
        }
        .whatsapp-float:hover { background-color: #128C7E; }
        @media (max-width: 768px) { .whatsapp-float { bottom: 20px; right: 20px; padding: 12px 20px; font-size: 15px; } }
        
        .header-container { display: flex; align-items: center; justify-content: center; gap: 15px; margin-bottom: 0; }
        .header-icono { width: 55px; height: auto; }
        .header-container h1 { margin: 0; font-size: 3.2rem; }
    </style>
""", unsafe_allow_html=True)

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
""", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #dc4990; font-size: 1.2rem; margin-top: 5px; font-weight: 600;'>Explora nuestro catálogo y haz tu pedido al instante.</p>", unsafe_allow_html=True)

# CARGA DE DATOS
df_bruto = cargar_catalogo_publico()
if df_bruto.empty:
    st.info("Estamos actualizando las estanterías. ¡Vuelve pronto!")
    st.stop()

with st.spinner("Acomodando los libros en la vitrina..."):
    df_catalogo = filtrar_solo_con_imagen(df_bruto, URL_BASE_SUPABASE)

# Filtrar para que solo se muestren los libros autorizados para la web
if 'visible_catalogo' in df_catalogo.columns:
    df_catalogo = df_catalogo[df_catalogo['visible_catalogo'] == True]
    
if df_catalogo.empty:
    st.warning("No hay libros con portadas disponibles por el momento.")
    st.stop()
    
generos_disp = sorted(df_catalogo['genero'].dropna().unique())
autores_disp = sorted(df_catalogo['autor'].dropna().unique())
editoriales_disp = sorted(df_catalogo['editorial'].dropna().unique()) if 'editorial' in df_catalogo.columns else []

# =====================================================================
# NAVBAR SUPERIOR FIJA
# =====================================================================
st.markdown('<div class="navbar-fija">', unsafe_allow_html=True)

col_filtros, col_bolsa = st.columns([3, 1])

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
                
                col_t, col_b = st.columns([3, 1])
                with col_t: st.write(f"**{item['cantidad']}x** {item['titulo']}")
                with col_b:
                    st.button("❌", key=f"del_nav_{l_id}", help="Quitar", on_click=quitar_del_carrito, args=(l_id,))
                        
            st.markdown("---")
            st.markdown(f"**Total:** ${total_carrito:,.0f}")
            mensaje_wa += f"\n*Total Estimado a pagar: ${total_carrito:,.0f}*\n\n⚠️ _Nota: Entiendo que deben confirmarme el stock disponible y el valor final antes de realizar el pago._\n\n¡Quedo atenta, muchas gracias!"
            
            st.session_state.url_wa_flotante = f"https://wa.me/{NUMERO_WHATSAPP}?text={urllib.parse.quote(mensaje_wa)}"
            st.markdown(f'<a href="{st.session_state.url_wa_flotante}" target="_blank" style="display: block; text-align: center; background-color: #25D366; color: white; padding: 10px; border-radius: 8px; text-decoration: none; font-weight: bold; margin-bottom:10px;">📲 ENVIAR PEDIDO</a>', unsafe_allow_html=True)

st.write("") 
busqueda_texto = st.text_input("🔍 Buscar:", placeholder="Ej. Fantasía, amor, o el nombre de tu autor favorito...", label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================
# 🎪 ENRUTADOR DE SUBPÁGINAS Y MEGA CARRUSEL DE BANNERS
# =====================================================================
# Leemos la URL para saber si el usuario hizo clic en algún banner
seccion_actual = st.query_params.get("seccion", "inicio")

if seccion_actual == "inicio":
    # --- 1. ESTAMOS EN EL INICIO: MOSTRAMOS EL MEGA CARRUSEL ---
    LINK_FORMULARIO_SUSCRIPCION = "https://docs.google.com/forms/d/e/1FAIpQLSc8FpBSwizmcinCdemJo31APqa24fU_Xw837mHJU2VJW2xNNg/viewform"
    URL_FOTO_CAJITA = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/caja_referencia.png"
    URL_ICONO = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/libro-abierto.png"

    html_mega_carrusel = f"""
    <style>
        /* CONTENEDOR PRINCIPAL: Por defecto (móvil) es 1 columna hacia abajo */
        .mega-carrusel-wrapper {{
            display: grid;
            grid-template-columns: 1fr; 
            gap: 20px;
            padding: 10px 0;
            width: 100%;
        }}
        
        /* PANTALLAS GRANDES (PC/Tablets): Cambia a 3 columnas iguales */
        @media (min-width: 1024px) {{
            .mega-carrusel-wrapper {{
                grid-template-columns: repeat(3, 1fr);
            }}
        }}
        
        /* DISEÑO DE CADA BANNER */
        .banner-promo {{
            border-radius: 20px; 
            padding: 25px 30px; 
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            display: flex; 
            align-items: center; 
            justify-content: space-between;
            text-decoration: none !important;
            width: 100%; 
            box-sizing: border-box;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .banner-promo:hover {{ 
            transform: translateY(-5px); 
            box-shadow: 0 12px 30px rgba(0,0,0,0.2); 
        }}
        
        /* COLORES Y DEGRADADOS */
        .bg-cajita {{ background: linear-gradient(135deg, #fcdce8 0%, #e790b3 100%); }}
        .bg-destacados {{ background: linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%); }}
        .bg-ofertas {{ background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); }}
        
        /* TEXTOS Y BOTONES */
        .banner-texto {{ flex: 1; padding-right: 10px; }}
        .banner-titulo {{ font-family: 'Dancing Script', cursive !important; color: #ffffff !important; font-size: 2.2rem; margin-bottom: 5px; line-height: 1.1; }}
        .banner-subtitulo {{ color: #ffffff; font-size: 0.95rem; margin-bottom: 15px; font-weight: 500; line-height: 1.2; }}
        .banner-btn {{ 
            background-color: #ffffff; padding: 8px 20px; border-radius: 50px; 
            font-weight: 700; font-size: 0.9rem; display: inline-block; 
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); transition: transform 0.2s ease; text-decoration: none !important;
        }}
        .banner-btn:hover {{ transform: scale(1.05); }}
        
        /* IMÁGENES */
        .banner-img-container {{ flex: 0.45; text-align: right; }}
        .banner-img-container img {{ width: 100%; max-width: 110px; height: auto; border-radius: 15px; transform: rotate(5deg); }}
        .img-icono {{ transform: rotate(0deg) !important; max-width: 85px !important; box-shadow: none !important; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.1));}}
    </style>

    <div class="mega-carrusel-wrapper">
        <!-- BANNER 1: OFERTAS -->
        <a href="?seccion=ofertas" target="_self" class="banner-promo bg-ofertas">
            <div class="banner-texto">
                <h2 class="banner-titulo">Ofertas 🔥</h2>
                <p class="banner-subtitulo">Descuentos mágicos en nuestro catálogo.</p>
                <span class="banner-btn" style="color: #e88c71 !important;">💸 VER OFERTAS</span>
            </div>
            <div class="banner-img-container"><img src="{URL_ICONO}" class="img-icono"></div>
        </a>

        <!-- BANNER 2: CAJITA LITERARIA -->
        <a href="{LINK_FORMULARIO_SUSCRIPCION}" target="_blank" class="banner-promo bg-cajita">
            <div class="banner-texto">
                <h2 class="banner-titulo">Cajita Literaria ✨</h2>
                <p class="banner-subtitulo">Libro sorpresa, regalitos y magia mensual.</p>
                <span class="banner-btn" style="color: #dc4990 !important;">📝 SUSCRIBIRME</span>
            </div>
            <div class="banner-img-container"><img src="{URL_FOTO_CAJITA}"></div>
        </a>

        <!-- BANNER 3: DESTACADOS -->
        <a href="?seccion=destacados" target="_self" class="banner-promo bg-destacados">
            <div class="banner-texto">
                <h2 class="banner-titulo">Destacados ⭐</h2>
                <p class="banner-subtitulo">Las mejores historias seleccionadas para ti.</p>
                <span class="banner-btn" style="color: #9283e0 !important;">📚 VER LIBROS</span>
            </div>
            <div class="banner-img-container"><img src="{URL_ICONO}" class="img-icono"></div>
        </a>
    </div>
    """
    
    st.html(html_mega_carrusel)
    st.write("---")
    
    df_base = df_catalogo.copy()

elif seccion_actual == "destacados":
    # --- 2. SUBPÁGINA: DESTACADOS ---
    st.html("<h2 class='banner-titulo' style='text-align:center; font-size: 3rem;'>⭐ Libros Destacados</h2>")
    st.html("<div style='text-align:center; margin-bottom: 20px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    
    if 'destacado' in df_catalogo.columns:
        df_base = df_catalogo[df_catalogo['destacado'] == True]
    else:
        df_base = df_catalogo.head(0) 

elif seccion_actual == "ofertas":
    # --- 3. SUBPÁGINA: OFERTAS ---
    st.html("<h2 class='banner-titulo' style='text-align:center; font-size: 3rem;'>🔥 Libros en Oferta</h2>")
    st.html("<div style='text-align:center; margin-bottom: 20px;'><a href='?' target='_self' style='padding: 10px 25px; background-color: #fcdce8; border-radius: 50px; text-decoration: none; color: #dc4990; font-weight: bold; border: 1px solid #e790b3; display: inline-block;'>⬅️ Volver al Catálogo Principal</a></div>")
    
    if 'precio_original' in df_catalogo.columns and 'precio' in df_catalogo.columns:
        df_base = df_catalogo[df_catalogo['precio'] < df_catalogo['precio_original']]
    else:
        df_base = df_catalogo.head(0)

# =====================================================================
# --- APLICAR FILTROS Y BÚSQUEDA A LA CUADRÍCULA ---
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
            url_imagen = f"{URL_BASE_SUPABASE}{libro_id_limpio}.jpg"
            titulo_seguro = row.get('titulo', "Sin título")
            autor_seguro = row.get('autor', 'Desconocido')
            precio = float(row.get('precio', 0.0))
            precio_orig = float(row.get('precio_original', precio))

            html_card = f"""
            <div class="libro-card">
                <img src="{url_imagen}" onerror="this.onerror=null; this.src='https://via.placeholder.com/250x350?text=Sin+Portada';">
                <div class="info-container">
                    <h4>{titulo_seguro}</h4>
                    <p style='color: #888888; font-size: 0.9rem; margin-top: 0; margin-bottom: 15px;'>por {autor_seguro}</p>
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