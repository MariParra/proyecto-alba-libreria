import psycopg2
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

@st.cache_resource
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def limpiar_texto(texto):
    """Elimina espacios extra y convierte todo a MAYÚSCULAS."""
    if not texto: return ""
    return " ".join(str(texto).split()).upper()

def ejecutar_query_escritura(query, params):
    """Ejecuta INSERT, UPDATE o DELETE de forma segura."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
        st.cache_data.clear()
        return True, None
    except psycopg2.Error as e:
        conn.rollback()
        return False, str(e)