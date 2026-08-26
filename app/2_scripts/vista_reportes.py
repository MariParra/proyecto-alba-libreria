import streamlit as st
import pandas as pd
import io
import json
from datetime import datetime
from utilidades import get_db_connection, log_error

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

def convertir_pendientes_a_excel(df_caja, df_asig):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if not df_caja.empty:
            df_caja_seguro = limpiar_df_para_excel(df_caja)
            df_caja_seguro.to_excel(writer, index=False, sheet_name='Ventas Caja Pendientes')
            worksheet = writer.sheets['Ventas Caja Pendientes']
            for i, col in enumerate(df_caja_seguro.columns):
                try:
                    max_len = max(df_caja_seguro[col].fillna('').astype(str).map(len).max(), len(str(col))) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
                except (ValueError, TypeError):
                    worksheet.set_column(i, i, 15)
        if not df_asig.empty:
            df_asig_seguro = limpiar_df_para_excel(df_asig)
            df_asig_seguro.to_excel(writer, index=False, sheet_name='Asignaciones Pendientes')
            worksheet = writer.sheets['Asignaciones Pendientes']
            for i, col in enumerate(df_asig_seguro.columns):
                try:
                    max_len = max(df_asig_seguro[col].fillna('').astype(str).map(len).max(), len(str(col))) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
                except (ValueError, TypeError):
                    worksheet.set_column(i, i, 15)
    return output.getvalue()

# ====================================================
# --- FUNCIONES DE EXTRACCIÓN DE DATOS ---
# ====================================================

def obtener_tabla(nombre_tabla):
    """Descarga de forma dinámica y paginada el 100% de una tabla para backup sin límite de 1000."""
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        
        # Mapeamos la columna ID correcta según la tabla para un ordenamiento consistente
        order_col = "id"
        if nombre_tabla == "clientes": order_col = "cliente_id"
        elif nombre_tabla == "libros": order_col = "libro_id"
        elif nombre_tabla == "registro_ventas": order_col = "venta_id"
        elif nombre_tabla == "asignaciones": order_col = "asignacion_id"
        elif nombre_tabla == "suscripciones": order_col = "suscripcion_id"
        elif nombre_tabla == "ventas_masivas": order_col = "evento_id"
        elif nombre_tabla == "librero_historico": order_col = "registro_id"
        elif nombre_tabla == "costos_no_ventas": order_col = "costo_id"

        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table(nombre_tabla)
                .select("*")
                .order(order_col)
                .range(start, end).execute())
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception as e:
        log_error("vista_reportes", "obtener_tabla", e, st.session_state.get('email_usuario', 'Desconocido'))
        return pd.DataFrame()

def obtener_reporte_asignaciones(ano, lista_meses):
    """Genera reporte paginado de asignaciones del periodo cruzando tablas sin límites."""
    conn = get_db_connection()
    try:
        all_asig = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_asig = (conn.table("asignaciones")
                .select("*")
                .eq("ano", ano)
                .in_("mes", lista_meses)
                .order("asignacion_id")
                .range(start, end).execute())
            if res_asig.data:
                all_asig.extend(res_asig.data)
                if len(res_asig.data) < chunk_size:
                    break
            else:
                break
                
        if not all_asig: return pd.DataFrame()
        df_asig = pd.DataFrame(all_asig)
        
        ids_clientes = df_asig['cliente_id'].dropna().unique().tolist()
        df_clientes = pd.DataFrame()
        if ids_clientes:
            client_data = []
            for idx in range(0, len(ids_clientes), 1000):
                chunk = ids_clientes[idx:idx + 1000]
                res_cli = conn.table("clientes").select("cliente_id, nombre, rut, email, status").in_("cliente_id", chunk).execute()
                if res_cli.data:
                    client_data.extend(res_cli.data)
            df_clientes = pd.DataFrame(client_data) if client_data else pd.DataFrame()
        
        ids_libros = [int(x) for x in df_asig['libro_suscripcion_id'].dropna().unique() if pd.notna(x)]
        df_libros = pd.DataFrame()
        if ids_libros:
            book_data = []
            for idx in range(0, len(ids_libros), 1000):
                chunk = ids_libros[idx:idx + 1000]
                res_lib = conn.table("libros").select("libro_id, titulo, autor, destacado, visible_catalogo").in_("libro_id", chunk).execute()
                if res_lib.data:
                    book_data.extend(res_lib.data)
            if book_data: 
                df_libros = pd.DataFrame(book_data)
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
            'comentario': 'Comentarios',
            'destacado': '¿Libro Destacado?', 'visible_catalogo': '¿Visible en Web?'
        }, inplace=True)
        
        for col in ['Cliente', 'Libro Principal Asignado', 'Estado Logística', 'Suscripción Pagada']:
            if col in df_reporte.columns:
                df_reporte[col] = df_reporte[col].fillna('N/A')

        columnas_ordenadas = [
            'ID Asignacion', 'Año', 'Mes', 'Cliente', 'RUT', 'Estado Suscripción', 
            'Libro Principal Asignado', 'Autor', '¿Libro Destacado?', '¿Visible en Web?',
            'Libros Extras', 'Estado Logística', 'Suscripción Pagada', 'Monto Total ($)', 'Comentarios'
        ]
        columnas_finales = [c for c in columnas_ordenadas if c in df_reporte.columns]
        
        return df_reporte[columnas_finales]
        
    except Exception as e:
        st.error(f"Error generando reporte de asignaciones: {e}")
        return pd.DataFrame()

