# cache_utils.py
import streamlit as st
import pandas as pd
import requests
import concurrent.futures
from utilidades import get_db_connection

@st.cache_data(ttl=180) # Guarda el resultado en memoria por 3 minutos
def obtener_libros_publicables():
    """
    Filtro Maestro: Obtiene libros visibles, con precio > 0 y con portada en el bucket.
    """
    try:
        conn = get_db_connection()
        
        # 1. Libros visibles y con precio
        res_libros = conn.table("libros").select("*").eq("visible_catalogo", True).gt("precio", 0).execute()
        if not res_libros.data:
            return pd.DataFrame()
            
        df_libros = pd.DataFrame(res_libros.data)

        # 2. Portadas en el bucket
        archivos_bucket = conn.storage.from_("portadas").list()
        portadas_existentes = {archivo['name'] for archivo in archivos_bucket}
        
        # 3. Filtrar
        df_libros['tiene_portada'] = df_libros['libro_id'].apply(lambda id: f"{id}.jpg" in portadas_existentes)
        df_final = df_libros[df_libros['tiene_portada'] == True].copy()
        df_final.drop(columns=['tiene_portada'], inplace=True)
        
        return df_final

    except Exception as e:
        print(f"Error en obtener_libros_publicables: {e}")
        return pd.DataFrame()