import streamlit as st
import pandas as pd
import io
from datetime import datetime
import json
import time
import re
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# ====================================================
# --- LÓGICA 1: CREACIÓN DE CLIENTES NUEVOS ---
# ====================================================
def generar_plantilla_clientes():
    columnas = ['nombre', 'email', 'telefono', 'direccion', 'instagram', 'rut', 'status']
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Nuevos Clientes')
        worksheet = writer.sheets['Nuevos Clientes']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 25)
    return output.getvalue()

def procesar_clientes_masivos(df):
    conn = get_db_connection()
    exitos, duplicados, errores = 0, 0, []

    # 🚀 BYPASS DE 1000 REGISTROS: Cargamos la base completa de clientes para validar duplicados
    all_names = []
    chunk_size = 1000
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_clientes = (conn.table('clientes')
            .select('nombre')
            .order('cliente_id')
            .range(start, end)
            .execute())
        if res_clientes.data:
            all_names.extend(res_clientes.data)
            if len(res_clientes.data) < chunk_size:
                break
        else:
            break
            
    catalogo_actual = [limpiar_texto_para_busqueda(c['nombre']) for c in all_names] if all_names else []
    
    barra_progreso = st.progress(0, text='Iniciando carga de clientes...')
    total_filas = len(df)
    
    columnas_texto = ['nombre', 'email', 'telefono', 'direccion', 'instagram', 'rut', 'status']

    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f'Procesando cliente {indice + 1}/{total_filas}...')
        
        nombre_limpio = limpiar_texto_para_busqueda(fila.get('nombre', ''))
        
        if not nombre_limpio:
            errores.append(f'Fila {indice + 2}: Falta el "nombre". Es obligatorio.')
            continue
            
        if nombre_limpio in catalogo_actual:
            duplicados += 1
            errores.append(f'Fila {indice + 2}: El cliente "{nombre_limpio}" ya existe.')
            continue
            
        try:
            status_val = str(fila.get('status', 'CLIENTE REGULAR')).strip().upper()
            if not status_val or pd.isna(fila.get('status')):
                status_val = 'CLIENTE REGULAR'
                
            rut_raw = str(fila.get('rut', '')) if pd.notna(fila.get('rut')) else ''
            rut_limpio = re.sub(r'[^0-9kK]', '', rut_raw).upper()

            nuevo_cliente = {
                'status': status_val,
                'rut': rut_limpio if rut_limpio else None
            }
            
            for col in df.columns:
                if col not in ['status', 'rut'] and pd.notna(fila[col]):
                    if col in columnas_texto:
                        nuevo_cliente[col] = limpiar_texto_para_busqueda(str(fila[col]))
                    else:
                        nuevo_cliente[col] = fila[col]
            
            if 'nombre' in nuevo_cliente:
                nuevo_cliente['nombre'] = limpiar_texto_para_busqueda(nuevo_cliente['nombre'])

            conn.table('clientes').insert(nuevo_cliente).execute()
            exitos += 1
            catalogo_actual.append(nombre_limpio)
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f'Fallo en creación masiva en Fila {indice + 2} ("{nombre_limpio}"). Detalle: {e}'
            
            log_error(
                vista='vista_creacion_masiva',
                funcion='procesar_clientes_masivos (bucle)',
                error=error_detalle,
                email_usuario=email_usuario
            )
            
            errores.append(f'Fila {indice + 2} ("{nombre_limpio}"): Error -> {str(e)}')
            continue
            
    barra_progreso.progress(1.0, text='¡Carga finalizada!')
    return exitos, duplicados, errores

# ====================================================
# --- LÓGICA 2: CREACIÓN DE LIBROS NUEVOS ---
# ====================================================
def generar_plantilla_libros():
    columnas = [
        'titulo', 'autor', 'genero', 'editorial', 'encuadernacion', 
        'stock', 'precio', 'precio_original', 'costo', 
        'apto_cajita', 'destacado', 'visible_catalogo',
        'descuento_inicio_YYYY_MM_DD', 'descuento_fin_YYYY_MM_DD'
    ]
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Nuevos Libros')
        worksheet = writer.sheets['Nuevos Libros']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 18)
    return output.getvalue()

