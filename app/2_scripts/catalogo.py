import streamlit as st
import pandas as pd
import urllib.parse
import requests
import concurrent.futures
from utilidades import get_db_connection

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Catálogo | Alba Librería", page_icon="📚", layout="wide")

# ====================================================
# ⚙️ CARGA SEGURA DE CONFIGURACIÓN DESDE st.secrets
# ====================================================
try:
    NUMERO_WHATSAPP = st.secrets["catalogo_publico"]["whatsapp_numero"]
    URL_BASE_SUPABASE = st.secrets["catalogo_publico"]["supabase_portadas_url"]
except KeyError:
    st.error("🚨 Error de configuración: Faltan claves en secrets.toml.")
    st.stop()

# --- CSS AESTHETIC PREMIUM ---
st.markdown("""
    <style>
        /* Importar fuente elegante */
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Montserrat', sans-serif;
        }
        
        /* Fondo rosa pastel de la app */
        .stApp {
            background-color: #FDF2F8;
        }

        /* Diseño de Tarjetas (Cards) */
        .libro-card {
            background-color: white;
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 25px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        
        /* Efecto al pasar el mouse */
        .libro-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 12px 25px rgba(225, 29, 72, 0.15);
        }

        /* Tipografías de precios */
        .precio-tachado { color: #9CA3AF; text-decoration: line-through; font-size: 1rem; }
        .precio-oferta { color: #E11D48; font-weight: 700; font-size: 1.5rem; }
        .precio-normal { color: #4A4D7E; font-weight: 700; font-size: 1.4rem; }
        
        /* Botón WhatsApp Flotante */
        .whatsapp-float {
            position: fixed;
            bottom: 40px;
            right: 40px;
            background-color: #25D366;
            color: white !important;
            border-radius: 50px;
            padding: 15px 30px;
            font-size: 18px;
            font-weight: 700;
            box-shadow: 0 4px 20px rgba(37, 211, 102, 0.4);
            z-index: 1000;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background-color 0.3s ease;
        }
        .whatsapp-float:hover {
            background-color: #128C7E;
        }
    </style>
""", unsafe_allow_html=True)

# --- LÓGICA DE DATOS Y "RADAR" DE IMÁGENES ---
@st.cache_data(ttl=120)
def cargar_catalogo_publico():
    conn = get_db_connection()
    try:
        # Intentamos traer la editorial también si existe
        res = conn.table("libros").select("libro_id, titulo, autor, editorial, precio, precio_original, genero, stock").gt("stock", 0).order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        if not df.empty:
            df.dropna(subset=['libro_id', 'titulo', 'precio'], inplace=True)
        return df
    except Exception:
        # Fallback por si la columna 'editorial' no existe en tu base de datos
        res = conn.table("libros").select("libro_id, titulo, autor, precio, precio_original, genero, stock").gt("stock", 0).order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        if not df.empty:
            df.dropna(subset=['libro_id', 'titulo', 'precio'], inplace=True)
        return df

@st.cache_data(ttl=300)
def filtrar_solo_con_imagen(df):
    """RADAR: Revisa rápidamente en Supabase si la imagen existe."""
    def check_url(row):
        try:
            libro_id = str(int(float(row.get('libro_id', 0))))
            url = f"{URL_BASE_SUPABASE}{libro_id}.jpg"
            # Un request 'head' solo lee los metadatos (súper rápido)
            return requests.head(url, timeout=2).status_code == 200
        except:
            return False

    # Usamos hilos (concurrencia) para revisar 20 libros al mismo tiempo
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        resultados = list(executor.map(check_url, df.to_dict('records')))
    
    return df[resultados]

# Inicializamos el carrito
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

# --- CABECERA ESTÉTICA ---
st.markdown("<h1 style='text-align: center; color: #4A4D7E; font-weight: 800; font-size: 3rem; margin-bottom: 0;'>📚 Alba Librería</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #6B7280; font-size: 1.2rem; margin-top: 5px;'>Explora nuestro catálogo y haz tu pedido al instante.</p>", unsafe_allow_html=True)
st.write("---")

df_bruto = cargar_catalogo_publico()
if df_bruto.empty:
    st.info("Estamos actualizando las estanterías. ¡Vuelve pronto!")
    st.stop()

# Filtramos solo los que tienen imagen en Supabase
with st.spinner("Acomodando los libros en la vitrina..."):
    df_catalogo = filtrar_solo_con_imagen(df_bruto)

if df_catalogo.empty:
    st.warning("No hay libros con portadas disponibles por el momento.")
    st.stop()

