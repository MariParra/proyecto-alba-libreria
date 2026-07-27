import streamlit as st
import pandas as pd
import datetime
from utilidades import get_db_connection

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
    
    with col_izq:
        with st.container(border=True):
            st.markdown(f"#### 📊 Cantidad de Asignaciones ({texto_freq})")
            if not df_a_filt.empty:
                # Contar asignaciones en el tiempo
                conteo_asig = df_a_filt.groupby(df_a_filt['fecha_asignacion'].dt.to_period(frecuencia)).size().rename("Cantidad Asignaciones")
                conteo_asig.index = conteo_asig.index.astype(str)
                # Gráfico de barras, ideal para conteos (volumen)
                st.bar_chart(conteo_asig, use_container_width=True, color="#4CAF50")
            else:
                st.info("No hay asignaciones registradas en estas fechas.")

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