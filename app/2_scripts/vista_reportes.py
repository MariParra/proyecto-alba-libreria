import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime
from utilidades import get_db_connection

# ====================================================
# --- FUNCIÓN DE UTILIDAD PARA GENERAR EXCEL ---
# ====================================================

def limpiar_df_para_excel(df):
    """
    Limpia el DataFrame antes de exportarlo a Excel:
    1. Convierte diccionarios y listas (JSONB) a strings para que Excel no falle.
    2. Remueve las zonas horarias (tz) de las fechas, ya que Excel no las soporta bien.
    """
    df_limpio = df.copy()
    for col in df_limpio.columns:
        # Convertir JSON/Listas a string
        if df_limpio[col].apply(lambda x: isinstance(x, (dict, list))).any():
            df_limpio[col] = df_limpio[col].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x)
        
        # Quitar Timezone para compatibilidad con Excel
        if pd.api.types.is_datetime64tz_dtype(df_limpio[col]):
            df_limpio[col] = df_limpio[col].dt.tz_localize(None)
            
    return df_limpio

def convertir_df_a_excel(df):
    df_seguro = limpiar_df_para_excel(df)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_seguro.to_excel(writer, index=False, sheet_name='Datos')
        worksheet = writer.sheets['Datos']
        for i, col in enumerate(df_seguro.columns):
            try:
                max_len = max(df_seguro[col].fillna('').astype(str).map(len).max(), len(str(col))) + 2
                # Limitamos el ancho máximo a 50 para evitar columnas infinitas con JSON largos
                worksheet.set_column(i, i, min(max_len, 50))
            except (ValueError, TypeError):
                worksheet.set_column(i, i, 15)
    return output.getvalue()

# ====================================================
# --- FUNCIONES DE EXTRACCIÓN DE DATOS ---
# ====================================================

def obtener_tabla(nombre_tabla):
    conn = get_db_connection()
    try:
        res = conn.table(nombre_tabla).select("*").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: 
        return pd.DataFrame()

def obtener_reporte_bajo_stock(limite=5):
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("titulo, autor, editorial, stock, precio").lte("stock", limite).order("stock").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: 
        return pd.DataFrame()

def obtener_reporte_envios_pendientes():
    conn = get_db_connection()
    try:
        # 1. Obtenemos las ASIGNACIONES (suscripciones) pendientes
        res_asig = conn.table("asignaciones").select("cliente_id, estado_envio").in_("estado_envio", ["POR ENVIAR", "POR RETIRAR"]).execute()
        df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
        if not df_asig.empty:
            df_asig['origen'] = 'Suscripción'
            df_asig.rename(columns={'estado_envio': 'estado'}, inplace=True)
        
        # 2. Obtenemos las VENTAS DIRECTAS pendientes
        estados_venta = ["LISTO / PENDIENTE PAGO", "PENDIENTE ARMADO PAQUETE"]
        res_ventas = conn.table("registro_ventas").select("cliente_id, estado, metodo_envio").in_("estado", estados_venta).execute()
        df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas['origen'] = 'Venta Directa'
            df_ventas = df_ventas[df_ventas['metodo_envio'] != 'Retiro en tienda']
        
        # 3. Unimos ambos DataFrames
        if df_asig.empty and df_ventas.empty:
            return pd.DataFrame()
        elif df_asig.empty:
            df_pendientes = df_ventas
        elif df_ventas.empty:
            df_pendientes = df_asig
        else:
            df_pendientes = pd.concat([df_asig, df_ventas], ignore_index=True)
            
        if df_pendientes.empty: return pd.DataFrame()
            
        # 4. Obtenemos los datos de los clientes
        ids_clientes_pendientes = df_pendientes['cliente_id'].unique().tolist()
        res_clientes = conn.table("clientes").select("cliente_id, nombre, direccion, telefono").in_("cliente_id", ids_clientes_pendientes).execute()
        if not res_clientes.data: return pd.DataFrame() 
            
        df_clientes = pd.DataFrame(res_clientes.data)
        
        # 5. Hacemos el merge final
        df_reporte = pd.merge(df_pendientes, df_clientes, on='cliente_id', how='left')
        columnas_finales = ['nombre', 'direccion', 'telefono', 'origen', 'estado']
        
        for col in columnas_finales:
            if col not in df_reporte.columns: df_reporte[col] = ''
                
        return df_reporte[columnas_finales]
        
    except Exception as e:
        st.error(f"Error generando reporte de envíos: {e}")
        return pd.DataFrame()

