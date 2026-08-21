import streamlit as st
import pandas as pd
import datetime
import json
from utilidades import get_db_connection, log_error

def mapear_sino(val):
    v = str(val).upper()
    if v in ["TRUE", "T", "1"]: return "SI"
    if v in ["FALSE", "F", "0"]: return "NO"
    return v

def unificar_formatos_fecha(serie_fechas):
    """
    Función de parseo de fechas a prueba de balas, capaz de interpretar
    múltiples formatos (YYYY-MM-DD y DD-MM-YYYY) de la base de datos.
    """
    def parsear_valor(val):
        if pd.isna(val) or not str(val).strip() or str(val).strip().lower() in ['nan', 'nat']:
            return pd.NaT
        val_str = str(val).strip()
        try:
            if len(val_str.split('-')[0]) == 4 or len(val_str.split('/')[0]) == 4:
                return pd.to_datetime(val_str, dayfirst=False, errors='coerce')
            else:
                return pd.to_datetime(val_str, dayfirst=True, errors='coerce')
        except:
            return pd.to_datetime(val_str, errors='coerce')
    try:
        return serie_fechas.apply(parsear_valor)
    except Exception:
        return pd.to_datetime(serie_fechas, errors='coerce')

def obtener_secuencia_ano_mes(meses_atras):
    """Genera una lista de enteros en formato YYYYMM retroactivos a partir de hoy."""
    hoy = datetime.date.today()
    secuencia = []
    current_year = hoy.year
    current_month = hoy.month
    
    for _ in range(meses_atras):
        secuencia.append(current_year * 100 + current_month)
        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1
            
    return secuencia

