import streamlit as st
import pandas as pd
from datetime import datetime
from utilidades import get_db_connection, log_error

def unificar_formatos_fecha(serie_fechas):
    """
    Función de parseo de fechas a prueba de balas, capaz de interpretar
    múltiples formatos y de remover de forma segura zonas horarias (Timezones).
    """
    def parsear_valor(val):
        if pd.isna(val) or not str(val).strip() or str(val).strip().lower() in ['nan', 'nat']:
            return pd.NaT
        val_str = str(val).strip()
        try:
            # Si tiene zona horaria (como la T de ISO o el símbolo +), se procesa y remueve
            if 't' in val_str.lower() or '+' in val_str:
                return pd.to_datetime(val_str).tz_localize(None)
            
            # Formatos tradicionales
            if len(val_str.split('-')[0]) == 4 or len(val_str.split('/')[0]) == 4:
                return pd.to_datetime(val_str, dayfirst=False, errors='coerce').tz_localize(None)
            else:
                return pd.to_datetime(val_str, dayfirst=True, errors='coerce').tz_localize(None)
        except:
            try:
                return pd.to_datetime(val_str, errors='coerce').tz_localize(None)
            except:
                return pd.NaT

    try:
        return serie_fechas.apply(parsear_valor)
    except Exception as e:
        return pd.to_datetime(serie_fechas, errors='coerce').dt.tz_localize(None)

@st.cache_data(ttl=60)  # TTL reducido a 1 minuto para mayor frescura de datos
def cargar_datos_prioritarios():
    conn = get_db_connection()
    try:
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

    # 1. Unificar fechas y calcular la antigüedad en días (Timezone Naive)
    df_ventas['fecha_limpia'] = unificar_formatos_fecha(df_ventas['fecha_venta'])
    hoy = datetime.now()
    
    # Restamos las fechas convirtiendo ambas a tipo naive (sin zona horaria)
    df_ventas['dias_antiguedad'] = df_ventas['fecha_limpia'].apply(
        lambda x: (hoy - x).days if pd.notna(x) else 0
    )
    
    # 2. Re-calcular las métricas de dinero de manera explícita
    df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0.0)
    df_ventas['abono'] = pd.to_numeric(df_ventas['abono'], errors='coerce').fillna(0.0)
    df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
    
    # Aplanar nombre del cliente para consistencia visual
    if 'cliente' in df_ventas.columns:
        df_ventas['cliente_nombre'] = df_ventas['cliente'].apply(
            lambda x: x.get('nombre') if (isinstance(x, dict) and x.get('nombre')) else 'Cliente Desconocido'
        )
    else:
        df_ventas['cliente_nombre'] = 'Cliente Desconocido'

    # Dividimos la pantalla en dos columnas de alta visibilidad
    col_envios, col_cobranzas = st.columns(2)

    # ================= COLUMNA 1: ENVÍOS PENDIENTES (>5 días) =================
    with col_envios:
        st.markdown("### 📦 Armado de Paquetes Demorados (>5 días)")
        
        # Filtro: Mayor de 5 días y estado NO es "PAQUETE LISTO" ni "FINALIZADO"
        df_envios_limbo = df_ventas[
            (df_ventas['dias_antiguedad'] > 5) & 
            (~df_ventas['estado'].isin(['PAQUETE LISTO', 'FINALIZADO']))
        ].copy()

        if df_envios_limbo.empty:
            st.success("🟢 Al día: No tienes paquetes pendientes con más de 5 días de retraso.")
        else:
            st.error(f"⚠️ Atención: Tienes **{len(df_envios_limbo)}** órdenes pendientes de armado en bodega.")
            for _, row in df_envios_limbo.iterrows():
                # Formatear el texto de libros de manera amigable
                libros_raw = row.get('libros_vendidos', '')
                with st.container(border=True):
                    st.markdown(f"**Venta #{row['venta_id']} — {row['cliente_nombre']}**")
                    st.markdown(f"⏳ Hace `{row['dias_antiguedad']} días` (Creado el {row['fecha_limpia'].strftime('%d/%m/%Y')})")
                    st.markdown(f"📚 **Libros:** `{libros_raw}`")

    # ================= COLUMNA 2: COBRANZAS CRÍTICAS (>14 días) =================
    with col_cobranzas:
        st.markdown("### 💸 Cuentas con Mora Crítica (>14 días)")
        
        # Filtro: Deuda real mayor a cero y antigüedad mayor a 14 días
        df_deudores_criticos = df_ventas[
            (df_ventas['deuda'] > 0) & 
            (df_ventas['dias_antiguedad'] > 14)
        ].copy()

        if df_deudores_criticos.empty:
            st.success("🟢 Al día: No tienes cuentas críticas de cobranza con más de 2 semanas de mora.")
        else:
            st.error(f"🚨 Alerta: Tienes **{len(df_deudores_criticos)}** deudas críticas acumulando atraso.")
            for _, row in df_deudores_criticos.iterrows():
                with st.container(border=True):
                    st.markdown(f"👤 **{row['cliente_nombre']}**")
                    st.markdown(f"💰 **Deuda Pendiente:** `${row['deuda']:,.0f}` (Total: `${row['monto_final']:,.0f}`)")
                    st.markdown(f"⏳ `{row['dias_antiguedad']} días` de atraso desde la fecha de venta.")

    st.markdown("---")
    st.info("💡 **Nota:** Para solucionar o actualizar estas alertas, dirígete a los paneles de **Caja / Ventas Rápidas**.")