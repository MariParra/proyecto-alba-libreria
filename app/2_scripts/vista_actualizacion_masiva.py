import streamlit as st
import pandas as pd
import io
import re
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# ==========================================================
# 🧹 FUNCIONES AUXILIARES DE LIMPIEZA
# ==========================================================

def normalizar_celda_excel(val):
    """
    Normaliza valores leídos de Excel/CSV para eliminar .0 de enteros,
    manejar de forma segura valores nulos y eliminar espacios en blanco.
    """
    if pd.isna(val):
        return ""
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    if val_str.lower() in ["nan", "none", "<na>"]:
        return ""
    return val_str

# ==========================================================
# 🛠️ FUNCIONES DE GENERACIÓN DE PLANTILLAS (EXCEL)
# ==========================================================

def generar_plantilla_actualizacion_libros():
    """
    Genera una plantilla Excel con TODOS los libros y sus datos actuales,
    incluyendo los nuevos campos del esquema (descuentos, visible_catalogo, etc.), superando la limitación de 1000.
    """
    conn = get_db_connection()
    try:
        all_books = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table('libros')
                .select('libro_id, titulo, autor, editorial, genero, encuadernacion, stock, precio, costo, precio_original, apto_cajita, destacado, visible_catalogo, descuento_inicio, descuento_fin')
                .order('libro_id')
                .range(start, end)
                .execute())
            
            if res.data:
                all_books.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_books:
            return None
            
        df = pd.DataFrame(all_books)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Libros')
            worksheet = writer.sheets['Actualizar Libros']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista='vista_actualizacion_masiva', 
            funcion='generar_plantilla_actualizacion_libros',
            error=e,
            email_usuario=email_usuario
        )
        st.error(f'Error generando plantilla de libros: {e}')
        return None

def generar_plantilla_actualizacion_clientes():
    """Genera una plantilla Excel con TODOS los clientes actuales, superando la limitación de 1000."""
    conn = get_db_connection()
    try:
        all_clients = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table('clientes')
                .select('cliente_id, nombre, rut, email, telefono, instagram, direccion, status')
                .order('cliente_id')
                .range(start, end)
                .execute())
            if res.data:
                all_clients.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_clients:
            return None
            
        df = pd.DataFrame(all_clients)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Clientes')
            worksheet = writer.sheets['Actualizar Clientes']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista='vista_actualizacion_masiva', 
            funcion='generar_plantilla_actualizacion_clientes',
            error=e,
            email_usuario=email_usuario
        )
        st.error(f'Error generando plantilla de clientes: {e}')
        return None

def generar_plantilla_actualizacion_costos():
    """Genera una plantilla Excel con TODOS los costos no de ventas actuales, superando la limitación de 1000."""
    conn = get_db_connection()
    try:
        all_costs = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table('costos_no_ventas')
                .select('costo_id, fecha_ocurrencia, tipo_costo, monto, comentario, creado_por')
                .order('costo_id')
                .range(start, end)
                .execute())
            if res.data:
                all_costs.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        if not all_costs:
            return None
            
        df = pd.DataFrame(all_costs)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Actualizar Costos')
            worksheet = writer.sheets['Actualizar Costos']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista='vista_actualizacion_masiva', 
            funcion='generar_plantilla_actualizacion_costos',
            error=e,
            email_usuario=email_usuario
        )
        st.error(f'Error generando plantilla de costos: {e}')
        return None

# ==========================================================
# 📥 FUNCIONES DE PROCESAMIENTO Y ACTUALIZACIÓN EN BD
# ==========================================================

