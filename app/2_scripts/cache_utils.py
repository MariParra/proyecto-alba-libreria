# cache_utils.py
import streamlit as st
import pandas as pd
import requests
import concurrent.futures
from utilidades import get_db_connection

@st.cache_data(ttl=120)
def cargar_catalogo_publico():
    conn = get_db_connection()
    # Intenta buscar la nueva columna "destacado". Si no existe, usa los fallbacks.
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, editorial, precio, precio_original, genero, stock, destacado").gt("stock", 0).gt("precio", 0).order("titulo").execute()
        df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception:
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
def filtrar_solo_con_imagen(df, url_base_supabase):
    def check_url(row):
        try:
            libro_id = str(int(float(row.get('libro_id', 0))))
            url = f"{url_base_supabase}{libro_id}.jpg"
            return requests.head(url, timeout=2).status_code == 200
        except:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        resultados = list(executor.map(check_url, df.to_dict('records')))
    return df[resultados]