def procesar_nuevos_libros(df):
    conn = get_db_connection()
    exitos, duplicados, errores = 0, 0, []
    
    # 🚀 BYPASS DE 1000 REGISTROS: Cargamos todo el catálogo de títulos y autores para validar duplicados
    all_titles = []
    chunk_size = 1000
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_libros = (conn.table('libros')
            .select('titulo, autor')
            .order('libro_id')
            .range(start, end)
            .execute())
        if res_libros.data:
            all_titles.extend(res_libros.data)
            if len(res_libros.data) < chunk_size:
                break
        else:
            break
            
    catalogo_actual = [(limpiar_texto_para_busqueda(l['titulo']), limpiar_texto_para_busqueda(l.get('autor', ''))) for l in all_titles] if all_titles else []
    
    barra_progreso = st.progress(0, text='Iniciando carga de catálogo...')
    total_filas = len(df)
    
    columnas_texto = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion']
    columnas_numericas = ['stock', 'precio', 'precio_original', 'costo']

    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f'Procesando libro {indice + 1} de {total_filas}...')
        
        titulo_limpio = limpiar_texto_para_busqueda(fila.get('titulo', ''))
        autor_limpio = limpiar_texto_para_busqueda(fila.get('autor', ''))
        
        if not titulo_limpio:
            errores.append(f'Fila {indice + 2}: Falta el "titulo". Es obligatorio.')
            continue
            
        if (titulo_limpio, autor_limpio) in catalogo_actual:
            duplicados += 1
            errores.append(f'Fila {indice + 2}: El libro "{titulo_limpio}" ya existe.')
            continue
            
        try:
            nuevo_libro = {}
            # 1. Columnas de texto
            for col in columnas_texto:
                if col in fila and pd.notna(fila[col]):
                    nuevo_libro[col] = limpiar_texto_para_busqueda(str(fila[col]))
            
            # 2. Columnas numéricas
            for col in columnas_numericas:
                if col in fila and pd.notna(fila[col]):
                    try:
                        nuevo_libro[col] = float(fila[col])
                    except (ValueError, TypeError):
                        errores.append(f'Fila {indice + 2}: Valor no numérico en columna "{col}". Se omitió.')
                        continue
            
            encuadernacion = nuevo_libro.get('encuadernacion', '').upper()
            
            if 'apto_cajita' in fila and pd.notna(fila['apto_cajita']):
                nuevo_libro['apto_cajita'] = bool(fila['apto_cajita'])
            else:
                nuevo_libro['apto_cajita'] = False if encuadernacion == 'TAPA DURA' else True
            
            if 'destacado' in fila and pd.notna(fila['destacado']):
                nuevo_libro['destacado'] = bool(fila['destacado'])
            else:
                nuevo_libro['destacado'] = False
            
            if 'visible_catalogo' in fila and pd.notna(fila['visible_catalogo']):
                nuevo_libro['visible_catalogo'] = bool(fila['visible_catalogo'])
            else:
                nuevo_libro['visible_catalogo'] = True
                
            if 'descuento_inicio_YYYY_MM_DD' in fila and pd.notna(fila['descuento_inicio_YYYY_MM_DD']):
                try:
                    nuevo_libro['descuento_inicio'] = pd.to_datetime(fila['descuento_inicio_YYYY_MM_DD']).strftime('%Y-%m-%d')
                except:
                    errores.append(f'Fila {indice + 2}: Formato de "descuento_inicio" inválido.')
            if 'descuento_fin_YYYY_MM_DD' in fila and pd.notna(fila['descuento_fin_YYYY_MM_DD']):
                try:
                    nuevo_libro['descuento_fin'] = pd.to_datetime(fila['descuento_fin_YYYY_MM_DD']).strftime('%Y-%m-%d')
                except:
                    errores.append(f'Fila {indice + 2}: Formato de "descuento_fin" inválido.')
            
            if 'titulo' in nuevo_libro:
                nuevo_libro['portada_last_updated'] = 'now()'
                conn.table('libros').insert(nuevo_libro).execute()
                exitos += 1
                catalogo_actual.append((titulo_limpio, autor_limpio))

        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f'Fallo en creación masiva en Fila {indice + 2} ("{titulo_limpio}"). Detalle: {e}'
            log_error(vista='vista_creacion_masiva', funcion='procesar_nuevos_libros', error=error_detalle, email_usuario=email_usuario)
            errores.append(f'Fila {indice + 2} ("{titulo_limpio}"): Error -> {str(e)}')
            
    barra_progreso.progress(1.0, text='¡Carga finalizada!')
    return exitos, duplicados, errores

# ====================================================
# --- LÓGICA 3: IMPORTACIÓN DE VENTAS PASADAS ---
# ====================================================
def generar_plantilla_ventas():
    columnas = ['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente', 'Titulo_Libro', 'Cantidad', 'Precio_Unitario', 'Valor_Envio', 'Metodo_Envio', 'Comentario', 'Estado', 'Abono', 'Tipo_Cobro_Envio']
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Ventas Pasadas')
        worksheet = writer.sheets['Ventas Pasadas']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 20)
    return output.getvalue()

