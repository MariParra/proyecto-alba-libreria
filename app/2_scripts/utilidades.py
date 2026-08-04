import streamlit as st
from supabase import create_client, Client
import pandas as pd
import unicodedata
import traceback

def get_db_connection() -> Client:
    """
    Crea y devuelve un cliente de Supabase usando los secretos
    nativos de Streamlit Cloud.
    """
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    
    # Crea el cliente de Supabase directamente
    supabase: Client = create_client(url, key)
    return supabase

def limpiar_texto(texto):
    """
    Normaliza un texto de forma exhaustiva:
    1. Convierte a string.
    2. Elimina tildes y acentos (diacríticos).
    3. Pasa todo a MAYÚSCULAS.
    4. Elimina espacios al inicio y al final.
    5. Reduce múltiples espacios internos a uno solo.
    """
    if texto is None:
        return ""
    
    # Convierte a string por seguridad
    texto_str = str(texto)
    
    # Elimina tildes y acentos de forma robusta
    s = ''.join(c for c in unicodedata.normalize('NFD', texto_str) if unicodedata.category(c) != 'Mn')
    
    # Pasa a mayúsculas, elimina espacios extra y retorna
    return ' '.join(s.strip().upper().split())

def log_error(vista, funcion, error, email_usuario="No disponible"):
    """
    Registra un error de la aplicación en la tabla 'errores_app',
    incluyendo el email del usuario que lo experimentó.
    """
    try:
        conn = get_db_connection()
        traceback_completo = traceback.format_exc()
        
        datos_error = {
            "vista": vista,
            "funcion": funcion,
            "mensaje_error": str(error),
            "traceback": traceback_completo,
            "email_usuario": email_usuario
        }
        
        conn.table("errores_app").insert(datos_error).execute()
        
    except Exception as e:
        print(f"--- ERROR CRÍTICO EN EL SISTEMA DE LOGS ---")
        print(f"No se pudo registrar el siguiente error en Supabase: {str(error)}")
        print(f"Causa del fallo en el log: {str(e)}")