def obtener_reporte_facturacion_sii(ano, mes):
    conn = get_db_connection()
    try:
        mes_str = f"{mes:02d}"
        res_ventas = conn.table("registro_ventas").select("cliente_id, fecha_venta, monto_final").gte('fecha_venta', f'{ano}-{mes_str}-01').lte('fecha_venta', f'{ano}-{mes_str}-31').execute()
        
        if not res_ventas.data: return pd.DataFrame()
        df_ventas = pd.DataFrame(res_ventas.data)

        res_clientes = conn.table("clientes").select("cliente_id, nombre, rut").execute()
        if not res_clientes.data:
            df_ventas['nombre_cliente'] = 'Cliente no encontrado'
            df_ventas['rut_cliente'] = ''
            return df_ventas
            
        df_clientes = pd.DataFrame(res_clientes.data)
        df_reporte = pd.merge(df_ventas, df_clientes, on='cliente_id', how='left')
        
        df_reporte.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
        df_reporte['Tipo DTE'] = 39 
        df_reporte['Folio'] = '' 
        df_reporte.rename(columns={'fecha_venta': 'Fecha Emision', 'rut': 'RUT Receptor', 'nombre_cliente': 'Razon Social Receptor'}, inplace=True)
        df_reporte['Monto Total'] = df_reporte['monto_final']
        
        columnas_sii = ['Tipo DTE', 'Folio', 'Fecha Emision', 'RUT Receptor', 'Razon Social Receptor', 'Monto Total']
        for col in columnas_sii:
            if col not in df_reporte.columns: df_reporte[col] = ''
                
        return df_reporte[columnas_sii]
    except Exception as e: 
        st.error(f"Error generando reporte SII: {e}")
        return pd.DataFrame()