def procesar_ventas_masivas(df):
    conn = get_db_connection()
    exitos, errores = 0, []

    df['Fecha_Venta_YYYY_MM_DD'] = pd.to_datetime(df['Fecha_Venta_YYYY_MM_DD'], errors='coerce')
    filas_con_fecha_invalida = df[df['Fecha_Venta_YYYY_MM_DD'].isna()]
    for i, fila in filas_con_fecha_invalida.iterrows():
        errores.append(f'Fila {i+2}: La fecha es inválida o está vacía y fue omitida.')
    df.dropna(subset=['Fecha_Venta_YYYY_MM_DD'], inplace=True)

    # 🚀 BYPASS DE 1000 REGISTROS: Cargamos y mapeamos todos los clientes existentes de la base
    all_clients = []
    chunk_size = 1000
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_clientes = (conn.table('clientes')
            .select('cliente_id, nombre')
            .order('cliente_id')
            .range(start, end)
            .execute())
        if res_clientes.data:
            all_clients.extend(res_clientes.data)
            if len(res_clientes.data) < chunk_size:
                break
        else:
            break
            
    map_clientes = {limpiar_texto_para_busqueda(c['nombre']): c['cliente_id'] for c in all_clients} if all_clients else {}

    # 🚀 BYPASS DE 1000 REGISTROS: Cargamos y mapeamos todos los libros del catálogo
    all_books = []
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_libros = (conn.table('libros')
            .select('libro_id, titulo, autor, costo')
            .order('libro_id')
            .range(start, end)
            .execute())
        if res_libros.data:
            all_books.extend(res_libros.data)
            if len(res_libros.data) < chunk_size:
                break
        else:
            break
            
    map_libros = {limpiar_texto_para_busqueda(l['titulo']): l for l in all_books} if all_books else {}

    df['Valor_Envio'] = pd.to_numeric(df['Valor_Envio'], errors='coerce').fillna(0)
    df['Cantidad'] = pd.to_numeric(df['Cantidad'], errors='coerce').fillna(1)
    df['Precio_Unitario'] = pd.to_numeric(df['Precio_Unitario'], errors='coerce').fillna(0)
    df['Abono'] = pd.to_numeric(df.get('Abono'), errors='coerce').fillna(0)
    
    grupos = df.groupby(['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente'])
    barra_progreso = st.progress(0, text='Procesando ventas...')
    total_grupos, actual = len(grupos), 0

    for (fecha_dt, cliente_nombre), grupo in grupos:
        actual += 1
        barra_progreso.progress(actual / total_grupos, text=f'Procesando venta {actual} de {total_grupos}...')
        
        try:
            cliente_norm = limpiar_texto_para_busqueda(str(cliente_nombre))
            if cliente_norm not in map_clientes:
                errores.append(f'Venta {fecha_dt.strftime("%Y-%m-%d")}: Cliente "{cliente_nombre}" no existe en tu base de datos.')
                continue
            cliente_id = map_clientes[cliente_norm]

            libros_vendidos, subtotal, costo_total_venta = [], 0.0, 0.0

            for _, fila in grupo.iterrows():
                titulo_norm = limpiar_texto_para_busqueda(fila.get('Titulo_Libro', ''))
                libro_info = map_libros.get(titulo_norm)
                
                libro_id = int(libro_info['libro_id']) if libro_info and pd.notna(libro_info.get('libro_id')) else None
                autor_libro = limpiar_texto_para_busqueda(libro_info['autor']) if libro_info and pd.notna(libro_info.get('autor')) else 'DESCONOCIDO'

                if libro_info and pd.notna(libro_info.get('costo')):
                    costo_total_venta += float(libro_info['costo']) * int(fila['Cantidad'])

                cant = int(fila['Cantidad'])
                precio_u = float(fila['Precio_Unitario'])
                
                libros_vendidos.append({
                    'libro_id': libro_id, 'titulo': titulo_norm, 'autor': autor_libro,
                    'cantidad': cant, 'precio': precio_u
                })
                subtotal += (cant * precio_u)

            valor_envio = float(grupo['Valor_Envio'].iloc[0])
            metodo_envio = limpiar_texto_para_busqueda(str(grupo['Metodo_Envio'].iloc[0])) if pd.notna(grupo['Metodo_Envio'].iloc[0]) else 'NO ESPECIFICADO'
            comentario = limpiar_texto_para_busqueda(str(grupo['Comentario'].iloc[0])) if pd.notna(grupo['Comentario'].iloc[0]) else 'IMPORTACION MASIVA'
            estado_venta = limpiar_texto_para_busqueda(str(grupo['Estado'].iloc[0])) if pd.notna(grupo['Estado'].iloc[0]) else 'FINALIZADO'
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            abono_total_venta = float(grupo['Abono'].sum())
            monto_final = subtotal + valor_envio
            tipo_cobro_envio = limpiar_texto_para_busqueda(str(grupo['Tipo_Cobro_Envio'].iloc[0])) if ('Tipo_Cobro_Envio' in grupo.columns and pd.notna(grupo['Tipo_Cobro_Envio'].iloc[0])) else 'NO ESPECIFICADO'

            venta_data = {
                'cliente_id': cliente_id, 'fecha_venta': fecha_str,
                'libros_vendidos': json.dumps(libros_vendidos, ensure_ascii=False),
                'subtotal_libros': subtotal, 'valor_envio': valor_envio,
                'monto_final': monto_final, 'metodo_envio': metodo_envio,
                'comentario': comentario, 'estado': estado_venta,
                'abono': abono_total_venta, 'costo_venta': costo_total_venta,
                'tipo_cobro_envio': tipo_cobro_envio
            }

            conn.table('registro_ventas').insert(venta_data).execute()
            exitos += 1

        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f'Fallo en creación masiva en Fecha-Cliente {fecha_dt.strftime("%Y-%m-%d")} ("{cliente_nombre}"). Detalle: {e}'
            
            log_error(
                vista='vista_creacion_masiva',
                funcion='procesar_ventas_masivas',
                error=error_detalle,
                email_usuario=email_usuario
            )
            errores.append(f'Error en Venta de {cliente_nombre} ({fecha_dt.strftime("%Y-%m-%d")}): {str(e)}')

    barra_progreso.progress(1.0, text='¡Carga finalizada!')
    return exitos, errores