def procesar_actualizacion_libros(df, progress_bar=None, status_text=None):
    conn = get_db_connection()
    updates = 0
    sin_cambios = 0
    no_encontrados = 0
    errores = []
    
    columnas_texto = ['titulo', 'autor', 'editorial', 'genero', 'encuadernacion']
    columnas_float = ['precio', 'costo', 'precio_original']
    columnas_bool = ['apto_cajita', 'destacado', 'visible_catalogo']
    columnas_fecha = ['descuento_inicio', 'descuento_fin']

    # Filtrar IDs de libros del archivo
    ids_libros = []
    for val in df['libro_id'].dropna():
        try:
            val_norm = normalizar_celda_excel(val)
            if val_norm:
                ids_libros.append(int(float(val_norm)))
        except:
            pass

    # Descargar datos existentes en BD en bloques para comparación
    existing_books_data = []
    if ids_libros:
        for idx in range(0, len(ids_libros), 1000):
            chunk = ids_libros[idx:idx + 1000]
            res_original = (conn.table('libros')
                .select('libro_id, titulo, autor, editorial, genero, encuadernacion, stock, precio, costo, precio_original, apto_cajita, destacado, visible_catalogo, descuento_inicio, descuento_fin')
                .in_('libro_id', chunk)
                .execute())
            if res_original.data:
                existing_books_data.extend(res_original.data)
                
    existing_books_dict = {r['libro_id']: r for r in existing_books_data}
    total_filas = len(df)

    for i, fila in df.iterrows():
        # Actualización de la barra de progreso
        if progress_bar and status_text:
            progress_bar.progress((i + 1) / total_filas)
            status_text.text(f"📖 Procesando libro {i+1} de {total_filas}...")

        try:
            # Omitir filas vacías silenciosamente
            if fila.dropna().empty or all(str(val).strip().lower() in ['', 'nan', 'none', '<na>'] for val in fila.values):
                sin_cambios += 1
                continue

            if 'libro_id' not in fila or pd.isna(fila['libro_id']):
                continue
            
            libro_id_str = normalizar_celda_excel(fila['libro_id'])
            if not libro_id_str:
                continue
                
            libro_id = int(float(libro_id_str))
            
            if libro_id not in existing_books_dict:
                no_encontrados += 1
                errores.append(f'Fila {i+2} (ID Libro: {libro_id}): El libro no existe en la base de datos.')
                continue
                
            db_row = existing_books_dict[libro_id]
            datos_update = {}
            
            # Comparación de diferencias columna por columna
            for col in df.columns:
                if col in fila and pd.notna(fila[col]) and col != 'libro_id':
                    valor_celda = normalizar_celda_excel(fila[col])
                    if valor_celda != '':
                        val_converted = None
                        if col in columnas_texto:
                            val_converted = limpiar_texto_para_busqueda(valor_celda)
                        elif col == 'stock':
                            val_converted = int(float(valor_celda))
                        elif col in columnas_float:
                            val_converted = float(valor_celda)
                        elif col in columnas_bool:
                            val_converted = valor_celda.lower().strip() in ['true', '1', 'si', 'sí', 'yes', 'y']
                        elif col in columnas_fecha:
                            try:
                                val_converted = pd.to_datetime(valor_celda).strftime('%Y-%m-%d')
                            except:
                                val_converted = None
                                errores.append(f'Fila {i+2}: Formato de fecha inválido en {col}.')
                        
                        if val_converted is not None:
                            db_val = db_row.get(col)
                            is_different = False
                            if col in columnas_bool:
                                is_different = (val_converted != bool(db_val))
                            elif col == 'stock':
                                is_different = (val_converted != (int(db_val) if db_val is not None else 0))
                            elif col in columnas_float:
                                is_different = (abs(val_converted - (float(db_val) if db_val is not None else 0.0)) > 1e-4)
                            else:
                                db_val_str = "" if db_val is None else str(db_val).strip()
                                is_different = (str(val_converted).strip() != db_val_str)
                                
                            if is_different:
                                datos_update[col] = val_converted

            # Lógica de Recálculo de Precios basados en el descuento actual
            if 'precio_original' in datos_update:
                nuevo_precio_orig = float(datos_update['precio_original'])
                db_precio_orig = float(db_row.get('precio_original') or 0.0)
                db_precio = float(db_row.get('precio') or 0.0)
                porcentaje_dcto_actual = 0.0
                if db_precio_orig > db_precio and db_precio_orig > 0:
                    porcentaje_dcto_actual = ((db_precio_orig - db_precio) / db_precio_orig) * 100.0
                
                if porcentaje_dcto_actual > 0:
                    factor = 1.0 - (porcentaje_dcto_actual / 100.0)
                    calculated_precio = round(nuevo_precio_orig * factor, 0)
                    if 'precio' not in datos_update:
                        datos_update['precio'] = calculated_precio
                else:
                    if 'precio' not in datos_update:
                        datos_update['precio'] = nuevo_precio_orig
            
            if 'precio' in fila and pd.notna(fila['precio']):
                precio_val = normalizar_celda_excel(fila['precio'])
                if precio_val != '':
                    precio_float = float(precio_val)
                    if abs(precio_float - (float(db_row.get('precio') or 0.0))) > 1e-4:
                        datos_update['precio'] = precio_float

            if datos_update:
                conn.table('libros').update(datos_update).eq('libro_id', libro_id).execute()
                updates += 1
            else:
                sin_cambios += 1
        except Exception as e:
            errores.append(f'Fila {i+2} (ID Libro: {fila.get("libro_id", "N/A")}): {str(e)}')
            
    return updates, sin_cambios, no_encontrados, errores

