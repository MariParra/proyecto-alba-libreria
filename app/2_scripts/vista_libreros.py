import streamlit as st
import pandas as pd
import os
import unicodedata
from utilidades import get_db_connection, limpiar_texto

def normalizar_texto(texto):
    """Normaliza el texto para búsquedas exactas (sin acentos, en mayúsculas)."""
    if not isinstance(texto, str): return ""
    s = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
    return ' '.join(s.strip().upper().split())

def procesar_archivos_masivos(archivos):
    conn = get_db_connection()
    log_resultados = []
    
    # 1. Obtener clientes
    res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
    clientes_db = res_clientes.data if res_clientes.data else []

    # 2. Precargar catálogo de libros para no consultar la BD por cada fila
    res_libros = conn.table("libros").select("libro_id, titulo, autor").execute()
    inventario_titulos = {normalizar_texto(l['titulo']): l['libro_id'] for l in res_libros.data} if res_libros.data else {}

    for archivo in archivos:
        nombre_archivo_limpio = limpiar_texto(os.path.splitext(archivo.name)[0])
        cliente_encontrado = None
        
        # Buscar cliente por nombre en el archivo
        for cliente in clientes_db:
            if limpiar_texto(cliente['nombre']) in nombre_archivo_limpio:
                cliente_encontrado = cliente
                break

        if not cliente_encontrado:
            log_resultados.append(f"⚠️ {archivo.name}: No se encontró un cliente coincidente.")
            continue
            
        cliente_id = cliente_encontrado['cliente_id']
        
        try:
            if archivo.name.lower().endswith('.csv'):
                df = pd.read_csv(archivo)
            else:
                df = pd.read_excel(archivo, engine='openpyxl') # Asegúrate de tener openpyxl instalado
        except Exception as e:
            log_resultados.append(f"❌ {archivo.name}: Error al leer el archivo. {e}")
            continue

        # Buscar columnas clave
        col_titulo = next((c for c in df.columns if str(c).lower().strip() in ['titulo', 'título', 'libro']), None)
        col_autor = next((c for c in df.columns if str(c).lower().strip() in ['autor', 'escritor']), None)

        if not col_titulo:
            log_resultados.append(f"⚠️ {archivo.name}: No se encontró columna 'Título'.")
            continue

        libros_asignados = 0
        for _, row in df.iterrows():
            titulo_raw = row.get(col_titulo)
            if pd.isna(titulo_raw) or str(titulo_raw).strip() == "": continue
            
            titulo_norm = normalizar_texto(str(titulo_raw))
            libro_id = inventario_titulos.get(titulo_norm)

            if libro_id:
                # Verificar si ya lo tiene para no duplicar
                res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", libro_id).execute()
                if not res_hist.data:
                    autor_raw = str(row.get(col_autor, "")) if col_autor else "Desconocido"
                    conn.table("librero_historico").insert({
                        "cliente_id": cliente_id, 
                        "libro_id": libro_id, 
                        "autor_historico": autor_raw, 
                        "origen": "IMPORTACIÓN MASIVA"
                    }).execute()
                    libros_asignados += 1

        log_resultados.append(f"✅ {archivo.name}: {libros_asignados} libros enlazados al historial de {cliente_encontrado['nombre']}.")

    return log_resultados

def mostrar_importacion_libreros():
    st.title("📚 Importar Historial de Lectura")
    st.info("💡 Sube los archivos. El sistema buscará a la clienta según el nombre del archivo y solo enlazará los libros que ya existan en tu catálogo.")
    
    archivos = st.file_uploader("Selecciona archivos Excel/CSV", type=["xlsx", "csv"], accept_multiple_files=True)
    
    if archivos and st.button("Iniciar Importación", type="primary"):
        with st.spinner("Procesando..."):
            logs = procesar_archivos_masivos(archivos)
            for log in logs:
                st.write(log)