# ====================================================
# --- LÓGICA 4: IMPORTACIÓN DE SUSCRIPCIONES ---
# ====================================================
def generar_plantilla_suscripciones():
    '''Genera la plantilla cargando de forma paginada al 100% de clientes.'''
    conn = get_db_connection()
    try:
        all_clients = []
        chunk_size = 1000
        for bloques in range(100):
            start = bloques * chunk_size
            end = start + chunk_size - 1
            res_clientes = (conn.table('clientes')
                .select('cliente_id, nombre')
                .order('cliente_id')
                .range(start, end)
                .execute())
            if res_clientes.data:
                all_clients.extend(res_clientes.data)
                if len(res_clientes.data) < chunk_size:
                    break
            else:
                break
                
        if not all_clients:
            return None
            
        df_clientes = pd.DataFrame(all_clients)
        df_clientes['valor_suscripcion'] = ''
        df_clientes['fecha_pago'] = ''
        df_clientes['metodo_entrega'] = ''
        df_clientes['generos_preferencia'] = ''
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_clientes.to_excel(writer, index=False, sheet_name='Suscripciones')
            worksheet = writer.sheets['Suscripciones']
            worksheet.set_column('A:A', 10)
            worksheet.set_column('B:B', 30)
            worksheet.set_column('C:C', 20)
            worksheet.set_column('D:D', 20)
            worksheet.set_column('E:E', 20)
            worksheet.set_column('F:F', 30)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista='vista_creacion_masiva',
            funcion='generar_plantilla_suscripciones',
            error=e,
            email_usuario=email_usuario
        )
        st.error(f'Error al generar plantilla de suscripciones: {e}')
        return None

def procesar_suscripciones_masivas(df):
    conn = get_db_connection()
    actualizados, creados, errores = 0, 0, []

    df.dropna(subset=['valor_suscripcion'], inplace=True)
    df['valor_suscripcion'] = pd.to_numeric(df['valor_suscripcion'], errors='coerce')
    df.dropna(subset=['valor_suscripcion'], inplace=True)

    barra_progreso = st.progress(0, text='Procesando suscripciones...')
    total_filas = len(df)

    for i, fila in df.iterrows():
        barra_progreso.progress((i + 1) / total_filas, text=f'Procesando cliente {i+1}/{total_filas}...')
        try:
            cliente_id = int(fila['cliente_id'])
            valor = float(fila['valor_suscripcion'])
            fecha_pago = str(fila['fecha_pago']).strip() if ('fecha_pago' in fila and pd.notna(fila['fecha_pago'])) else None
            metodo_entrega = str(fila['metodo_entrega']).strip().upper() if ('metodo_entrega' in fila and pd.notna(fila['metodo_entrega'])) else None
            generos_preferencia = str(fila['generos_preferencia']).strip() if ('generos_preferencia' in fila and pd.notna(fila['generos_preferencia'])) else None

            res = conn.table('suscripciones').select('suscripcion_id').eq('cliente_id', cliente_id).execute()
            datos = {
                'cliente_id': cliente_id, 
                'valor_suscripcion': valor,
                'fecha_pago': fecha_pago,
                'metodo_entrega': metodo_entrega,
                'generos_preferencia': generos_preferencia
            }

            if res.data:
                conn.table('suscripciones').update(datos).eq('cliente_id', cliente_id).execute()
                actualizados += 1
            else:
                conn.table('suscripciones').insert(datos).execute()
                creados += 1
        except Exception as e:
            errores.append(f'Fila {i+2}: Error con cliente ID {fila.get("cliente_id", "N/A")} -> {str(e)}')

    barra_progreso.progress(1.0, text='¡Carga finalizada!')
    return actualizados, creados, errores

