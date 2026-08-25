# cache_utils.py
import streamlit as st
import pandas as pd
from utilidades import get_db_connection
from datetime import datetime

@st.cache_data(ttl=1800) 
def obtener_libros_publicables():
    """
    Filtro Maestro: Obtiene libros visibles, con precio > 0 y con portada en el bucket.
    Versión blindada contra el límite de 1000 registros, caracteres invisibles y descuentos expirados.
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

        # 🌟 LÓGICA DE AUTOCORRECCIÓN DE DESCUENTOS EXPIRADOS (EVITA EL BUG EN EL CATÁLOGO PÚBLICO)
        hoy = pd.Timestamp(datetime.now().date())
        
        if 'precio' in df_libros.columns:
            df_libros['precio'] = pd.to_numeric(df_libros['precio'], errors='coerce').fillna(0.0)
        if 'precio_original' in df_libros.columns:
            df_libros['precio_original'] = pd.to_numeric(df_libros['precio_original'], errors='coerce').fillna(df_libros['precio'])
        else:
            df_libros['precio_original'] = df_libros['precio']

        if 'descuento_inicio' in df_libros.columns and 'descuento_fin' in df_libros.columns:
            df_libros['f_ini_dt'] = pd.to_datetime(df_libros['descuento_inicio'], errors='coerce') 
            df_libros['f_fin_dt'] = pd.to_datetime(df_libros['descuento_fin'], errors='coerce')
            
            # Identificar libros cuyo descuento ya no está vigente en la fecha de hoy
            mask_expirado = (
                (df_libros['precio_original'] > df_libros['precio']) & 
                (
                    ((df_libros['f_ini_dt'].notna()) & (df_libros['f_ini_dt'] > hoy)) | 
                    ((df_libros['f_fin_dt'].notna()) & (df_libros['f_fin_dt'] < hoy))
                )
            )
            
            # Restaurar precio en memoria inmediatamente
            if mask_expirado.any():
                df_libros.loc[mask_expirado, 'precio'] = df_libros.loc[mask_expirado, 'precio_original']
                
                # Sincronizar actualización masiva de precios en Supabase de forma transparente
                try:
                    libros_a_restaurar = df_libros.loc[mask_expirado, ['libro_id', 'precio_original']].copy()
                    libros_a_restaurar.rename(columns={'precio_original': 'precio'}, inplace=True)
                    libros_a_restaurar['libro_id'] = libros_a_restaurar['libro_id'].astype(int)
                    libros_a_restaurar['precio'] = libros_a_restaurar['precio'].astype(float)
                    
                    datos_restaurar = libros_a_restaurar.to_dict(orient='records')
                    if datos_restaurar:
                        conn.table("libros").upsert(datos_restaurar, on_conflict='libro_id').execute()
                except Exception as ex_db:
                    print(f"Error al restaurar precios expirados en cache_utils: {ex_db}")

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
            
            for archivo in bloque:
                if archivo['name'] is not None:
                    portadas_existentes.add(archivo['name'].strip())
            
            offset += 100
        
        # 3. Filtrar por portadas existentes en bucket
        df_libros['portada_esperada'] = df_libros['libro_id'].apply(lambda id: f"{int(id)}.jpg".strip())
        df_libros['tiene_portada'] = df_libros['portada_esperada'].isin(portadas_existentes)
        
        df_final = df_libros[df_libros['tiene_portada'] == True].copy()
        
        # Limpieza de columnas auxiliares
        columnas_a_borrar = ['portada_esperada', 'tiene_portada']
        if 'f_ini_dt' in df_final.columns:
            columnas_a_borrar.extend(['f_ini_dt', 'f_fin_dt'])
        df_final.drop(columns=columnas_a_borrar, inplace=True, errors='ignore')
        
        return df_final

    except Exception as e:
        print(f"Error en obtener_libros_publicables: {e}")
        return pd.DataFrame()