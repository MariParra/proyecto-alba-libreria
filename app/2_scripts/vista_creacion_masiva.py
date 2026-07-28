import streamlit as st
import pandas as pd
import io
import json
import unicodedata
from utilidades import get_db_connection

def normalizar_texto(texto):
    """Normaliza el texto eliminando acentos y mayúsculas para búsquedas exactas."""
    if pd.isna(texto): return ""
    s = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
    return ' '.join(s.strip().upper().split())

# ==========================================
# --- LÓGICA 1: CREACIÓN DE LIBROS NUEVOS ---
# ==========================================
def generar_plantilla_libros():
    columnas = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion', 'stock', 'precio', 'precio_original']
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Nuevos Libros')
        worksheet = writer.sheets['Nuevos Libros']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 15)
    return output.getvalue()

def procesar_nuevos_libros(df):
    conn = get_db_connection()
    exitos, duplicados, errores = 0, 0, []
    
    res_libros = conn.table("libros").select("titulo, autor").execute()
    catalogo_actual = [(normalizar_texto(l['titulo']), normalizar_texto(l.get('autor', ''))) for l in res_libros.data] if res_libros.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de catálogo...")
    total_filas = len(df)
    
    columnas_texto = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion']
    
    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        
        titulo_limpio = normalizar_texto(fila.get('titulo', ''))
        autor_limpio = normalizar_texto(fila.get('autor', ''))
        
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
                if pd.isna(fila[col]):
                    nuevo_libro[col] = None
                elif col in columnas_texto:
                    nuevo_libro[col] = normalizar_texto(fila[col])
                else:
                    nuevo_libro[col] = fila[col]
                    
            conn.table("libros").insert(nuevo_libro).execute()
            exitos += 1
            catalogo_actual.append((titulo_limpio, autor_limpio))
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{titulo_limpio}'): Error -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ==========================================
# --- LÓGICA 2: IMPORTACIÓN DE VENTAS ---
# ==========================================
def generar_plantilla_ventas():
    columnas = ['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente', 'Titulo_Libro', 'Cantidad', 'Precio_Unitario', 'Valor_Envio', 'Metodo_Envio', 'Comentario']
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

    res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
    res_libros = conn.table("libros").select("libro_id, titulo, autor").execute()
    
    map_clientes = {normalizar_texto(c['nombre']): c['cliente_id'] for c in res_clientes.data} if res_clientes.data else {}
    map_libros = {normalizar_texto(l['titulo']): l for l in res_libros.data} if res_libros.data else {}

    df['Valor_Envio'] = pd.to_numeric(df['Valor_Envio'], errors='coerce').fillna(0)
    df['Cantidad'] = pd.to_numeric(df['Cantidad'], errors='coerce').fillna(1)
    df['Precio_Unitario'] = pd.to_numeric(df['Precio_Unitario'], errors='coerce').fillna(0)
    
    grupos = df.groupby(['Fecha_Venta_YYYY_MM_DD', 'Nombre_Cliente'])
    
    barra_progreso = st.progress(0, text="Procesando ventas...")
    total_grupos = len(grupos)
    actual = 0

    for (fecha_raw, cliente_nombre), grupo in grupos:
        actual += 1
        barra_progreso.progress(actual / total_grupos, text=f"Procesando venta {actual} de {total_grupos}...")
        
        try:
            cliente_norm = normalizar_texto(cliente_nombre)
            if cliente_norm not in map_clientes:
                errores.append(f"Venta {fecha_raw}: Cliente '{cliente_nombre}' no existe en tu base de datos.")
                continue
            cliente_id = map_clientes[cliente_norm]

            libros_vendidos = []
            subtotal = 0.0

            for _, fila in grupo.iterrows():
                titulo = str(fila.get('Titulo_Libro', ''))
                titulo_norm = normalizar_texto(titulo)
                
                libro_info = map_libros.get(titulo_norm)
                libro_id = int(libro_info['libro_id']) if libro_info else None
                autor_libro = libro_info['autor'] if libro_info else "Desconocido"

                cant = int(fila['Cantidad'])
                precio_u = float(fila['Precio_Unitario'])
                
                libros_vendidos.append({
                    "libro_id": libro_id, "titulo": titulo, "autor": autor_libro,
                    "cantidad": cant, "precio": precio_u
                })
                subtotal += (cant * precio_u)

            valor_envio = float(grupo['Valor_Envio'].iloc[0])
            metodo_envio = str(grupo['Metodo_Envio'].iloc[0]) if pd.notna(grupo['Metodo_Envio'].iloc[0]) else "No especificado"
            comentario = str(grupo['Comentario'].iloc[0]) if pd.notna(grupo['Comentario'].iloc[0]) else "Importación Masiva"
            fecha_str = str(fecha_raw).split()[0]
            
            monto_final = subtotal + valor_envio

            venta_data = {
                "cliente_id": cliente_id, "fecha_venta": fecha_str,
                "libros_vendidos": json.dumps(libros_vendidos, ensure_ascii=False),
                "subtotal_libros": subtotal, "valor_envio": valor_envio,
                "monto_final": monto_final, "metodo_envio": metodo_envio,
                "comentario": comentario
            }

            conn.table("registro_ventas").insert(venta_data).execute()
            exitos += 1

        except Exception as e:
            errores.append(f"Error en Venta de {cliente_nombre} ({fecha_raw}): {str(e)}")

    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, errores

# ====================================================
# --- LÓGICA 3: IMPORTACIÓN DE SUSCRIPCIONES ---
# ====================================================

