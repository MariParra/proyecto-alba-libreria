import streamlit as st
import gspread
import pandas as pd
import json
import base64
from utilidades import get_db_connection, limpiar_texto
import time

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
    Sincronización Total (Clientes + Suscripciones) decodificando el JSON completo desde Base64.
    """
    try:
        # 1. Leemos la clave Base64 DESDE DENTRO del bloque que sí funciona
        b64_str = st.secrets["gcp_service_account"]["credentials_b64"]
        
        # 2. Lo decodificamos de vuelta a su formato original JSON
        json_str = base64.b64decode(b64_str).decode('utf-8')
        creds_dict = json.loads(json_str)

        with st.spinner("Conectando con Google Sheets..."):
            gc = gspread.service_account_from_dict(creds_dict)
            spreadsheet = gc.open("INSCRIPCIONES CAJA MENSUAL") 
            worksheet = spreadsheet.worksheet("formulario")
            df = pd.DataFrame(worksheet.get_all_records())
            
        st.success("✅ ¡Conexión exitosa con Google Sheets!")
        
    except Exception as e:
        st.error(f"Error de conexión con Google: {e}")
        return False
    
    conn = get_db_connection()
    try:
        with st.spinner("Sincronizando Clientes y Suscripciones..."):
            # Lógica de sincronización (sin cambios)
            col_nombre = next((c for c in df.columns if 'nombre' in c.lower()), df.columns[0])
            col_estado = next((c for c in df.columns if 'estado' in c.lower() or 'status' in c.lower()), None)
            col_telefono = next((c for c in df.columns if 'tel' in c.lower() or 'fono' in c.lower() or 'celular' in c.lower()), None)
            col_email = next((c for c in df.columns if 'correo' in c.lower() or 'email' in c.lower()), None)
            col_fecha = next((c for c in df.columns if 'fecha de pago' in c.lower() or 'pago' in c.lower()), None)
            col_generos = next((c for c in df.columns if 'géneros' in c.lower() or 'generos' in c.lower()), None)
            col_metodo = next((c for c in df.columns if 'método de entrega' in c.lower() or 'entrega' in c.lower()), None)
            
            procesados, clientes_nuevos, clientes_actualizados = 0, 0, 0
            
            for index, row in df.iterrows():
                nombre_sync = limpiar_texto(str(row.get(col_nombre, "")))
                if not nombre_sync or nombre_sync == "SIN INFORMACION": continue
                
                estado_sync = str(row.get(col_estado, "")).strip().upper() if col_estado else "ACTIVA"
                if not estado_sync or estado_sync == "NONE" or estado_sync == "": estado_sync = "ACTIVA"
                
                tel_sync = limpiar_texto(str(row.get(col_telefono, ""))) if col_telefono else ""
                email_sync = limpiar_texto(str(row.get(col_email, ""))) if col_email else ""
                
                fecha_sync = str(row.get(col_fecha, "")) if col_fecha else ""
                generos_sync = str(row.get(col_generos, "")) if col_generos else ""
                metodo_sync = str(row.get(col_metodo, "")) if col_metodo else ""
                
                res_nombre = conn.table("clientes").select("*").eq("nombre", nombre_sync).execute()
                res_email = conn.table("clientes").select("*").eq("email", email_sync).execute() if email_sync else None
                
                cliente_existente = None
                if res_nombre.data:
                    cliente_existente = res_nombre.data[0]
                elif res_email and res_email.data:
                    cliente_existente = res_email.data[0]
                
                if cliente_existente:
                    c_id = cliente_existente['cliente_id']
                    datos_c_actualizar = {}
                    if estado_sync and estado_sync != str(cliente_existente.get('status', '')).upper():
                        datos_c_actualizar['status'] = estado_sync
                    if tel_sync and tel_sync != cliente_existente.get('telefono'):
                        datos_c_actualizar['telefono'] = tel_sync
                    if email_sync and email_sync != cliente_existente.get('email'):
                        datos_c_actualizar['email'] = email_sync
                    if datos_c_actualizar:
                        conn.table("clientes").update(datos_c_actualizar).eq("cliente_id", c_id).execute()
                        clientes_actualizados += 1
                else:
                    res_insert = conn.table("clientes").insert({'nombre': nombre_sync, 'email': email_sync, 'telefono': tel_sync, 'status': estado_sync}).execute()
                    c_id = res_insert.data[0]['cliente_id']
                    clientes_nuevos += 1
                
                res_sub = conn.table("suscripciones").select("suscripcion_id").eq("cliente_id", c_id).execute()
                datos_sub = {"fecha_pago": fecha_sync, "metodo_entrega": metodo_sync, "generos_preferencia": generos_sync}
                if res_sub.data:
                    s_id = res_sub.data[0]['suscripcion_id']
                    conn.table("suscripciones").update(datos_sub).eq("suscripcion_id", s_id).execute()
                else:
                    datos_sub["cliente_id"] = c_id
                    datos_sub["valor_suscripcion"] = 0.0
                    conn.table("suscripciones").insert(datos_sub).execute()
                procesados += 1
                
        st.success(f"🎉 Sincronización Total Finalizada. Total: {procesados} | Nuevos: {clientes_nuevos} | Actualizados: {clientes_actualizados}")
        st.cache_data.clear()
        
    except Exception as e:
        st.error(f"Error crítico durante la sincronización a la BD: {e}")
        return False

import time # <--- Asegúrate de agregar import time en la parte de arriba de tu script si no lo tienes

def mostrar_herramientas():
    st.title("🛠️ Herramientas Administrativas")
    total_cli, activos_cli, inactivos_cli = obtener_resumen_clientes()
    
    st.markdown("### 👥 Resumen del Directorio")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Clientes Registrados", total_cli)
    c2.metric("🟢 Suscripciones (ACTIVA)", activos_cli)
    c3.metric("🔴 Clientes (NO ACTIVA)", inactivos_cli) # Actualizado con tu nueva regla
    st.markdown("---")
    
    with st.container(border=True):
        st.markdown("### 🔄 Sincronización Total con Google Sheets")
        st.info("💡 **Lógica 2.0:** El sistema leerá el Excel y actualizará los datos de contacto y las preferencias de suscripción.")
        
        if st.button("🚀 Iniciar Sincronización de Clientes y Suscripciones", type="primary", use_container_width=True):
            exito = sync_google_sheets()
            
            if exito:
                # Si todo salió bien, espera 3 segundos para que leas el mensaje y luego recarga
                time.sleep(5)
                st.rerun()
            # Si 'exito' es False (hubo error), NO hace st.rerun(), dejando el error fijo en pantalla.