def obtener_reporte_envios_pendientes():
    """Genera reporte paginado consolidando envíos del suscripción y de ventas."""
    conn = get_db_connection()
    try:
        # Asignaciones (Paginado)
        all_asig = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_asig = (conn.table("asignaciones")
                .select("cliente_id, estado_envio")
                .in_("estado_envio", ["POR ENVIAR", "POR RETIRAR"])
                .order("asignacion_id")
                .range(start, end).execute())
            if res_asig.data:
                all_asig.extend(res_asig.data)
                if len(res_asig.data) < chunk_size:
                    break
            else:
                break
        df_asig = pd.DataFrame(all_asig) if all_asig else pd.DataFrame()
        if not df_asig.empty:
            df_asig['origen'] = 'Suscripción'
            df_asig.rename(columns={'estado_envio': 'estado'}, inplace=True)
        
        # Ventas directas (Paginado)
        all_ventas = []
        estados_venta = ["LISTO / PENDIENTE PAGO", "PENDIENTE ARMADO PAQUETE", "PAQUETE LISTO"]
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_ventas = (conn.table("registro_ventas")
                .select("cliente_id, estado, metodo_envio")
                .in_("estado", estados_venta)
                .order("venta_id")
                .range(start, end).execute())
            if res_ventas.data:
                all_ventas.extend(res_ventas.data)
                if len(res_ventas.data) < chunk_size:
                    break
            else:
                break
        df_ventas = pd.DataFrame(all_ventas) if all_ventas else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas['origen'] = 'Venta Directa'
            df_ventas = df_ventas[~df_ventas['metodo_envio'].str.contains('Retiro', na=False, case=False)]

        df_pendientes = pd.concat([df_asig, df_ventas], ignore_index=True)
        if df_pendientes.empty: return pd.DataFrame()
            
        ids_clientes = [int(x) for x in df_pendientes['cliente_id'].dropna().unique()]
        if not ids_clientes: return pd.DataFrame()
            
        client_data = []
        for idx in range(0, len(ids_clientes), 1000):
            chunk = ids_clientes[idx:idx + 1000]
            res_clientes = conn.table("clientes").select("cliente_id, nombre, rut, email, telefono, direccion").in_("cliente_id", chunk).execute()
            if res_clientes.data:
                client_data.extend(res_clientes.data)
        if not client_data: return df_pendientes

        df_clientes = pd.DataFrame(client_data)
        df_reporte = pd.merge(df_pendientes, df_clientes, on='cliente_id', how='left')

        df_reporte.rename(columns={
            'nombre': 'Nombre Cliente', 'rut': 'RUT', 'email': 'Email',
            'telefono': 'Telefono', 'direccion': 'Dirección Completa'
        }, inplace=True)
        
        # Añadir columnas estándar para la empresa de courier
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
    """Genera reporte paginado mensual del SII cruzando clientes."""
    conn = get_db_connection()
    try:
        mes_str = f"{mes:02d}"
        
        # Ventas (Paginado)
        all_ventas = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_ventas = (conn.table("registro_ventas")
                .select("cliente_id, fecha_venta, monto_final, libros_vendidos")
                .gte('fecha_venta', f'{ano}-{mes_str}-01')
                .transparent_range('fecha_venta', f'{ano}-{mes_str}-31T23:59:59') # placeholder range
                .order("venta_id")
                .range(start, end).execute())
            if res_ventas.data:
                all_ventas.extend(res_ventas.data)
                if len(res_ventas.data) < chunk_size:
                    break
            else:
                break
                
        if not all_ventas: return pd.DataFrame()
        df_ventas = pd.DataFrame(all_ventas)

        ids_clientes = [int(x) for x in df_ventas['cliente_id'].dropna().unique()]
        client_data = []
        for idx in range(0, len(ids_clientes), 1000):
            chunk = ids_clientes[idx:idx + 1000]
            res_clientes = conn.table("clientes").select("cliente_id, nombre, rut, direccion").in_("cliente_id", chunk).execute()
            if res_clientes.data:
                client_data.extend(res_clientes.data)
        df_clientes = pd.DataFrame(client_data)
        
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
    """Filtra y descarta stock crítico en Supabase de forma paginada."""
    conn = get_db_connection()
    try:
        all_books = []
        chunk_size = 1000
        for bloques in range(100):
            start = bloques * chunk_size
            end = start + chunk_size - 1
            res = (conn.table("libros")
                .select("titulo, autor, editorial, stock, precio, visible_catalogo, destacado")
                .lte("stock", limite)
                .order("stock")
                .range(start, end).execute())
            if res.data:
                all_books.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_books) if all_books else pd.DataFrame()
    except: 
        return pd.DataFrame()

