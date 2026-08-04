import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto, log_error

# --- VERSIÓN DEFINITIVA DE LA FUNCIÓN DE PROCESAMIENTO ---
def procesar_archivos_masivos(archivos):
    conn = get_db_connection()
    log_resultados = []
    
    # 1. Obtener clientes con su RUT
    res_clientes = conn.table("clientes").select("cliente_id, nombre, rut").execute()
    clientes_db = res_clientes.data if res_clientes.data else []

    # 2. Precargar catálogo de libros
    res_libros = conn.table("libros").select("libro_id, titulo").execute()
    inventario_titulos = {limpiar_texto(l['titulo']): l['libro_id'] for l in res_libros.data} if res_libros.data else {}

    for archivo in archivos:
        nombre_archivo_original = os.path.splitext(archivo.name)[0]
        cliente_encontrado = None
        
        # --- INTENTO 1: BUSCAR POR RUT (Lógica Simple y Robusta) ---
        # Limpia el nombre del archivo para dejar solo números y 'k'
        rut_en_archivo = re.sub(r'[^0-9kK]', '', nombre_archivo_original)
        
        if len(rut_en_archivo) >= 7: # Solo intenta si parece un RUT
            for cliente in clientes_db:
                rut_cliente_bruto = str(cliente.get('rut', ''))
                # Limpia el RUT de la base de datos
                rut_db_limpio = re.sub(r'[^0-9kK]', '', rut_cliente_bruto)
                
                # Compara los RUTs limpios
                if rut_db_limpio and rut_db_limpio == rut_en_archivo:
                    cliente_encontrado = cliente
                    break

        # --- INTENTO 2: BUSCAR POR NOMBRE (Plan B) ---
        if not cliente_encontrado:
            nombre_archivo_limpio = limpiar_texto(nombre_archivo_original)
            for cliente in clientes_db:
                nombre_cliente_limpio = limpiar_texto(cliente['nombre'])
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
            error_detalle = f"Error leyendo el archivo '{archivo.name}'. Podría estar corrupto, tener un formato inválido o una contraseña. Detalle: {e}"
            log_error(
                vista="vista_libreros",
                funcion="procesar_archivos_masivos (lectura archivo)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            log_resultados.append(f"❌ {archivo.name}: Error al leer. El archivo podría estar dañado o tener un formato incorrecto.")
            continue

        col_titulo = next((c for c in df.columns if str(c).lower().strip() in ['titulo', 'título', 'libro']), None)
        if not col_titulo:
            log_resultados.append(f"⚠️ {archivo.name}: No se encontró columna 'Título'.")
            continue

        libros_asignados = 0
        for _, row in df.iterrows():
            titulo_raw = row.get(col_titulo)
            if pd.isna(titulo_raw) or not str(titulo_raw).strip(): continue
            
            titulo_norm = limpiar_texto(str(titulo_raw))
            libro_id = inventario_titulos.get(titulo_norm)

            if libro_id:
                res_hist = conn.table("librero_historico").select("registro_id", count='exact').eq("cliente_id", cliente_id).eq("libro_id", libro_id).execute()
                if res_hist.count == 0:
                    conn.table("librero_historico").insert({"cliente_id": cliente_id, "libro_id": libro_id, "origen": "IMPORTACIÓN MASIVA"}).execute()
                    libros_asignados += 1
        
        # --- BLOQUE DE GUARDADO DE FECHA (CORREGIDO Y BLINDADO) ---
        try:
            # Enviamos la orden de actualización a Supabase
            update_response = conn.table("clientes").update({
                "fecha_actualizacion_librero": datetime.now().isoformat()
            }).eq("cliente_id", cliente_id).execute()

            # Verificamos si la actualización fue exitosa
            if update_response.data:
                log_resultados.append(f"✅ {archivo.name}: {libros_asignados} libros nuevos enlazados. Fecha actualizada para {cliente_encontrado['nombre']}.")
            else:
                # Esto captura si la base de datos no actualizó la fila por alguna razón
                log_resultados.append(f"❌ {archivo.name}: Se enlazaron {libros_asignados} libros, pero NO SE PUDO guardar la fecha para {cliente_encontrado['nombre']}. Verifique el ID del cliente.")
        
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Error CRÍTICO al guardar la fecha para {cliente_encontrado['nombre']} (ID: {cliente_id}) del archivo '{archivo.name}'. Detalle: {e}"
            log_error(
                vista="vista_libreros",
                funcion="procesar_archivos_masivos (guardar fecha)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            log_resultados.append(f"❌ Error CRÍTICO al registrar la fecha para {cliente_encontrado['nombre']}: {e}")
            
    st.cache_data.clear()
    return log_resultados

# --- La función mostrar_importacion_libreros() no necesita cambios ---
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