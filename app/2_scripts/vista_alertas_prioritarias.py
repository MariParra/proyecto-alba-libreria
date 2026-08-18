import streamlit as st
import pandas as pd
from datetime import datetime
from utilidades import get_db_connection, log_error

@st.cache_data(ttl=120)
def cargar_datos_prioritarios():
    conn = get_db_connection()
    try:
        # Traemos las ventas con los datos del cliente para procesar ambos tipos de alertas
        res = conn.table("registro_ventas").select("*, cliente:clientes(cliente_id, nombre, rut, email, telefono)").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_alertas_prioritarias", "cargar_datos_prioritarios", e, st.session_state.get('email_usuario', 'Desconocido'))
        return pd.DataFrame()

def mostrar_alertas_prioritarias():
    st.title("🚨 Centro de Alertas Prioritarias")
    st.markdown("---")
    
    df_ventas = cargar_datos_prioritarios()
    
    if df_ventas.empty:
        st.success("🎉 ¡Felicidades! No hay alertas pendientes en el sistema.")
        return

    # Procesar fechas de forma segura
    df_ventas['fecha_dt'] = pd.to_datetime(df_ventas['fecha_venta'], errors='coerce')
    hoy = datetime.now()
    df_ventas['dias_antiguedad'] = (hoy - df_ventas['fecha_dt']).dt.days
    
    # Aplanar nombre del cliente
    df_ventas['cliente_nombre'] = df_ventas['cliente'].apply(lambda x: x.get('nombre') if isinstance(x, dict) else 'Cliente')

    # Separar en dos columnas de visualización de alta visibilidad
    col_envios, col_cobranzas = st.columns(2)

    # ================= COLUMNA 1: ENVÍOS PENDIENTES (>5 días) =================
    with col_envios:
        st.markdown("### 📦 Armado de Paquetes Demorados (>5 días)")
        df_envios_limbo = df_ventas[
            (df_ventas['dias_antiguedad'] > 5) & 
            (~df_ventas['estado'].isin(['PAQUETE LISTO', 'FINALIZADO']))
        ].copy()

        if df_envios_limbo.empty:
            st.success("🟢 Al día: No tienes paquetes pendientes con más de 5 días de retraso.")
        else:
            st.error(f"⚠️ Atención: Tienes **{len(df_envios_limbo)}** órdenes pendientes de armado.")
            for _, row in df_envios_limbo.iterrows():
                with st.container(border=True):
                    st.markdown(f"**Venta #{row['venta_id']} - {row['cliente_nombre']}**")
                    st.markdown(f"⏳ Hace `{row['dias_antiguedad']} días` | 📚 `{row['libros_vendidos']}`")

    # ================= COLUMNA 2: COBRANZAS CRÍTICAS (>14 días) =================
    with col_cobranzas:
        st.markdown("### 💸 Cuentas con Mora Crítica (>14 días)")
        
        # Calcular deudas
        df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0)
        df_ventas['abono'] = pd.to_numeric(df_ventas['abono'], errors='coerce').fillna(0)
        df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
        
        df_deudores_criticos = df_ventas[
            (df_ventas['deuda'] > 0) & 
            (df_ventas['dias_antiguedad'] > 14)
        ].copy()

        if df_deudores_criticos.empty:
            st.success("🟢 Al día: No tienes cuentas críticas de cobranza con más de 2 semanas de mora.")
        else:
            st.error(f"🚨 Alerta: Tienes **{len(df_deudores_criticos)}** deudas con más de 14 días pendientes.")
            for _, row in df_deudores_criticos.iterrows():
                with st.container(border=True):
                    st.markdown(f"👤 **{row['cliente_nombre']}**")
                    st.markdown(f"💰 **Deuda:** `${row['deuda']:,.0f}` (Monto total: `${row['monto_final']:,.0f}`)")
                    st.markdown(f"⏳ `{row['dias_antiguedad']} días` desde la compra original.")

    st.markdown("---")
    st.info("💡 **Nota:** Para solucionar o actualizar estas alertas, dirígete a los paneles de **Caja / Ventas Rápidas**.")