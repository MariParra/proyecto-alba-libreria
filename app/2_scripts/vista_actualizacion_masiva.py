import streamlit as st
import pandas as pd
from utilidades import get_db_connection

def procesar_actualizacion(tabla, pk_col, df):
    """
    Recorre el DataFrame y actualiza fila por fila en la base de datos.
    pk_col es el nombre de la columna que sirve como Identificador Único (Primary Key).
    """
    conn = get_db_connection()
    exitos = 0
    errores = []
    
    barra_progreso = st.progress(0, text="Iniciando actualización...")
    total_filas = len(df)
    
    for indice, fila in df.iterrows():
        # Actualizamos la barra de progreso
        progreso_actual = (indice + 1) / total_filas
        barra_progreso.progress(progreso_actual, text=f"Actualizando registro {indice + 1} de {total_filas}...")
        
        try:
            # Validar que el ID exista y sea válido
            if pd.isna(fila[pk_col]):
                errores.append(f"Fila Excel {indice + 2}: El campo '{pk_col}' está vacío. Se omitió.")
                continue
                
            pk_val = int(fila[pk_col])
            
            # Construir el diccionario de datos a actualizar
            datos_actualizar = {}
            for columna in df.columns:
                if columna != pk_col:
                    valor = fila[columna]
                    # Convertir valores nulos de Pandas (NaN/NaT) a None (NULL en la base de datos)
                    if pd.isna(valor):
                        datos_actualizar[columna] = None
                    else:
                        datos_actualizar[columna] = valor
            
            # Ejecutar la actualización en Supabase
            conn.table(tabla).update(datos_actualizar).eq(pk_col, pk_val).execute()
            exitos += 1
            
        except Exception as e:
            errores.append(f"Fila Excel {indice + 2} (ID {fila.get(pk_col, 'N/A')}): Error en BD -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Proceso finalizado!")
    return exitos, errores

def mostrar_actualizacion_masiva():
    st.title("⚡ Actualización Masiva de Datos")
    st.markdown("""
    Utiliza esta herramienta para modificar múltiples registros a la vez usando Excel.
    
    **Instrucciones de uso seguro:**
    1. Ve a la sección **Reportes y Descargas** y exporta la tabla que deseas modificar.
    2. Abre el Excel descargado, modifica los datos que necesites y guarda los cambios. 
    3. **IMPORTANTE:** Nunca modifiques ni elimines la columna de ID (`cliente_id` o `libro_id`). El sistema la necesita para saber qué registro actualizar.
    """)
    
    st.markdown("---")
    
    # 1. Selección de Entidad
    entidad_opciones = {
        "👥 Clientes": {"tabla": "clientes", "id_columna": "cliente_id"},
        "📚 Libros": {"tabla": "libros", "id_columna": "libro_id"}
    }
    
    entidad_seleccionada = st.radio(
        "¿Qué base de datos deseas actualizar?", 
        list(entidad_opciones.keys()), 
        horizontal=True
    )
    
    config = entidad_opciones[entidad_seleccionada]
    
    with st.container(border=True):
        st.markdown(f"#### Subir archivo de {entidad_seleccionada.split(' ')[1]}")
        archivo_subido = st.file_uploader(
            f"Sube tu archivo Excel (.xlsx) con la columna {config['id_columna']}", 
            type=["xlsx"],
            key=f"uploader_{config['tabla']}"
        )
        
        if archivo_subido is not None:
            try:
                # Leer el Excel
                df = pd.read_excel(archivo_subido, engine='openpyxl')
                
                # 2. Validación UX de seguridad
                if config['id_columna'] not in df.columns:
                    st.error(f"🛑 **Error crítico:** El archivo subido no contiene la columna obligatoria `{config['id_columna']}`.")
                    st.stop()
                
                # 3. Vista previa para dar confianza al usuario
                st.success("✅ Archivo leído correctamente. Revisa la vista previa antes de aplicar los cambios:")
                with st.expander("👀 Ver vista previa de los datos a actualizar", expanded=True):
                    st.dataframe(df.head(5), use_container_width=True)
                    st.caption(f"Mostrando las primeras 5 filas de un total de {len(df)} registros encontrados.")
                
                st.warning("⚠️ **Atención:** Esta acción sobrescribirá los datos actuales en la base de datos con la información de este archivo. No se puede deshacer.")
                
                # 4. Ejecución
                if st.button("🚀 Aplicar Cambios Masivamente", type="primary", use_container_width=True):
                    with st.spinner("Conectando con la base de datos..."):
                        exitos, errores = procesar_actualizacion(config['tabla'], config['id_columna'], df)
                        
                        st.markdown("### 📊 Resumen de la Operación")
                        col1, col2 = st.columns(2)
                        col1.metric("✅ Registros Actualizados", exitos)
                        col2.metric("❌ Errores", len(errores))
                        
                        if errores:
                            st.error("Se encontraron algunos problemas durante la actualización:")
                            with st.expander("Ver detalle de errores"):
                                for error in errores:
                                    st.write(error)
                        elif exitos > 0:
                            st.balloons()
                            st.success("¡Todos los registros se actualizaron correctamente sin errores!")
                            
            except Exception as e:
                st.error(f"Ocurrió un error al leer el archivo Excel: {e}")

if __name__ == '__main__':
    mostrar_actualizacion_masiva()