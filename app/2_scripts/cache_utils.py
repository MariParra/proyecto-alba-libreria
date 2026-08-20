# cache_utils.py
import streamlit as st
import pandas as pd
from utilidades import get_db_connection

@st.cache_data(ttl=1800) 
def obtener_libros_publicables():
    """
    Filtro Maestro: Obtiene libros visibles, con precio > 0 y con portada en el bucket.
    Versión blindada contra el límite de 1000 registros y caracteres invisibles.
    """
    try:
        conn = get_db_connection()
        
        # 1. Libros visibles y con precio (PAGINADO PARA EVITAR LÍMITE DE 1000)
        all_books = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("libros")\
                .select("*")\
                .eq("visible_catalogo", True)\
                .gt("precio", 0)\
                .order("libro_id")\
                .range(start, end).execute()
            if res.data:
                all_books.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_books:
            return pd.DataFrame()
            
        df_libros = pd.DataFrame(all_books)

        # 2. Portadas en el bucket (con paginación y limpieza .strip())
        portadas_existentes = set()
        offset = 0
        while True:
            try:
                bloque = conn.storage.from_("portadas").list(path="", search_options={"limit": 100, "offset": offset})
            except TypeError:
                bloque = conn.storage.from_("portadas").list(path="", options={"limit": 100, "offset": offset})
            
            if not bloque:
                break
            
            # Limpiamos cada nombre de archivo al momento de añadirlo
            for archivo in bloque:
                if archivo['name'] is not None:
                    portadas_existentes.add(archivo['name'].strip())
            
            offset += 100
        
        # 3. Filtrar (con limpieza .strip() y conversión a int)
        df_libros['portada_esperada'] = df_libros['libro_id'].apply(lambda id: f"{int(id)}.jpg".strip())
        df_libros['tiene_portada'] = df_libros['portada_esperada'].isin(portadas_existentes)
        
        df_final = df_libros[df_libros['tiene_portada'] == True].copy()
        df_final.drop(columns=['portada_esperada', 'tiene_portada'], inplace=True)
        
        return df_final

    except Exception as e:
        print(f"Error en obtener_libros_publicables: {e}")
        return pd.DataFrame()