def obtener_reporte_pendientes_consolidado():
    """Genera reporte paginado de registros pendientes (no finalizados) en Caja y Asignaciones."""
    conn = get_db_connection()
    try:
        chunk_size = 1000
        
        # 1. Obtener registro_ventas (Caja) no finalizados
        all_ventas = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_ventas = (conn.table("registro_ventas")
                .select("*")
                .order("venta_id")
                .range(start, end).execute())
            if res_ventas.data:
                all_ventas.extend(res_ventas.data)
                if len(res_ventas.data) < chunk_size: break
            else: break
            
        df_ventas = pd.DataFrame(all_ventas) if all_ventas else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas = df_ventas[df_ventas['estado'].astype(str).str.strip().str.upper() != 'FINALIZADO']
            
        # 2. Obtener asignaciones no finalizadas (estado_envio != ENVIADO y != RETIRADO)
        all_asig = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_asig = (conn.table("asignaciones")
                .select("*")
                .order("asignacion_id")
                .range(start, end).execute())
            if res_asig.data:
                all_asig.extend(res_asig.data)
                if len(res_asig.data) < chunk_size: break
            else: break
            
        df_asig = pd.DataFrame(all_asig) if all_asig else pd.DataFrame()
        if not df_asig.empty:
            df_asig = df_asig[~df_asig['estado_envio'].astype(str).str.strip().str.upper().isin(['ENVIADO', 'RETIRADO'])]
            
        # Enriquecer df_ventas con nombres de clientes
        if not df_ventas.empty:
            ids_clientes_v = df_ventas['cliente_id'].dropna().unique().tolist()
            if ids_clientes_v:
                client_data_v = []
                for idx in range(0, len(ids_clientes_v), 1000):
                    chunk = ids_clientes_v[idx:idx + 1000]
                    res_cli = conn.table("clientes").select("cliente_id, nombre, rut").in_("cliente_id", chunk).execute()
                    if res_cli.data:
                        client_data_v.extend(res_cli.data)
                df_clientes_v = pd.DataFrame(client_data_v) if client_data_v else pd.DataFrame()
                if not df_clientes_v.empty:
                    df_ventas = pd.merge(df_ventas, df_clientes_v, on='cliente_id', how='left')
                    df_ventas.rename(columns={'nombre': 'Nombre Cliente', 'rut': 'RUT Cliente'}, inplace=True)

        # Enriquecer df_asig con nombres de clientes
        if not df_asig.empty:
            ids_clientes_a = df_asig['cliente_id'].dropna().unique().tolist()
            if ids_clientes_a:
                client_data_a = []
                for idx in range(0, len(ids_clientes_a), 1000):
                    chunk = ids_clientes_a[idx:idx + 1000]
                    res_cli = conn.table("clientes").select("cliente_id, nombre, rut").in_("cliente_id", chunk).execute()
                    if res_cli.data:
                        client_data_a.extend(res_cli.data)
                df_clientes_a = pd.DataFrame(client_data_a) if client_data_a else pd.DataFrame()
                if not df_clientes_a.empty:
                    df_asig = pd.merge(df_asig, df_clientes_a, on='cliente_id', how='left')
                    df_asig.rename(columns={'nombre': 'Nombre Cliente', 'rut': 'RUT Cliente'}, inplace=True)
                    
        return df_ventas, df_asig
    except Exception as e:
        log_error("vista_reportes", "obtener_reporte_pendientes_consolidado", e, st.session_state.get('email_usuario', 'Desconocido'))
        return pd.DataFrame(), pd.DataFrame()

