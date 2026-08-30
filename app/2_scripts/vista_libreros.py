import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# --- VERSIÓN DEFINITIVA CORREGIDA ---
def procesar_archivos_masivos(archivos):
    conn = get_db_connection()
    log_resultados = []
    chunk_size = 1000
    
    # 1. Obtener clientes con su RUT (PAGINADO PARA BYPASS LÍMITE DE 1000)
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

    # 2. Precargar catálogo de libros (PAGINADO PARA BYPASS LÍMITE DE 1000)
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

    # 📌 DIAGNÓSTICOS DE CATÁLOGO (Ahora sí con los datos cargados)
    st.write(f"📚 **Total libros cargados desde Supabase:** {len(all_books)}")

    inventario_titulos = {limpiar_texto_para_busqueda(l['titulo']): l['libro_id'] for l in all_books} if all_books else {}

    veil_en_dict = {k: v for k, v in inventario_titulos.items() if 'VEIL' in k}
    st.write("🔎 **Títulos con 'VEIL' en diccionario:**", veil_en_dict)

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
        
        # 📌 DIAGNÓSTICO DE COLUMNA DETECTADA
        st.write(f"🎯 **Columna detectada:** '{col_titulo}'")

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

            # 📌 DIAGNÓSTICO POR FILA
            st.write(f"• Fila Excel: **'{titulo_raw}'** -> Buscado como: **'{titulo_norm}'** -> ID en BD: **{libro_id}**")

            if libro_id:
                res_hist = conn.table("librero_historico").select("registro_id", count='exact').eq("cliente_id", cliente_id).eq("libro_id", libro_id).execute()
                
                # 📌 DIAGNÓSTICO DE EXISTENCIA EN HISTORIAL
                st.write(f"  └─ ¿Ya existe en historial?: **{res_hist.count > 0}** (Count: {res_hist.count})")

                if res_hist.count == 0:
                    conn.table("librero_historico").insert({"cliente_id": cliente_id, "libro_id": libro_id, "origen": "IMPORTACIÓN MASIVA"}).execute()
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


def mostrar_importacion_libreros():
    st.title("📚 Importar Historial de Lectura")
    st.info("💡 Sube los archivos. El sistema buscará a la clienta según el nombre del archivo y solo enlazará los libros que ya existan en tu catálogo.")
    
    archivos = st.file_uploader("Selecciona archivos Excel/CSV", type=["xlsx", "csv"], accept_multiple_files=True)
    
    if archivos and st.button("Iniciar Importación", type="primary"):
        with st.spinner("Procesando..."):
            logs = procesar_archivos_masivos(archivos)
            st.markdown("---")
            st.markdown("### Resultados de la Importación")
            for log in logs:
                if "✅" in log:
                    st.success(log)
                elif "⚠️" in log:
                    st.warning(log)
                else:
                    st.error(log)
