import streamlit as st
import json
import time
from utilidades import get_db_connection

def mostrar_rollback():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⏪ Rollback de Base de Datos")
    
    st.info("💡 **¿Cómo usar esta herramienta?**\n"
            "1. Ve a Google Cloud Storage y descarga el archivo JSON del día que quieres restaurar.\n"
            "2. Selecciona aquí a qué tabla pertenece ese archivo.\n"
            "3. Sube el archivo y presiona Restaurar. El sistema actualizará o re-creará los registros perdidos.")
    
    with st.container(border=True):
        st.markdown("### 🛠️ Configuración de Restauración")
        
        # 1. Selector de tabla
        tablas_disponibles = [
            "asignaciones", "clientes", "librero_historico", 
            "libros", "meses_cerrados", "registro_ventas", 
            "suscripciones", "tareas_internas", "tareas_comentarios"
        ]
        tabla_seleccionada = st.selectbox("1. Selecciona la tabla que deseas restaurar:", tablas_disponibles)
        
        # 2. Subida del archivo de respaldo
        archivo_respaldo = st.file_uploader("2. Sube el archivo de respaldo (.json):", type=['json'])
        
        st.markdown("---")
        st.warning("⚠️ **CUIDADO:** Esta acción sobreescribirá los datos actuales en Supabase con los del archivo de respaldo. Asegúrate de estar subiendo el archivo correcto.")
        
        # 3. Botón de ejecución
        if archivo_respaldo is not None:
            confirmacion = st.text_input(f"Escribe el nombre de la tabla ('{tabla_seleccionada}') para confirmar:")
            
            if confirmacion == tabla_seleccionada:
                if st.button("🚨 EJECUTAR ROLLBACK", type="primary", use_container_width=True):
                    with st.spinner(f"Procesando archivo para la tabla '{tabla_seleccionada}'..."):
                        try:
                            # Leer y decodificar el archivo NDJSON
                            registros = []
                            contenido = archivo_respaldo.getvalue().decode("utf-8")
                            for linea in contenido.splitlines():
                                if linea.strip():
                                    registros.append(json.loads(linea))
                            
                            total_registros = len(registros)
                            if total_registros == 0:
                                st.error("El archivo está vacío o no tiene el formato correcto.")
                                return
                                
                            st.info(f"📦 Se encontraron {total_registros} filas para restaurar. Iniciando subida...")
                            
                            # Conectar a Supabase
                            conn = get_db_connection()
                            tamanio_lote = 100
                            exitosos = 0
                            
                            # Barra de progreso visual
                            progress_bar = st.progress(0, text="Iniciando restauración...")
                            
                            # Inserción en lotes (Upsert)
                            for i in range(0, total_registros, tamanio_lote):
                                lote = registros[i:i + tamanio_lote]
                                
                                # .upsert() actualiza si existe, inserta si no existe
                                conn.table(tabla_seleccionada).upsert(lote).execute()
                                
                                exitosos += len(lote)
                                avance = exitosos / total_registros
                                progress_bar.progress(avance, text=f"Restaurando... {exitosos}/{total_registros} filas")
                                
                            st.success(f"🎉 ¡Rollback completado con éxito! Se restauraron {exitosos} registros en '{tabla_seleccionada}'.")
                            st.balloons()
                            
                        except Exception as e:
                            st.error(f"❌ Error crítico durante el rollback: {str(e)}")
                            st.caption("Verifica que tu aplicación web tenga permisos de escritura (Service Role) en Supabase para realizar restauraciones masivas.")