import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# ====================================================
# --- LÓGICA 1: CREACIÓN DE CLIENTES NUEVOS ---
# ====================================================

def generar_plantilla_clientes():
    columnas = ['nombre', 'email', 'telefono', 'rut', 'direccion', 'instagram']
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
            columnas_texto = ['nombre', 'email', 'telefono', 'rut', 'direccion', 'instagram']
            for col in df.columns:
                if pd.notna(fila[col]):
                    if col in columnas_texto:
                        nuevo_cliente[col] = limpiar_texto_para_busqueda(str(fila[col]))
                    else:
                        nuevo_cliente[col] = fila[col]
            
            conn.table("clientes").insert(nuevo_cliente).execute()
            exitos += 1
            catalogo_actual.append(nombre_limpio)
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{nombre_limpio}'): Error -> {str(e)}")
            continue
            
    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ====================================================
# --- LÓGICA 2: CREACIÓN DE LIBROS NUEVOS ---
# ====================================================

def generar_plantilla_libros():
    # --- CAMBIO: Se añade la columna apto_cajita ---
    columnas = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion', 'stock', 'precio', 'costo', 'apto_cajita']
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
    
    for indice, fila in df.iterrows():
        barra_progreso.progress((indice + 1) / total_filas, text=f"Procesando libro {indice + 1} de {total_filas}...")
        titulo_limpio = limpiar_texto_para_busqueda(fila.get('titulo', ''))
        autor_limpio = limpiar_texto_para_busqueda(fila.get('autor', ''))
        
        if not titulo_limpio:
            errores.append(f"Fila {indice + 2}: Falta el 'titulo'. Es obligatorio.")
            continue
            
        if (titulo_limpio, autor_limpio) in catalogo_actual:
            duplicados += 1
            errores.append(f"Fila {indice + 2}: El libro '{titulo_limpio}' ({autor_limpio}) ya existe.")
            continue
            
        try:
            nuevo_libro = {}
            columnas_texto = ['titulo', 'autor', 'genero', 'editorial', 'encuadernacion']
            for col in df.columns:
                if pd.notna(fila[col]):
                    if col in columnas_texto:
                        nuevo_libro[col] = limpiar_texto_para_busqueda(str(fila[col]))
                    elif col != 'apto_cajita': # El campo booleano se trata aparte
                        nuevo_libro[col] = fila[col]
            
            # --- LÓGICA INTELIGENTE PARA 'apto_cajita' ---
            encuadernacion = nuevo_libro.get('encuadernacion', '')
            if pd.notna(fila.get('apto_cajita')):
                # Si el usuario escribió algo (TRUE, FALSE, 1, 0), se respeta
                nuevo_libro['apto_cajita'] = bool(fila['apto_cajita'])
            else:
                # Si la celda está vacía, aplicamos la regla de negocio
                nuevo_libro['apto_cajita'] = False if encuadernacion == 'TAPA DURA' else True

            conn.table("libros").insert(nuevo_libro).execute()
            exitos += 1
            catalogo_actual.append((titulo_limpio, autor_limpio))
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{titulo_limpio}'): Error -> {str(e)}")

    barra_progreso.progress(1.0, text="¡Carga finalizada!")
    return exitos, duplicados, errores

# ======================================================
# --- LÓGICA 3: IMPORTACIÓN DE VENTAS DE EVENTOS ---
# ======================================================

