import streamlit as st
import gspread
import pandas as pd
import json
import base64
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIÓN: RESUMEN DE CLIENTES ---
def obtener_resumen_clientes():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("status").execute()
        df = pd.DataFrame(res.data)
        if df.empty: return 0, 0, 0
        total = len(df)
        activos = len(df[df['status'] == 'ACTIVA'])
        inactivos = len(df[df['status'] == 'NO ACTIVA'])
        return total, activos, inactivos
    except:
        return 0, 0, 0

def sync_google_sheets():
    """
    Sincroniza los clientes decodificando el archivo JSON completo desde Base64.
    ¡Muestra un resumen visual de la tabla leída!
    """
    try:
        # 1. Traemos el Base64 gigante desde los secretos
        b64_str = st.secrets["GCP_B64"]
        
        # 2. Lo decodificamos de vuelta a su formato original JSON perfecto
        json_str = base64.b64decode(b64_str).decode('utf-8')
        creds_dict = json.loads(json_str)

        with st.spinner("Conectando con Google Sheets..."):
            gc = gspread.service_account_from_dict(creds_dict)
            spreadsheet = gc.open("INSCRIPCIONES CAJA MENSUAL") 
            worksheet = spreadsheet.worksheet("formulario")
            df = pd.DataFrame(worksheet.get_all_records())
            
        st.success("✅ ¡Conexión exitosa con Google Sheets!")
        
        # --- BLOQUE DE DIAGNÓSTICO TEMPORAL ---
        st.markdown("#### 📑 Vista previa de lo que leyó el sistema:")
        if not df.empty:
            st.dataframe(df.head(5), use_container_width=True) # Te muestra las primeras 5 filas del Excel
        else:
            st.warning("⚠️ Atención: La planilla de Google Sheets está vacía o no tiene registros.")
            return
        # --------------------------------------
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("❌ Error: No se encontró la hoja 'INSCRIPCIONES CAJA MENSUAL'. Revisa que esté compartida con el correo del robot.")
        return
    except Exception as e:
        st.error(f"Error de conexión con Google: {e}")
        return

    conn = get_db_connection()
    try:
        with st.spinner("Sincronizando clientes en la base de datos..."):
            # Buscar columnas dinámicamente con mayor flexibilidad
            col_nombre = next((c for c in df.columns if 'nombre' in c.lower()), df.columns[0])
            col_estado = next((c for c in df.columns if 'estado' in c.lower() or 'status' in c.lower()), None)
            col_telefono = next((c for c in df.columns if 'tel' in c.lower() or 'fono' in c.lower() or 'celular' in c.lower()), None)
            col_email = next((c for c in df.columns if 'correo' in c.lower() or 'email' in c.lower()), None)
            
            procesados, nuevos, actualizados = 0, 0, 0
            
            for index, row in df.iterrows():
                nombre_sync = limpiar_texto(str(row.get(col_nombre, "")))
                if not nombre_sync or nombre_sync == "SIN INFORMACION": continue
                
                estado_sync = str(row.get(col_estado, "")).strip().upper() if col_estado else None
                # Si el estado viene en blanco del excel o dice cosas raras, lo dejamos como ACTIVA por defecto
                if not estado_sync or estado_sync == "NONE" or estado_sync == "VACÍO" or estado_sync == "":
                    estado_sync = "ACTIVA"
                
                tel_sync = limpiar_texto(str(row.get(col_telefono, ""))) if col_telefono else ""
                email_sync = limpiar_texto(str(row.get(col_email, ""))) if col_email else ""
                
                res = conn.table("clientes").select("*").eq("nombre", nombre_sync).limit(1).execute()
                
                if res.data:
                    c_id = res.data[0]['cliente_id']
                    datos_a_actualizar = {}
                    if estado_sync and estado_sync != str(res.data[0].get('status', '')).upper():
                        datos_a_actualizar['status'] = estado_sync
                    if tel_sync and tel_sync != res.data[0].get('telefono'):
                        datos_a_actualizar['telefono'] = tel_sync
                    if email_sync and email_sync != res.data[0].get('email'):
                        datos_a_actualizar['email'] = email_sync
                        
                    if datos_a_actualizar:
                        conn.table("clientes").update(datos_a_actualizar).eq("cliente_id", c_id).execute()
                        actualizados += 1
                else:
                    conn.table("clientes").insert({
                        'nombre': nombre_sync, 'email': email_sync, 'telefono': tel_sync, 
                        'status': estado_sync
                    }).execute()
                    nuevos += 1
                    
                procesados += 1
                
        st.success(f"🎉 Sincronización finalizada. Total de filas analizadas: {procesados} | Clientes nuevos: {nuevos} | Datos actualizados: {actualizados}")
        st.cache_data.clear()
        
    except Exception as e:
        st.error(f"Error crítico durante la sincronización: {e}")

def mostrar_herramientas():
    st.title("🛠️ Herramientas Administrativas")
    
    total_cli, activos_cli, inactivos_cli = obtener_resumen_clientes()
    st.markdown("### 👥 Resumen del Directorio")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Clientes Registrados", total_cli)
    c2.metric("🟢 Suscripciones (ACTIVA)", activos_cli)
    c3.metric("🔴 Clientes (INACTIVO)", inactivos_cli)
    st.markdown("---")
    
    with st.container(border=True):
        st.markdown("### 🔄 Sincronización con Google Sheets")
        st.info("💡 **Lógica:** El sistema leerá la columna 'Estado cliente' y respetará esa decisión.")
        if st.button("🚀 Iniciar Sincronización de Clientes", type="primary", use_container_width=True):
            sync_google_sheets()
            st.rerun()