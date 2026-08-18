import streamlit as st
import pandas as pd
import json 
from datetime import datetime
from utilidades import get_db_connection, log_error

def formatear_libros_amigable(libros_raw):
    """
    Toma la cadena técnica JSON de libros vendidos y la convierte 
    en un texto limpio y elegante para la dueña de la librería.
    """
    if not isinstance(libros_raw, str) or not libros_raw.strip():
        return "Sin Detalle"
    
    if libros_raw.strip().startswith('['):
        try:
            libros = json.loads(libros_raw)
            # Retorna en formato amigable: "1 x **Ami** | 1 x **Manual de señoritas...**"
            return " | ".join([f"{item.get('cantidad', 1)} x **{item.get('titulo', 'N/A')}**" for item in libros])
        except Exception:
            return libros_raw
    return libros_raw

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

    # ================= PASO 1: CÁLCULOS Y PLANCHADO DE DATOS (AL INICIO) =================
    # A. Unificar fechas y calcular la antigüedad en días
    df_ventas['fecha_limpia'] = unificar_formatos_fecha(df_ventas['fecha_venta'])
    hoy = datetime.now()
    df_ventas['dias_antiguedad'] = df_ventas['fecha_limpia'].apply(
        lambda x: (hoy - x).days if pd.notna(x) else 0
    )
    
    # B. Cálculos monetarios explícitos
    df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0.0)
    df_ventas['abono'] = pd.to_numeric(df_ventas['abono'], errors='coerce').fillna(0.0)
    df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
    
    # C. Aplanar nombre del cliente de forma ultra segura
    if 'cliente' in df_ventas.columns:
        df_ventas['cliente_nombre'] = df_ventas['cliente'].apply(
            lambda x: x.get('nombre') if (isinstance(x, dict) and x.get('nombre')) else 'Cliente Desconocido'
        )
    else:
        df_ventas['cliente_nombre'] = 'Cliente Desconocido'


    # ================= PASO 2: COMPROBACIÓN DE ALERTAS ACTIVAS =================
    df_envios_limbo = df_ventas[
        (df_ventas['dias_antiguedad'] > 5) & 
        (~df_ventas['estado'].isin(['PAQUETE LISTO', 'FINALIZADO']))
    ].copy()
    
    df_deudores_criticos = df_ventas[
        (df_ventas['deuda'] > 0) & 
        (df_ventas['dias_antiguedad'] > 14)
    ].copy()

    hay_envios_limbo = not df_envios_limbo.empty
    hay_cobranzas_criticas = not df_deudores_criticos.empty


    # ================= PASO 3: BANNER CÓMICO DE BIENVENIDA (HÁMSTER) =================
    if hay_envios_limbo or hay_cobranzas_criticas:
        col_b1, col_b2 = st.columns([1, 2.5])
        with col_b1:
            st.image("https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster.png", width=180)
        with col_b2:
            st.markdown(
                """
                <div style="background-color:#ffebee; border:3px solid #ff4b4b; padding:20px; border-radius:10px; display:flex; flex-direction:column; justify-content:center; height:100%;">
                    <h2 style="color:#c62828; margin:0; font-size:26px;">🐹💤 ¡ALERTA CRÍTICA DE PRODUCTIVIDAD!</h2>
                    <p style="color:#b71c1c; font-size:20px; font-weight:bold; margin:8px 0 0 0;">
                        ¡Ivonne, deja de dormir y ponte a trabajar!
                    </p>
                    <p style="color:#333; margin:4px 0 0 0; font-size:14px;">
                        Tienes cajas acumulando polvo y cobros pendientes en bodega. ¡Mueve la rueda del hámster! 🏃‍♀️💨
                    </p>
                </div>
                """, 
                unsafe_allow_html=True
            )
        st.markdown("---")


    # ================= PASO 4: RENDERIZADO DE COLUMNAS =================
    col_envios, col_cobranzas = st.columns(2)

    # COLUMNA 1: ENVÍOS
    with col_envios:
        st.markdown("### 📦 Armado de Paquetes Demorados (>5 días)")
        if not hay_envios_limbo:
            st.success("🟢 Al día: No tienes paquetes pendientes con más de 5 días de retraso.")
        else:
            st.error(f"⚠️ Atención: Tienes **{len(df_envios_limbo)}** órdenes pendientes de armado en bodega.")
            for _, row in df_envios_limbo.iterrows():
                libros_raw = row.get('libros_vendidos', '')
                libros_formateados = formatear_libros_amigable(libros_raw)
                
                with st.container(border=True):
                    st.markdown(f"**Venta #{row['venta_id']} — {row['cliente_nombre']}**")
                    st.markdown(f"⏳ Hace `{row['dias_antiguedad']} días` (Creado el {row['fecha_limpia'].strftime('%d/%m/%Y')})")
                    st.markdown(f"📚 **Libros a empacar:** {libros_formateados}")

    # COLUMNA 2: COBRANZAS
    with col_cobranzas:
        st.markdown("### 💸 Cuentas con Mora Crítica (>14 días)")
        if not hay_cobranzas_criticas:
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