def generar_plantilla_ventas_masivas():
    columnas = ['nombre_evento', 'tipo_evento', 'fecha_evento', 'ingreso_total', 'costo_total', 'estado_evento', 'estado_pago', 'comentarios']
    df_vacio = pd.DataFrame(columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Eventos Masivos')
        worksheet = writer.sheets['Eventos Masivos']
        for i, col in enumerate(columnas):
            worksheet.set_column(i, i, 20)
    return output.getvalue()

def procesar_eventos_masivos(df):
    conn = get_db_connection()
    exitos, errores = 0, []

    for indice, fila in df.iterrows():
        nombre_evento = fila.get('nombre_evento')
        if pd.isna(nombre_evento):
            errores.append(f"Fila {indice + 2}: El 'nombre_evento' es obligatorio.")
            continue
        try:
            datos_evento = {
                'nombre_evento': str(nombre_evento),
                'tipo_evento': str(fila.get('tipo_evento', 'OTRO')),
                'fecha_evento': pd.to_datetime(fila.get('fecha_evento')).strftime('%Y-%m-%d') if pd.notna(fila.get('fecha_evento')) else None,
                'ingreso_total': float(fila.get('ingreso_total', 0)),
                'costo_total': float(fila.get('costo_total', 0)),
                'estado_evento': str(fila.get('estado_evento', 'FINALIZADO')),
                'estado_pago': str(fila.get('estado_pago', 'PAGADO')),
                'comentarios': str(fila.get('comentarios', '')),
                'libros_implicados': json.dumps([]), # Por defecto, sin libros asociados
                'stock_descontado': False
            }
            conn.table("ventas_masivas").insert(datos_evento).execute()
            exitos += 1
        except Exception as e:
            errores.append(f"Fila {indice + 2} ('{nombre_evento}'): Error -> {str(e)}")

    return exitos, errores

# ==========================================
# --- VISTA PRINCIPAL ---
# ==========================================
def mostrar_creacion_masiva():
    st.title("✨ Importación Masiva de Datos")
    st.markdown("Añade decenas de registros a la vez usando nuestras plantillas de Excel.")
    
    tab_clientes, tab_libros, tab_ventas_masivas, tab_suscripciones = st.tabs(["👥 Nuevos Clientes", "📚 Nuevos Libros", "📈 Eventos de Venta", "💰 Suscripciones"])

    with tab_clientes:
        # (El código de la pestaña Clientes se mantiene igual, es robusto)
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Clientes")
            st.download_button(label="📥 Descargar Plantilla Clientes (.xlsx)", data=generar_plantilla_clientes(), file_name="plantilla_nuevos_clientes.xlsx")
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el archivo con los datos")
            archivo_clientes = st.file_uploader("Sube el archivo de clientes", type=["xlsx"], key="up_clientes")
            if archivo_clientes:
                df_c = pd.read_excel(archivo_clientes, engine='openpyxl')
                if 'nombre' not in df_c.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de clientes.")
                elif st.button("🚀 Ingresar Nuevos Clientes", type="primary", use_container_width=True, key="btn_cli"):
                    exitos, duplicados, errores = procesar_clientes_masivos(df_c)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ Creados", exitos); c2.metric("⚠️ Duplicados", duplicados); c3.metric("❌ Errores", len(errores) - duplicados)
                    if errores:
                        with st.expander("Ver detalle de conflictos"):
                            st.dataframe(pd.DataFrame(errores, columns=["Descripción"]), use_container_width=True)

    with tab_libros:
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Libros")
            st.info(
                "ℹ️ **Formato Esperado:**\n"
                "- **titulo, autor:** (Obligatorios) Se usan para detectar duplicados.\n"
                "- **stock, precio, costo:** (Obligatorios) Deben ser números puros, sin '$'.\n"
                "- **apto_cajita:** (Opcional) Escribe `TRUE` o `FALSE`. Si lo dejas en blanco, se marcará como **NO APTO** si la encuadernación es 'TAPA DURA'."
            )
            st.download_button(label="📥 Descargar Plantilla Libros (.xlsx)", data=generar_plantilla_libros(), file_name="plantilla_nuevos_libros.xlsx")
        with st.container(border=True):
            st.markdown("### Paso 2: Sube tu Excel Lleno")
            archivo_libros = st.file_uploader("Sube el archivo de libros", type=["xlsx"], key="up_libros")
            if archivo_libros:
                df = pd.read_excel(archivo_libros, engine='openpyxl')
                if 'titulo' not in df.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de libros.")
                elif st.button("🚀 Ingresar Nuevos Libros", type="primary", use_container_width=True, key="btn_lib"):
                    exitos, duplicados, errores = procesar_nuevos_libros(df)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ Ingresados", exitos); c2.metric("⚠️ Duplicados", duplicados); c3.metric("❌ Errores", len(errores) - duplicados)
                    if errores:
                        with st.expander("Ver detalle de conflictos"):
                            st.dataframe(pd.DataFrame(errores, columns=["Descripción"]), use_container_width=True)
                            
    with tab_ventas_masivas:
        st.markdown("### 📈 Carga Masiva de Eventos de Venta")
        st.info("Usa esta sección para registrar rápidamente ferias, ventas de bodega o eventos especiales que no tienen libros asociados de forma individual.")
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla de Eventos")
            st.download_button(label="📥 Descargar Plantilla de Eventos (.xlsx)", data=generar_plantilla_ventas_masivas(), file_name="plantilla_eventos_masivos.xlsx")
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el archivo con los eventos")
            archivo_eventos = st.file_uploader("Sube el archivo de eventos", type=["xlsx"], key="up_eventos")
            if archivo_eventos:
                df_e = pd.read_excel(archivo_eventos, engine='openpyxl')
                if 'nombre_evento' not in df_e.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de eventos.")
                elif st.button("🚀 Registrar Eventos de Venta", type="primary", use_container_width=True, key="btn_eventos"):
                    exitos, errores = procesar_eventos_masivos(df_e)
                    c1, c2 = st.columns(2)
                    c1.metric("✅ Eventos Registrados", exitos); c2.metric("❌ Errores", len(errores))
                    if errores:
                        with st.expander("Ver detalle de conflictos"):
                            st.dataframe(pd.DataFrame(errores, columns=["Descripción"]), use_container_width=True)

    with tab_suscripciones:
        # (El código de la pestaña Suscripciones se mantiene igual, es robusto)
        with st.container(border=True):
            st.markdown("### Paso 1: Descarga la Plantilla Inteligente")
            st.download_button(label="📥 Descargar Plantilla Suscripciones (.xlsx)", data=generar_plantilla_suscripciones(), file_name="plantilla_suscripciones.xlsx")
        with st.container(border=True):
            st.markdown("### Paso 2: Sube el archivo con los valores")
            archivo_subs = st.file_uploader("Sube el archivo de suscripciones", type=["xlsx"], key="up_subs")
            if archivo_subs:
                df_s = pd.read_excel(archivo_subs, engine='openpyxl')
                if 'cliente_id' not in df_s.columns or 'valor_suscripcion' not in df_s.columns:
                    st.error("🛑 El archivo no es válido. Usa la plantilla de suscripciones.")
                elif st.button("🚀 Actualizar/Crear Suscripciones", type="primary", use_container_width=True, key="btn_subs"):
                    actualizados, creados, errores = procesar_suscripciones_masivas(df_s)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ Actualizadas", actualizados); c2.metric("✨ Nuevas Creadas", creados); c3.metric("❌ Errores", len(errores))
                    if errores:
                        with st.expander("Ver lista de conflictos"):
                            st.dataframe(pd.DataFrame(errores, columns=["Descripción"]), use_container_width=True)

if __name__ == "__main__":
    mostrar_creacion_masiva()