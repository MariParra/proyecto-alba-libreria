import streamlit as st
import pandas as pd
import datetime
import json
from utilidades import get_db_connection, log_error

# Esta función ya está bien, la mantenemos
@st.cache_data(ttl=60)
def cargar_datos_base():
    """Carga los datos crudos desde la base de datos."""
    conn = get_db_connection()
    
    # Ventas
    res_ventas = conn.table("registro_ventas").select("fecha_venta, monto_final, libros_vendidos").execute()
    df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
    if not df_ventas.empty:
        df_ventas['fecha_venta'] = pd.to_datetime(df_ventas['fecha_venta'], errors='coerce')
        df_ventas.dropna(subset=['fecha_venta'], inplace=True)
        
    # Asignaciones
    res_asig = conn.table("asignaciones").select("fecha_asignacion, monto_total, libro_suscripcion_id").execute()
    df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()
    if not df_asig.empty:
        df_asig['fecha_asignacion'] = pd.to_datetime(df_asig['fecha_asignacion'], errors='coerce')
        df_asig.dropna(subset=['fecha_asignacion'], inplace=True)
        
    # Clientes
    res_clientes = conn.table("clientes").select("status").execute()
    df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()
    
    return df_ventas, df_asig, df_clientes

# La función de Alertas también está bien
def mostrar_alertas_proactivas():
    # ... (El código de esta función no necesita cambios)
    conn = get_db_connection()
    try:
        res_stock = conn.table("libros").select("titulo, stock").lte("stock", 3).execute()
        libros_criticos = res_stock.data if res_stock.data else []
        if libros_criticos:
            st.toast(f"🚨 Tienes {len(libros_criticos)} libros con stock crítico.", icon="⚠️")
            with st.expander(f"⚠️ Alerta Operativa: {len(libros_criticos)} libros requieren reabastecimiento", expanded=False):
                st.error("Los siguientes libros están a punto de agotarse o ya no tienen stock:")
                for l in libros_criticos:
                    st.markdown(f"- **{l['titulo']}** (Stock actual: `{l['stock']}` unidades)")
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        log_error(
            vista="vista_dashboard",
            funcion="mostrar_alertas_proactivas",
            error=f"Fallo al obtener alertas de stock crítico. Detalle: {e}",
            email_usuario=email_usuario
        )
        
        st.toast("No se pudieron verificar las alertas de stock.", icon="❗")

def obtener_top_libros_populares(df_ventas_filt, df_asig_filt):
    conn = get_db_connection()
    conteo_libros = {}
    try:
        # Procesar Asignaciones del periodo (ya filtradas)
        if not df_asig_filt.empty:
            for libro_id in df_asig_filt['libro_suscripcion_id'].dropna():
                conteo_libros[int(libro_id)] = conteo_libros.get(int(libro_id), 0) + 1
        
        # Procesar Ventas Directas del periodo (ya filtradas)
        if not df_ventas_filt.empty:
            for _, row in df_ventas_filt.iterrows():
                try:
                    libros = json.loads(row['libros_vendidos'])
                    for l in libros:
                        l_id = l.get('libro_id')
                        if l_id:
                            conteo_libros[int(l_id)] = conteo_libros.get(int(l_id), 0) + 1
                except (json.JSONDecodeError, TypeError) as json_e:
                    log_error(
                        vista="vista_dashboard",
                        funcion="obtener_top_libros_populares (JSON Ventas)",
                        error=f"JSON Corrupto en venta ID {row.get('venta_id', 'N/A')}. Detalle: {json_e}",
                        email_usuario="Sistema"
                    )
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
        log_error(
            vista="vista_dashboard",
            funcion="obtener_top_libros_populares",
            error=f"Error generando ranking de libros: {e}",
            email_usuario=email_usuario
        )
        st.error(f"Error generando ranking de libros: {e}")
    return pd.DataFrame()

