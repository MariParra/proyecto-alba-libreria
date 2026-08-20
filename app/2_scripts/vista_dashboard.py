import streamlit as st
import pandas as pd
import datetime
import json
from utilidades import get_db_connection, log_error

@st.cache_data(ttl=300)
def cargar_datos_base():
    """Carga de forma dinámica y paginada todos los datos crudos desde la BD superando el límite de 1000."""
    conn = get_db_connection()
    
    # 1. Registro de Ventas Directas (Paginado)
    df_ventas = pd.DataFrame()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("registro_ventas")\
                .select("fecha_venta, monto_final, costo_venta, valor_envio, estado_pago, metodo_envio, libros_vendidos")\
                .order("venta_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        df_ventas = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas['fecha_venta'] = pd.to_datetime(df_ventas['fecha_venta'], errors='coerce')
            df_ventas.dropna(subset=['fecha_venta'], inplace=True)
    except Exception as e:
        log_error("vista_dashboard", "cargar_datos_base_ventas", e)
        
    # 2. Asignaciones de Suscripción (Paginado)
    df_asig = pd.DataFrame()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("asignaciones")\
                .select("fecha_asignacion, monto_total, costo_caja, pagado, libro_suscripcion_id")\
                .order("asignacion_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        df_asig = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df_asig.empty:
            df_asig['fecha_asignacion'] = pd.to_datetime(df_asig['fecha_asignacion'], errors='coerce')
            df_asig.dropna(subset=['fecha_asignacion'], inplace=True)
    except Exception as e:
        log_error("vista_dashboard", "cargar_datos_base_asignaciones", e)
        
    # 3. Ventas Masivas y Eventos (Paginado)
    df_vm = pd.DataFrame()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("ventas_masivas")\
                .select("fecha_evento, ingreso_total, costo_total, utilidad_estimada, estado_pago")\
                .order("evento_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        df_vm = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df_vm.empty:
            df_vm['fecha_evento'] = pd.to_datetime(df_vm['fecha_evento'], errors='coerce')
            df_vm.dropna(subset=['fecha_evento'], inplace=True)
    except Exception as e:
        log_error("vista_dashboard", "cargar_datos_base_ventas_masivas", e)
        
    # 4. Estados de Clientes (Paginado)
    df_clientes = pd.DataFrame()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("clientes")\
                .select("status")\
                .order("cliente_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        df_clientes = pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception as e:
        log_error("vista_dashboard", "cargar_datos_base_clientes", e)
        
    return df_ventas, df_asig, df_vm, df_clientes

def mostrar_alertas_proactivas():
    """Alerta de stock crítico con bypass del límite de 1000."""
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_stock = conn.table("libros")\
                .select("titulo, stock")\
                .lte("stock", 3)\
                .order("libro_id")\
                .range(start, end).execute()
            if res_stock.data:
                all_data.extend(res_stock.data)
                if len(res_stock.data) < chunk_size:
                    break
            else:
                break
                
        libros_criticos = all_data if all_data else []
        if libros_criticos:
            st.toast(f"🚨 Tienes {len(libros_criticos)} libros con stock crítico.", icon="⚠️")
            with st.expander(f"⚠️ Alerta Operativa: {len(libros_criticos)} libros requieren reabastecimiento", expanded=False):
                st.error("Los siguientes libros están a punto de agotarse o ya no tienen stock:")
                for l in libros_criticos:
                    st.markdown(f"- **{l['titulo']}** (Stock actual: `{l['stock']}` unidades)")
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error("vista_dashboard", "mostrar_alertas_proactivas", f"Fallo al verificar stock crítico: {e}", email_usuario)
        st.toast("No se pudieron verificar las alertas de stock.", icon="❗")

def obtener_top_libros_populares(df_ventas_filt, df_asig_filt):
    conn = get_db_connection()
    conteo_libros = {}
    try:
        # Procesar Asignaciones del periodo
        if not df_asig_filt.empty:
            for libro_id in df_asig_filt['libro_suscripcion_id'].dropna():
                conteo_libros[int(libro_id)] = conteo_libros.get(int(libro_id), 0) + 1
        
        # Procesar Ventas Directas del periodo
        if not df_ventas_filt.empty:
            for _, row in df_ventas_filt.iterrows():
                try:
                    libros = json.loads(row['libros_vendidos'])
                    for l in libros:
                        l_id = l.get('libro_id')
                        if l_id:
                            conteo_libros[int(l_id)] = conteo_libros.get(int(l_id), 0) + 1
                except (json.JSONDecodeError, TypeError) as json_e:
                    log_error("vista_dashboard", "obtener_top_libros_populares (JSON Ventas)", f"JSON Corrupto: {json_e}", "Sistema")
                    continue
        
        if not conteo_libros:
            return pd.DataFrame()
        
        ids_libros = list(conteo_libros.keys())
        res_detalles = conn.table("libros").select("libro_id, titulo").in_(libro_id, ids_libros).execute()
        df_detalles = pd.DataFrame(res_detalles.data) if res_detalles.data else pd.DataFrame()

        if not df_detalles.empty:
            df_detalles['Cantidad'] = df_detalles['libro_id'].map(conteo_libros)
            df_top = df_detalles.sort_values(by="Cantidad", ascending=False).head(10)
            return df_top.set_index('titulo')[['Cantidad']]
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error("vista_dashboard", "obtener_top_libros_populares", f"Error ranking: {e}", email_usuario)
        st.error(f"Error generando ranking de libros: {e}")
    return pd.DataFrame()

# --- VISTA PRINCIPAL ---

def mostrar_dashboard():
    st.title("📈 Panel de Control y Estadísticas")
    
    mostrar_alertas_proactivas()
    df_ventas, df_asig, df_vm, df_clientes = cargar_datos_base()
    
    # Mapeo de meses de trabajo (Idéntico a vista_asignaciones.py)
    meses_dict = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }

    # Widget de selección de Mes y Año de Trabajo (Default: Mes y Año Actuales)
    with st.container(border=True):
        st.markdown("### 📅 Mes de Trabajo")
        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mes:", list(meses_dict.values()), index=datetime.date.today().month - 1)
        ano_sel = c2.number_input("Año:", min_value=2020, max_value=2050, value=datetime.date.today().year, step=1)
        mes_num = list(meses_dict.keys())[list(meses_dict.values()).index(mes_sel)]

    # Filtrar datos del año y mes seleccionados de forma precisa
    df_v_filt = df_ventas[(df_ventas['fecha_venta'].dt.year == ano_sel) & (df_ventas['fecha_venta'].dt.month == mes_num)] if not df_ventas.empty else pd.DataFrame()
    df_a_filt = df_asig[(df_asig['fecha_asignacion'].dt.year == ano_sel) & (df_asig['fecha_asignacion'].dt.month == mes_num)] if not df_asig.empty else pd.DataFrame()
    
    if not df_vm.empty:
        df_vm['fecha_evento_dt'] = pd.to_datetime(df_vm['fecha_evento'], errors='coerce')
        df_vm_filt = df_vm[(df_vm['fecha_evento_dt'].dt.year == ano_sel) & (df_vm['fecha_evento_dt'].dt.month == mes_num)]
    else:
        df_vm_filt = pd.DataFrame()

    # --- CÁLCULO DE MÉTRICAS SEGURAS POR CANAL (PAGADOS) ---
    df_a_paid = df_a_filt[df_a_filt['pagado'].str.upper() == 'SI'] if not df_a_filt.empty else pd.DataFrame()
    df_v_paid = df_v_filt[df_v_filt['estado_pago'].str.upper() == 'PAGADO'] if not df_v_filt.empty else pd.DataFrame()
    df_vm_paid = df_vm_filt[df_vm_filt['estado_pago'].str.upper() == 'PAGADO'] if not df_vm_filt.empty else pd.DataFrame()

    # 1. Métricas Club de Suscripción (Asignaciones)
    ingreso_asig = pd.to_numeric(df_a_paid['monto_total'], errors='coerce').sum() if not df_a_paid.empty else 0.0
    costo_asig = pd.to_numeric(df_a_paid['costo_caja'], errors='coerce').sum() if not df_a_paid.empty else 0.0
    utilidad_asig = ingreso_asig - costo_asig

    # 2. Métricas Caja y Ventas Rápidas (Directas)
    ingreso_caja = pd.to_numeric(df_v_paid['monto_final'], errors='coerce').sum() if not df_v_paid.empty else 0.0
    costo_caja = pd.to_numeric(df_v_paid['costo_venta'], errors='coerce').sum() if not df_v_paid.empty else 0.0
    envio_caja = pd.to_numeric(df_v_paid['valor_envio'], errors='coerce').sum() if not df_v_paid.empty else 0.0
    utilidad_caja = (ingreso_caja - envio_caja) - costo_caja if not df_v_paid.empty else 0.0

    # 3. Métricas Ventas Masivas (Eventos)
    ingreso_vm = pd.to_numeric(df_vm_paid['ingreso_total'], errors='coerce').sum() if not df_vm_paid.empty else 0.0
    costo_vm = pd.to_numeric(df_vm_paid['costo_total'], errors='coerce').sum() if not df_vm_paid.empty else 0.0
    utilidad_vm = pd.to_numeric(df_vm_paid['utilidad_estimada'], errors='coerce').sum() if not df_vm_paid.empty else 0.0

    # 4. Totales Consolidados
    ingresos_totales = ingreso_asig + ingreso_caja + ingreso_vm
    costos_totales = costo_asig + costo_caja + costo_vm
    utilidad_total = utilidad_asig + utilidad_caja + utilidad_vm

    # ================= RENDERIZADO DE LAS 4 LÍNEAS DE MÉTRICAS =================
    st.markdown("---")
    st.markdown("### 🎯 Rendimiento Financiero por Canal de Venta")
    
    # Línea 1: Suscripciones
    st.markdown("#### 📦 1. Club de Suscripción (Asignaciones)")
    col_a1, col_a2, col_a3 = st.columns(3)
    col_a1.metric("Ingreso Suscripciones", f"${ingreso_asig:,.0f}")
    col_a2.metric("Costo Suscripciones", f"${costo_asig:,.0f}")
    col_a3.metric("Utilidad Suscripciones", f"${utilidad_asig:,.0f}")

    # Línea 2: Ventas Directas
    st.markdown("#### 🛒 2. Caja y Ventas Rápidas (Directas)")
    col_b1, col_b2, col_b3 = st.columns(3)
    col_b1.metric("Ingreso Ventas Directas", f"${ingreso_caja:,.0f}")
    col_b2.metric("Costo Ventas Directas", f"${costo_caja:,.0f}", help="Costo de adquisición de libros.")
    col_b3.metric("Utilidad Ventas Directas", f"${utilidad_caja:,.0f}", help="Utilidad excluyendo costos de despacho.")

    # Línea 3: Ventas Masivas
    st.markdown("#### 🎡 3. Ventas Masivas y Eventos")
    col_c1, col_c2, col_c3 = st.columns(3)
    col_c1.metric("Ingreso Eventos", f"${ingreso_vm:,.0f}")
    col_c2.metric("Costo Eventos", f"${costo_vm:,.0f}")
    col_c3.metric("Utilidad Eventos", f"${utilidad_vm:,.0f}")

    # Línea 4: Consolidado Total
    st.markdown("#### 📊 4. Totales Consolidados (Balance Total Alba)")
    with st.container(border=True):
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("🔥 Ingreso Neto Consolidado", f"${ingresos_totales:,.0f}")
        col_t2.metric("📦 Costo Total Consolidado", f"${costos_totales:,.0f}")
        if utilidad_total >= 0:
            col_t3.metric("📈 Utilidad Alba Estimada", f"${utilidad_total:,.0f}")
        else:
            col_t3.metric("📉 Pérdida Consolidada", f"${utilidad_total:,.0f}")

    st.markdown("---")
    st.markdown("### 📊 Gráficos de Análisis Comercial")

    # Cambio de Frecuencia: De Mensual ("M") a Diario ("D") al analizar un mes específico
    frecuencia = "D"
    texto_freq = "Diario"

    # Fila 1: Línea Temporal de Evolución y Comparativa de Canales
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        with st.container(border=True):
            st.markdown(f"#### 💵 Tendencia de Ingresos ({texto_freq})")
            if not df_v_paid.empty or not df_a_paid.empty or not df_vm_paid.empty:
                # 🚀 SEGURIDAD ULTRA: Formatear solo si las dataframes contienen registros reales
                if not df_v_paid.empty:
                    df_v_paid['dia_str'] = df_v_paid['fecha_venta'].dt.strftime('%d/%m')
                if not df_a_paid.empty:
                    df_a_paid['dia_str'] = df_a_paid['fecha_asignacion'].dt.strftime('%d/%m')
                if not df_vm_paid.empty:
                    df_vm_paid['dia_str'] = df_vm_paid['fecha_evento_dt'].dt.strftime('%d/%m')

                v_agrupado = df_v_paid.groupby('dia_str')['monto_final'].sum().rename("Ventas Directas") if not df_v_paid.empty else pd.Series(name="Ventas Directas", dtype=float)
                a_agrupado = df_a_paid.groupby('dia_str')['monto_total'].sum().rename("Suscripciones") if not df_a_paid.empty else pd.Series(name="Suscripciones", dtype=float)
                vm_agrupado = df_vm_paid.groupby('dia_str')['ingreso_total'].sum().rename("Ventas Masivas") if not df_vm_paid.empty else pd.Series(name="Ventas Masivas", dtype=float)

                df_tendencia = pd.concat([v_agrupado, a_agrupado, vm_agrupado], axis=1).fillna(0.0).sort_index()
                df_tendencia.index = df_tendencia.index.astype(str)
                st.line_chart(df_tendencia, use_container_width=True)
            else:
                st.info("No hay ingresos registrados en el periodo.")

    with col_g2:
        with st.container(border=True):
            st.markdown("#### ⚖️ Volumen vs. Rentabilidad por Canal")
            df_canales = pd.DataFrame({
                "Canal": ["Suscripciones", "Ventas Directas", "Ventas Masivas"],
                "Ingresos": [ingreso_asig, ingreso_caja, ingreso_vm],
                "Utilidad": [utilidad_asig, utilidad_caja, utilidad_vm]
            }).set_index("Canal")
            st.bar_chart(df_canales, use_container_width=True)

    # Fila 2: Gráficos de Operaciones
    col_g3, col_g4 = st.columns(2)
    
    with col_g3:
        with st.container(border=True):
            st.markdown("#### 👥 Salud y Estado del Club de Lectura")
            if not df_clientes.empty and 'status' in df_clientes.columns:
                conteo_clientes = df_clientes['status'].value_counts()
                st.bar_chart(conteo_clientes, use_container_width=True, color="#4CAF50")
            else:
                st.info("No se registran estados de clientes.")

    with col_g4:
        with st.container(border=True):
            st.markdown("#### 🚚 Métodos de Envío más Utilizados (Ventas)")
            if not df_v_filt.empty and 'metodo_envio' in df_v_filt.columns:
                df_v_filt['envio_limpio'] = df_v_filt['metodo_envio'].fillna("Sin especificar")
                conteo_envios = df_v_filt['envio_limpio'].value_counts()
                st.bar_chart(conteo_envios, use_container_width=True, color="#FF9800")
            else:
                st.info("No hay registros de envío en este periodo.")

    # Fila 3: Rankings
    col_g5, col_g6 = st.columns(2)
    
    with col_g5:
        with st.container(border=True):
            st.markdown("#### 🔥 Top 10 Libros Populares (Ventas + Suscripción)")
            df_populares = obtener_top_libros_populares(df_v_filt, df_a_filt)
            if not df_populares.empty:
                st.bar_chart(df_populares, use_container_width=True, color="#9C27B0")
            else:
                st.info("No hay asignaciones o ventas en este período.")

    with col_g6:
        with st.container(border=True):
            st.markdown(f"#### 📊 Volumen de Suscripciones del Período ({texto_freq})")
            if not df_a_filt.empty:
                # Agrupación por día en formato dd/mm para mayor detalle visual
                conteo_asig = df_a_filt.groupby(df_a_filt['fecha_asignacion'].dt.strftime('%d/%m')).size().rename("Cantidad")
                conteo_asig.index = conteo_asig.index.astype(str)
                st.bar_chart(conteo_asig, use_container_width=True, color="#E91E63")
            else:
                st.info("No hay asignaciones en este periodo.")

if __name__ == '__main__':
    mostrar_dashboard()