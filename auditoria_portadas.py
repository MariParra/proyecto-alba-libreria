import os
import pandas as pd
import streamlit as st
from supabase import create_client, Client

def listar_archivos_en_storage(supabase: Client, bucket_id: str, carpeta: str = ""):
    """Consulta directa a Supabase Storage"""
    response = supabase.storage.from_(bucket_id).list(carpeta)
    nombres_de_archivos = [
        archivo['name'] for archivo in response 
        if 'metadata' in archivo and archivo['metadata'] is not None
    ]
    if not nombres_de_archivos and response:
        nombres_de_archivos = [archivo['name'] for archivo in response if archivo['name'] != '.emptyFolderPlaceholder']
    return nombres_de_archivos

def generar_excel():
    print("Conectando a Supabase...")
    # Lee los secretos tal como lo hace tu app web
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    supabase: Client = create_client(url, key)

    print("Descargando lista de archivos en Storage (bucket: 'portadas')...")
    archivos_storage = listar_archivos_en_storage(supabase, "portadas")
    
    # Quitar la extensión (.jpg, .png) para tener solo el ID
    ids_limpios = [os.path.splitext(archivo)[0] for archivo in archivos_storage]
    df_portadas = pd.DataFrame({'portada_libro_id': ids_limpios})
    
    print("Descargando base de datos de libros...")
    response = supabase.table("libros").select("libro_id, titulo, autor").execute()
    df_libros = pd.DataFrame(response.data)
    
    if df_libros.empty:
        print("⚠️ No hay libros en la base de datos.")
        return

    print("Cruzando los datos...")
    # Convertir a texto para un cruce exacto
    df_libros['libro_id_str'] = df_libros['libro_id'].astype(str)
    df_portadas['portada_libro_id'] = df_portadas['portada_libro_id'].astype(str)
    
    # Hacer el LEFT JOIN
    df_cruce = pd.merge(
        df_libros, 
        df_portadas, 
        left_on='libro_id_str', 
        right_on='portada_libro_id', 
        how='left'
    )
    
    # Crear columna True/False
    df_cruce['tiene_portada'] = df_cruce['portada_libro_id'].notna()
    
    # Limpiar columnas temporales
    df_cruce = df_cruce.drop(columns=['libro_id_str', 'portada_libro_id'])
    
    # Ordenar: primero los que NO tienen portada (False) para que sea fácil trabajar
    df_cruce = df_cruce.sort_values(by='tiene_portada')

    # Guardar el Excel
    nombre_archivo = "Reporte_Faltantes_Portadas.xlsx"
    print(f"Guardando resultados en: {nombre_archivo} ...")
    
    df_cruce.to_excel(nombre_archivo, index=False, engine='openpyxl')
    
    total = len(df_cruce)
    faltantes = len(df_cruce[df_cruce['tiene_portada'] == False])
    print(f"✅ ¡Proceso terminado! Tienes {total} libros en total, de los cuales {faltantes} no tienen portada.")

if __name__ == "__main__":
    generar_excel()