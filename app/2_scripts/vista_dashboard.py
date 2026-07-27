import streamlit as st
import pandas as pd
import datetime
from utilidades import get_db_connection

def obtener_top_libros_populares(fecha_inicio, fecha_fin):
    """
    Consolida las ventas directas y las asignaciones del periodo seleccionado 
    para identificar los 10 libros más populares.
    """
    conn = get_db_connection()
    conteo_libros = {}

    try:
        # 1. Procesar Asignaciones del periodo
        res_asig = conn.table("asignaciones").select("libro_suscripcion_id, fecha_asignacion").execute()
        df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
        if not df_asig.empty:
            df_asig['fecha_asignacion'] = pd.to_datetime(df_asig['fecha_asignacion'], errors='coerce')
            # Filtrar por fecha
            df_asig = df_asig[(df_asig['fecha_asignacion'] >= pd.to_datetime(fecha_inicio)) & 
                               (df_asig['fecha_asignacion'] <= pd.to_datetime(fecha_fin))]
            
            for libro_id in df_asig['libro_suscripcion_id'].dropna().astype(int):
                conteo_libros[libro_id] = conteo_libros.get(libro_id, 0) + 1

        # 2. Procesar Ventas Directas del periodo
        res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta").execute()
        df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
        if not df_ventas.empty:
            df_ventas['fecha_venta'] = pd.to_datetime(df_ventas['fecha_venta'], errors='coerce')
            df_ventas = df_ventas[(df_ventas['fecha_venta'] >= pd.to_datetime(fecha_inicio)) & 
                                 (df_ventas['fecha_venta'] <= pd.to_datetime(fecha_fin))]
            
            for _, row in df_ventas.iterrows():
                try:
                    libros = json.loads(row['libros_vendidos'])
                    for l in libros:
                        l_id = l.get('libro_id')
                        if l_id:
                            conteo_libros[int(l_id)] = conteo_libros.get(int(l_id), 0) + 1
                except:
                    continue

        if not conteo_libros:
            return pd.DataFrame()

        # 3. Cruzar con títulos de libros
        ids_libros = list(conteo_libros.keys())
        res_detalles = conn.table("libros").select("libro_id, titulo").in_("libro_id", ids_libros).execute()
        df_detalles = pd.DataFrame(res_detalles.data) if res_detalles.data else pd.DataFrame()

        if not df_detalles.empty:
            df_detalles['Cantidad'] = df_detalles['libro_id'].map(conteo_libros)
            # Ordenar de mayor a menor y tomar el Top 10
            df_top = df_detalles.sort_values(by="Cantidad", ascending=False).head(10)
            return df_top.set_index('titulo')[['Cantidad']]
            
    except Exception as e:
        st.error(f"Error generando ranking de libros: {e}")
        
    return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_datos_base():
    """Carga los datos crudos desde la base de datos."""
    conn = get_db_connection()
    
    # Ventas
    res_ventas = conn.table("registro_ventas").select("fecha_venta, monto_final").execute()
    df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
    if not df_ventas.empty:
        df_ventas['fecha_venta'] = pd.to_datetime(df_ventas['fecha_venta'], errors='coerce')
        df_ventas.dropna(subset=['fecha_venta'], inplace=True)
        
    # Asignaciones
    res_asig = conn.table("asignaciones").select("fecha_asignacion, monto_total").execute()
    df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
    if not df_asig.empty:
        df_asig['fecha_asignacion'] = pd.to_datetime(df_asig['fecha_asignacion'], errors='coerce')
        df_asig.dropna(subset=['fecha_asignacion'], inplace=True)
        
    # Clientes
    res_clientes = conn.table("clientes").select("status").execute()
    df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()
    
    return df_ventas, df_asig, df_clientes
def mostrar_alertas_proactivas():
    conn = get_db_connection()
    try:
        # Buscar libros con stock 3 o inferior
        res_stock = conn.table("libros").select("titulo, stock").lte("stock", 3).execute()
        libros_criticos = res_stock.data if res_stock.data else []
        
        if libros_criticos:
            # 1. Alerta Flotante (Toast UX)
            st.toast(f"🚨 Tienes {len(libros_criticos)} libros con stock crítico.", icon="⚠️")
            
            # 2. Banner visual en la parte superior del Dashboard
            with st.expander(f"⚠️ Alerta Operativa: {len(libros_criticos)} libros requieren reabastecimiento", expanded=True):
                st.error("Los siguientes libros están a punto de agotarse o ya no tienen stock:")
                for l in libros_criticos:
                    st.markdown(f"- **{l['titulo']}** (Stock actual: `{l['stock']}` unidades)")
    except Exception:
        pass # Silenciamos errores si falla la conexión para no dañar el dashboard
    