# ====================================================
# --- LÓGICA 5: CREACIÓN MASIVA DE COSTOS ---
# ====================================================
def generar_plantilla_costos():
    '''Genera la plantilla Excel vacía con el esquema estructurado de costos no de ventas.'''
    columnas = ['fecha_ocurrencia_YYYY_MM_DD', 'tipo_costo', 'monto', 'comentario']
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Nuevos Costos')
        worksheet = writer.sheets['Nuevos Costos']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 25)
    return output.getvalue()

def procesar_costos_masivos(df):
    '''Procesa, valida e inserta de forma masiva los costos no operacionales en Supabase.'''
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    exitos, errores = 0, []
    
    barra_progreso = st.progress(0, text='Iniciando procesamiento de costos...')
    total_filas = len(df)
    
    for i, fila in df.iterrows():
        barra_progreso.progress((i + 1) / total_filas, text=f'Procesando costo {i + 1} de {total_filas}...')
        
        fecha_val = fila.get('fecha_ocurrencia_YYYY_MM_DD')
        tipo_costo = fila.get('tipo_costo')
        monto_val = fila.get('monto')
        comentario = fila.get('comentario', '')
        
        if pd.isna(fecha_val) or not str(fecha_val).strip():
            errores.append(f'Fila {i+2}: La columna "fecha_ocurrencia_YYYY_MM_DD" es obligatoria.')
            continue
        if pd.isna(tipo_costo) or not str(tipo_costo).strip():
            errores.append(f'Fila {i+2}: La columna "tipo_costo" es obligatoria.')
            continue
        if pd.isna(monto_val):
            errores.append(f'Fila {i+2}: La columna "monto" es obligatoria.')
            continue
            
        try:
            fecha_clean = pd.to_datetime(fecha_val).strftime('%Y-%m-%d')
        except Exception as e:
            errores.append(f'Fila {i+2}: Formato de fecha inválido en "{fecha_val}". Debe ser YYYY-MM-DD o DD-MM-YYYY.')
            continue
            
        try:
            monto_clean = float(monto_val)
            if monto_clean <= 0:
                errores.append(f'Fila {i+2}: El monto debe ser un valor mayor a $0.')
                continue
        except Exception as e:
            errores.append(f'Fila {i+2}: El monto debe ser un valor exclusivamente numérico.')
            continue
            
        try:
            datos_costo = {
                'fecha_ocurrencia': fecha_clean,
                'tipo_costo': limpiar_texto_para_busqueda(str(tipo_costo)).upper(),
                'monto': monto_clean,
                'comentario': str(comentario).strip() if pd.notna(comentario) else '',
                'creado_por': email_usuario
            }
            conn.table('costos_no_ventas').insert(datos_costo).execute()
            exitos += 1
        except Exception as e:
            log_error(vista='vista_creacion_masiva', funcion='procesar_costos_masivos', error=str(e), email_usuario=email_usuario)
            errores.append(f'Fila {i+2}: Error de base de datos -> {str(e)}')
            continue
            
    barra_progreso.progress(1.0, text='¡Carga finalizada!')
    return exitos, errores