def generar_plantilla_suscripciones():
    """Genera una plantilla Excel pre-rellenada con todos los clientes."""
    conn = get_db_connection()
    try:
        # Obtenemos todos los clientes
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        df_clientes = pd.DataFrame(res_clientes.data)
        
        # Añadimos la columna para que el usuario rellene
        df_clientes['valor_suscripcion'] = ''
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_clientes.to_excel(writer, index=False, sheet_name='Suscripciones')
            worksheet = writer.sheets['Suscripciones']
            worksheet.set_column('A:A', 10) # cliente_id
            worksheet.set_column('B:B', 30) # nombre
            worksheet.set_column('C:C', 20) # valor_suscripcion
        return output.getvalue()
    except Exception as e:
        st.error(f"Error al generar plantilla de suscripciones: {e}")
        return None

def procesar_suscripciones_masivas(df):
    """Actualiza o crea suscripciones basadas en el Excel subido."""
    conn = get_db_connection()
    actualizados, creados, errores = 0, 0, []

    # Limpiamos el DataFrame de filas sin valor de suscripción
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

            # Verificamos si ya existe una suscripción para ese cliente
            res = conn.table("suscripciones").select("suscripcion_id").eq("cliente_id", cliente_id).execute()
            
            datos = {"cliente_id": cliente_id, "valor_suscripcion": valor}

            if res.data:
                # Si existe, la actualizamos (UPSERT)
                conn.table("suscripciones").update(datos).eq("cliente_id", cliente_id).execute()
                actualizados += 1
            else:
                # Si no existe, la creamos
                conn.table("suscripciones").insert(datos).execute()
                creados += 1
        except Exception as e:
            errores.append(f"Fila {i+2}: Error con cliente ID {fila.get('cliente_id', 'N/A')} -> {str(e)}")

    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return actualizados, creados, errores

# ==========================================
# --- LÓGICA 4: CREACIÓN DE CLIENTES NUEVOS ---
# ==========================================
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
    catalogo_actual = [normalizar_texto(c['nombre']) for c in res_clientes.data] if res_clientes.data else []
    
    barra_progreso = st.progress(0, text="Iniciando carga de clientes...")
    total_filas = len(df)
    
    columnas_texto = ['nombre', 'email', 'telefono', 'direccion', 'instagram']

    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando cliente {indice + 1}/{total_filas}...")
        
        nombre_limpio = normalizar_texto(fila.get('nombre', ''))
        
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
                if pd.isna(fila[col]):
                    nuevo_cliente[col] = None
                elif col in columnas_texto:
                    nuevo_cliente[col] = normalizar_texto(str(fila[col]))
                else:
                    nuevo_cliente[col] = fila[col]
                    
            conn.table("clientes").insert(nuevo_cliente).execute()
            exitos += 1
            catalogo_actual.append(nombre_limpio)
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{nombre_limpio}'): Error -> {str(e)}")
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores
# ==========================================
# --- VISTA PRINCIPAL ---
# ==========================================
def mostrar_creacion_masiva():
    st.title("✨ Importación Masiva")
    st.markdown("Añade decenas de registros a la vez usando nuestras plantillas de Excel.")
    
    tab_clientes, tab_libros, tab_ventas, tab_suscripciones = st.tabs(["👥 Nuevos Clientes", "📚 Nuevos Libros", "🛒 Ventas Pasadas", "🐧 Suscripciones"])
    
    with tab_libros:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Libros")
            st.download_button(
                label="📥 Descargar Plantilla Libros (.xlsx)", data=generar_plantilla_libros(),
                file_name="plantilla_nuevos_libros.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
                            c2.metric("⚠️ Duplicados", duplicados)
                            c3.metric("❌ Errores", len(errores) - duplicados)
                            if exitos > 0: st.success(f"¡{exitos} libros añadidos!")
                            if errores:
                                with st.expander("Ver lista de conflictos"):
                                    for err in errores: st.write(err)

    with tab_ventas:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Ventas")
            st.info("💡 **Tip UX:** Si una clienta compró 3 libros en el mismo día, usa 3 filas en el Excel con la misma fecha y el mismo nombre. El sistema las agrupará en una sola Venta/Boleta automáticamente calculando los subtotales.")
            st.download_button(
                label="📥 Descargar Plantilla Ventas (.xlsx)", data=generar_plantilla_ventas(),
                file_name="plantilla_ventas_pasadas.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
                            c2.metric("❌ Errores", len(errores_v))
                            if exitos_v > 0: 
                                st.balloons()
                                st.success("¡Ventas registradas correctamente en el historial!")
                            if errores_v:
                                with st.expander("Ver lista de conflictos (Clientes no encontrados)"):
                                    for err in errores_v: st.write(err)
    with tab_clientes:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Clientes")
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
                    st.error("🛑 El archivo no es válido. Usa la plantilla de clientes.")
                else:
                    if st.button("🚀 Ingresar Nuevos Clientes", type="primary", use_container_width=True):
                        with st.spinner("Procesando y validando clientes..."):
                            exitos, duplicados, errores = procesar_clientes_masivos(df_c)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("✅ Creados", exitos)
                            c2.metric("⚠️ Duplicados", duplicados)
                            c3.metric("❌ Errores", len(errores) - duplicados)
                            if exitos > 0: 
                                st.balloons()
                                st.success("¡Nuevos clientes añadidos correctamente!")
                            if errores:
                                with st.expander("Ver lista de conflictos"):
                                    for err in errores: st.write(err)
    with tab_suscripciones:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla Inteligente")
            st.info("La plantilla se generará con los IDs y Nombres de todos tus clientes actuales.")
            st.download_button(
                label="📥 Descargar Plantilla Suscripciones (.xlsx)",
                data=generar_plantilla_suscripciones(),
                file_name="plantilla_suscripciones.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el archivo con los valores")
            st.warning("El sistema solo procesará las filas donde la columna `valor_suscripcion` tenga un número.")
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