@st.cache_data(ttl=300)
def cargar_datos_base():
    """Carga de forma dinámica y paginada todos los datos crudos desde la BD superando el límite de 1000."""
    conn = get_db_connection()
    
    # 1. Registro de Ventas Directas (Paginado con unificación de fechas)
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
            df_ventas['fecha_venta'] = unificar_formatos_fecha(df_ventas['fecha_venta'])
            df_ventas.dropna(subset=['fecha_venta'], inplace=True)
    except Exception as e:
        log_error("vista_dashboard", "cargar_datos_base_ventas", e)
        
    # 2. Asignaciones de Suscripción (Paginado con cruce de suscripciones base)
    df_asig = pd.DataFrame()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("asignaciones")\
                .select("fecha_asignacion, monto_total, costo_caja, pagado, libro_suscripcion_id, cliente_id, ano, mes")\
                .order("asignacion_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        df_asig = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        
        # Cruzamos con suscripciones para obtener el valor_suscripcion real (Recaudación Bruta)
        if not df_asig.empty:
            res_susc = conn.table("suscripciones").select("cliente_id, valor_suscripcion").execute()
            df_susc = pd.DataFrame(res_susc.data) if res_susc.data else pd.DataFrame()
            if not df_susc.empty:
                df_asig = pd.merge(df_asig, df_susc, on="cliente_id", how="left")
            else:
                df_asig['valor_suscripcion'] = 18500.0
            
            # Calibración retrospectiva para datos históricos (Bypass de nulos en BD)
            df_asig['valor_suscripcion'] = pd.to_numeric(df_asig['valor_suscripcion'], errors='coerce').fillna(18500.0)
            df_asig['costo_caja'] = pd.to_numeric(df_asig['costo_caja'], errors='coerce').fillna(10000.0)
            df_asig['fecha_asignacion'] = pd.to_datetime(df_asig['fecha_asignacion'], errors='coerce')
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

    # 5. Costos No de Ventas (Paginado)
    df_costos_no_ventas = pd.DataFrame()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("costos_no_ventas")\
                .select("fecha_ocurrencia, monto, tipo_costo")\
                .order("costo_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        df_costos_no_ventas = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df_costos_no_ventas.empty:
            df_costos_no_ventas['fecha_ocurrencia'] = unificar_formatos_fecha(df_costos_no_ventas['fecha_ocurrencia'])
            df_costos_no_ventas.dropna(subset=['fecha_ocurrencia'], inplace=True)
    except Exception as e:
        log_error("vista_dashboard", "cargar_datos_base_costos_no_ventas", e)
        
    return df_ventas, df_asig, df_vm, df_clientes, df_costos_no_ventas

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
        res_detalles = conn.table("libros").select("libro_id, titulo").in_("libro_id", ids_libros).execute()
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
    df_ventas, df_asig, df_vm, df_clientes, df_costos_no_ventas = cargar_datos_base()
    
    # Mapeo de meses de trabajo
    meses_dict = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }

    # ================= FILTRO TEMPORAL COMERCIAL CON PERIODOS RÁPIDOS =================
    with st.container(border=True):
        st.markdown("### 📅 Filtro Temporal Comercial")
        
        opciones_periodo = [
            "📅 Mes Actual",
            "📊 Último Trimestre (3 Meses)",
            "📈 Último Semestre (6 Meses)",
            "🏆 Últimos 12 Meses",
            "⚙️ Personalizado (Selección Manual)"
        ]
        
        periodo_sel = st.selectbox(
            "Selecciona el Periodo de Análisis Rápido:",
            options=opciones_periodo,
            index=0
        )
        
        secuencia_ano_mes = []
        es_mes_unico = False
        
        if periodo_sel == "📅 Mes Actual":
            hoy = datetime.date.today()
            secuencia_ano_mes = [hoy.year * 100 + hoy.month]
            es_mes_unico = True
            
        elif periodo_sel == "📊 Último Trimestre (3 Meses)":
            secuencia_ano_mes = obtener_secuencia_ano_mes(3)
            
        elif periodo_sel == "📈 Último Semestre (6 Meses)":
            secuencia_ano_mes = obtener_secuencia_ano_mes(6)
            
        elif periodo_sel == "🏆 Últimos 12 Meses":
            secuencia_ano_mes = obtener_secuencia_ano_mes(12)
            
        else: # Personalizado
            st.markdown("#### Configuración Manual del Periodo")
            anos_disponibles = list(range(2020, 2031))
            ano_actual = datetime.date.today().year
            
            col_t1, col_t2 = st.columns(2)
            
            with col_t1:
                todos_anos = st.checkbox("Incluir todos los años disponibles", value=False)
                anos_seleccionados = st.multiselect(
                    "Años a Analizar:",
                    options=anos_disponibles,
                    default=[ano_actual] if not todos_anos else [],
                    disabled=todos_anos
                )
                
            with col_t2:
                todos_meses = st.checkbox("Incluir todos los meses", value=False)
                mes_actual_nombre = meses_dict[datetime.date.today().month]
                meses_seleccionados_nombres = st.multiselect(
                    "Meses a Analizar:",
                    options=list(meses_dict.values()),
                    default=[mes_actual_nombre] if not todos_meses else [],
                    disabled=todos_meses
                )
                
            # Resolución de años y meses manuales
            if todos_anos:
                anos_finales = df_ventas['fecha_venta'].dt.year.dropna().unique().astype(int).tolist() if not df_ventas.empty else [ano_actual]
                if not df_asig.empty:
                    anos_finales.extend(df_asig['ano'].dropna().unique().astype(int).tolist())
                if not df_vm.empty:
                    df_vm['fecha_evento_dt'] = pd.to_datetime(df_vm['fecha_evento'], errors='coerce')
                    anos_finales.extend(df_vm['fecha_evento_dt'].dt.year.dropna().unique().astype(int).tolist())
                anos_finales = sorted(list(set(anos_finales)))
            else:
                anos_finales = anos_seleccionados if anos_seleccionados else [ano_actual]

            if todos_meses:
                meses_numeros_finales = list(meses_dict.keys())
            else:
                meses_numeros_finales = [k for k, v in meses_dict.items() if v in meses_seleccionados_nombres]
                if not meses_numeros_finales:
                    meses_numeros_finales = [datetime.date.today().month]
                    
            for y in anos_finales:
                for m in meses_numeros_finales:
                    secuencia_ano_mes.append(y * 100 + m)
            
            es_mes_unico = (len(anos_finales) == 1 and len(meses_numeros_finales) == 1)

    # Filtrado preciso usando la secuencia de YYYYMM consolidada
    if not df_ventas.empty:
        df_ventas['ano_mes_int'] = df_ventas['fecha_venta'].dt.year * 100 + df_ventas['fecha_venta'].dt.month
        df_v_filt = df_ventas[df_ventas['ano_mes_int'].isin(secuencia_ano_mes)]
    else:
        df_v_filt = pd.DataFrame()
        
    if not df_asig.empty:
        df_asig['ano_mes_int'] = df_asig['ano'] * 100 + df_asig['mes']
        df_a_filt = df_asig[df_asig['ano_mes_int'].isin(secuencia_ano_mes)]
    else:
        df_a_filt = pd.DataFrame()
        
    if not df_vm.empty:
        df_vm['fecha_evento_dt'] = pd.to_datetime(df_vm['fecha_evento'], errors='coerce')
        df_vm['ano_mes_int'] = df_vm['fecha_evento_dt'].dt.year * 100 + df_vm['fecha_evento_dt'].dt.month
        df_vm_filt = df_vm[df_vm['ano_mes_int'].isin(secuencia_ano_mes)]
    else:
        df_vm_filt = pd.DataFrame()

    if not df_costos_no_ventas.empty:
        df_costos_no_ventas['ano_mes_int'] = df_costos_no_ventas['fecha_ocurrencia'].dt.year * 100 + df_costos_no_ventas['fecha_ocurrencia'].dt.month
        df_costos_no_v_filt = df_costos_no_ventas[df_costos_no_ventas['ano_mes_int'].isin(secuencia_ano_mes)]
    else:
        df_costos_no_v_filt = pd.DataFrame()

    # --- CÁLCULO DE MÉTRICAS SEGURAS POR CANAL (CONCILIADAS CON HISTORIALES) ---
    if not df_a_filt.empty:
        df_a_filt['pagado_clean'] = df_a_filt['pagado'].apply(mapear_sino)
        df_a_paid = df_a_filt[df_a_filt['pagado_clean'] == 'SI']
    else:
        df_a_paid = pd.DataFrame()
        
    df_v_paid = df_v_filt.copy() if not df_v_filt.empty else pd.DataFrame() 
    df_vm_paid = df_vm_filt.copy() if not df_vm_filt.empty else pd.DataFrame()

    # 1. Métricas Club de Suscripción (Recaudación Bruta y Costo de Caja)
    ingreso_asig = pd.to_numeric(df_a_paid['valor_suscripcion'], errors='coerce').sum() if not df_a_paid.empty else 0.0
    costo_asig = pd.to_numeric(df_a_paid['costo_caja'], errors='coerce').sum() if not df_a_paid.empty else 0.0
    utilidad_asig = ingreso_asig - costo_asig

    # 2. Métricas Caja y Ventas Rápidas (Conciliadas con vista_caja.py)
    ingreso_caja = pd.to_numeric(df_v_paid['monto_final'], errors='coerce').sum() if not df_v_paid.empty else 0.0
    costo_caja = pd.to_numeric(df_v_paid['costo_venta'], errors='coerce').sum() if not df_v_paid.empty else 0.0
    envio_caja = pd.to_numeric(df_v_paid['valor_envio'], errors='coerce').sum() if not df_v_paid.empty else 0.0
    utilidad_caja = (ingreso_caja - envio_caja) - costo_caja if not df_v_paid.empty else 0.0

    # 3. Métricas Ventas Masivas (Eventos conciliados con vista_ventas_masivas.py)
    ingreso_vm = pd.to_numeric(df_vm_paid['ingreso_total'], errors='coerce').sum() if not df_vm_paid.empty else 0.0
    costo_vm = pd.to_numeric(df_vm_paid['costo_total'], errors='coerce').sum() if not df_vm_paid.empty else 0.0
    utilidad_vm = pd.to_numeric(df_vm_paid['utilidad_estimada'], errors='coerce').sum() if not df_vm_paid.empty else 0.0

    # 3.5 Costos No operacionales (Gastos Generales)
    costos_no_ventas_total = pd.to_numeric(df_costos_no_v_filt['monto'], errors='coerce').sum() if not df_costos_no_v_filt.empty else 0.0

    # 4. Totales Consolidados de Alba Librería
    ingresos_totales = ingreso_asig + ingreso_caja + ingreso_vm
    costos_totales = costo_asig + costo_caja + costo_vm
    utilidad_pre_operacional = utilidad_asig + utilidad_caja + utilidad_vm

    # ================= RENDERIZADO DE LAS MÉTRICAS DE CANAL =================
    st.markdown("---")
    st.markdown("### 🎯 Rendimiento Financiero por Canal de Venta")
    
    # Línea 1: Suscripciones
    st.markdown("#### 📦 1. Cajitas de suscripcion")
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

    # Línea 4: Costos no Operacionales
    st.markdown("#### 💸 4. Costos No de Ventas (Gastos Operacionales)")
    col_cnv1, col_cnv2, col_cnv3 = st.columns(3)
    col_cnv1.metric("Total Gastos No Ventas", f"${costos_no_ventas_total:,.0f}")
    col_cnv2.metric("Cantidad de Registros", f"{len(df_costos_no_v_filt)}" if not df_costos_no_v_filt.empty else "0")
    col_cnv3.metric("Gasto Promedio", f"${df_costos_no_v_filt['monto'].mean():,.0f}" if (not df_costos_no_v_filt.empty and len(df_costos_no_v_filt) > 0) else "$0")

    # Línea 5: Consolidado Total
    st.markdown("#### 📊 5. Totales Consolidados (Balance Total Alba Libreria)")
    with st.container(border=True):
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("🔥 Ingreso Neto Consolidado", f"${ingresos_totales:,.0f}")
        col_t2.metric("📦 Costo Total Consolidado (Venta + No Venta)", f"${(costos_totales + costos_no_ventas_total):,.0f}")
        
        utilidad_final = utilidad_pre_operacional - costos_no_ventas_total
        if utilidad_final >= 0:
            col_t3.metric("📈 Utilidad Alba Libreria Estimada", f"${utilidad_final:,.0f}")
        else:
            col_t3.metric("📉 Pérdida Consolidada", f"${utilidad_final:,.0f}")

    st.markdown("---")
    st.markdown("### 📊 Gráficos de Análisis Comercial")

    # Ajuste automático de la frecuencia de gráficos según el rango seleccionado
    if es_mes_unico:
        frecuencia = "D"
        texto_freq = "Diario"
    else:
        frecuencia = "M"
        texto_freq = "Mensual"

    # Fila 1: Tendencia de Ingresos y Tendencia de Costos
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        with st.container(border=True):
            st.markdown(f"#### 💵 Tendencia de Ingresos ({texto_freq})")
            if not df_v_paid.empty or not df_a_paid.empty or not df_vm_paid.empty:
                if es_mes_unico:
                    if not df_v_paid.empty: df_v_paid['dia_str'] = df_v_paid['fecha_venta'].dt.strftime('%d/%m')
                    if not df_a_paid.empty: df_a_paid['dia_str'] = df_a_paid['fecha_asignacion'].dt.strftime('%d/%m')
                    if not df_vm_paid.empty: df_vm_paid['dia_str'] = df_vm_paid['fecha_evento_dt'].dt.strftime('%d/%m')
                    col_agrupa = 'dia_str'
                else:
                    if not df_v_paid.empty: df_v_paid['mes_str'] = df_v_paid['fecha_venta'].dt.strftime('%Y-%m')
                    if not df_a_paid.empty: df_a_paid['mes_str'] = df_a_paid['fecha_asignacion'].dt.strftime('%Y-%m')
                    if not df_vm_paid.empty: df_vm_paid['mes_str'] = df_vm_paid['fecha_evento_dt'].dt.strftime('%Y-%m')
                    col_agrupa = 'mes_str'

                v_agrupado = df_v_paid.groupby(col_agrupa)['monto_final'].sum().rename("Ventas Directas") if not df_v_paid.empty else pd.Series(name="Ventas Directas", dtype=float)
                a_agrupado = df_a_paid.groupby(col_agrupa)['valor_suscripcion'].sum().rename("Suscripciones") if not df_a_paid.empty else pd.Series(name="Suscripciones", dtype=float)
                vm_agrupado = df_vm_paid.groupby(col_agrupa)['ingreso_total'].sum().rename("Ventas Masivas") if not df_vm_paid.empty else pd.Series(name="Ventas Masivas", dtype=float)

                df_tendencia = pd.concat([v_agrupado, a_agrupado, vm_agrupado], axis=1).fillna(0.0).sort_index()
                df_tendencia.index = df_tendencia.index.astype(str)
                st.line_chart(df_tendencia, use_container_width=True)
            else:
                st.info("No hay ingresos registrados en el periodo.")

    with col_g2:
        with st.container(border=True):
            st.markdown(f"#### 💸 Tendencia de Costos de Ventas vs No Ventas ({texto_freq})")
            if not df_v_paid.empty or not df_a_paid.empty or not df_vm_paid.empty or not df_costos_no_v_filt.empty:
                if es_mes_unico:
                    if not df_v_paid.empty: df_v_paid['dia_str'] = df_v_paid['fecha_venta'].dt.strftime('%d/%m')
                    if not df_a_paid.empty: df_a_paid['dia_str'] = df_a_paid['fecha_asignacion'].dt.strftime('%d/%m')
                    if not df_vm_paid.empty: df_vm_paid['dia_str'] = df_vm_paid['fecha_evento_dt'].dt.strftime('%d/%m')
                    if not df_costos_no_v_filt.empty: df_costos_no_v_filt['dia_str'] = df_costos_no_v_filt['fecha_ocurrencia'].dt.strftime('%d/%m')
                    col_agrupa = 'dia_str'
                else:
                    if not df_v_paid.empty: df_v_paid['mes_str'] = df_v_paid['fecha_venta'].dt.strftime('%Y-%m')
                    if not df_a_paid.empty: df_a_paid['mes_str'] = df_a_paid['fecha_asignacion'].dt.strftime('%Y-%m')
                    if not df_vm_paid.empty: df_vm_paid['mes_str'] = df_vm_paid['fecha_evento_dt'].dt.strftime('%Y-%m')
                    if not df_costos_no_v_filt.empty: df_costos_no_v_filt['mes_str'] = df_costos_no_v_filt['fecha_ocurrencia'].dt.strftime('%Y-%m')
                    col_agrupa = 'mes_str'

                v_costo_agrupado = df_v_paid.groupby(col_agrupa)['costo_venta'].sum().rename("Costo Ventas Directas") if not df_v_paid.empty else pd.Series(name="Costo Ventas Directas", dtype=float)
                a_costo_agrupado = df_a_paid.groupby(col_agrupa)['costo_caja'].sum().rename("Costo Suscripciones") if not df_a_paid.empty else pd.Series(name="Costo Suscripciones", dtype=float)
                vm_costo_agrupado = df_vm_paid.groupby(col_agrupa)['costo_total'].sum().rename("Costo Ventas Masivas") if not df_vm_paid.empty else pd.Series(name="Costo Ventas Masivas", dtype=float)
                cnv_costo_agrupado = df_costos_no_v_filt.groupby(col_agrupa)['monto'].sum().rename("Costos No de Ventas") if not df_costos_no_v_filt.empty else pd.Series(name="Costos No de Ventas", dtype=float)

                df_costos_tendencia = pd.concat([v_costo_agrupado, a_costo_agrupado, vm_costo_agrupado, cnv_costo_agrupado], axis=1).fillna(0.0).sort_index()
                df_costos_tendencia.index = df_costos_tendencia.index.astype(str)
                st.line_chart(df_costos_tendencia, use_container_width=True)
            else:
                st.info("No hay costos registrados en el periodo.")

    # Fila 2: Operaciones y Clientes
    col_g3, col_g4 = st.columns(2)
    
    with col_g3:
        with st.container(border=True):
            st.markdown("#### ⚖️ Volumen vs. Rentabilidad por Canal")
            df_canales = pd.DataFrame({
                "Canal": ["Suscripciones", "Ventas Directas", "Ventas Masivas"],
                "Ingresos": [ingreso_asig, ingreso_caja, ingreso_vm],
                "Utilidad": [utilidad_asig, utilidad_caja, utilidad_vm]
            }).set_index("Canal")
            st.bar_chart(df_canales, use_container_width=True)

    with col_g4:
        with st.container(border=True):
            st.markdown("#### 👥 Volumen según tipo de cliente")
            if not df_clientes.empty and 'status' in df_clientes.columns:
                conteo_clientes = df_clientes['status'].value_counts()
                st.bar_chart(conteo_clientes, use_container_width=True, color="#4CAF50")
            else:
                st.info("No se registran estados de clientes.")

    # Fila 3: Envíos y Libros Populares
    col_g5, col_g6 = st.columns(2)
    
    with col_g5:
        with st.container(border=True):
            st.markdown("#### 🚚 Métodos de Envío más Utilizados (Ventas)")
            if not df_v_filt.empty and 'metodo_envio' in df_v_filt.columns:
                df_v_filt['envio_limpio'] = df_v_filt['metodo_envio'].fillna("Sin especificar")
                conteo_envios = df_v_filt['envio_limpio'].value_counts()
                st.bar_chart(conteo_envios, use_container_width=True, color="#FF9800")
            else:
                st.info("No hay registros de envío en este periodo.")

    with col_g6:
        with st.container(border=True):
            st.markdown("#### 🔥 Top 10 Libros Populares (Ventas + Suscripción)")
            df_populares = obtener_top_libros_populares(df_v_filt, df_a_filt)
            if not df_populares.empty:
                st.bar_chart(df_populares, use_container_width=True, color="#9C27B0")
            else:
                st.info("No hay asignaciones o ventas en este período.")

    # Fila 4: Volumen de Suscripciones (Frecuencia Mensual Forzada)
    with st.container(border=True):
        st.markdown("#### 📊 Volumen de Suscripciones del Período (Mensual)")
        if not df_a_filt.empty:
            df_a_filt['vol_str'] = df_a_filt['ano'].astype(str) + "-" + df_a_filt['mes'].astype(str).str.zfill(2)
            conteo_asig = df_a_filt.groupby('vol_str').size().rename("Cantidad")
            conteo_asig.index = conteo_asig.index.astype(str)
            st.bar_chart(conteo_asig, use_container_width=True, color="#E91E63")
        else:
            st.info("No hay asignaciones en este periodo.")

if __name__ == '__main__':
    mostrar_dashboard()