def mostrar_dashboard():
    st.title("📈 Panel de Control y Estadísticas")
    
    mostrar_alertas_proactivas()
    df_ventas, df_asig, df_clientes = cargar_datos_base()
    
    # --- UI: FILTROS GLOBALES ---
    with st.container(border=True):
        st.markdown("### 🔎 Filtro de Tiempo Global")
        st.write("Selecciona un periodo. Todas las métricas y gráficos se actualizarán según estas fechas.")
        
        hoy = datetime.date.today()
        hace_30_dias = hoy - datetime.timedelta(days=30)
        
        # Selector de rango de fechas
        rango_fechas = st.date_input(
            "Rango de fechas",
            value=(hace_30_dias, hoy),
            max_value=hoy,
            format="DD/MM/YYYY"
        )
        
    # Validar que el usuario haya seleccionado inicio y fin
    if len(rango_fechas) != 2:
        st.warning("Por favor, selecciona una fecha de inicio y una de fin para visualizar los datos.")
        st.stop()
        
    fecha_inicio, fecha_fin = rango_fechas
    
    # Convertir a datetime para poder filtrar Pandas correctamente
    fecha_inicio_pd = pd.to_datetime(fecha_inicio)
    fecha_fin_pd = pd.to_datetime(fecha_fin) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1) # Incluir el día final completo

    # --- LÓGICA: FILTRADO DE DATOS ---
    df_v_filt = df_ventas[(df_ventas['fecha_venta'] >= fecha_inicio_pd) & (df_ventas['fecha_venta'] <= fecha_fin_pd)] if not df_ventas.empty else pd.DataFrame()
    df_a_filt = df_asig[(df_asig['fecha_asignacion'] >= fecha_inicio_pd) & (df_asig['fecha_asignacion'] <= fecha_fin_pd)] if not df_asig.empty else pd.DataFrame()

    # --- UI: MÉTRICAS CLAVE ---
    st.markdown("---")
    st.markdown("#### 🎯 Rendimiento en el Periodo Seleccionado")
    
    col1, col2, col3, col4 = st.columns(4)
    
    ingresos_ventas = df_v_filt['monto_final'].sum() if not df_v_filt.empty else 0
    ingresos_asig = df_a_filt['monto_total'].sum() if not df_a_filt.empty else 0
    cantidad_asig = len(df_a_filt)
    clientes_activos = len(df_clientes[df_clientes['status'] == 'ACTIVA']) if not df_clientes.empty else 0
    
    col1.metric("💰 Ingresos Ventas", f"${ingresos_ventas:,.0f}")
    col2.metric("📦 Ingresos Suscripción", f"${ingresos_asig:,.0f}")
    col3.metric("📈 Vol. Asignaciones", cantidad_asig, help="Cantidad de asignaciones realizadas en este periodo")
    col4.metric("👥 Clientes Activos", clientes_activos, help="Total histórico de clientes activos")

    # --- LÓGICA DE UX: AGRUPAMIENTO INTELIGENTE ---
    # Si el rango es mayor a 90 días, agrupamos por mes para que el gráfico no sea un código de barras ilegible.
    dias_rango = (fecha_fin - fecha_inicio).days
    frecuencia = "M" if dias_rango > 90 else "D"
    texto_freq = "Mensual" if dias_rango > 90 else "Diaria"

    # --- UI: GRÁFICOS ---
    st.markdown("<br>", unsafe_allow_html=True)
    col_izq, col_der = st.columns(2)
    
    st.markdown("<br>", unsafe_allow_html=True)
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        # (Aquí mantienes el gráfico de cantidad de asignaciones diarias/mensuales)
        with st.container(border=True):
            st.markdown(f"#### 📊 Cantidad de Asignaciones ({texto_freq})")
            # ... tu gráfico de barras de asignaciones ...

    with col_der:
        # ¡AÑADIMOS EL TOP 10 DE LIBROS POPULARES AQUÍ!
        with st.container(border=True):
            st.markdown("#### 🔥 Top 10 Libros Más Populares (Ventas + Suscripción)")
            df_populares = obtener_top_libros_populares(fecha_inicio, fecha_fin)
            
            if not df_populares.empty:
                # Usamos un gráfico de barras horizontal (Streamlit lo hace automáticamente si los datos están bien indexados)
                st.bar_chart(df_populares, use_container_width=True, color="#9C27B0") # Color Púrpura elegante
            else:
                st.info("No hay suficientes ventas o asignaciones en este rango de fechas para generar el ranking.")

    with col_der:
        with st.container(border=True):
            st.markdown(f"#### 💵 Evolución de Ingresos ({texto_freq})")
            if not df_v_filt.empty or not df_a_filt.empty:
                v_agrupado = pd.Series(dtype=float)
                a_agrupado = pd.Series(dtype=float)
                
                if not df_v_filt.empty:
                    v_agrupado = df_v_filt.groupby(df_v_filt['fecha_venta'].dt.to_period(frecuencia))['monto_final'].sum().rename("Ventas Directas")
                if not df_a_filt.empty:
                    a_agrupado = df_a_filt.groupby(df_a_filt['fecha_asignacion'].dt.to_period(frecuencia))['monto_total'].sum().rename("Suscripciones")
                    
                df_tendencia = pd.concat([v_agrupado, a_agrupado], axis=1).fillna(0)
                df_tendencia.index = df_tendencia.index.astype(str)
                
                # Gráfico de líneas o áreas, ideal para tendencias financieras
                st.line_chart(df_tendencia, use_container_width=True)
            else:
                st.info("No hay ingresos registrados en estas fechas.")

if __name__ == '__main__':
    mostrar_dashboard()