def procesar_actualizacion_clientes(df, progress_bar=None, status_text=None):
    conn = get_db_connection()
    updates = 0
    sin_cambios = 0
    no_encontrados = 0
    errores = []
    
    df.columns = df.columns.str.lower().str.strip()
    
    if 'correo' in df.columns and 'email' not in df.columns:
        df.rename(columns={'correo': 'email'}, inplace=True)
        
    columnas_permitidas = ['rut', 'direccion', 'email', 'telefono', 'instagram', 'nombre', 'status']

    # Obtener IDs del archivo Excel
    ids_clientes = []
    for val in df['cliente_id'].dropna():
        try:
            val_norm = normalizar_celda_excel(val)
            if val_norm:
                ids_clientes.append(int(val_norm))
        except:
            pass

    # Descargar datos existentes en BD en bloques de 1000
    existing_data = []
    if ids_clientes:
        for idx in range(0, len(ids_clientes), 1000):
            chunk = ids_clientes[idx:idx + 1000]
            res_original = (conn.table('clientes')
                .select('cliente_id, nombre, rut, email, telefono, instagram, direccion, status')
                .in_('cliente_id', chunk)
                .execute())
            if res_original.data:
                existing_data.extend(res_original.data)
                
    existing_dict = {r['cliente_id']: r for r in existing_data}
    total_filas = len(df)

    for i, fila in df.iterrows():
        # Actualización de la barra de progreso
        if progress_bar and status_text:
            progress_bar.progress((i + 1) / total_filas)
            status_text.text(f"👥 Procesando cliente {i+1} de {total_filas}...")

        try:
            # Omitir filas vacías silenciosamente
            if fila.dropna().empty or all(str(val).strip().lower() in ['', 'nan', 'none', '<na>'] for val in fila.values):
                sin_cambios += 1
                continue

            if 'cliente_id' not in fila or pd.isna(fila['cliente_id']):
                errores.append(f'Fila {i+2}: Falta la columna "cliente_id".')
                continue
            
            cliente_id_str = normalizar_celda_excel(fila['cliente_id'])
            if not cliente_id_str:
                errores.append(f'Fila {i+2}: El ID de cliente es vacío o inválido.')
                continue
                
            cliente_id = int(cliente_id_str)
            
            if cliente_id not in existing_dict:
                no_encontrados += 1
                errores.append(f'Fila {i+2} (ID Cliente: {cliente_id}): El cliente no existe en la base de datos.')
                continue
                
            db_row = existing_dict[cliente_id]
            datos_update = {}
            
            # Comparar solo lo que sea diferente
            for col in columnas_permitidas:
                if col in fila and pd.notna(fila[col]):
                    valor_celda = normalizar_celda_excel(fila[col])
                    if valor_celda != '':
                        if col == 'rut':
                            val_uploaded = re.sub(r'[^0-9kK]', '', valor_celda).upper()
                        else:
                            val_uploaded = valor_celda
                            
                        # Limpiar valor existente de DB para comparación exacta
                        val_db = db_row.get(col)
                        val_db_str = "" if val_db is None else str(val_db).strip()
                        if val_db_str.endswith(".0"):
                            val_db_str = val_db_str[:-2]
                        if val_db_str.lower() in ["nan", "none"]:
                            val_db_str = ""
                            
                        # Si es diferente, se agrega para actualizar
                        if val_uploaded != val_db_str:
                            datos_update[col] = val_uploaded

            if datos_update:
                conn.table('clientes').update(datos_update).eq('cliente_id', cliente_id).execute()
                updates += 1
            else:
                sin_cambios += 1
        except Exception as e:
            errores.append(f'Fila {i+2} (ID Cliente: {fila.get("cliente_id", "N/A")}): {str(e)}')
            
    return updates, sin_cambios, no_encontrados, errores

