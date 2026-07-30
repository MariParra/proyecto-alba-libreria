import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime
from utilidades import get_db_connection, normalizar_texto, limpiar_texto

def procesar_archivos_masivos(archivos):
    conn = get_db_connection()
    log_resultados = []
    
    # 1. Obtener clientes
    res_clientes = conn.table("clientes").select("cliente_id, nombre, rut").execute()
    clientes_db = res_clientes.data if res_clientes.data else []

    # 2. Precargar catálogo de libros para no consultar la BD por cada fila
    res_libros = conn.table("libros").select("libro_id, titulo, autor").execute()
    inventario_titulos = {normalizar_texto(l['titulo']): l['libro_id'] for l in res_libros.data} if res_libros.data else {}

    for archivo in archivos:
        # Extraemos el nombre original (ej: "Librero_19.375.695-6_Mariana.xlsx")
        nombre_archivo_original = os.path.splitext(archivo.name)[0]
        
        # Preparamos dos versiones del nombre del archivo para los dos intentos
        nombre_archivo_solo_letras = limpiar_texto(nombre_archivo_original)
        # Extrae SOLO números y la letra K del nombre del archivo
        nombre_archivo_solo_rut = re.sub(r'[^0-9kK]', '', nombre_archivo_original).upper()
        
        cliente_encontrado = None
        
        # --- INTENTO 1: BUSCAR POR RUT (Infalible y Normalizado) ---
        for cliente in clientes_db:
            rut_cliente_bruto = str(cliente.get('rut', ''))
            # Limpiamos el RUT de la Base de Datos (quita puntos y guiones)
            rut_db_limpio = re.sub(r'[^0-9kK]', '', rut_cliente_bruto).upper()
            
            # Verificamos que el RUT exista y tenga largo de RUT chileno (mínimo 7-8 caracteres)
            if rut_db_limpio and len(rut_db_limpio) >= 7:
                # Si el RUT crudo está dentro del nombre del archivo crudo = MATCH PERFECTO
                if rut_db_limpio in nombre_archivo_solo_rut:
                    cliente_encontrado = cliente
                    break

        # --- INTENTO 2: BUSCAR POR NOMBRE (Plan B) ---
        if not cliente_encontrado:
            for cliente in clientes_db:
                if limpiar_texto(cliente['nombre']) in nombre_archivo_solo_letras:
                    cliente_encontrado = cliente
                    break

        # Si fallan ambos intentos, saltamos este archivo
        if not cliente_encontrado:
            log_resultados.append(f"⚠️ {archivo.name}: No se encontró un cliente coincidente por RUT ni por nombre.")
            continue
            
        cliente_id = cliente_encontrado['cliente_id']
        
        try:
            if archivo.name.lower().endswith('.csv'):
                df = pd.read_csv(archivo)
            else:
                df = pd.read_excel(archivo, engine='openpyxl')
        except Exception as e:
            log_resultados.append(f"❌ {archivo.name}: Error al leer el archivo. {e}")
            continue

        # Búsqueda de las columnas clave (Título y Autor)
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
                # Verificamos si la clienta ya tiene este libro en su histórico
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
        
        # --- REGISTRO DE TIMESTAMP AL FINALIZAR ---
        try:
            conn.table("clientes").update({
                "fecha_actualizacion_librero": datetime.now().isoformat()
            }).eq("cliente_id", cliente_id).execute()
            
            log_resultados.append(f"✅ {archivo.name}: {libros_asignados} libros nuevos enlazados. Fecha actualizada para {cliente_encontrado['nombre']}.")
        except Exception as e:
            log_resultados.append(f"❌ Error al registrar la fecha para {cliente_encontrado['nombre']}: {e}")
            
    # Limpiamos caché para que las demás vistas lean los datos frescos
    st.cache_data.clear()

    return log_resultados

def mostrar_importacion_libreros():
    st.markdown("<h2 style='color: #4A4D7E;'>📔 Importación Masiva de Libreros</h2>", unsafe_allow_html=True)
    st.markdown("""
    Sube los archivos Excel o CSV con los libreros de las clientas. 
    * **Tip UX:** Nombra el archivo con el **RUT** de la clienta (con o sin puntos/guiones, el sistema lo detectará igual). Si no usas el RUT, nómbralo con su **Nombre**. El sistema enlazará los libros y actualizará su fecha de última subida.
    """)
    
    with st.container(border=True):
        archivos_subidos = st.file_uploader(
            "Arrastra aquí todos los archivos (Excel o CSV)", 
            type=['xlsx', 'csv'], 
            accept_multiple_files=True
        )
        
        if archivos_subidos:
            st.info(f"Se han cargado {len(archivos_subidos)} archivo(s) listos para procesar.")
            
            if st.button("🚀 Iniciar Procesamiento Masivo", type="primary", use_container_width=True):
                with st.spinner("Procesando archivos, limpiando RUTs y actualizando fechas..."):
                    resultados = procesar_archivos_masivos(archivos_subidos)
                    
                    st.markdown("### 📊 Resultados del Proceso")
                    for msj in resultados:
                        if "✅" in msj:
                            st.success(msj)
                        elif "⚠️" in msj:
                            st.warning(msj)
                        else:
                            st.error(msj)
                    
                    st.balloons()