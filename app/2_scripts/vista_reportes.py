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
    1. Convierte diccionarios y listas (JSONB) a strings.
    2. Remueve las zonas horarias (tz) de las fechas.
    """
    df_limpio = df.copy()
    for col in df_limpio.columns:
        if df_limpio[col].apply(lambda x: isinstance(x, (dict, list))).any():
            df_limpio[col] = df_limpio[col].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x)
        
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

def obtener_reporte_asignaciones(ano, lista_meses):
    conn = get_db_connection()
    try:
        res_asig = conn.table("asignaciones").select("*").eq("ano", ano).in_("mes", lista_meses).execute()
        if not res_asig.data: return pd.DataFrame()
        df_asig = pd.DataFrame(res_asig.data)
        
        ids_clientes = df_asig['cliente_id'].dropna().unique().tolist()
        df_clientes = pd.DataFrame()
        if ids_clientes:
            res_cli = conn.table("clientes").select("cliente_id, nombre, rut, email, status").in_("cliente_id", ids_clientes).execute()
            if res_cli.data: df_clientes = pd.DataFrame(res_cli.data)
        
        ids_libros = [int(x) for x in df_asig['libro_suscripcion_id'].dropna().unique() if pd.notna(x)]
        df_libros = pd.DataFrame()
        if ids_libros:
            res_lib = conn.table("libros").select("libro_id, titulo, autor").in_("libro_id", ids_libros).execute()
            if res_lib.data: 
                df_libros = pd.DataFrame(res_lib.data)
                df_libros.rename(columns={'libro_id': 'libro_suscripcion_id', 'titulo': 'libro_principal', 'autor': 'autor_libro'}, inplace=True)

        df_reporte = pd.merge(df_asig, df_clientes, on='cliente_id', how='left')
        if not df_libros.empty:
            df_reporte = pd.merge(df_reporte, df_libros, on='libro_suscripcion_id', how='left')

        df_reporte.rename(columns={
            'asignacion_id': 'ID Asignacion', 'ano': 'Año', 'mes': 'Mes',
            'nombre': 'Cliente', 'rut': 'RUT', 'status': 'Estado Suscripción',
            'libro_principal': 'Libro Principal Asignado', 'autor_libro': 'Autor',
            'extras': 'Libros Extras', 'estado_envio': 'Estado Logística',
            'pagado': 'Suscripción Pagada', 'monto_total': 'Monto Total ($)',
            'comentario': 'Comentarios'
        }, inplace=True)
        
        for col in ['Cliente', 'Libro Principal Asignado', 'Estado Logística', 'Suscripción Pagada']:
            df_reporte[col] = df_reporte.get(col, 'N/A').fillna('N/A')

        columnas_ordenadas = ['ID Asignacion', 'Año', 'Mes', 'Cliente', 'RUT', 'Estado Suscripción', 'Libro Principal Asignado', 'Autor', 'Libros Extras', 'Estado Logística', 'Suscripción Pagada', 'Monto Total ($)', 'Comentarios']
        columnas_finales = [c for c in columnas_ordenadas if c in df_reporte.columns]
        
        return df_reporte[columnas_finales]
        
    except Exception as e:
        st.error(f"Error generando reporte de asignaciones: {e}")
        return pd.DataFrame()

def obtener_reporte_envios_pendientes():
    conn = get_db_connection()
    try:
        res_asig = conn.table("asignaciones").select("cliente_id, estado_envio").in_("estado_envio", ["POR ENVIAR", "POR RETIRAR"]).execute()
        df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
        if not df_asig.empty:
            df_asig['origen'] = 'Suscripción'
            df_asig.rename(columns={'estado_envio': 'estado'}, inplace=True)
        
        estados_venta = ["LISTO / PENDIENTE PAGO", "PENDIENTE ARMADO PAQUETE", "PAQUETE LISTO"]
        res_ventas = conn.table("registro_ventas").select("cliente_id, estado, metodo_envio").in_("estado", estados_venta).execute()
        df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas['origen'] = 'Venta Directa'
            df_ventas = df_ventas[~df_ventas['metodo_envio'].str.contains('Retiro', na=False, case=False)]

        df_pendientes = pd.concat([df_asig, df_ventas], ignore_index=True)
        if df_pendientes.empty: return pd.DataFrame()
            
        ids_clientes = [int(x) for x in df_pendientes['cliente_id'].dropna().unique()]
        if not ids_clientes: return pd.DataFrame()
            
        res_clientes = conn.table("clientes").select("cliente_id, nombre, rut, email, telefono, direccion").in_("cliente_id", ids_clientes).execute()
        if not res_clientes.data: return df_pendientes

        df_clientes = pd.DataFrame(res_clientes.data)
        df_reporte = pd.merge(df_pendientes, df_clientes, on='cliente_id', how='left')

        df_reporte.rename(columns={
            'nombre': 'Nombre Cliente', 'rut': 'RUT', 'email': 'Email',
            'telefono': 'Telefono', 'direccion': 'Dirección Completa'
        }, inplace=True)
        
        # Añadir columnas para la empresa de courier
        df_reporte['Comuna'] = ''
        df_reporte['Detalle/Depto'] = ''
        df_reporte['Largo(cm)'] = 25
        df_reporte['Ancho(cm)'] = 20
        df_reporte['Alto(cm)'] = 10
        df_reporte['Peso(kg)'] = 1
        
        columnas_finales = ['Nombre Cliente', 'RUT', 'Email', 'Telefono', 'Dirección Completa', 'Comuna', 'Detalle/Depto', 'Largo(cm)', 'Ancho(cm)', 'Alto(cm)', 'Peso(kg)', 'origen', 'estado']
        return df_reporte[columnas_finales]
    except Exception as e:
        st.error(f"Error generando reporte de envíos: {e}")
        return pd.DataFrame()

def obtener_reporte_sii(ano, mes, tipo_dte):
    conn = get_db_connection()
    try:
        mes_str = f"{mes:02d}"
        res_ventas = conn.table("registro_ventas").select("cliente_id, fecha_venta, monto_final, libros_vendidos").gte('fecha_venta', f'{ano}-{mes_str}-01').lte('fecha_venta', f'{ano}-{mes_str}-31T23:59:59').execute()
        if not res_ventas.data: return pd.DataFrame()
        df_ventas = pd.DataFrame(res_ventas.data)

        ids_clientes = [int(x) for x in df_ventas['cliente_id'].dropna().unique()]
        res_clientes = conn.table("clientes").select("cliente_id, nombre, rut, direccion").in_("cliente_id", ids_clientes).execute()
        df_clientes = pd.DataFrame(res_clientes.data)
        
        df_reporte = pd.merge(df_ventas, df_clientes, on='cliente_id', how='left').fillna('')

        if tipo_dte == 'Boleta':
            df_reporte['Fecha Emisin'] = pd.to_datetime(df_reporte['fecha_venta']).dt.strftime('%d-%m-%Y')
            df_reporte['Tipo Boleta'] = 'Afecta'
            df_reporte['RUT Receptor'] = df_reporte['rut']
            df_reporte['Nombre Receptor'] = df_reporte['nombre']
            df_reporte['Detalle Producto/Servicio'] = df_reporte['libros_vendidos'].apply(lambda x: ", ".join([f"{item['cantidad']}x {item['titulo']}" for item in json.loads(x)]) if isinstance(x, str) and x.startswith('[') else x)
            df_reporte['Cantidad'] = 1
            df_reporte['Precio Unitario'] = df_reporte['monto_final']
            df_reporte['Monto Exento'] = 0
            df_reporte['Monto Total'] = df_reporte['monto_final']
            columnas_finales = ['Fecha Emisin', 'Tipo Boleta', 'RUT Receptor', 'Nombre Receptor', 'Detalle Producto/Servicio', 'Cantidad', 'Precio Unitario', 'Monto Exento', 'Monto Total']
        
        elif tipo_dte == 'Factura':
            df_reporte['Fecha Emisin'] = pd.to_datetime(df_reporte['fecha_venta']).dt.strftime('%d-%m-%Y')
            df_reporte['RUT Empresa Receptor'] = df_reporte['rut']
            df_reporte['Razon Social'] = df_reporte['nombre']
            df_reporte['Giro Comercial'] = '' # Campo manual
            df_reporte['Comuna Receptor'] = '' # Campo manual
            df_reporte['Direccin Receptor'] = df_reporte['direccion']
            df_reporte['Detalle Item'] = df_reporte['libros_vendidos'].apply(lambda x: ", ".join([f"{item['cantidad']}x {item['titulo']}" for item in json.loads(x)]) if isinstance(x, str) and x.startswith('[') else x)
            df_reporte['Cantidad'] = 1
            df_reporte['Monto Neto'] = (df_reporte['monto_final'].astype(float) / 1.19).round(0)
            df_reporte['Precio Unitario (Neto)'] = df_reporte['Monto Neto']
            df_reporte['IVA (19%)'] = (df_reporte['Monto Neto'] * 0.19).round(0)
            df_reporte['Total'] = df_reporte['monto_final']
            columnas_finales = ['Fecha Emisin', 'RUT Empresa Receptor', 'Razon Social', 'Giro Comercial', 'Comuna Receptor', 'Direccin Receptor', 'Detalle Item', 'Cantidad', 'Precio Unitario (Neto)', 'Monto Neto', 'IVA (19%)', 'Total']

        return df_reporte[columnas_finales]
    except Exception as e:
        st.error(f"Error generando reporte SII: {e}")
        return pd.DataFrame()

def obtener_reporte_bajo_stock(limite=5):
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("titulo, autor, editorial, stock, precio").lte("stock", limite).order("stock").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: 
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
        st.info("💡 Estos reportes cruzan datos para entregarte información lista para la toma de decisiones.")
        
        # --- REPORTE 1: ASIGNACIONES ---
        with st.container(border=True):
            st.markdown("#### 🎁 Historial de Asignaciones (Cajitas)")
            st.write("Exporta el detalle de las cajas armadas con el nombre del cliente y los libros que recibió.")
            
            c1, c2 = st.columns(2)
            ano_asig = c1.number_input("Año del reporte:", min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="ano_asig")
            meses_dict_asig = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
            meses_asig_nombres = c2.multiselect("Selecciona los meses a incluir:", list(meses_dict_asig.values()), default=[meses_dict_asig[datetime.now().month]], key="meses_asig")
            
            if st.button("Generar Reporte de Asignaciones", type="primary", use_container_width=True, key="btn_asig"):
                if not meses_asig_nombres:
                    st.error("Debes seleccionar al menos un mes.")
                else:
                    meses_asig_nums = [list(meses_dict_asig.keys())[list(meses_dict_asig.values()).index(m)] for m in meses_asig_nombres]
                    df_asig_reporte = obtener_reporte_asignaciones(ano_asig, meses_asig_nums)
                    if not df_asig_reporte.empty:
                        st.download_button(label=f"Descargar Asignaciones ({len(df_asig_reporte)} registros) (.xlsx)", data=convertir_df_a_excel(df_asig_reporte), file_name=f"reporte_asignaciones_{ano_asig}.xlsx")
                    else:
                        st.warning("No se encontraron registros de asignación para los meses seleccionados.")

        # --- REPORTE 2: ENVÍOS PENDIENTES ---
        with st.container(border=True):
            st.markdown("#### 🚚 Envíos Pendientes Unificados")
            st.write("Lista consolidada de todas las cajas (suscripciones y ventas) listas para despacho, con formato para courier.")
            if st.button("Generar Reporte de Envíos", type="primary", use_container_width=True, key="btn_envios"):
                df_envios = obtener_reporte_envios_pendientes()
                if not df_envios.empty:
                    st.download_button(label=f"Descargar {len(df_envios)} Envíos Pendientes (.xlsx)", data=convertir_df_a_excel(df_envios), file_name="envios_pendientes.xlsx")
                else:
                    st.success("✅ ¡Todo despachado! No hay envíos pendientes.")

        # --- REPORTE 3: SII ---
        with st.container(border=True):
            st.markdown("#### 🇨🇱 Facturación (SII)")
            st.write("Genera el reporte de ventas del mes con el formato para Boletas o Facturas electrónicas.")
            
            c3, c4 = st.columns(2)
            mes_fact_sel = c3.selectbox("Mes:", list(meses_dict_asig.values()), index=datetime.now().month - 1, key="mes_fact_sii")
            ano_fact_sel = c4.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="ano_fact_sii")
            
            tipo_dte_sel = st.selectbox("Selecciona el tipo de documento a generar:", ["Boleta", "Factura"])
            
            if st.button(f"Generar Reporte SII para {tipo_dte_sel}s", type="primary", use_container_width=True, key="btn_sii"):
                mes_fact_num = list(meses_dict_asig.keys())[list(meses_dict_asig.values()).index(mes_fact_sel)]
                df_sii = obtener_reporte_sii(ano_fact_sel, mes_fact_num, tipo_dte_sel)
                if not df_sii.empty:
                    st.download_button(label=f"Descargar {tipo_dte_sel}s de {mes_fact_sel}-{ano_fact_sel} (.xlsx)", data=convertir_df_a_excel(df_sii), file_name=f"reporte_sii_{tipo_dte_sel.lower()}_{ano_fact_sel}_{mes_fact_num}.xlsx")
                else:
                    st.warning("No se encontraron ventas para el período seleccionado.")

        # --- REPORTE 4: BAJO STOCK ---
        with st.container(border=True):
            st.markdown("#### 🚨 Libros con Bajo Stock")
            st.write("Identifica rápidamente los libros que están por agotarse para planificar tus compras.")
            limite_stock = st.number_input("Considerar bajo stock si es igual o menor a:", min_value=0, max_value=50, value=5, step=1, key="limite_stock_reporte")
            if st.button("Generar Reporte de Stock", type="primary", use_container_width=True, key="btn_stock"):
                df_stock = obtener_reporte_bajo_stock(limite_stock)
                if not df_stock.empty:
                    st.download_button(label=f"Descargar Reporte ({len(df_stock)} libros) (.xlsx)", data=convertir_df_a_excel(df_stock), file_name="reporte_bajo_stock.xlsx")
                else:
                    st.success("¡Excelente! No tienes libros con stock crítico.")

    with tab2:
        st.markdown("### Descarga de Respaldo Crudo (Backup)")
        st.write("Aquí puedes descargar el contenido directo y sin procesar de cualquier tabla de la base de datos.")
        
        tablas_disponibles = ["clientes", "libros", "registro_ventas", "asignaciones", "suscripciones", "ventas_masivas", "librero_historico", "historial_cambios_masivos", "historial_logs", "meses_cerrados"]
        tabla_seleccionada = st.selectbox("Selecciona la tabla a exportar:", sorted(tablas_disponibles))
        
        if st.button(f"📥 Exportar tabla '{tabla_seleccionada}' completa", use_container_width=True, key="btn_export"):
            with st.spinner(f"Extrayendo y formateando datos de {tabla_seleccionada}..."):
                df_tabla = obtener_tabla(tabla_seleccionada)
                if not df_tabla.empty:
                    st.download_button(label="✅ Haz clic aquí para descargar el archivo .xlsx", data=convertir_df_a_excel(df_tabla), file_name=f"backup_{tabla_seleccionada}_{datetime.now().strftime('%Y%m%d')}.xlsx", type="primary")
                else:
                    st.warning("La tabla seleccionada está vacía.")