def procesar_actualizacion_costos(df, progress_bar=None, status_text=None):
    """Procesa y actualiza en caliente los costos no operacionales en Supabase."""
    conn = get_db_connection()
    updates = 0
    sin_cambios = 0
    no_encontrados = 0
    errores = []
    
    df.columns = df.columns.str.lower().str.strip()
    columnas_permitidas = ['fecha_ocurrencia', 'tipo_costo', 'monto', 'comentario']

    # Filtrar IDs del archivo
    ids_costos = []
    for val in df['costo_id'].dropna():
        try:
            val_norm = normalizar_celda_excel(val)
            if val_norm:
                ids_costos.append(int(float(val_norm)))
        except:
            pass

    # Descargar datos existentes de BD en bloques
    existing_costos_data = []
    if ids_costos:
        for idx in range(0, len(ids_costos), 1000):
            chunk = ids_costos[idx:idx + 1000]
            res_original = (conn.table('costos_no_ventas')
                .select('costo_id, fecha_ocurrencia, tipo_costo, monto, comentario')
                .in_('costo_id', chunk)
                .execute())
            if res_original.data:
                existing_costos_data.extend(res_original.data)
                
    existing_costos_dict = {r['costo_id']: r for r in existing_costos_data}
    total_filas = len(df)

    for i, fila in df.iterrows():
        # Barra de progreso
        if progress_bar and status_text:
            progress_bar.progress((i + 1) / total_filas)
            status_text.text(f"💸 Procesando costo {i+1} de {total_filas}...")

        try:
            # Omitir filas vacías silenciosamente
            if fila.dropna().empty or all(str(val).strip().lower() in ['', 'nan', 'none', '<na>'] for val in fila.values):
                sin_cambios += 1
                continue

            if 'costo_id' not in fila or pd.isna(fila['costo_id']):
                errores.append(f'Fila {i+2}: Falta la columna obligatoria "costo_id".')
                continue
            
            costo_id_str = normalizar_celda_excel(fila['costo_id'])
            if not costo_id_str:
                errores.append(f'Fila {i+2}: El "costo_id" es vacío o inválido.')
                continue
                
            costo_id = int(float(costo_id_str))
            
            if costo_id not in existing_costos_dict:
                no_encontrados += 1
                errores.append(f'Fila {i+2} (ID Costo: {costo_id}): El registro de costo no existe en la base de datos.')
                continue
                
            db_row = existing_costos_dict[costo_id]
            datos_update = {}
            
            for col in columnas_permitidas:
                if col in fila and pd.notna(fila[col]):
                    valor_celda = normalizar_celda_excel(fila[col])
                    if valor_celda != '':
                        val_converted = None
                        if col == 'monto':
                            val_converted = float(valor_celda)
                        elif col == 'fecha_ocurrencia':
                            try:
                                val_converted = pd.to_datetime(valor_celda).strftime('%Y-%m-%d')
                            except:
                                val_converted = None
                                errores.append(f'Fila {i+2}: Formato de fecha de costo inválido.')
                        else:
                            val_converted = limpiar_texto_para_busqueda(valor_celda).upper() if col == 'tipo_costo' else valor_celda

                        if val_converted is not None:
                            db_val = db_row.get(col)
                            is_different = False
                            if col == 'monto':
                                is_different = (abs(val_converted - (float(db_val) if db_val is not None else 0.0)) > 1e-4)
                            else:
                                db_val_str = "" if db_val is None else str(db_val).strip()
                                is_different = (str(val_converted).strip() != db_val_str)
                                
                            if is_different:
                                datos_update[col] = val_converted

            if datos_update:
                conn.table('costos_no_ventas').update(datos_update).eq('costo_id', costo_id).execute()
                updates += 1
            else:
                sin_cambios += 1
        except Exception as e:
            errores.append(f'Fila {i+2} (ID Costo: {fila.get("costo_id", "N/A")}): {str(e)}')
            
    return updates, sin_cambios, no_encontrados, errores

