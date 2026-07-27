import streamlit as st
import pandas as pd
from utilidades import get_db_connection

def cargar_datos_dashboard():
    conn = get_db_connection()
    
    # Ventas Directas
    res_ventas = conn.table("registro_ventas").select("fecha_venta, monto_final").execute()
    df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
    
    # Asignaciones
    res_asig = conn.table("asignaciones").select("fecha_asignacion, monto_total").execute()
    df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
    
    # Clientes
    res_clientes = conn.table("clientes").select("status").execute()
    df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()
    
    return df_ventas, df_asig, df_clientes

def mostrar_dashboard():
    st.title("📈 Panel de Control")
    df_ventas, df_asig, df_clientes = cargar_datos_dashboard()
    
    # Preparar datos de tiempo
    if not df_ventas.empty:
        df_ventas['fecha_venta'] = pd.to_datetime(df_ventas['fecha_venta'], errors='coerce')
    if not df_asig.empty:
        df_asig['fecha_asignacion'] = pd.to_datetime(df_asig['fecha_asignacion'], errors='coerce')

    # Métricas Superiores
    col1, col2, col3 = st.columns(3)
    total_ventas = df_ventas['monto_final'].sum() if not df_ventas.empty else 0
    total_asig = df_asig['monto_total'].sum() if not df_asig.empty else 0
    clientes_activos = len(df_clientes[df_clientes['status'] == 'ACTIVO']) if not df_clientes.empty else 0
    
    col1.metric("💰 Ventas Directas", f"${total_ventas:,.0f}")
    col2.metric("📦 Ingresos Asignaciones", f"${total_asig:,.0f}")
    col3.metric("👥 Clientes Activos", clientes_activos)

    st.markdown("---")
    
    # Gráfico de evolución en el tiempo
    st.subheader("Evolución de Ingresos en el Tiempo")
    
    # Agrupar por mes/día
    if not df_ventas.empty and not df_asig.empty:
        v_agrupado = df_ventas.groupby(df_ventas['fecha_venta'].dt.to_period("M"))['monto_final'].sum().rename("Ventas")
        a_agrupado = df_asig.groupby(df_asig['fecha_asignacion'].dt.to_period("M"))['monto_total'].sum().rename("Suscripciones")
        
        df_tendencia = pd.concat([v_agrupado, a_agrupado], axis=1).fillna(0)
        df_tendencia.index = df_tendencia.index.astype(str)
        
        st.bar_chart(df_tendencia, use_container_width=True)
    elif not df_ventas.empty:
        v_agrupado = df_ventas.groupby(df_ventas['fecha_venta'].dt.date)['monto_final'].sum()
        st.line_chart(v_agrupado, use_container_width=True)
    else:
        st.info("No hay suficientes datos de fechas para mostrar el gráfico de evolución.")