def obtener_reporte_asignaciones(ano, lista_meses):
    """Genera un reporte de asignaciones legible con cruce de clientes y libros."""
    conn = get_db_connection()
    try:
        # 1. Obtener asignaciones del periodo
        res_asig = conn.table("asignaciones").select("*").eq("ano", ano).in_("mes", lista_meses).execute()
        if not res_asig.data: return pd.DataFrame()
        df_asig = pd.DataFrame(res_asig.data)
        
        # 2. Obtener Clientes (nombres, rut, email)
        ids_clientes = df_asig['cliente_id'].dropna().unique().tolist()
        df_clientes = pd.DataFrame()
        if ids_clientes:
            res_cli = conn.table("clientes").select("cliente_id, nombre, rut, email, status").in_("cliente_id", ids_clientes).execute()
            if res_cli.data: df_clientes = pd.DataFrame(res_cli.data)
        
        # 3. Obtener Libros Principales (título, autor)
        ids_libros = df_asig['libro_suscripcion_id'].dropna().unique().tolist()
        ids_libros = [int(x) for x in ids_libros if pd.notna(x)]
        df_libros = pd.DataFrame()
        if ids_libros:
            res_lib = conn.table("libros").select("libro_id, titulo, autor").in_("libro_id", ids_libros).execute()
            if res_lib.data: 
                df_libros = pd.DataFrame(res_lib.data)
                df_libros.rename(columns={'libro_id': 'libro_suscripcion_id', 'titulo': 'libro_principal', 'autor': 'autor_libro'}, inplace=True)

        # 4. Cruce de datos (Merge)
        df_reporte = df_asig.copy()
        if not df_clientes.empty:
            df_reporte = pd.merge(df_reporte, df_clientes, on='cliente_id', how='left')
        else:
            df_reporte['nombre'] = 'Desconocido'
            df_reporte['rut'] = ''
            
        if not df_libros.empty:
            df_reporte = pd.merge(df_reporte, df_libros, on='libro_suscripcion_id', how='left')
        else:
            df_reporte['libro_principal'] = 'Pendiente'
            df_reporte['autor_libro'] = ''

        # 5. Limpiar y formatear para humanos
        df_reporte['nombre'] = df_reporte.get('nombre', 'Desconocido').fillna('Desconocido')
        df_reporte['libro_principal'] = df_reporte.get('libro_principal', '⏳ PENDIENTE').fillna('⏳ PENDIENTE')
        df_reporte['estado_envio'] = df_reporte.get('estado_envio', '').fillna('SIN ESTADO')
        df_reporte['pagado'] = df_reporte.get('pagado', '').fillna('NO')
        
        # Extraer nombres lógicos
        df_reporte.rename(columns={
            'asignacion_id': 'ID Asignacion',
            'ano': 'Año',
            'mes': 'Mes',
            'nombre': 'Cliente',
            'rut': 'RUT',
            'status': 'Estado Suscripción',
            'libro_principal': 'Libro Principal Asignado',
            'autor_libro': 'Autor',
            'extras': 'Libros Extras',
            'estado_envio': 'Estado Logística',
            'pagado': 'Suscripción Pagada',
            'monto_total': 'Monto Total ($)',
            'comentario': 'Comentarios'
        }, inplace=True)
        
        # Eliminar las columnas ID para no ensuciar el reporte
        cols_a_eliminar = ['cliente_id', 'libro_suscripcion_id']
        df_reporte.drop(columns=[c for c in cols_a_eliminar if c in df_reporte.columns], inplace=True)
        
        # Ordenar columnas lógicamente
        columnas_ordenadas = ['ID Asignacion', 'Año', 'Mes', 'Cliente', 'RUT', 'Estado Suscripción', 'Libro Principal Asignado', 'Autor', 'Libros Extras', 'Estado Logística', 'Suscripción Pagada', 'Monto Total ($)', 'Comentarios']
        columnas_finales = [c for c in columnas_ordenadas if c in df_reporte.columns]
        
        return df_reporte[columnas_finales]
        
    except Exception as e:
        st.error(f"Error generando reporte de asignaciones: {e}")
        return pd.DataFrame()