# ==========================================================
# 🎨 INTERFAZ GRÁFICA DE USUARIO (UX/UI)
# ==========================================================

def mostrar_actualizacion_masiva():
    st.markdown("<h2 style='color: #4A4D7E;'>⚡ Actualización Masiva de Datos</h2>", unsafe_allow_html=True)
    st.markdown("Modifica registros de forma masiva subiendo un archivo Excel/CSV. **La columna ID es obligatoria** para aplicar los cambios.")
    
    tab_libros, tab_clientes, tab_costos = st.tabs([
        '📚 Actualizar Libros', '👥 Actualizar Clientes', '💸 Actualizar Costos'
    ])
    
    # ---------------- TAB: LIBROS ----------------
    with tab_libros:
        st.markdown('### 1. Descarga el Inventario Actual')
        st.caption('Obtén el archivo Excel con tus libros actuales, modifícalo en tu equipo y súbelo abajo.')
        
        try:
            plantilla_libros = generar_plantilla_actualizacion_libros()
            if plantilla_libros:
                st.download_button(
                    label='📥 Descargar Inventario de Libros (.xlsx)',
                    data=plantilla_libros,
                    file_name='inventario_libros_actualizar.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True
                )
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista='vista_actualizacion_masiva', 
                funcion='generar_plantilla_actualizacion_libros',
                error=e,
                email_usuario=email_usuario
            )
            st.error(f'Error al generar la plantilla de libros: {e}')
            
        st.markdown('---')
        st.markdown('### 2. Sube tus Modificaciones')
        archivo_libros = st.file_uploader('Sube el archivo Excel modificado de Libros', type=['xlsx', 'csv'], key='up_libros')
        
        if archivo_libros:
            if st.button('🚀 Aplicar Cambios en Libros', type='primary', use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                with st.spinner('Actualizando catálogo de libros en Supabase...'):
                    try:
                        df = pd.read_excel(archivo_libros) if archivo_libros.name.endswith('.xlsx') else pd.read_csv(archivo_libros)
                        updates, sin_cambios, no_encontrados, errores = procesar_actualizacion_libros(df, progress_bar, status_text)
                        
                        # Remover widgets de progreso al finalizar
                        progress_bar.empty()
                        status_text.empty()

                        # Resumen Métrico
                        st.markdown("### 📊 Resumen de la Actualización")
                        m1, m2, m3, m4, m5 = st.columns(5)
                        m1.metric("Filas Analizadas", len(df))
                        m2.metric("Con Cambios (Actualizados)", updates, delta=f"+{updates}" if updates > 0 else None)
                        m3.metric("Sin Cambios (Ignorados)", sin_cambios)
                        m4.metric("No Encontrados (En BD)", no_encontrados)
                        m5.metric("Errores / Alertas", len(errores))

                        if updates > 0:
                            st.success(f'✅ ¡Se actualizaron {updates} libros exitosamente!')
                            st.balloons()
                            st.cache_data.clear()
                        else:
                            st.info('ℹ️ No se detectaron cambios pendientes en los libros comparados con la base de datos.')
                            
                        if errores:
                            st.error(f'⚠️ Se presentaron {len(errores)} advertencias durante la actualización:')
                            with st.expander("Ver Detalles de Advertencias/Errores"):
                                for err in errores: st.write(f"- {err}")
                        
                    except Exception as e:
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        log_error(
                            vista='vista_actualizacion_masiva', 
                            funcion='procesar_actualizacion_libros',
                            error=e,
                            email_usuario=email_usuario
                        )
                        st.error(f'Error al procesar el archivo: {e}')
                        st.caption('Verifica que el formato del archivo sea correcto y que las columnas no hayan sido modificadas.')
            
            # Botón de autolimpieza de estado de Streamlit
            if st.button('🧹 Limpiar Archivo Cargado', use_container_width=True, key='btn_clean_up_libros'):
                if 'up_libros' in st.session_state:
                    del st.session_state['up_libros']
                st.rerun()

    # ---------------- TAB: CLIENTES ----------------
    with tab_clientes:
        st.markdown('### 1. Descarga el Listado de Clientes Actual')
        st.caption('Obtén el archivo Excel con tus clientes actuales, edita su RUT, dirección o correo y súbelo abajo.')
        
        try:
            plantilla_clientes = generar_plantilla_actualizacion_clientes()
            if plantilla_clientes:
                st.download_button(
                    label='📥 Descargar Listado de Clientes (.xlsx)',
                    data=plantilla_clientes,
                    file_name='listado_clientes_actualizar.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True
                )
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista='vista_actualizacion_masiva', 
                funcion='generar_plantilla_actualizacion_clientes',
                error=e,
                email_usuario=email_usuario
            )
            st.error(f'Error al generar la plantilla de clientes: {e}')
            
        st.markdown('---')
        st.markdown('### 2. Sube tus Modificaciones')
        archivo_clientes = st.file_uploader('Sube el archivo Excel modificado de Clientes', type=['xlsx', 'csv'], key='up_clientes')
        
        if archivo_clientes:
            if st.button('🚀 Aplicar Cambios en Clientes', type='primary', use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                with st.spinner('Actualizando datos de clientes en Supabase...'):
                    try:
                        df_cli = pd.read_excel(archivo_clientes, dtype=str) if archivo_clientes.name.endswith('.xlsx') else pd.read_csv(archivo_clientes, dtype=str)
                        updates_cli, sin_cambios_cli, no_encontrados_cli, errores_cli = procesar_actualizacion_clientes(df_cli, progress_bar, status_text)
                        
                        # Remover widgets de progreso al finalizar
                        progress_bar.empty()
                        status_text.empty()

                        # Resumen Métrico
                        st.markdown("### 📊 Resumen de la Actualización")
                        m1, m2, m3, m4, m5 = st.columns(5)
                        m1.metric("Filas Analizadas", len(df_cli))
                        m2.metric("Con Cambios (Actualizados)", updates_cli, delta=f"+{updates_cli}" if updates_cli > 0 else None)
                        m3.metric("Sin Cambios (Ignorados)", sin_cambios_cli)
                        m4.metric("No Encontrados (En BD)", no_encontrados_cli)
                        m5.metric("Errores / Alertas", len(errores_cli))

                        if updates_cli > 0:
                            st.success(f'✅ ¡Se actualizaron {updates_cli} perfiles de clientes exitosamente!')
                            st.balloons()
                            st.cache_data.clear()
                        else:
                            st.info('ℹ️ No se detectaron cambios en los clientes comparados con la base de datos actual.')
                            
                        if errores_cli:
                            st.error(f'⚠️ Se presentaron {len(errores_cli)} errores durante la actualización:')
                            with st.expander("Ver Detalles de los Errores"):
                                for err in errores_cli: st.write(f"- {err}")
                        
                    except Exception as e:
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        log_error(
                            vista='vista_actualizacion_masiva', 
                            funcion='procesar_actualizacion_clientes',
                            error=e,
                            email_usuario=email_usuario
                        )
                        st.error(f'Error al procesar el archivo de clientes: {e}')
                        st.caption('Verifica que el formato del archivo sea correcto y que las columnas no hayan sido modificadas.')
            
            # Botón de autolimpieza de estado de Streamlit
            if st.button('🧹 Limpiar Archivo Cargado', use_container_width=True, key='btn_clean_up_clientes'):
                if 'up_clientes' in st.session_state:
                    del st.session_state['up_clientes']
                st.rerun()

    # ---------------- TAB: COSTOS NO VENTAS ----------------
    with tab_costos:
        st.markdown('### 1. Descarga el Listado de Costos Actual')
        st.caption('Obtén el archivo Excel con tus costos no operacionales actuales, edita su monto, tipo de costo o comentario y súbelo abajo.')
        
        try:
            plantilla_costos = generar_plantilla_actualizacion_costos()
            if plantilla_costos:
                st.download_button(
                    label='📥 Descargar Listado de Costos (.xlsx)',
                    data=plantilla_costos,
                    file_name='listado_costos_actualizar.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True
                )
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista='vista_actualizacion_masiva', 
                funcion='generar_plantilla_actualizacion_costos',
                error=e,
                email_usuario=email_usuario
            )
            st.error(f'Error al generar la plantilla de costos: {e}')
            
        st.markdown('---')
        st.markdown('### 2. Sube tus Modificaciones')
        archivo_costos = st.file_uploader('Sube el archivo Excel modificado de Costos', type=['xlsx', 'csv'], key='up_costos')
        
        if archivo_costos:
            if st.button('🚀 Aplicar Cambios en Costos', type='primary', use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                with st.spinner('Actualizando datos de costos en Supabase...'):
                    try:
                        df_cos = pd.read_excel(archivo_costos, dtype=str) if archivo_costos.name.endswith('.xlsx') else pd.read_csv(archivo_costos, dtype=str)
                        updates_cos, sin_cambios_cos, no_encontrados_cos, errores_cos = procesar_actualizacion_costos(df_cos, progress_bar, status_text)
                        
                        # Remover widgets de progreso al finalizar
                        progress_bar.empty()
                        status_text.empty()

                        # Resumen Métrico
                        st.markdown("### 📊 Resumen de la Actualización")
                        m1, m2, m3, m4, m5 = st.columns(5)
                        m1.metric("Filas Analizadas", len(df_cos))
                        m2.metric("Con Cambios (Actualizados)", updates_cos, delta=f"+{updates_cos}" if updates_cos > 0 else None)
                        m3.metric("Sin Cambios (Ignorados)", sin_cambios_cos)
                        m4.metric("No Encontrados (En BD)", no_encontrados_cos)
                        m5.metric("Errores / Alertas", len(errores_cos))

                        if updates_cos > 0:
                            st.success(f'✅ ¡Se actualizaron {updates_cos} registros de costos exitosamente!')
                            st.balloons()
                            st.cache_data.clear()
                        else:
                            st.info('ℹ️ No se detectaron cambios en el archivo de costos comparado con la base de datos actual.')
                            
                        if errores_cos:
                            st.error(f'⚠️ Se presentaron {len(errores_cos)} errores durante la actualización:')
                            with st.expander("Ver Detalles de los Errores"):
                                for err in errores_cos: st.write(f"- {err}")
                        
                    except Exception as e:
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        log_error(
                            vista='vista_actualizacion_masiva', 
                            funcion='procesar_actualizacion_costos',
                            error=e,
                            email_usuario=email_usuario
                        )
                        st.error(f'Error al procesar el archivo de costos: {e}')
                        st.caption('Verifica que el formato del archivo sea correcto y que las columnas no hayan sido modificadas.')
            
            # Botón de autolimpieza de estado de Streamlit
            if st.button('🧹 Limpiar Archivo Cargado', use_container_width=True, key='btn_clean_up_costos'):
                if 'up_costos' in st.session_state:
                    del st.session_state['up_costos']
                st.rerun()

if __name__ == '__main__':
    mostrar_actualizacion_masiva()