# ==========================================
# --- VISTA PRINCIPAL ---
# ==========================================
def mostrar_creacion_masiva():
    st.title('✨ Importación Masiva')
    st.markdown('Añade decenas de registros a la vez usando nuestras plantillas de Excel. Sigue las instrucciones de cada pestaña para evitar errores.')
    
    tab_clientes, tab_libros, tab_ventas, tab_suscripciones, tab_costos = st.tabs([
        '👥 Nuevos Clientes', '📚 Nuevos Libros', '🛒 Ventas Pasadas', '💰 Suscripciones', '💸 Nuevos Costos'
    ])

    # ---------------- TAB: CLIENTES ----------------
    with tab_clientes:
        with st.container(border=True):
            st.markdown('### Paso 1: Descarga la Plantilla de Clientes')
            st.info(
                'ℹ/ **Formato Esperado en Excel:**\n'
                '- **nombre:** (Obligatorio) No importa si usas mayúsculas o tildes, el sistema lo limpiará automáticamente. Se usa para evitar duplicados.\n'
                '- **email, telefono, direccion, instagram:** (Opcionales) Se guardarán tal como los escribas.\n'
                '- **rut:** (Recomendado) RUT del cliente para facturación e identificador único.\n'
                '- **status:** (Opcional) Por defecto "CLIENTE REGULAR". Escribe "SUSCRITO" para miembros del club.'
            )
            st.download_button(
                label='📥 Descargar Plantilla Clientes (.xlsx)',
                data=generar_plantilla_clientes(),
                file_name='plantilla_nuevos_clientes.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
        with st.container(border=True):
            st.markdown('### Paso 2: Sube el archivo con los datos')
            archivo_clientes = st.file_uploader('Sube el archivo de clientes', type=['xlsx'], key='up_clientes')
            
            if archivo_clientes:
                df_c = pd.read_excel(archivo_clientes, engine='openpyxl')
                if 'nombre' not in df_c.columns:
                    st.error('🛑 El archivo no es válido. Usa la plantilla de clientes que descargaste en el Paso 1.')
                else:
                    if st.button('🚀 Ingresar Nuevos Clientes', type='primary', use_container_width=True):
                        with st.spinner('Procesando y validando clientes...'):
                            exitos, duplicados, errores = procesar_clientes_masivos(df_c)
                            c1, c2, c3 = st.columns(3)
                            c1.metric('✅ Creados', exitos)
                            c2.metric('⚠️ Duplicados Omitidos', duplicados)
                            c3.metric('❌ Errores Críticos', len(errores) - duplicados)
                            if exitos > 0: 
                                st.balloons()
                                st.success('¡Nuevos clientes añadidos correctamente!')
                            if errores:
                                with st.expander('Ver lista de conflictos'):
                                    for err in errores: st.write(err)
                            
                            # Botón de autolimpieza de estado
                            if st.button('🧹 Limpiar Estado y Subir de Nuevo', use_container_width=True, key='btn_clean_clientes'):
                                if 'up_clientes' in st.session_state:
                                    del st.session_state['up_clientes']
                                st.rerun()

    # ---------------- TAB: LIBROS ----------------
    with tab_libros:
        with st.container(border=True):
            st.markdown('### Paso 1: Descarga la Plantilla de Libros')
            st.info(
                'ℹ/ **Formato Esperado en Excel:**\n'
                '- **titulo y autor:** (Obligatorios) El sistema los limpiará (mayúsculas, sin tilde) y los usará combinados para detectar si el libro ya existe.\n'
                '- **genero, editorial, encuadernacion:** (Opcionales) Texto libre.\n'
                '- **stock, precio, precio_original, costo:** (Obligatorios numéricos) Deben ser números puros. **NO escribas** el signo "$" ni letras. Ej: Escribe "15000", no "$15.000".\n'
                '- **apto_cajita:** (Opcional) Escribe `TRUE` o `FALSE`. Si lo dejas en blanco, se detectará automáticamente.\n'
                '- **destacado:** (Opcional) Escribe `TRUE` para que aparezca en el carrusel de destacados. Por defecto es `FALSE`.\n'
                '- **visible_catalogo:** (Opcional) Escribe `FALSE` para ocultar el libro del catálogo público. Por defecto es `TRUE`.\n'
                '- **descuento_inicio_YYYY_MM_DD / descuento_fin_YYYY_MM_DD:** (Opcionales) Fechas de inicio y fin del descuento comercial del libro.'
            )
            st.download_button(
                label='📥 Descargar Plantilla Libros (.xlsx)',
                data=generar_plantilla_libros(),
                file_name='plantilla_nuevos_libros.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        with st.container(border=True):
            st.markdown('### Paso 2: Sube tu Excel Lleno')
            archivo_libros = st.file_uploader('Sube el archivo de libros', type=['xlsx'], key='up_libros')
            if archivo_libros:
                df = pd.read_excel(archivo_libros, engine='openpyxl')
                if 'titulo' not in df.columns:
                    st.error('🛑 El archivo no es válido. Usa la plantilla de libros.')
                else:
                    if st.button('🚀 Ingresar Libros', type='primary', use_container_width=True):
                        with st.spinner('Creando libros...'):
                            exitos, duplicados, errores = procesar_nuevos_libros(df)
                            c1, c2, c3 = st.columns(3)
                            c1.metric('✅ Ingresados', exitos)
                            c2.metric('⚠️ Duplicados Omitidos', duplicados)
                            c3.metric('❌ Errores Críticos', len(errores) - duplicados)
                            if exitos > 0: st.success(f'¡{exitos} libros añadidos!')
                            if errores:
                                with st.expander('Ver lista de conflictos'):
                                    for err in errores: st.write(err)
                            
                            # Botón de autolimpieza de estado
                            if st.button('🧹 Limpiar Estado y Subir de Nuevo', use_container_width=True, key='btn_clean_libros'):
                                if 'up_libros' in st.session_state:
                                    del st.session_state['up_libros']
                                st.rerun()

    # ---------------- TAB: VENTAS ----------------
    with tab_ventas:
        with st.container(border=True):
            st.markdown('### Paso 1: Descarga la Plantilla de Ventas')
            st.warning(
                '**¡Condición Previa!** Antes de subir ventas, asegúrate de que los **Clientes** y **Libros** '
                'que vas a reportar YA EXISTAN en tu base de datos. Si un cliente o libro no existe, la fila será rechazada.'
            )
            st.info(
                'ℹ/ **Formato Esperado en Excel:**\n'
                '- **Fecha_Venta_YYYY_MM_DD:** El sistema soporta formatos normales (ej: 25/08/2026, 2026-08-25). Celdas vacías o texto inválido se omitirán.\n'
                '- **Nombre_Cliente y Titulo_Libro:** Deben coincidir con los nombres en tu base de datos (no te preocupes por tildes o mayúsculas).\n'
                '- **Cantidad, Precio_Unitario, Valor_Envio, Abono:** Deben ser **números puros**, sin símbolos.\n'
                '- **Estado:** Escribe estados como "FINALIZADO" o "PENDIENTE PAGO" (por defecto será "FINALIZADO").\n'
                '- **Tipo_Cobro_Envio:** (Opcional) Indica si el envío es cobrado, gratis o diferido.\n'
                '💡 **Tip UX:** Si una clienta compró 3 libros el mismo día, usa 3 filas en el Excel con la misma fecha y cliente. El sistema las agrupará en una sola Venta automáticamente.'
            )
            st.download_button(
                label='📥 Descargar Plantilla Ventas (.xlsx)',
                data=generar_plantilla_ventas(),
                file_name='plantilla_ventas_pasadas.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        with st.container(border=True):
            st.markdown('### Paso 2: Sube el Archivo de Ventas')
            archivo_ventas = st.file_uploader('Sube el archivo de ventas', type=['xlsx'], key='up_ventas')
            if archivo_ventas:
                df_v = pd.read_excel(archivo_ventas, engine='openpyxl')
                if 'Nombre_Cliente' not in df_v.columns:
                    st.error('🛑 El archivo no es válido. Usa la plantilla de ventas.')
                else:
                    if st.button('🚀 Registrar Ventas Masivamente', type='primary', use_container_width=True):
                        with st.spinner('Procesando y agrupando ventas...'):
                            exitos_v, errores_v = procesar_ventas_masivas(df_v)
                            c1, c2 = st.columns(2)
                            c1.metric('✅ Boletas Exitosas', exitos_v)
                            c2.metric('❌ Filas con Errores', len(errores_v))
                            if exitos_v > 0: 
                                st.balloons()
                                st.success('¡Ventas registradas correctamente en el historial!')
                            if errores_v:
                                with st.expander('Ver lista de conflictos (Revisa fechas o clientes no encontrados)'):
                                    for err in errores_v: st.write(err)
                            
                            # Botón de autolimpieza de estado
                            if st.button('🧹 Limpiar Estado y Subir de Nuevo', use_container_width=True, key='btn_clean_ventas'):
                                if 'up_ventas' in st.session_state:
                                    del st.session_state['up_ventas']
                                st.rerun()

    # ---------------- TAB: SUSCRIPCIONES ----------------
    with tab_suscripciones:
        with st.container(border=True):
            st.markdown('### Paso 1: Descarga la Plantilla Inteligente')
            st.info(
                'La plantilla se generará automáticamente con el ID y Nombre de todos tus clientes actuales.\n\n'
                'ℹ/ **Formato Esperado en Excel:**\n'
                '- **No modifiques** las columnas `cliente_id` ni `nombre`.\n'
                '- **valor_suscripcion:** Escribe el precio como un número puro (ej: 18500), sin puntos, comas, ni signos de $.\n'
                '- **fecha_pago / metodo_entrega / generos_preferencia:** (Opcionales) Rellena los datos de la membresía del cliente.'
            )
            st.download_button(
                label='📥 Descargar Plantilla Suscripciones (.xlsx)',
                data=generar_plantilla_suscripciones(),
                file_name='plantilla_suscripciones.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
        with st.container(border=True):
            st.markdown('### Paso 2: Sube el archivo con los valores')
            st.warning('El sistema solo procesará las filas donde la columna `valor_suscripcion` tenga un número válido.')
            archivo_subs = st.file_uploader('Sube el archivo de suscripciones', type=['xlsx'], key='up_subs')
            
            if archivo_subs:
                df_s = pd.read_excel(archivo_subs, engine='openpyxl')
                if 'cliente_id' not in df_s.columns or 'valor_suscripcion' not in df_s.columns:
                    st.error('🛑 El archivo no es válido. Usa la plantilla de suscripciones.')
                else:
                    if st.button('🚀 Actualizar/Crear Suscripciones', type='primary', use_container_width=True):
                        with st.spinner('Procesando suscripciones...'):
                            actualizados, creados, errores = procesar_suscripciones_masivas(df_s)
                            c1, c2, c3 = st.columns(3)
                            c1.metric('✅ Actualizadas', actualizados)
                            c2.metric('✨ Nuevas Creadas', creados)
                            c3.metric('❌ Errores', len(errores))
                            if actualizados > 0 or creados > 0: 
                                st.balloons()
                                st.success('¡Valores de suscripción guardados correctamente!')
                            if errores:
                                with st.expander('Ver lista de conflictos'):
                                    for err in errores: st.write(err)
                            
                            # Botón de autolimpieza de estado
                            if st.button('🧹 Limpiar Estado y Subir de Nuevo', use_container_width=True, key='btn_clean_subs'):
                                if 'up_subs' in st.session_state:
                                    del st.session_state['up_subs']
                                st.rerun()

    # ---------------- TAB: COSTOS NO VENTAS ----------------
    with tab_costos:
        with st.container(border=True):
            st.markdown('### Paso 1: Descarga la Plantilla de Costos')
            st.info(
                'ℹ/ **Formato Esperado en Excel:**\n'
                '- **fecha_ocurrencia_YYYY_MM_DD:** (Obligatorio) Formatos estándar (ej: 25/08/2026, 2026-08-25). Celdas vacías se omitirán.\n'
                '- **tipo_costo:** (Obligatorio) Tipo o categoría de gasto (ej: Contadora, Publicidad, Insumos, Personal).\n'
                '- **monto:** (Obligatorio numérico) Escribe números puros sin letras ni símbolos (ej: escribe "150000", no "$150.000").\n'
                '- **comentario:** (Opcional) Texto explicativo del costo.'
            )
            st.download_button(
                label='📥 Descargar Plantilla Costos (.xlsx)',
                data=generar_plantilla_costos(),
                file_name='plantilla_nuevos_costos.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
        with st.container(border=True):
            st.markdown('### Paso 2: Sube tu Excel Lleno')
            archivo_costos = st.file_uploader('Sube el archivo de costos', type=['xlsx'], key='up_costos')
            
            if archivo_costos:
                df_cos = pd.read_excel(archivo_costos, engine='openpyxl')
                if 'tipo_costo' not in df_cos.columns or 'monto' not in df_cos.columns:
                    st.error('🛑 El archivo no es válido. Usa la plantilla de costos del Paso 1.')
                else:
                    if st.button('🚀 Ingresar Costos Masivamente', type='primary', use_container_width=True):
                        with st.spinner('Procesando costos...'):
                            exitos_cos, errores_cos = procesar_costos_masivos(df_cos)
                            c1, c2 = st.columns(2)
                            c1.metric('✅ Ingresados exitosamente', exitos_cos)
                            c2.metric('❌ Registros fallidos', len(errores_cos))
                            
                            if exitos_cos > 0:
                                st.balloons()
                                st.success('¡Registros de costos importados exitosamente!')
                                st.cache_data.clear()
                            if errores_cos:
                                with st.expander('Ver lista de conflictos'):
                                    for err in errores_cos: st.write(err)
                            
                            # Botón de autolimpieza de estado
                            if st.button('🧹 Limpiar Estado y Subir de Nuevo', use_container_width=True, key='btn_clean_costos'):
                                if 'up_costos' in st.session_state:
                                    del st.session_state['up_costos']
                                st.rerun()

if __name__ == '__main__':
    mostrar_creacion_masiva()