# ====================================================
# --- VISTA PRINCIPAL ---
# ====================================================
def mostrar_reportes():
    st.title("📥 Reportes y Descargas")
    st.markdown("Genera reportes estratégicos o descarga la información bruta de tu base de datos.")
    
    tab1, tab2 = st.tabs(["📊 Reportes Inteligentes", "💾 Exportar Tablas Base"])
    
    with tab1:
        st.markdown("### Reportes listos para usar")
        st.info("💡 Estos reportes cruzan datos de varias tablas para entregarte información legible (con nombres en lugar de IDs) y lista para la toma de decisiones.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.markdown("#### 🚨 Libros con Bajo Stock")
                st.write("Identifica rápidamente los libros que están por agotarse para planificar tus compras.")
                limite_stock = st.number_input("Considerar bajo stock si es igual o menor a:", min_value=0, max_value=50, value=5, step=1)
                
                if st.button("Generar Reporte de Stock", type="primary", use_container_width=True):
                    df_stock = obtener_reporte_bajo_stock(limite_stock)
                    if not df_stock.empty:
                        st.download_button(
                            label=f"Descargar Reporte ({len(df_stock)} libros) (.xlsx)",
                            data=convertir_df_a_excel(df_stock),
                            file_name="reporte_bajo_stock.xlsx"
                        )
                    else:
                        st.success("¡Excelente! No tienes libros con stock crítico.")

            with st.container(border=True):
                st.markdown("#### 🇨🇱 Facturación (SII)")
                st.write("Genera el reporte de ventas del mes con el formato para el SII (Boleta Electrónica).")
                
                meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                mes_fact_sel = st.selectbox("Mes:", list(meses_dict.values()), index=datetime.now().month - 1, key="mes_fact")
                ano_fact_sel = st.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="ano_fact")
                mes_fact_num = list(meses_dict.keys())[list(meses_dict.values()).index(mes_fact_sel)]
                
                if st.button("Generar Reporte SII", type="primary", use_container_width=True):
                    df_sii = obtener_reporte_facturacion_sii(ano_fact_sel, mes_fact_num)
                    if not df_sii.empty:
                        st.download_button(
                            label=f"Descargar Facturación {mes_fact_sel}-{ano_fact_sel} (.xlsx)",
                            data=convertir_df_a_excel(df_sii),
                            file_name=f"reporte_sii_{ano_fact_sel}_{mes_fact_num}.xlsx",
                        )
                    else:
                        st.warning("No se encontraron ventas para el período seleccionado.")

        with col2:
            with st.container(border=True):
                st.markdown("#### 📦 Envíos Pendientes Unificados")
                st.write("Lista consolidada de **todas** las cajas (suscripciones y ventas) que están listas para ser despachadas.")
                
                if st.button("Generar Reporte de Envíos", type="primary", use_container_width=True):
                    df_envios = obtener_reporte_envios_pendientes()
                    
                    if not df_envios.empty:
                        st.download_button(
                            label=f"Descargar {len(df_envios)} Envíos Pendientes (.xlsx)",
                            data=convertir_df_a_excel(df_envios),
                            file_name="envios_pendientes.xlsx"
                        )
                    else:
                        st.success("✅ ¡Todo despachado! No hay envíos pendientes.")

            with st.container(border=True):
                st.markdown("#### 🎁 Historial de Asignaciones (Cajitas)")
                st.write("Exporta el detalle de las cajas armadas con el nombre del cliente y los libros que recibió.")
                
                meses_dict_asig = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                mes_actual = datetime.now().month
                
                ano_asig = st.number_input("Año del reporte:", min_value=2020, max_value=2050, value=datetime.now().year, step=1)
                meses_asig_nombres = st.multiselect("Selecciona los meses a incluir:", list(meses_dict_asig.values()), default=[meses_dict_asig[mes_actual]])
                
                meses_asig_nums = [list(meses_dict_asig.keys())[list(meses_dict_asig.values()).index(m)] for m in meses_asig_nombres]
                
                if st.button("Generar Reporte de Asignaciones", type="primary", use_container_width=True):
                    if not meses_asig_nums:
                        st.error("Debes seleccionar al menos un mes.")
                    else:
                        df_asig_reporte = obtener_reporte_asignaciones(ano_asig, meses_asig_nums)
                        if not df_asig_reporte.empty:
                            st.download_button(
                                label=f"Descargar Asignaciones ({len(df_asig_reporte)} registros) (.xlsx)",
                                data=convertir_df_a_excel(df_asig_reporte),
                                file_name=f"reporte_asignaciones_{ano_asig}.xlsx"
                            )
                        else:
                            st.warning("No se encontraron registros de asignación para los meses seleccionados.")

    with tab2:
        st.markdown("### Descarga de Respaldo Crudo (Backup)")
        st.write("Aquí puedes descargar el contenido directo y sin procesar de cualquier tabla de la base de datos.")
        
        # Tablas actualizadas excluyendo errores y tareas
        tablas_disponibles = [
            "clientes", 
            "libros", 
            "registro_ventas", 
            "asignaciones", 
            "suscripciones", 
            "ventas_masivas", 
            "librero_historico", 
            "historial_cambios_masivos", 
            "historial_logs",
            "meses_cerrados"
        ]
        
        tabla_seleccionada = st.selectbox("Selecciona la tabla a exportar:", sorted(tablas_disponibles))
        
        if st.button(f"📥 Exportar tabla '{tabla_seleccionada}' completa", use_container_width=True):
            with st.spinner(f"Extrayendo y formateando datos de {tabla_seleccionada}..."):
                df_tabla = obtener_tabla(tabla_seleccionada)
                if not df_tabla.empty:
                    st.download_button(
                        label="✅ Haz clic aquí para descargar el archivo .xlsx",
                        data=convertir_df_a_excel(df_tabla),
                        file_name=f"backup_{tabla_seleccionada}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        type="primary"
                    )
                else:
                    st.warning("La tabla seleccionada está vacía.")