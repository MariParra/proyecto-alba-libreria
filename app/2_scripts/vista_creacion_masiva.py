import streamlit as st
import pandas as pd
import io
from datetime import datetime
import json
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# ====================================================
# --- LÓGICA 1: CREACIÓN DE CLIENTES NUEVOS ---
# ====================================================
def generar_plantilla_clientes():
    columnas = ['nombre', 'email', 'telefono', 'direccion', 'instagram']
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

    res_clientes = conn.table("clientes").select("nombre").execute()
    catalogo_actual = [limpiar_texto_para_busqueda(c['nombre']) for c in res_clientes.data] if res_clientes.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de clientes...")
    total_filas = len(df)
    
    columnas_texto = ['nombre', 'email', 'telefono', 'direccion', 'instagram']

    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando cliente {indice + 1}/{total_filas}...")
        
        nombre_limpio = limpiar_texto_para_busqueda(fila.get('nombre', ''))
        
        if not nombre_limpio:
            errores.append(f"Fila {indice + 2}: Falta el 'nombre'. Es obligatorio.")
            continue
            
        if nombre_limpio in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El cliente '{nombre_limpio}' ya existe.")
            continue
            
        try:
            nuevo_cliente = {"status": "CLIENTE REGULAR"}
            for col in df.columns:
                if pd.notna(fila[col]):
                    if col in columnas_texto:
                        nuevo_cliente[col] = limpiar_texto_para_busqueda(str(fila[col]))
                    else:
                        nuevo_cliente[col] = fila[col]
            
            # Asegurarse de que el nombre principal esté limpio
            if 'nombre' in nuevo_cliente:
                nuevo_cliente['nombre'] = limpiar_texto_para_busqueda(nuevo_cliente['nombre'])

            conn.table("clientes").insert(nuevo_cliente).execute()
            exitos += 1
            catalogo_actual.append(nombre_limpio)
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Fallo en creación masiva en Fila {indice + 2} ('{nombre_limpio}'). Detalle: {e}"
            
            log_error(
                vista="vista_creacion_masiva",
                funcion="procesar_clientes_masivos (bucle)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            
            errores.append(f"Fila {indice + 2} ('{nombre_limpio}'): Error -> {str(e)}")
            continue
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ====================================================
# --- LÓGICA 2: CREACIÓN DE LIBROS NUEVOS ---
# ====================================================
def generar_plantilla_libros():
    columnas = [
        'titulo', 'autor', 'genero', 'editorial', 'encuadernacion', 
        'stock', 'precio', 'precio_original', 'costo', 
        'apto_cajita', 'destacado', 'visible_catalogo'
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
    
    res_libros = conn.table("libros").select("titulo, autor").execute()
    catalogo_actual = [(limpiar_texto_para_busqueda(l['titulo']), limpiar_texto_para_busqueda(l.get('autor', ''))) for l in res_libros.data] if res_libros.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de catálogo...")
    total_filas = len(df)
    
    columnas_texto = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion']
    
    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        
        titulo_limpio = limpiar_texto_para_busqueda(fila.get('titulo', ''))
        autor_limpio = limpiar_texto_para_busqueda(fila.get('autor', ''))
        
        if not titulo_limpio:
            errores.append(f"Fila {indice + 2}: Falta el 'titulo'. Es obligatorio.")
            continue
            
        if (titulo_limpio, autor_limpio) in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El libro '{titulo_limpio}' ya existe.")
            continue
            
        try:
            nuevo_libro = {}
            for col in df.columns:
                if pd.notna(fila[col]):
                    if col in columnas_texto:
                        nuevo_libro[col] = limpiar_texto_para_busqueda(str(fila[col]))
                    elif col not in ['apto_cajita', 'destacado', 'visible_catalogo']:
                        nuevo_libro[col] = fila[col]
            
            # --- LÓGICA BOOLEANOS ---
            encuadernacion = str(nuevo_libro.get('encuadernacion', ''))
            
            # 1. apto_cajita
            if pd.notna(fila.get('apto_cajita')):
                nuevo_libro['apto_cajita'] = bool(fila['apto_cajita'])
            else:
                nuevo_libro['apto_cajita'] = False if encuadernacion.upper() == 'TAPA DURA' else True
            
            # 2. destacado
            if pd.notna(fila.get('destacado')):
                nuevo_libro['destacado'] = bool(fila['destacado'])
            else:
                nuevo_libro['destacado'] = False
                
            # 3. visible_catalogo
            if pd.notna(fila.get('visible_catalogo')):
                nuevo_libro['visible_catalogo'] = bool(fila['visible_catalogo'])
            else:
                nuevo_libro['visible_catalogo'] = True
                    
            conn.table("libros").insert(nuevo_libro).execute()
            exitos += 1
            catalogo_actual.append((titulo_limpio, autor_limpio))
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Fallo en creación masiva en Fila {indice + 2} ('{titulo_limpio}'). Detalle: {e}"
            
            log_error(
                vista="vista_creacion_masiva",
                funcion="procesar_nuevos_libros",
                error=error_detalle,
                email_usuario=email_usuario
            )
            errores.append(f"Fila {indice + 2} ('{titulo_limpio}'): Error -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ======================================================
# --- LÓGICA 3: IMPORTACIÓN DE VENTAS PASADAS ---
# ======================================================
def generar_plantilla_ventas():
    columnas = ['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente', 'Titulo_Libro', 'Cantidad', 'Precio_Unitario', 'Valor_Envio', 'Metodo_Envio', 'Comentario', 'Estado', 'Abono']
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
        errores.append(f"Fila {i+2}: La fecha es inválida o está vacía y fue omitida.")
    df.dropna(subset=['Fecha_Venta_YYYY_MM_DD'], inplace=True)

    res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
    res_libros = conn.table("libros").select("libro_id, titulo, autor, costo").execute()
    
    map_clientes = {limpiar_texto_para_busqueda(c['nombre']): c['cliente_id'] for c in res_clientes.data} if res_clientes.data else {}
    map_libros = {limpiar_texto_para_busqueda(l['titulo']): l for l in res_libros.data} if res_libros.data else {}

    df['Valor_Envio'] = pd.to_numeric(df['Valor_Envio'], errors='coerce').fillna(0)
    df['Cantidad'] = pd.to_numeric(df['Cantidad'], errors='coerce').fillna(1)
    df['Precio_Unitario'] = pd.to_numeric(df['Precio_Unitario'], errors='coerce').fillna(0)
    df['Abono'] = pd.to_numeric(df.get('Abono'), errors='coerce').fillna(0)
    
    grupos = df.groupby(['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente'])
    barra_progreso = st.progress(0, text="Procesando ventas...")
    total_grupos, actual = len(grupos), 0

    for (fecha_dt, cliente_nombre), grupo in grupos:
        actual += 1
        barra_progreso.progress(actual / total_grupos, text=f"Procesando venta {actual} de {total_grupos}...")
        
        try:
            cliente_norm = limpiar_texto_para_busqueda(str(cliente_nombre))
            if cliente_norm not in map_clientes:
                errores.append(f"Venta {fecha_dt.strftime('%Y-%m-%d')}: Cliente '{cliente_nombre}' no existe en tu base de datos.")
                continue
            cliente_id = map_clientes[cliente_norm]

            libros_vendidos, subtotal, costo_total_venta = [], 0.0, 0.0

            for _, fila in grupo.iterrows():
                titulo_norm = limpiar_texto_para_busqueda(fila.get('Titulo_Libro', ''))
                libro_info = map_libros.get(titulo_norm)
                
                libro_id = int(libro_info['libro_id']) if libro_info and pd.notna(libro_info.get('libro_id')) else None
                autor_libro = limpiar_texto_para_busqueda(libro_info['autor']) if libro_info and pd.notna(libro_info.get('autor')) else "DESCONOCIDO"

                if libro_info and pd.notna(libro_info.get('costo')):
                    costo_total_venta += float(libro_info['costo']) * int(fila['Cantidad'])

                cant = int(fila['Cantidad'])
                precio_u = float(fila['Precio_Unitario'])
                
                libros_vendidos.append({
                    "libro_id": libro_id, "titulo": titulo_norm, "autor": autor_libro,
                    "cantidad": cant, "precio": precio_u
                })
                subtotal += (cant * precio_u)

            valor_envio = float(grupo['Valor_Envio'].iloc[0])
            metodo_envio = limpiar_texto_para_busqueda(str(grupo['Metodo_Envio'].iloc[0])) if pd.notna(grupo['Metodo_Envio'].iloc[0]) else "NO ESPECIFICADO"
            comentario = limpiar_texto_para_busqueda(str(grupo['Comentario'].iloc[0])) if pd.notna(grupo['Comentario'].iloc[0]) else "IMPORTACION MASIVA"
            estado_venta = limpiar_texto_para_busqueda(str(grupo['Estado'].iloc[0])) if pd.notna(grupo['Estado'].iloc[0]) else "FINALIZADO"
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            abono_total_venta = float(grupo['Abono'].sum())
            monto_final = subtotal + valor_envio

            venta_data = {
                "cliente_id": cliente_id, "fecha_venta": fecha_str,
                "libros_vendidos": json.dumps(libros_vendidos, ensure_ascii=False),
                "subtotal_libros": subtotal, "valor_envio": valor_envio,
                "monto_final": monto_final, "metodo_envio": metodo_envio,
                "comentario": comentario, "estado": estado_venta,
                "abono": abono_total_venta, "costo_venta": costo_total_venta
            }

            conn.table("registro_ventas").insert(venta_data).execute()
            exitos += 1

        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Fallo en creación masiva en Fecha-Cliente {fecha_dt.strftime('%Y-%m-%d')} ('{cliente_nombre}'). Detalle: {e}"
            
            log_error(
                vista="vista_creacion_masiva",
                funcion="procesar_ventas_masivas",
                error=error_detalle,
                email_usuario=email_usuario
            )
            errores.append(f"Error en Venta de {cliente_nombre} ({fecha_dt.strftime('%Y-%m-%d')}): {str(e)}")

    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, errores

# ====================================================
# --- LÓGICA 4: IMPORTACIÓN DE SUSCRIPCIONES ---
# ====================================================
def generar_plantilla_suscripciones():
    conn = get_db_connection()
    try:
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        df_clientes = pd.DataFrame(res_clientes.data)
        df_clientes['valor_suscripcion'] = ''
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_clientes.to_excel(writer, index=False, sheet_name='Suscripciones')
            worksheet = writer.sheets['Suscripciones']
            worksheet.set_column('A:A', 10)
            worksheet.set_column('B:B', 30)
            worksheet.set_column('C:C', 20)
        return output.getvalue()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        log_error(
            vista="vista_creacion_masiva",
            funcion="generar_plantilla_suscripciones",
            error=e,
            email_usuario=email_usuario
        )
        
        st.error(f"Error al generar plantilla de suscripciones: {e}")
        return None

def procesar_suscripciones_masivas(df):
    conn = get_db_connection()
    actualizados, creados, errores = 0, 0, []

    df.dropna(subset=['valor_suscripcion'], inplace=True)
    df['valor_suscripcion'] = pd.to_numeric(df['valor_suscripcion'], errors='coerce')
    df.dropna(subset=['valor_suscripcion'], inplace=True)

    barra_progreso = st.progress(0, text="Procesando suscripciones...")
    total_filas = len(df)

    for i, fila in df.iterrows():
        barra_progreso.progress((i + 1) / total_filas, text=f"Procesando cliente {i+1}/{total_filas}...")
        try:
            cliente_id = int(fila['cliente_id'])
            valor = float(fila['valor_suscripcion'])

            res = conn.table("suscripciones").select("suscripcion_id").eq("cliente_id", cliente_id).execute()
            datos = {"cliente_id": cliente_id, "valor_suscripcion": valor}

            if res.data:
                conn.table("suscripciones").update(datos).eq("cliente_id", cliente_id).execute()
                actualizados += 1
            else:
                conn.table("suscripciones").insert(datos).execute()
                creados += 1
        except Exception as e:
            errores.append(f"Fila {i+2}: Error con cliente ID {fila.get('cliente_id', 'N/A')} -> {str(e)}")

    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return actualizados, creados, errores

# ==========================================
# --- VISTA PRINCIPAL ---
# ==========================================
def mostrar_creacion_masiva():
    st.title("✨ Importación Masiva")
    st.markdown("Añade decenas de registros a la vez usando nuestras plantillas de Excel. Sigue las instrucciones de cada pestaña para evitar errores.")
    
    tab_clientes, tab_libros, tab_ventas, tab_suscripciones = st.tabs(["👥 Nuevos Clientes", "📚 Nuevos Libros", "🛒 Ventas Pasadas", "💰 Suscripciones"])

    with tab_clientes:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Clientes")
            st.info(
                "ℹ️ **Formato Esperado en Excel:**\n"
                "- **nombre:** (Obligatorio) No importa si usas mayúsculas o tildes, el sistema lo limpiará automáticamente. Se usa para evitar duplicados.\n"
                "- **email, telefono, direccion, instagram:** (Opcionales) Se guardarán tal como los escribas."
            )
            st.download_button(
                label="📥 Descargar Plantilla Clientes (.xlsx)",
                data=generar_plantilla_clientes(),
                file_name="plantilla_nuevos_clientes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el archivo con los datos")
            archivo_clientes = st.file_uploader("Sube el archivo de clientes", type=["xlsx"], key="up_clientes")
            
            if archivo_clientes:
                df_c = pd.read_excel(archivo_clientes, engine='openpyxl')
                if 'nombre' not in df_c.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de clientes que descargaste en el Paso 1.")
                else:
                    if st.button("🚀 Ingresar Nuevos Clientes", type="primary", use_container_width=True):
                        with st.spinner("Procesando y validando clientes..."):
                            exitos, duplicados, errores = procesar_clientes_masivos(df_c)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("✅ Creados", exitos)
                            c2.metric("⚠️ Duplicados Omitidos", duplicados)
                            c3.metric("❌ Errores Críticos", len(errores) - duplicados)
                            if exitos > 0: 
                                st.balloons()
                                st.success("¡Nuevos clientes añadidos correctamente!")
                            if errores:
                                with st.expander("Ver lista de conflictos"):
                                    for err in errores: st.write(err)

    with tab_libros:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Libros")
            st.info(
                "ℹ️ **Formato Esperado en Excel:**\n"
                "- **titulo y autor:** (Obligatorios) El sistema los limpiará (mayúsculas, sin tilde) y los usará combinados para detectar si el libro ya existe.\n"
                "- **genero, editorial, encuadernacion:** (Opcionales) Texto libre.\n"
                "- **stock, precio, precio_original, costo:** (Obligatorios numéricos) Deben ser números puros. **NO escribas** el signo '$' ni letras. Ej: Escribe '15000', no '$15.000'.\n"
                "- **apto_cajita:** (Opcional) Escribe `TRUE` o `FALSE`. Si lo dejas en blanco, se detectará automáticamente.\n"
                "- **destacado:** (Opcional) Escribe `TRUE` para que aparezca en el carrusel de destacados. Por defecto es `FALSE`.\n"
                "- **visible_catalogo:** (Opcional) Escribe `FALSE` para ocultar el libro del catálogo público. Por defecto es `TRUE`."
            )
            st.download_button(
                label="📥 Descargar Plantilla Libros (.xlsx)",
                data=generar_plantilla_libros(),
                file_name="plantilla_nuevos_libros.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with st.container(border=True):
            st.markdown("### Paso 2: Sube tu Excel Lleno")
            archivo_libros = st.file_uploader("Sube el archivo de libros", type=["xlsx"], key="up_libros")
            if archivo_libros:
                df = pd.read_excel(archivo_libros, engine='openpyxl')
                if 'titulo' not in df.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de libros.")
                else:
                    if st.button("🚀 Ingresar Libros", type="primary", use_container_width=True):
                        with st.spinner("Creando libros..."):
                            exitos, duplicados, errores = procesar_nuevos_libros(df)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("✅ Ingresados", exitos)
                            c2.metric("⚠️ Duplicados Omitidos", duplicados)
                            c3.metric("❌ Errores Críticos", len(errores) - duplicados)
                            if exitos > 0: st.success(f"¡{exitos} libros añadidos!")
                            if errores:
                                with st.expander("Ver lista de conflictos"):
                                    for err in errores: st.write(err)

    with tab_ventas:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Ventas")
            st.warning(
                "**¡Condición Previa!** Antes de subir ventas, asegúrate de que los **Clientes** y **Libros** "
                "que vas a reportar YA EXISTAN en tu base de datos. Si un cliente o libro no existe, la fila será rechazada."
            )
            st.info(
                "ℹ️ **Formato Esperado en Excel:**\n"
                "- **Fecha_Venta_YYYY_MM_DD:** El sistema soporta formatos normales (ej: 25/08/2026, 2026-08-25). Celdas vacías o texto inválido se omitirán.\n"
                "- **Nombre_Cliente y Titulo_Libro:** Deben coincidir con los nombres en tu base de datos (no te preocupes por tildes o mayúsculas).\n"
                "- **Cantidad, Precio_Unitario, Valor_Envio, Abono:** Deben ser **números puros**, sin símbolos.\n"
                "- **Estado:** Escribe estados como 'FINALIZADO' o 'PENDIENTE PAGO' (por defecto será 'FINALIZADO').\n"
                "- **Costos:** Sube las ventas con los costos ya calculados, sino quedarán en cero\n"
                "💡 **Tip UX:** Si una clienta compró 3 libros el mismo día, usa 3 filas en el Excel con la misma fecha y cliente. El sistema las agrupará en una sola Venta automáticamente."
            )
            st.download_button(
                label="📥 Descargar Plantilla Ventas (.xlsx)",
                data=generar_plantilla_ventas(),
                file_name="plantilla_ventas_pasadas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el Archivo de Ventas")
            archivo_ventas = st.file_uploader("Sube el archivo de ventas", type=["xlsx"], key="up_ventas")
            if archivo_ventas:
                df_v = pd.read_excel(archivo_ventas, engine='openpyxl')
                if 'Nombre_Cliente' not in df_v.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de ventas.")
                else:
                    if st.button("🚀 Registrar Ventas Masivamente", type="primary", use_container_width=True):
                        with st.spinner("Procesando y agrupando ventas..."):
                            exitos_v, errores_v = procesar_ventas_masivas(df_v)
                            c1, c2 = st.columns(2)
                            c1.metric("✅ Boletas Exitosas", exitos_v)
                            c2.metric("❌ Filas con Errores", len(errores_v))
                            if exitos_v > 0: 
                                st.balloons()
                                st.success("¡Ventas registradas correctamente en el historial!")
                            if errores_v:
                                with st.expander("Ver lista de conflictos (Revisa fechas o clientes no encontrados)"):
                                    for err in errores_v: st.write(err)

    with tab_suscripciones:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla Inteligente")
            st.info(
                "La plantilla se generará automáticamente con el ID y Nombre de todos tus clientes actuales.\n\n"
                "ℹ️ **Formato Esperado en Excel:**\n"
                "- **No modifiques** las columnas `cliente_id` ni `nombre`.\n"
                "- **valor_suscripcion:** Escribe el precio como un número puro (ej: 15000), sin puntos, comas, ni signos de $. Deja en blanco los que no quieras actualizar."
            )
            st.download_button(
                label="📥 Descargar Plantilla Suscripciones (.xlsx)",
                data=generar_plantilla_suscripciones(),
                file_name="plantilla_suscripciones.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el archivo con los valores")
            st.warning("El sistema solo procesará las filas donde la columna `valor_suscripcion` tenga un número válido.")
            archivo_subs = st.file_uploader("Sube el archivo de suscripciones", type=["xlsx"], key="up_subs")
            
            if archivo_subs:
                df_s = pd.read_excel(archivo_subs, engine='openpyxl')
                if 'cliente_id' not in df_s.columns or 'valor_suscripcion' not in df_s.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de suscripciones.")
                else:
                    if st.button("🚀 Actualizar/Crear Suscripciones", type="primary", use_container_width=True):
                        with st.spinner("Procesando suscripciones..."):
                            actualizados, creados, errores = procesar_suscripciones_masivas(df_s)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("✅ Actualizadas", actualizados)
                            c2.metric("✨ Nuevas Creadas", creados)
                            c3.metric("❌ Errores", len(errores))
                            if actualizados > 0 or creados > 0: 
                                st.balloons()
                                st.success("¡Valores de suscripción guardados correctamente!")
                            if errores:
                                with st.expander("Ver lista de conflictos"):
                                    for err in errores: st.write(err)

if __name__ == "__main__":
    mostrar_creacion_masiva()