# --- FUNCIÓN PRINCIPAL MODIFICADA ---
def mostrar_dashboard():
    st.title("📈 Panel de Control y Estadísticas")
    
    mostrar_alertas_proactivas()
    df_ventas, df_asig, df_clientes = cargar_datos_base()
    
    with st.container(border=True):
        st.markdown("### 🔎 Filtro de Tiempo Global")
        hoy = datetime.date.today()
        # Ponemos por defecto los últimos 12 meses para que el gráfico mensual tenga sentido
        hace_un_ano = hoy - datetime.timedelta(days=365)
        
        rango_fechas = st.date_input(
            "Rango de fechas",
            value=(hace_un_ano, hoy),
            max_value=hoy,
            format="DD/MM/YYYY"
        )
        
    if len(rango_fechas) != 2:
        st.warning("Por favor, selecciona una fecha de inicio y una de fin para visualizar los datos.")
        st.stop()
        
    fecha_inicio, fecha_fin = rango_fechas
    fecha_inicio_pd = pd.to_datetime(fecha_inicio)
    fecha_fin_pd = pd.to_datetime(fecha_fin) + pd.Timedelta(days=1)

    df_v_filt = df_ventas[(df_ventas['fecha_venta'] >= fecha_inicio_pd) & (df_ventas['fecha_venta'] <= fecha_fin_pd)]
    df_a_filt = df_asig[(df_asig['fecha_asignacion'] >= fecha_inicio_pd) & (df_asig['fecha_asignacion'] <= fecha_fin_pd)]

    st.markdown("---")
    st.markdown("#### 🎯 Rendimiento en el Periodo Seleccionado")
    col1, col2, col3, col4 = st.columns(4)
    # ... (Métricas, sin cambios)
    ingresos_ventas = df_v_filt['monto_final'].sum()
    ingresos_asig = df_a_filt['monto_total'].sum()
    cantidad_asig = len(df_a_filt)
    clientes_activos = len(df_clientes[df_clientes['status'] == 'ACTIVA'])
    col1.metric("💰 Ingresos Ventas", f"${ingresos_ventas:,.0f}")
    col2.metric("📦 Ingresos Suscripción", f"${ingresos_asig:,.0f}")
    col3.metric("📈 Vol. Asignaciones", cantidad_asig)
    col4.metric("👥 Clientes Activos", clientes_activos)


    # --- 🛠️ CORRECCIÓN: FRECUENCIA MENSUAL Y SIN COLUMNAS ---
    frecuencia = "M"
    texto_freq = "Mensual"
    
    st.markdown("<br>", unsafe_allow_html=True)

    # Gráfico 1: Cantidad de Asignaciones (Pantalla Completa)
    with st.container(border=True):
        st.markdown(f"#### 📊 Cantidad de Asignaciones ({texto_freq})")
        if not df_a_filt.empty:
            conteo_asig = df_a_filt.groupby(df_a_filt['fecha_asignacion'].dt.to_period(frecuencia)).size().rename("Cantidad")
            conteo_asig.index = conteo_asig.index.astype(str)
            st.bar_chart(conteo_asig, use_container_width=True, color="#4CAF50")
        else:
            st.info("No hay asignaciones en este periodo.")

    # Gráfico 2: Evolución de Ingresos (Pantalla Completa)
    with st.container(border=True):
        st.markdown(f"#### 💵 Evolución de Ingresos ({texto_freq})")
        if not df_v_filt.empty or not df_a_filt.empty:
            v_agrupado = df_v_filt.groupby(df_v_filt['fecha_venta'].dt.to_period(frecuencia))['monto_final'].sum().rename("Ventas Directas")
            a_agrupado = df_a_filt.groupby(df_a_filt['fecha_asignacion'].dt.to_period(frecuencia))['monto_total'].sum().rename("Suscripciones")
            
            df_tendencia = pd.concat([v_agrupado, a_agrupado], axis=1).fillna(0)
            df_tendencia.index = df_tendencia.index.astype(str)
            st.line_chart(df_tendencia, use_container_width=True)
        else:
            st.info("No hay ingresos en este periodo.")

    # Gráfico 3: Top 10 Libros Populares (Pantalla Completa)
    with st.container(border=True):
        st.markdown("#### 🔥 Top 10 Libros Más Populares (Ventas + Suscripción)")
        df_populares = obtener_top_libros_populares(df_v_filt, df_a_filt)
        if not df_populares.empty:
            st.bar_chart(df_populares, use_container_width=True, color="#9C27B0")
        else:
            st.info("No hay ventas o asignaciones de libros en este periodo.")

if __name__ == '__main__':
    mostrar_dashboard()