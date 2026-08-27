import streamlit as st
import json
import time
from utilidades import get_db_connection, log_error

def mostrar_rollback():
    # --- TODA TU LÓGICA DE INTERFAZ ORIGINAL SE MANTIENE INTACTA ---
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⏪ Rollback de Base de Datos")
    
    st.info("💡 **¿Cómo usar esta herramienta?**\n"
            "1. Ve a Google Cloud Storage y descarga el archivo JSON del día que quieres restaurar.\n"
            "2. Selecciona aquí a qué tabla pertenece ese archivo.\n"
            "3. Sube el archivo y presiona Restaurar. El sistema actualizará o re-creará los registros perdidos.")
    
    with st.container(border=True):
        st.markdown("### 🛠️ Configuración de Restauración")
        
        # 🌟 SE INCORPORAN LAS TABLAS FALTANTES DEL ESQUEMA OFICIAL DE ALBA LIBRERÍA
        tablas_disponibles = [
            "asignaciones", 
            "clientes", 
            "costos_no_ventas", 
            "librero_historico", 
            "libros", 
            "meses_cerrados", 
            "registro_ventas", 
            "suscripciones", 
            "tareas_internas", 
            "tareas_comentarios",
            "ventas_masivas",           # ¡FALTABA! Tabla operacional crítica de ventas de eventos masivos
            "errores_app",              # Tabla de auditoría de errores de sistema
            "historial_logs",           # logs de cambios de auditoría
            "historial_cambios_masivos"  # logs de cambios masivos aplicados
        ]
        
        # UX GUIDELINE: Inicializar con index=None para forzar una selección explícita y evitar rollbacks accidentales
        tabla_seleccionada = st.selectbox(
            "1. Selecciona la tabla que deseas restaurar:", 
            tablas_disponibles,
            index=None,
            placeholder="Selecciona una tabla para restaurar..."
        )
        
        if not tabla_seleccionada:
            st.info("👈 Por favor, selecciona una tabla para comenzar.")
            return

        # Generar llave dinámica para reiniciar el file uploader si cambia la tabla
        file_key = f"up_rollback_{tabla_seleccionada}"
        archivo_respaldo = st.file_uploader("2. Sube el archivo de respaldo (.json):", type=['json'], key=file_key)
        
        st.markdown("---")
        st.warning(f"⚠️ **CUIDADO:** Esta acción sobreescribirá los datos actuales en la tabla '{tabla_seleccionada}' de Supabase con los del archivo de respaldo. Asegúrate de estar subiendo el archivo correcto.")
        
        if archivo_respaldo is not None:
            confirmacion = st.text_input(f"Escribe el nombre de la tabla ('{tabla_seleccionada}') para confirmar:")
            
            if confirmacion == tabla_seleccionada:
                if st.button("🚨 EJECUTAR ROLLBACK", type="primary", use_container_width=True):
                    with st.spinner(f"Procesando archivo para la tabla '{tabla_seleccionada}'..."):
                        try:
                            registros = []
                            contenido = archivo_respaldo.getvalue().decode("utf-8")
                            for linea in contenido.splitlines():
                                if linea.strip():
                                    registros.append(json.loads(linea))
                            
                            total_registros = len(registros)
                            if total_registros == 0:
                                st.error("El archivo está vacío o no tiene el formato correcto (debe ser formato JSON Lines / NDJSON).")
                                return
                                
                            st.info(f"📦 Se encontraron {total_registros} filas para restaurar. Iniciando subida...")
                            
                            conn = get_db_connection()
                            tamanio_lote = 100
                            exitosos = 0
                            
                            progress_bar = st.progress(0, text="Iniciando restauración...")
                            
                            for i in range(0, total_registros, tamanio_lote):
                                lote = registros[i:i + tamanio_lote]
                                conn.table(tabla_seleccionada).upsert(lote).execute()
                                
                                exitosos += len(lote)
                                avance = exitosos / total_registros
                                progress_bar.progress(avance, text=f"Restaurando... {exitosos}/{total_registros} filas")
                                
                            st.success(f"🎉 ¡Rollback completado con éxito! Se restauraron {exitosos} registros en '{tabla_seleccionada}'.")
                            st.balloons()
                            
                            # 🚨 CORE FIX: Limpiar el caché de Streamlit de inmediato para que toda la aplicación cargue la nueva data restaurada
                            st.cache_data.clear()
                            
                            # UX PATTERN: Eliminar la llave de estado del uploader para que aparezca limpio tras refrescar la UI
                            if file_key in st.session_state:
                                del st.session_state[file_key]
                                
                            time.sleep(1.5)
                            st.rerun()  # Forzar renderizado limpio
                            
                        except Exception as e:
                            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                            
                            # 1. Creamos un mensaje de error detallado
                            error_detalle = (
                                f"Fallo CRÍTICO durante el ROLLBACK de la tabla '{tabla_seleccionada}'. "
                                f"Archivo: {archivo_respaldo.name}. Detalle: {e}"
                            )
                            
                            # 2. Registramos el error en la "caja negra"
                            log_error(
                                vista="vista_rollback",
                                funcion="mostrar_rollback",
                                error=error_detalle,
                                email_usuario=email_usuario
                            )
                            
                            # 3. Mantenemos tu UI de error original
                            st.error(f"❌ Error crítico durante el rollback: {str(e)}")
                            st.caption("Verifica que tu aplicación web tenga permisos de escritura (Service Role) en Supabase para realizar restauraciones masivas.")

if __name__ == "__main__":
    mostrar_rollback()