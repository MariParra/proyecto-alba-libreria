import streamlit as st
import gspread
import pandas as pd
import json
import base64  # Importante
from utilidades import get_db_connection, limpiar_texto

def obtener_credenciales_google():
    """Decodifica la clave privada desde Base64 y construye las credenciales."""
    sec = st.secrets["gcp_service_account"]
    
    # Decodificar la clave privada desde Base64
    clave_b64 = sec.get("private_key_b64", "")
    clave_privada_limpia = base64.b64decode(clave_b64).decode('utf-8')

    return {
        "type": str(sec.get("type", "")),
        "project_id": str(sec.get("project_id", "")),
        "private_key_id": str(sec.get("private_key_id", "")),
        "private_key": clave_privada_limpia,
        "client_email": str(sec.get("client_email", "")),
        "client_id": str(sec.get("client_id", "")),
        "auth_uri": str(sec.get("auth_uri", "")),
        "token_uri": str(sec.get("token_uri", "")),
        "auth_provider_x509_cert_url": str(sec.get("auth_provider_x509_cert_url", "")),
        "client_x509_cert_url": str(sec.get("client_x509_cert_url", ""))
    }

def sync_google_sheets():
    try:
        creds_dict = obtener_credenciales_google()
        with st.spinner("Conectando con Google Sheets..."):
            gc = gspread.service_account_from_dict(creds_dict)
            spreadsheet = gc.open("INSCRIPCIONES CAJA MENSUAL") 
            worksheet = spreadsheet.worksheet("formulario")
            df = pd.DataFrame(worksheet.get_all_records())
        st.success("✅ ¡Conexión exitosa con Google Sheets!")
    except Exception as e:
        st.error(f"Error de conexión con Google: {e}")
        return

    conn = get_db_connection()
    try:
        with st.spinner("Sincronizando clientes en la base de datos..."):
            # Lógica de sincronización (sin cambios)
            col_nombre = next((c for c in df.columns if 'nombre' in c.lower()), df.columns[0])
            col_estado = next((c for c in df.columns if 'estado cliente' in c.lower()), None)
            col_telefono = next((c for c in df.columns if 'tel' in c.lower() or 'fono' in c.lower()), None)
            col_email = next((c for c in df.columns if 'correo' in c.lower() or 'email' in c.lower()), None)
            
            procesados, nuevos, actualizados = 0, 0, 0
            for index, row in df.iterrows():
                nombre_sync = limpiar_texto(str(row.get(col_nombre, "")))
                if not nombre_sync: continue
                estado_sync = str(row.get(col_estado, "")).strip().upper() if col_estado else None
                tel_sync = limpiar_texto(str(row.get(col_telefono, "")))
                email_sync = limpiar_texto(str(row.get(col_email, "")))
                res = conn.table("clientes").select("*").eq("nombre", nombre_sync).limit(1).execute()
                if res.data:
                    c_id = res.data[0]['cliente_id']
                    datos_a_actualizar = {}
                    if estado_sync and estado_sync != res.data[0].get('status', ''):
                        datos_a_actualizar['status'] = estado_sync
                    if tel_sync and tel_sync != res.data[0].get('telefono'):
                        datos_a_actualizar['telefono'] = tel_sync
                    if email_sync and email_sync != res.data[0].get('email'):
                        datos_a_actualizar['email'] = email_sync
                    if datos_a_actualizar:
                        conn.table("clientes").update(datos_a_actualizar).eq("cliente_id", c_id).execute()
                        actualizados += 1
                else:
                    conn.table("clientes").insert({'nombre': nombre_sync, 'email': email_sync, 'telefono': tel_sync, 'status': estado_sync if estado_sync else 'ACTIVA'}).execute()
                    nuevos += 1
                procesados += 1
        st.success(f"🎉 Sync completado. Total: {procesados} | Nuevos: {nuevos} | Actualizados: {actualizados}")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error crítico durante la sincronización: {e}")

def mostrar_herramientas():
    st.title("🛠️ Herramientas Administrativas")
    # ... (Métricas y resto de la interfaz sin cambios)
    total_cli, activos_cli, inactivos_cli = obtener_resumen_clientes()
    st.markdown("### 👥 Resumen del Directorio")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Clientes", total_cli)
    c2.metric("🟢 Activos", activos_cli)
    c3.metric("🔴 Inactivos", inactivos_cli)
    st.markdown("---")
    
    with st.container(border=True):
        st.markdown("### 🔄 Sincronización con Google Sheets")
        st.info("💡 **Lógica:** El sistema leerá la columna 'Estado cliente' y respetará esa decisión.")
        if st.button("🚀 Iniciar Sincronización de Clientes", type="primary", use_container_width=True):
            sync_google_sheets()
            st.rerun()
