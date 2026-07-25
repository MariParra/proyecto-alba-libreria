import streamlit as st
from supabase import create_client, Client
import pandas as pd

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
    """Función de utilidad para limpiar texto para búsquedas."""
    if texto is None:
        return ""
    return str(texto).strip().lower()