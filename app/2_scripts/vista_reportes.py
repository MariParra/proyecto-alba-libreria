import streamlit as st
import pandas as pd
import io
from datetime import datetime
from utilidades import get_db_connection

# ====================================================
# --- FUNCIÓN DE UTILIDAD PARA GENERAR EXCEL ---
# ====================================================
def convertir_df_a_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
        worksheet = writer.sheets['Datos']
        for i, col in enumerate(df.columns):
            try:
                max_len = max(df[col].fillna('').astype(str).map(len).max(), len(str(col))) + 2
                worksheet.set_column(i, i, max_len)
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
        # 1. Obtenemos las ASIGNACIONES (suscripciones) pendientes de envío/retiro
        res_asig = conn.table("asignaciones").select("cliente_id, estado_envio").in_("estado_envio", ["POR ENVIAR", "POR RETIRAR"]).execute()
        df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
        if not df_asig.empty:
            df_asig['origen'] = 'Suscripción'
            df_asig.rename(columns={'estado_envio': 'estado'}, inplace=True)
        
        # 2. Obtenemos las VENTAS DIRECTAS pendientes de envío/retiro
        estados_venta = ["LISTO / PENDIENTE PAGO", "PENDIENTE ARMADO PAQUETE"]
        res_ventas = conn.table("registro_ventas").select("cliente_id, estado, metodo_envio").in_("estado", estados_venta).execute()
        df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas['origen'] = 'Venta Directa'
            # Filtramos para quedarnos solo con las que realmente son para despacho
            df_ventas = df_ventas[df_ventas['metodo_envio'] != 'Retiro en tienda']
        
        # 3. Unimos ambos DataFrames de forma segura
        if df_asig.empty and df_ventas.empty:
            return pd.DataFrame()
        elif df_asig.empty:
            df_pendientes = df_ventas
        elif df_ventas.empty:
            df_pendientes = df_asig
        else:
            df_pendientes = pd.concat([df_asig, df_ventas], ignore_index=True)
            
        if df_pendientes.empty:
            return pd.DataFrame()
            
        # 4. Obtenemos los datos de los clientes para el cruce
        ids_clientes_pendientes = df_pendientes['cliente_id'].unique().tolist()
        res_clientes = conn.table("clientes").select("cliente_id, nombre, direccion, telefono").in_("cliente_id", ids_clientes_pendientes).execute()
        
        if not res_clientes.data:
            return pd.DataFrame() 
            
        df_clientes = pd.DataFrame(res_clientes.data)
        
        # 5. Hacemos el merge final y seleccionamos columnas
        df_reporte = pd.merge(df_pendientes, df_clientes, on='cliente_id', how='left')
        
        columnas_finales = ['nombre', 'direccion', 'telefono', 'origen', 'estado']
        # Evitar errores si alguna columna falta por datos incompletos
        for col in columnas_finales:
            if col not in df_reporte.columns:
                df_reporte[col] = ''
                
        return df_reporte[columnas_finales]
        
    except Exception as e:
        st.error(f"Error generando reporte de envíos: {e}")
        return pd.DataFrame()

def obtener_reporte_facturacion_sii(ano, mes):
    conn = get_db_connection()
    try:
        # 1. Obtenemos las ventas del mes y año especificados (formateamos a 2 dígitos)
        mes_str = f"{mes:02d}"
        res_ventas = conn.table("registro_ventas").select("cliente_id, fecha_venta, monto_final").gte('fecha_venta', f'{ano}-{mes_str}-01').lte('fecha_venta', f'{ano}-{mes_str}-31').execute()
        
        if not res_ventas.data:
            return pd.DataFrame()
        df_ventas = pd.DataFrame(res_ventas.data)

        # 2. Obtenemos los datos de los clientes para el cruce
        res_clientes = conn.table("clientes").select("cliente_id, nombre, rut").execute()
        if not res_clientes.data:
            df_ventas['nombre_cliente'] = 'Cliente no encontrado'
            df_ventas['rut_cliente'] = ''
            return df_ventas
            
        df_clientes = pd.DataFrame(res_clientes.data)
        
        # 3. Unimos las tablas
        df_reporte = pd.merge(df_ventas, df_clientes, on='cliente_id', how='left')
        
        # 4. Creamos y formateamos las columnas requeridas por el SII
        df_reporte.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
        df_reporte['Tipo DTE'] = 39 # Código oficial del SII para Boleta Electrónica
        df_reporte['Folio'] = '' # Dejar en blanco para llenado manual posterior
        df_reporte.rename(columns={'fecha_venta': 'Fecha Emision'}, inplace=True)
        df_reporte.rename(columns={'rut': 'RUT Receptor'}, inplace=True)
        df_reporte.rename(columns={'nombre_cliente': 'Razon Social Receptor'}, inplace=True)
        df_reporte['Monto Total'] = df_reporte['monto_final']
        
        # Seleccionamos y ordenamos las columnas finales
        columnas_sii = ['Tipo DTE', 'Folio', 'Fecha Emision', 'RUT Receptor', 'Razon Social Receptor', 'Monto Total']
        
        # Aseguramos que existan todas las columnas
        for col in columnas_sii:
            if col not in df_reporte.columns:
                df_reporte[col] = ''
                
        return df_reporte[columnas_sii]
        
    except Exception as e: 
        st.error(f"Error generando reporte SII: {e}")
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
        st.info("💡 Estos reportes están diseñados para ayudarte en la toma de decisiones y la logística diaria.")
        
        col1, col2, col3 = st.columns(3)
        
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
        
        with col2:
            with st.container(border=True):
                st.markdown("#### 📦 Envíos Pendientes Unificados")
                st.write("Lista consolidada de **todas** las cajas (suscripciones y ventas) que están listas para ser despachadas o retiradas.")
                
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

        with col3:
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

    with tab2:
        st.markdown("### Descarga de Respaldo Completo")
        st.write("Aquí puedes descargar el contenido crudo de las tablas principales de tu base de datos.")
        
        tablas_disponibles = ["clientes", "libros", "registro_ventas", "asignaciones", "suscripciones"]
        tabla_seleccionada = st.selectbox("Selecciona la tabla a exportar:", tablas_disponibles)
        
        if st.button(f"📥 Exportar tabla '{tabla_seleccionada}' completa", use_container_width=True):
            with st.spinner(f"Extrayendo datos de {tabla_seleccionada}..."):
                df_tabla = obtener_tabla(tabla_seleccionada)
                if not df_tabla.empty:
                    st.download_button(
                        label="Haz clic aquí para descargar el archivo .xlsx",
                        data=convertir_df_a_excel(df_tabla),
                        file_name=f"backup_{tabla_seleccionada}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        type="primary"
                    )
                else:
                    st.warning("La tabla seleccionada está vacía.")