import streamlit as st
import pandas as pd
import os
from utilidades import get_db_connection, limpiar_texto

def procesar_archivos_masivos(archivos):
    """
    Toma una lista de archivos, busca al cliente por el nombre del archivo,
    y carga sus libros en el historial (librero_historico) y en el catálogo si no existen.
    """
    conn = get_db_connection()
    
    # Contadores de métricas
    log_resultados = []
    total_libros_nuevos_catalogo = 0
    total_libros_asignados_historial = 0
    
    # Elementos visuales
    barra_progreso = st.progress(0, text="Iniciando importación masiva...")
    total_archivos = len(archivos)

    for i, archivo in enumerate(archivos):
        # 1. El nombre del archivo es el nombre del cliente (sin la extensión .xlsx o .csv)
        nombre_cliente_archivo = os.path.splitext(archivo.name)[0]
        nombre_limpio = limpiar_texto(nombre_cliente_archivo)
        
        # Actualizamos la barra de progreso
        barra_progreso.progress((i) / total_archivos, text=f"Procesando: {archivo.name}...")
        
        # 2. Buscar al cliente en la base de datos
        res_cliente = conn.table("clientes").select("cliente_id, nombre").ilike("nombre", f"%{nombre_limpio}%").execute()
        
        if not res_cliente.data:
            log_resultados.append(f"❌ **{archivo.name}**: No se encontró un cliente similar a '{nombre_cliente_archivo}' en la base de datos.")
            continue
            
        cliente_id = res_cliente.data[0]['cliente_id']
        nombre_cliente_bd = res_cliente.data[0]['nombre']
        
        # 3. Leer el archivo (Soporta Excel y CSV)
        try:
            if archivo.name.endswith('.csv'):
                df = pd.read_csv(archivo)
            else:
                df = pd.read_excel(archivo)
        except Exception as e:
            log_resultados.append(f"❌ **{archivo.name}**: El archivo está dañado o no se pudo leer ({e}).")
            continue
            
        # 4. Identificar las columnas clave (Soporta variaciones de nombre)
        col_titulo = next((c for c in df.columns if str(c).lower().strip() in ['titulo', 'título', 'libro', 'nombre libro']), None)
        col_autor = next((c for c in df.columns if str(c).lower().strip() in ['autor', 'escritor', 'autora']), None)
        
        if not col_titulo:
            log_resultados.append(f"⚠️ **{archivo.name}**: No se encontró una columna llamada 'Título' o 'Libro'. Se ignoró el archivo.")
            continue
            
        libros_procesados_este_archivo = 0
        
        # 5. Procesar fila por fila (cada libro)
        for index, row in df.iterrows():
            titulo_raw = row.get(col_titulo, "")
            if pd.isna(titulo_raw) or str(titulo_raw).strip() == "":
                continue
                
            titulo = limpiar_texto(str(titulo_raw))
            autor = limpiar_texto(str(row.get(col_autor, ""))) if col_autor else "Desconocido"
            
            # --- A. Revisar Catálogo General ---
            res_libro = conn.table("libros").select("libro_id").eq("titulo", titulo).execute()
            if not res_libro.data:
                # Si el libro no existe en el sistema, lo crea con stock 0
                res_insert = conn.table("libros").insert({"titulo": titulo, "autor": autor, "precio": 0, "stock": 0}).execute()
                l_id = res_insert.data[0]['libro_id']
                total_libros_nuevos_catalogo += 1
            else:
                l_id = res_libro.data[0]['libro_id']
                
            # --- B. Revisar Historial del Cliente ---
            res_historial = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", l_id).execute()
            if not res_historial.data:
                # Si el cliente no lo tiene anotado, se lo agregamos a su librero
                conn.table("librero_historico").insert({
                    "cliente_id": cliente_id, "libro_id": l_id, 
                    "autor_historico": autor, "origen": "IMPORTACIÓN INICIAL"
                }).execute()
                libros_procesados_este_archivo += 1
                total_libros_asignados_historial += 1
                
        log_resultados.append(f"✅ **{archivo.name}**: Emparejado con {nombre_cliente_bd}. Se añadieron {libros_procesados_este_archivo} libros a su historial.")
        
    barra_progreso.progress(1.0, text="¡Importación completada!")
    return log_resultados, total_libros_nuevos_catalogo, total_libros_asignados_historial

# --- INTERFAZ PRINCIPAL ---
def mostrar_importacion_libreros():
    st.title("📚 Importar Libreros Masivamente")
    
    with st.container(border=True):
        st.markdown("### 📥 Carga de Archivos (Múltiples)")
        st.info("💡 **Instrucciones:** Nombra cada archivo Excel o CSV con el nombre de tu clienta (Ej: `Mariana Parra.xlsx`). El sistema leerá automáticamente el archivo y asignará los libros a su historial.")
        
        # Permitimos carga masiva (drag and drop de múltiples archivos)
        archivos_subidos = st.file_uploader(
            "Arrastra aquí la carpeta completa, o selecciona múltiples archivos Excel/CSV", 
            type=["xlsx", "xls", "csv"], 
            accept_multiple_files=True
        )
        
        if archivos_subidos:
            st.write(f"📂 Has cargado **{len(archivos_subidos)}** archivos listos para procesar.")
            
            if st.button("🚀 Iniciar Importación Masiva a la Base de Datos", type="primary", use_container_width=True):
                with st.spinner("Procesando la información..."):
                    # Ejecutamos la magia
                    logs, libros_nuevos, asignaciones = procesar_archivos_masivos(archivos_subidos)
                    
                    st.markdown("---")
                    st.markdown("### 📊 Resumen de Importación")
                    c1, c2 = st.columns(2)
                    c1.metric("📚 Libros Nuevos Agregados al Catálogo", libros_nuevos)
                    c2.metric("👤 Asignaciones al Historial de Clientes", asignaciones)
                    
                    # Desplegable con el detalle archivo por archivo
                    with st.expander("📋 Ver detalle archivo por archivo", expanded=True):
                        for log in logs:
                            st.write(log)
                            
                    st.success("¡El proceso ha finalizado correctamente!")