# --- BARRA LATERAL: CARRITO Y MÚLTIPLES FILTROS ---
with st.sidebar:
    st.header("🛍️ Tu Bolsa")
    if not st.session_state.carrito_publico:
        st.write("Aún no has seleccionado ningún libro.")
    else:
        total_carrito = 0
        mensaje_wa = "¡Hola Alba Librería! 💖 Me encantaría pedir estos libros:\n\n"
        for l_id, item in list(st.session_state.carrito_publico.items()):
            subtotal = item['precio'] * item['cantidad']
            total_carrito += subtotal
            mensaje_wa += f"📖 {item['cantidad']}x {item['titulo']} - ${subtotal:,.0f}\n"
            
            col_titulo, col_btn = st.columns([4, 1]) 
            col_titulo.write(f"**{item['cantidad']}x** {item['titulo']}")
            if col_btn.button("❌", key=f"del_{l_id}", help="Quitar"):
                quitar_del_carrito(l_id)
                st.rerun()
                
        st.markdown("---")
        st.markdown(f"### Total: ${total_carrito:,.0f}")
        mensaje_wa += f"\n*Total a pagar: ${total_carrito:,.0f}*\n\n¡Quedo atenta, muchas gracias!"
        
        # Guardamos el enlace de WhatsApp en sesión para el botón flotante
        mensaje_wa_encoded = urllib.parse.quote(mensaje_wa)
        st.session_state.url_wa_flotante = f"https://wa.me/{NUMERO_WHATSAPP}?text={mensaje_wa_encoded}"

    st.markdown("---")
    st.header("🔍 Buscar Libros")
    
    # Filtros Dinámicos
    generos_disp = sorted(df_catalogo['genero'].dropna().unique())
    autores_disp = sorted(df_catalogo['autor'].dropna().unique())
    
    filtro_generos = st.multiselect("📖 Géneros:", generos_disp)
    filtro_autores = st.multiselect("✍️ Autores:", autores_disp)
    
    filtro_editoriales = []
    if 'editorial' in df_catalogo.columns:
        editoriales_disp = sorted(df_catalogo['editorial'].dropna().unique())
        if editoriales_disp:
            filtro_editoriales = st.multiselect("🏢 Editorial:", editoriales_disp)

# --- APLICAR FILTROS AL CATÁLOGO ---
df_filtrado = df_catalogo.copy()
if filtro_generos:
    df_filtrado = df_filtrado[df_filtrado['genero'].isin(filtro_generos)]
if filtro_autores:
    df_filtrado = df_filtrado[df_filtrado['autor'].isin(filtro_autores)]
if filtro_editoriales:
    df_filtrado = df_filtrado[df_filtrado['editorial'].isin(filtro_editoriales)]

st.markdown(f"<p style='color: #6B7280; font-weight: 600;'>Mostrando {len(df_filtrado)} libros mágicos ✨</p>", unsafe_allow_html=True)

# --- CUADRÍCULA ESTÉTICA DE LIBROS ---
columnas = st.columns(3)
for index, row in df_filtrado.reset_index(drop=True).iterrows():
    col = columnas[index % 3]
    with col:
        with st.container():
            st.markdown('<div class="libro-card">', unsafe_allow_html=True)
            
            # Imagen cargada fluidamente
            libro_id_limpio = str(int(float(row.get('libro_id', 0))))
            url_imagen = f"{URL_BASE_SUPABASE}{libro_id_limpio}.jpg"
            st.markdown(f'<img src="{url_imagen}" style="width:100%; border-radius: 10px; object-fit: contain; max-height: 280px; margin-bottom: 15px;">', unsafe_allow_html=True)

            titulo_seguro = row.get('titulo', "Sin título")
            autor_seguro = row.get('autor', 'Desconocido')
            
            st.markdown(f"<h4 style='color: #4A4D7E; font-weight: 700; font-size: 1.1rem; line-height: 1.3;'>{titulo_seguro}</h4>", unsafe_allow_html=True)
            st.markdown(f"<p style='color: #9CA3AF; font-size: 0.9rem; margin-top: -10px;'>por {autor_seguro}</p>", unsafe_allow_html=True)
            
            precio = float(row.get('precio', 0.0))
            precio_orig = float(row.get('precio_original', precio))
            
            if precio < precio_orig:
                st.markdown(f"<span class='precio-tachado'>${precio_orig:,.0f}</span><br><span class='precio-oferta'>${precio:,.0f}</span>", unsafe_allow_html=True)
                st.button("✨ Lo quiero", key=f"add_{libro_id_limpio}", type="primary", use_container_width=True, on_click=agregar_al_carrito, args=(libro_id_limpio, titulo_seguro, precio))
            else:
                st.markdown(f"<br><span class='precio-normal'>${precio:,.0f}</span>", unsafe_allow_html=True)
                st.button("✨ Lo quiero", key=f"add_{libro_id_limpio}", use_container_width=True, on_click=agregar_al_carrito, args=(libro_id_limpio, titulo_seguro, precio))
            
            st.markdown('</div>', unsafe_allow_html=True)

# --- BOTÓN FLOTANTE DE WHATSAPP ---
if st.session_state.get('carrito_publico'):
    url_flotante = st.session_state.get('url_wa_flotante', '#')
    btn_html = f"""
    <a href="{url_flotante}" target="_blank" class="whatsapp-float">
        💬 ENVIAR PEDIDO AHORA
    </a>
    """
    st.markdown(btn_html, unsafe_allow_html=True)