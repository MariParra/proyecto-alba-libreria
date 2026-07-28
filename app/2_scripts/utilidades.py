import streamlit as st
from supabase import create_client, Client
import pandas as pd
import unicodedata

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