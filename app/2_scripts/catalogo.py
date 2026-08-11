import streamlit as st
import pandas as pd
import urllib.parse
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
# ====================================================

# --- CSS ---
st.markdown("""
    <style>
        .libro-card {
            border: 1px solid #e0e0e0; border-radius: 10px; padding: 15px;
            margin-bottom: 20px; text-align: center; background-color: white;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.05); height: 95%; 
        }
        .precio-tachado { color: #999; text-decoration: line-through; font-size: 0.9em; }
        .precio-oferta { color: #E63946; font-weight: bold; font-size: 1.3em; }
        .precio-normal { color: #2B2D42; font-weight: bold; font-size: 1.2em; }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=120)
def cargar_catalogo_publico():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, precio_original, genero, stock").gt("stock", 0).order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
        # Limpieza de datos preventiva
        if not df.empty:
            df.dropna(subset=['libro_id', 'titulo', 'precio'], inplace=True)
            df['libro_id'] = df['libro_id'].astype(str)
        return df
    except Exception:
        return pd.DataFrame()

if 'carrito_publico' not in st.session_state:
    st.session_state.carrito_publico = {}

def agregar_al_carrito(libro_id, titulo, precio):
    if libro_id in st.session_state.carrito_publico:
        st.session_state.carrito_publico[libro_id]['cantidad'] += 1
    else:
        st.session_state.carrito_publico[libro_id] = {'titulo': titulo, 'precio': precio, 'cantidad': 1}
    st.toast(f"✅ Añadido: '{titulo}'")

def quitar_del_carrito(libro_id):
    if libro_id in st.session_state.carrito_publico:
        del st.session_state.carrito_publico[libro_id]

# --- ESTRUCTURA DE LA PÁGINA ---
st.markdown("<h1 style='text-align: center; color: #4A4D7E;'>📚 Alba Librería</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Explora nuestro catálogo y pide tus libros favoritos por WhatsApp.</p>", unsafe_allow_html=True)
st.write("---")

df_catalogo = cargar_catalogo_publico()

if df_catalogo.empty:
    st.info("Estamos actualizando el catálogo. ¡Vuelve pronto!")
    st.stop()

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🛒 Tu Carrito")
    if not st.session_state.carrito_publico:
        st.write("Tu carrito está vacío.")
    else:
        total_carrito = 0
        mensaje_wa = "Hola Alba Librería, me gustaría pedir:\n\n"
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
        mensaje_wa += f"\n*Total Estimado: ${total_carrito:,.0f}*\n\n¡Gracias!"
        mensaje_wa_encoded = urllib.parse.quote(mensaje_wa)
        url_whatsapp = f"https://wa.me/{NUMERO_WHATSAPP}?text={mensaje_wa_encoded}"
        st.link_button("📲 ENVIAR PEDIDO POR WHATSAPP", url_whatsapp, type="primary", use_container_width=True)

    st.markdown("---")
    st.header("🔍 Filtros")
    generos_disp = sorted(df_catalogo['genero'].dropna().unique())
    filtro_genero = st.selectbox("Buscar por Género:", ["Todos"] + generos_disp)

# --- CUADRÍCULA DE LIBROS ---
df_filtrado = df_catalogo
if filtro_genero != "Todos":
    df_filtrado = df_filtrado[df_filtrado['genero'] == filtro_genero]

st.markdown(f"**Mostrando {len(df_filtrado)} libros disponibles:**")

columnas = st.columns(3)
for index, row in df_filtrado.reset_index(drop=True).iterrows():
    col = columnas[index % 3]
    with col:
        with st.container():
            st.markdown('<div class="libro-card">', unsafe_allow_html=True)
            
            # --- VALIDACIÓN DE URL (LA SOLUCIÓN) ---
            libro_id_str = str(row.get('libro_id', '')).strip()
            if libro_id_str:
                url_imagen = f"{URL_BASE_SUPABASE}{libro_id_str}.jpg"
                st.image(url_imagen, use_container_width=True)
            else:
                # Si no hay ID, muestra un espacio reservado
                st.markdown("<div style='height: 200px; background-color: #f0f0f0; border-radius: 5px;'></div>", unsafe_allow_html=True)

            titulo_seguro = row.get('titulo', "Sin título")
            autor_seguro = row.get('autor', 'Desconocido')
            
            st.markdown(f"#### {titulo_seguro}")
            st.caption(f"por {autor_seguro}")
            
            precio = float(row.get('precio', 0.0))
            precio_orig = float(row.get('precio_original', precio))
            
            if precio < precio_orig:
                st.markdown(f"<span class='precio-tachado'>${precio_orig:,.0f}</span><br><span class='precio-oferta'>${precio:,.0f}</span>", unsafe_allow_html=True)
                st.button("➕ Añadir Oferta", key=f"add_{libro_id_str}", type="primary", use_container_width=True, on_click=agregar_al_carrito, args=(libro_id_str, titulo_seguro, precio))
            else:
                st.markdown(f"<br><span class='precio-normal'>${precio:,.0f}</span>", unsafe_allow_html=True)
                st.button("➕ Añadir al carrito", key=f"add_{libro_id_str}", use_container_width=True, on_click=agregar_al_carrito, args=(libro_id_str, titulo_seguro, precio))
            
            st.markdown('</div>', unsafe_allow_html=True)