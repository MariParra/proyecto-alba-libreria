import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

def procesar_archivos_masivos(archivos):
    conn = get_db_connection()
    log_resultados = []
    chunk_size = 1000
    
    # 1. Obtener clientes con su RUT (PAGINACIÓN SUPABASE)
    all_clients = []
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_clientes = conn.table("clientes")\
            .select("cliente_id, nombre, rut")\
            .order("cliente_id")\
            .range(start, end).execute()
        if res_clientes.data:
            all_clients.extend(res_clientes.data)
            if len(res_clientes.data) < chunk_size:
                break
        else:
            break
    clientes_db = all_clients if all_clients else []

    # 2. Precargar catálogo de libros (PAGINACIÓN SUPABASE)
    all_books = []
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_libros = conn.table("libros")\
            .select("libro_id, titulo")\
            .order("libro_id")\
            .range(start, end).execute()
        if res_libros.data:
            all_books.extend(res_libros.data)
            if len(res_libros.data) < chunk_size:
                break
        else:
            break

    inventario_titulos = {limpiar_texto_para_busqueda(l['titulo']): l['libro_id'] for l in all_books} if all_books else {}

    # 3. Procesamiento de archivos
    for archivo in archivos:
        nombre_archivo_original = os.path.splitext(archivo.name)[0]
        cliente_encontrado = None
        
        # --- INTENTO 1: BUSCAR POR RUT ---
        rut_en_archivo = re.sub(r'[^0-9kK]', '', nombre_archivo_original)
        
        if len(rut_en_archivo) >= 7:
            for cliente in clientes_db:
                rut_cliente_bruto = str(cliente.get('rut', ''))
                rut_db_limpio = re.sub(r'[^0-9kK]', '', rut_cliente_bruto)
                if rut_db_limpio and rut_db_limpio == rut_en_archivo:
                    cliente_encontrado = cliente
                    break

        # --- INTENTO 2: BUSCAR POR NOMBRE ---
        if not cliente_encontrado:
            nombre_archivo_limpio = limpiar_texto_para_busqueda(nombre_archivo_original)
            for cliente in clientes_db:
                nombre_cliente_limpio = limpiar_texto_para_busqueda(cliente['nombre'])
                if nombre_cliente_limpio and nombre_cliente_limpio in nombre_archivo_limpio:
                    cliente_encontrado = cliente
                    break

        if not cliente_encontrado:
            log_resultados.append(f"⚠️ {archivo.name}: No se encontró cliente coincidente por RUT ni por nombre.")
            continue
            
        cliente_id = cliente_encontrado['cliente_id']
        
        # 4. Cargar todo el historial del cliente (PAGINACIÓN SUPABASE)
        # Esto precarga los IDs de libros que la clienta ya posee para evitar hacer consultas fila por fila
        libros_historico_cliente = set()
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_hist = conn.table("librero_historico")\
                .select("libro_id")\
                .eq("cliente_id", cliente_id)\
                .range(start, end).execute()
            if res_hist.data:
                libros_historico_cliente.update(item['libro_id'] for item in res_hist.data)
                if len(res_hist.data) < chunk_size:
                    break
            else:
                break
        
        try:
            df = pd.read_excel(archivo) if archivo.name.lower().endswith('.xlsx') else pd.read_csv(archivo)
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Error leyendo el archivo '{archivo.name}'. Detalle: {e}"
            log_error(
                vista="vista_libreros",
                funcion="procesar_archivos_masivos (lectura archivo)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            log_resultados.append(f"❌ {archivo.name}: Error al leer el archivo.")
            continue

        col_titulo = next((c for c in df.columns if str(c).lower().strip() in ['titulo', 'título', 'libro']), None)

        if not col_titulo:
            log_resultados.append(f"⚠️ {archivo.name}: No se encontró columna 'Título'.")
            continue

        libros_asignados = 0
        for _, row in df.iterrows():
            titulo_raw = row.get(col_titulo)
            if pd.isna(titulo_raw) or not str(titulo_raw).strip(): 
                continue
            
            titulo_norm = limpiar_texto_para_busqueda(str(titulo_raw))
            libro_id = inventario_titulos.get(titulo_norm)

            # Si el libro existe en el catálogo y NO está en el historial del cliente
            if libro_id and libro_id not in libros_historico_cliente:
                conn.table("librero_historico").insert({
                    "cliente_id": cliente_id, 
                    "libro_id": libro_id, 
                    "origen": "IMPORTACIÓN MASIVA"
                }).execute()
                libros_historico_cliente.add(libro_id) # Se agrega al set local para no duplicar si viene 2 veces en el Excel
                libros_asignados += 1
        
        # --- BLOQUE DE GUARDADO DE FECHA ---
        try:
            update_response = conn.table("clientes").update({
                "fecha_actualizacion_librero": datetime.now().isoformat()
            }).eq("cliente_id", cliente_id).execute()

            if update_response.data:
                log_resultados.append(f"✅ {archivo.name}: {libros_asignados} libros nuevos enlazados. Fecha actualizada para {cliente_encontrado['nombre']}.")
            else:
                log_resultados.append(f"❌ {archivo.name}: Se enlazaron {libros_asignados} libros, pero NO SE PUDO guardar la fecha para {cliente_encontrado['nombre']}.")
        
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Error CRÍTICO al guardar la fecha para {cliente_encontrado['nombre']} (ID: {cliente_id}). Detalle: {e}"
            log_error(
                vista="vista_libreros",
                funcion="procesar_archivos_masivos (guardar fecha)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            log_resultados.append(f"❌ Error CRÍTICO al registrar la fecha para {cliente_encontrado['nombre']}: {e}")
            
    st.cache_data.clear()
    return log_resultados