# ====================================================
# --- REPORTE DE UTILIDADES Y BALANCE CONSOLIDADO ---
# ====================================================

def obtener_reporte_utilidades_mensual(ano):
    """Genera reporte paginado anual consolidando ingresos, costos y utilidades por mes."""
    conn = get_db_connection()
    try:
        chunk_size = 1000
        
        # 1. Cargar Ventas Directas del año
        all_ventas = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_ventas = conn.table("registro_ventas").select("fecha_venta, monto_final, costo_venta, valor_envio").order("venta_id").range(start, end).execute()
            if res_ventas.data:
                all_ventas.extend(res_ventas.data)
                if len(res_ventas.data) < chunk_size: break
            else: break
        df_v = pd.DataFrame(all_ventas) if all_ventas else pd.DataFrame()
        if not df_v.empty:
            df_v['fecha_venta'] = pd.to_datetime(df_v['fecha_venta'], errors='coerce')
            df_v = df_v[df_v['fecha_venta'].dt.year == ano]
            
        # 2. Cargar Asignaciones de Suscripciones del año
        all_asig = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_asig = conn.table("asignaciones").select("monto_total, costo_caja, pagado, cliente_id, ano, mes").eq("ano", ano).order("asignacion_id").range(start, end).execute()
            if res_asig.data:
                all_asig.extend(res_asig.data)
                if len(res_asig.data) < chunk_size: break
            else: break
        df_a = pd.DataFrame(all_asig) if all_asig else pd.DataFrame()
        if not df_a.empty:
            # Bypass del límite de 1000 para "suscripciones" ordenando por "suscripcion_id"
            all_susc = []
            for bloque_s in range(100):
                start_s = bloque_s * chunk_size
                end_s = start_s + chunk_size - 1
                res_susc = conn.table("suscripciones").select("cliente_id, valor_suscripcion").order("suscripcion_id").range(start_s, end_s).execute()
                if res_susc.data:
                    all_susc.extend(res_susc.data)
                    if len(res_susc.data) < chunk_size: break
                else: break
            df_susc = pd.DataFrame(all_susc) if all_susc else pd.DataFrame()
            if not df_susc.empty:
                df_a = pd.merge(df_a, df_susc, on="cliente_id", how="left")
            else:
                df_a['valor_suscripcion'] = 18500.0
            df_a['valor_suscripcion'] = pd.to_numeric(df_a['valor_suscripcion'], errors='coerce').fillna(18500.0)
            df_a['costo_caja'] = pd.to_numeric(df_a['costo_caja'], errors='coerce').fillna(10000.0)
            # Filtrar solo asignaciones pagadas
            df_a['pagado_clean'] = df_a['pagado'].apply(lambda x: "SI" if str(x).upper() in ["TRUE", "T", "1", "SI"] else "NO")
            df_a = df_a[df_a['pagado_clean'] == 'SI']

        # 3. Cargar Ventas Masivas
        all_vm = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_vm = conn.table("ventas_masivas").select("fecha_evento, ingreso_total, costo_total, utilidad_estimada").order("evento_id").range(start, end).execute()
            if res_vm.data:
                all_vm.extend(res_vm.data)
                if len(res_vm.data) < chunk_size: break
            else: break
        df_vm = pd.DataFrame(all_vm) if all_vm else pd.DataFrame()
        if not df_vm.empty:
            df_vm['fecha_evento'] = pd.to_datetime(df_vm['fecha_evento'], errors='coerce')
            df_vm = df_vm[df_vm['fecha_evento'].dt.year == ano]

        # 4. Cargar Costos No de Ventas
        all_cnv = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_cnv = conn.table("costos_no_ventas").select("fecha_ocurrencia, monto").order("costo_id").range(start, end).execute()
            if res_cnv.data:
                all_cnv.extend(res_cnv.data)
                if len(res_cnv.data) < chunk_size: break
            else: break
        df_cnv = pd.DataFrame(all_cnv) if all_cnv else pd.DataFrame()
        if not df_cnv.empty:
            df_cnv['fecha_ocurrencia'] = pd.to_datetime(df_cnv['fecha_ocurrencia'], errors='coerce')
            df_cnv = df_cnv[df_cnv['fecha_ocurrencia'].dt.year == ano]

        # Construcción del balance mes por mes
        meses_nombres = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
            7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        filas_reporte = []

        for m_num, m_nom in meses_nombres.items():
            # Canal 1: Suscripciones (Cajitas)
            if not df_a.empty:
                a_mes = df_a[df_a['mes'] == m_num]
                ing_a = pd.to_numeric(a_mes['valor_suscripcion'], errors='coerce').sum()
                costo_a = pd.to_numeric(a_mes['costo_caja'], errors='coerce').sum()
                util_a = ing_a - costo_a
            else:
                ing_a, costo_a, util_a = 0.0, 0.0, 0.0

            # Canal 2: Ventas Directas
            if not df_v.empty:
                v_mes = df_v[df_v['fecha_venta'].dt.month == m_num]
                ing_v = pd.to_numeric(v_mes['monto_final'], errors='coerce').sum()
                costo_v = pd.to_numeric(v_mes['costo_venta'], errors='coerce').sum()
                env_v = pd.to_numeric(v_mes['valor_envio'], errors='coerce').sum()
                util_v = (ing_v - env_v) - costo_v
            else:
                ing_v, costo_v, env_v, util_v = 0.0, 0.0, 0.0, 0.0

            # Canal 3: Ventas Masivas (Eventos)
            if not df_vm.empty:
                vm_mes = df_vm[df_vm['fecha_evento'].dt.month == m_num]
                ing_vm = pd.to_numeric(vm_mes['ingreso_total'], errors='coerce').sum()
                costo_vm = pd.to_numeric(vm_mes['costo_total'], errors='coerce').sum()
                util_vm = pd.to_numeric(vm_mes['utilidad_estimada'], errors='coerce').sum()
            else:
                ing_vm, costo_vm, util_vm = 0.0, 0.0, 0.0

            # Gastos Operacionales (No de ventas)
            if not df_cnv.empty:
                cnv_mes = df_cnv[df_cnv['fecha_ocurrencia'].dt.month == m_num]
                gasto_cnv = pd.to_numeric(cnv_mes['monto'], errors='coerce').sum()
            else:
                gasto_cnv = 0.0

            # Balance Total
            total_ingresos = ing_a + ing_v + ing_vm
            total_costos_ventas = costo_a + costo_v + costo_vm
            utilidad_pre_operacional = util_a + util_v + util_vm
            utilidad_consolidada_final = utilidad_pre_operacional - gasto_cnv

            filas_reporte.append({
                "Mes": m_nom,
                "Año": ano,
                "Ingresos Suscripciones ($)": ing_a,
                "Costos Suscripciones ($)": costo_a,
                "Utilidad Suscripciones ($)": util_a,
                "Ingresos Ventas Directas ($)": ing_v,
                "Costos Ventas Directas ($)": costo_v,
                "Despachos Ventas Directas ($)": env_v,
                "Utilidad Ventas Directas ($)": util_v,
                "Ingresos Ventas Masivas ($)": ing_vm,
                "Costos Ventas Masivas ($)": costo_vm,
                "Utilidad Ventas Masivas ($)": util_vm,
                "Costos No Ventas (G. Operacionales) ($)": gasto_cnv,
                "Total Ingresos Brutos ($)": total_ingresos,
                "Total Costos (Venta + Operaciones) ($)": (total_costos_ventas + gasto_cnv),
                "Utilidad Real Consolidada ($)": utilidad_consolidada_final
            })

        df_balance = pd.DataFrame(filas_reporte)
        
        # Generar Fila de Totales Consolidados
        suma_totales = df_balance.select_dtypes(include='number').sum()
        suma_totales['Mes'] = "TOTAL ANUAL"
        suma_totales['Año'] = ano
        
        df_reporte_final = pd.concat([df_balance, pd.DataFrame([suma_totales])], ignore_index=True)
        return df_reporte_final
    except Exception as e:
        st.error(f"Error generando reporte de utilidades y balances: {e}")
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
        
        # --- REPORTE 1: PENDIENTES DE DESPACHO / LOGÍSTICA (NUEVO) ---
        with st.container(border=True):
            st.markdown("#### ⏳ Control de Registros Pendientes (Caja y Asignaciones)")
            st.write("Identifica y descarga todas las asignaciones o ventas de caja que aún no se encuentran finalizadas (Ventas con estado distinto de 'FINALIZADO' y Asignaciones con estado de envío distinto de 'ENVIADO' o 'RETIRADO').")
            
            if st.button("Generar Reporte de Pendientes", type="primary", use_container_width=True, key="btn_pendientes_no_finalizados"):
                with st.spinner("Buscando registros pendientes en Supabase..."):
                    df_caja_pend, df_asig_pend = obtener_reporte_pendientes_consolidado()
                    total_pendientes = len(df_caja_pend) + len(df_asig_pend)
                    
                    if total_pendientes == 0:
                        st.success("🎉 ¡Todo está ok! No hay ventas de caja ni suscripciones")
                    else:
                        st.warning(f"Se encontraron {total_pendientes} registros pendientes ({len(df_caja_pend)} en Caja y {len(df_asig_pend)} en Asignaciones).")
                        
                        col_p1, col_p2 = st.columns(2)
                        col_p1.metric("🛒 Ventas Caja Pendientes", len(df_caja_pend))
                        col_p2.metric("🎁 Asignaciones Suscripción Pendientes", len(df_asig_pend))
                        
                        excel_data = convertir_pendientes_a_excel(df_caja_pend, df_asig_pend)
                        
                        st.download_button(
                            label="📥 Descargar Reporte de Pendientes (.xlsx)",
                            data=excel_data,
                            file_name=f"reporte_pendientes_logistica_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="btn_descarga_pendientes"
                        )

        # --- REPORTE 2: UTILIDADES Y BALANCES ---
        with st.container(border=True):
            st.markdown("#### 💸 Utilidades y Balance Consolidado")
            st.write("Genera un estado financiero consolidado por mes desglosando ingresos de cajitas, ventas rápidas, eventos masivos, costos de adquisición de catálogo y gastos no operacionales.")
            
            col_u1 = st.columns(1)[0]
            ano_balance = col_u1.number_input("Año del Balance Consolidado:", min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="ano_balance_cons")
            
            if st.button("Generar Reporte de Balance y Utilidades", type="primary", use_container_width=True, key="btn_balance"):
                with st.spinner("Compilando balances financieros de Supabase..."):
                    df_balance = obtener_reporte_utilidades_mensual(ano_balance)
                    if not df_balance.empty:
                        st.success("¡Balance generado exitosamente!")
                        st.download_button(
                            label=f"Descargar Balance Anual {ano_balance} (.xlsx)", 
                            data=convertir_df_a_excel(df_balance), 
                            file_name=f"balance_consolidado_utilidades_{ano_balance}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="btn_descarga_balance"
                        )
                        if st.button("🧹 Nueva Consulta (Limpiar Filtros)", use_container_width=True, key="btn_limpiar_balance"):
                            if "ano_balance_cons" in st.session_state:
                                del st.session_state["ano_balance_cons"]
                            st.rerun()
                    else:
                        st.warning("No se encontraron registros financieros para el año seleccionado.")

        # --- REPORTE 3: HISTORIAL DE ASIGNACIONES (CAJITAS) (CON SELECCIÓN TODOS AÑOS Y MESES) ---
        with st.container(border=True):
            st.markdown("#### 🎁 Historial de Asignaciones (Cajitas)")
            st.write("Exporta el detalle de las cajas armadas con el nombre del cliente y los libros que recibió.")
            
            c1, c2 = st.columns(2)
            
            # --- MEJORA: Seleccionar todos los años o año específico ---
            todos_anos = c1.checkbox("Seleccionar todos los años", value=False, key="chk_todos_anos")
            if not todos_anos:
                ano_asig = c1.number_input("Año del reporte:", min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="ano_asig")
            else:
                ano_asig = None
                
            # --- MEJORA: Seleccionar todos los meses o meses específicos ---
            todos_meses = c2.checkbox("Seleccionar todos los meses", value=False, key="chk_todos_meses")
            meses_dict_asig = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
            
            if not todos_meses:
                meses_asig_nombres = c2.multiselect("Selecciona los meses a incluir:", list(meses_dict_asig.values()), default=[meses_dict_asig[datetime.now().month]], key="meses_asig")
            else:
                meses_asig_nombres = list(meses_dict_asig.values())
            
            if st.button("Generar Reporte de Asignaciones", type="primary", use_container_width=True, key="btn_asig"):
                if not todos_meses and not meses_asig_nombres:
                    st.error("Debes seleccionar al menos un mes.")
                else:
                    meses_asig_nums = [list(meses_dict_asig.keys())[list(meses_dict_asig.values()).index(m)] for m in meses_asig_nombres]
                    df_asig_reporte = obtener_reporte_asignaciones(ano_asig, meses_asig_nums, todos_los_anos=todos_anos, todos_los_meses=todos_meses)
                    if not df_asig_reporte.empty:
                        st.success(f"¡Reporte de asignaciones generado exitosamente! ({len(df_asig_reporte)} registros)")
                        
                        nombre_archivo = f"reporte_asignaciones_{'todos_los_anos' if todos_anos else ano_asig}.xlsx"
                        st.download_button(
                            label=f"Descargar Asignaciones ({len(df_asig_reporte)} registros) (.xlsx)", 
                            data=convertir_df_a_excel(df_asig_reporte), 
                            file_name=nombre_archivo,
                            use_container_width=True,
                            key="btn_descarga_asig"
                        )
                        if st.button("🧹 Nueva Consulta (Limpiar Filtros)", use_container_width=True, key="btn_limpiar_asig"):
                            for k in ["ano_asig", "meses_asig", "chk_todos_anos", "chk_todos_meses"]:
                                if k in st.session_state:
                                    del st.session_state[k]
                            st.rerun()
                    else:
                        st.warning("No se encontraron registros de asignación para los filtros seleccionados.")


        # --- REPORTE 4: ENVÍOS PENDIENTES ---
        with st.container(border=True):
            st.markdown("#### 🚚 Envíos Pendientes Unificados")
            st.write("Lista consolidada de todas las cajas (suscripciones y ventas) listas para despacho, con formato para courier.")
            if st.button("Generar Reporte de Envíos", type="primary", use_container_width=True, key="btn_envios"):
                df_envios = obtener_reporte_envios_pendientes()
                if not df_envios.empty:
                    st.success("¡Reporte de envíos generado exitosamente!")
                    st.download_button(
                        label=f"Descargar {len(df_envios)} Envíos Pendientes (.xlsx)", 
                        data=convertir_df_a_excel(df_envios), 
                        file_name="envios_pendientes.xlsx",
                        use_container_width=True,
                        key="btn_descarga_envios"
                    )
                else:
                    st.success("✅ ¡Todo despachado! No hay envíos pendientes.")

        # --- REPORTE 5: SII ---
        with st.container(border=True):
            st.markdown("#### 🇨🇱 Facturación (SII)")
            st.write("Genera el reporte de ventas del mes con el formato para Boletas o Facturas electrónicas.")
            
            c3, c4 = st.columns(2)
            mes_fact_sel = c3.selectbox("Mes:", list(meses_dict_asig.values()), index=None, placeholder="Selecciona un mes...", key="mes_fact_sii")
            ano_fact_sel = c4.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="ano_fact_sii")
            
            tipo_dte_sel = st.selectbox("Selecciona el tipo de documento a generar:", ["Boleta", "Factura"], index=None, placeholder="Selecciona Tipo DTE...", key="tipo_dte_sel")
            
            if st.button("Generar Reporte SII", type="primary", use_container_width=True, key="btn_sii"):
                if not mes_fact_sel:
                    st.error("Debes seleccionar un mes.")
                elif not tipo_dte_sel:
                    st.error("Debes seleccionar un tipo de DTE.")
                else:
                    mes_fact_num = list(meses_dict_asig.keys())[list(meses_dict_asig.values()).index(mes_fact_sel)]
                    df_sii = obtener_reporte_sii(ano_fact_sel, mes_fact_num, tipo_dte_sel)
                    if not df_sii.empty:
                        st.success(f"¡Reporte SII de {tipo_dte_sel}s generado exitosamente!")
                        st.download_button(
                            label=f"Descargar {tipo_dte_sel}s de {mes_fact_sel}-{ano_fact_sel} (.xlsx)", 
                            data=convertir_df_a_excel(df_sii), 
                            file_name=f"reporte_sii_{tipo_dte_sel.lower()}_{ano_fact_sel}_{mes_fact_num}.xlsx",
                            use_container_width=True,
                            key="btn_descarga_sii"
                        )
                        if st.button("🧹 Nueva Consulta (Limpiar Filtros)", use_container_width=True, key="btn_limpiar_sii"):
                            for k in ["mes_fact_sii", "ano_fact_sii", "tipo_dte_sel"]:
                                if k in st.session_state:
                                    del st.session_state[k]
                            st.rerun()
                    else:
                        st.warning("No se encontraron ventas para el período seleccionado.")

        # --- REPORTE 6: BAJO STOCK ---
        with st.container(border=True):
            st.markdown("#### 🚨 Libros con Bajo Stock")
            st.write("Identifica rápidamente los libros que están por agotarse para planificar tus compras.")
            limite_stock = st.number_input("Considerar bajo stock si es igual o menor a:", min_value=0, max_value=50, value=5, step=1, key="limite_stock_reporte")
            if st.button("Generar Reporte de Stock", type="primary", use_container_width=True, key="btn_stock"):
                df_stock = obtener_reporte_bajo_stock(limite_stock)
                if not df_stock.empty:
                    st.success("¡Reporte de stock generado exitosamente!")
                    st.download_button(
                        label=f"Descargar Reporte ({len(df_stock)} libros) (.xlsx)", 
                        data=convertir_df_a_excel(df_stock), 
                        file_name="reporte_bajo_stock.xlsx",
                        use_container_width=True,
                        key="btn_descarga_stock"
                    )
                    if st.button("🧹 Nueva Consulta (Limpiar Filtros)", use_container_width=True, key="btn_limpiar_stock"):
                        if "limite_stock_reporte" in st.session_state:
                            del st.session_state["limite_stock_reporte"]
                        st.rerun()
                else:
                    st.success("¡Excelente! No tienes libros con stock crítico.")

    with tab2:
        st.markdown("### Descarga de Respaldo Crudo (Backup)")
        st.write("Aquí puedes descargar el contenido directo y sin procesar de cualquier tabla de la base de datos.")
        
        tablas_disponibles = ["clientes", "libros", "registro_ventas", "asignaciones", "suscripciones", "ventas_masivas", "librero_historico", "costos_no_ventas", "historial_cambios_masivos", "historial_logs", "meses_cerrados"]
        tabla_seleccionada = st.selectbox("Selecciona la tabla a exportar:", sorted(tablas_disponibles), index=None, placeholder="Selecciona una tabla...", key="tabla_seleccionada")
        
        if st.button("📥 Exportar tabla completa", use_container_width=True, key="btn_export"):
            if not tabla_seleccionada:
                st.error("Debes seleccionar una tabla para exportar.")
            else:
                with st.spinner(f"Extrayendo y formateando datos de {tabla_seleccionada}..."):
                    df_tabla = obtener_tabla(tabla_seleccionada)
                    if not df_tabla.empty:
                        st.success(f"¡Tabla '{tabla_seleccionada}' extraída con éxito!")
                        st.download_button(
                            label="✅ Haz clic aquí para descargar el archivo .xlsx", 
                            data=convertir_df_a_excel(df_tabla), 
                            file_name=f"backup_{tabla_seleccionada}_{datetime.now().strftime('%Y%m%d')}.xlsx", 
                            type="primary",
                            use_container_width=True,
                            key="btn_descarga_backup"
                        )
                        if st.button("🧹 Nueva Exportación (Limpiar)", use_container_width=True, key="btn_limpiar_backup"):
                            if "tabla_seleccionada" in st.session_state:
                                del st.session_state["tabla_seleccionada"]
                            st.rerun()
                    else:
                        st.warning("La tabla seleccionada está vacía.")

if __name__ == "__main__":
    mostrar_reportes()