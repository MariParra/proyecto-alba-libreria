import streamlit as st
import pandas as pd
from utilidades import get_db_connection

@st.cache_data(ttl=60)
def obtener_datos_dashboard():
    conn = get_db_connection()
    try:
        # Extraer datos de ventas
        res_ventas = conn.table("registro_ventas").select("fecha_venta, monto_final, metodo_pago").execute()
        df_ventas = pd.DataFrame(res_ventas.data)
        if not df_ventas.empty:
            df_ventas['fecha_venta'] = pd.to_datetime(df_ventas['fecha_venta']).dt.date
            
        # Extraer datos de clientes
        res_clientes = conn.table("clientes").select("status").execute()
        df_clientes = pd.DataFrame(res_clientes.data)
        
        # Extraer inventario
        res_libros = conn.table("libros").select("titulo, stock").order("stock").limit(10).execute()
        df_libros = pd.DataFrame(res_libros.data)
        
        return df_ventas, df_clientes, df_libros
    except Exception as e:
        st.error(f"Error cargando datos para gráficos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def mostrar_dashboard():
    st.title("📈 Panel de Control y Estadísticas")
    st.markdown("---")
    
    df_ventas, df_clientes, df_libros = obtener_datos_dashboard()
    
    if df_ventas.empty and df_clientes.empty:
        st.warning("No hay suficientes datos para generar gráficos aún.")
        return

    # --- MÉTRICAS SUPERIORES ---
    col1, col2, col3 = st.columns(3)
    if not df_ventas.empty:
        ingresos_totales = df_ventas['monto_final'].sum()
        col1.metric("💰 Ingresos Históricos (Caja)", f"${ingresos_totales:,.0f}")
    if not df_clientes.empty:
        col2.metric("👥 Total de Clientes", len(df_clientes))
        suscritos = len(df_clientes[df_clientes['status'] == 'SUSCRITO'])
        col3.metric("⭐ Clientes Suscritos", suscritos)

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        with st.container(border=True):
            st.markdown("#### 📅 Evolución de Ingresos diarios (Caja)")
            if not df_ventas.empty:
                # Agrupar por fecha y sumar
                ventas_diarias = df_ventas.groupby('fecha_venta')['monto_final'].sum().reset_index()
                ventas_diarias.set_index('fecha_venta', inplace=True)
                st.line_chart(ventas_diarias, use_container_width=True)
            else:
                st.info("Sin datos de ventas.")

        with st.container(border=True):
            st.markdown("#### 📊 Distribución de Clientes")
            if not df_clientes.empty:
                dist_clientes = df_clientes['status'].value_counts()
                st.bar_chart(dist_clientes, use_container_width=True)

    with col_der:
        with st.container(border=True):
            st.markdown("#### 💳 Preferencias de Pago (Caja)")
            if not df_ventas.empty:
                pagos = df_ventas['metodo_pago'].value_counts()
                st.bar_chart(pagos, use_container_width=True)
                
        with st.container(border=True):
            st.markdown("#### ⚠️ Top 10 Libros con Menos Stock")
            if not df_libros.empty:
                df_libros.set_index('titulo', inplace=True)
                st.bar_chart(df_libros, use_container_width=True)