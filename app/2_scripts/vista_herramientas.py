import streamlit as st
import gspread
import pandas as pd
import json
from utilidades import get_db_connection, limpiar_texto

def sync_google_sheets():
    try:
        # Cargar credenciales desde los secretos de Streamlit
        creds_json_str = st.secrets["gcp_service_account"]["credentials"]
        creds_dict = json.loads(creds_json_str)
        
        with st.spinner("Conectando con Google Sheets..."):
            gc = gspread.service_account_from_dict(creds_dict)
            spreadsheet = gc.open("INSCRIPCIONES CAJA MENSUAL") # Reemplaza con el nombre exacto de tu Sheet
            worksheet = spreadsheet.worksheet("formulario")     # Reemplaza con la hoja exacta
            df = pd.DataFrame(worksheet.get_all_records())
        st.success("✅ Conexión exitosa con Google Sheets.")
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets. Revisa tus secretos. Error: {e}")
        return

    conn = get_db_connection()
    try:
        with st.spinner("Sincronizando clientes en la base de datos..."):
            # Buscar nombres de columnas (ajustable)
            col_email = next((c for c in df.columns if 'correo' in c.lower() or 'email' in c.lower()), None)
            col_nombre = next((c for c in df.columns if 'nombre' in c.lower()), df.columns[0])
            col_telefono = next((c for c in df.columns if 'telefono' in c.lower() or 'celular' in c.lower()), None)

            procesados, nuevos, actualizados = 0, 0, 0
            
            for index, row in df.iterrows():
                nombre_sync = limpiar_texto(row.get(col_nombre, ""))
                if not nombre_sync or nombre_sync == "SIN INFORMACION": continue
                
                email_sync = limpiar_texto(row.get(col_email, f"SIN_CORREO_{index}@ALBALIBRERIA.CL")) if col_email else ""
                tel_sync = limpiar_texto(row.get(col_telefono, "")) if col_telefono else ""
                
                # Revisar si existe
                res = conn.table("clientes").select("cliente_id").eq("nombre", nombre_sync).execute()
                
                if res.data:
                    c_id = res.data[0]['cliente_id']
                    # Lo actualizamos y forzamos su status a SUSCRITO porque viene del formulario
                    conn.table("clientes").update({'email': email_sync, 'telefono': tel_sync, 'status': 'SUSCRITO'}).eq("cliente_id", c_id).execute()
                    actualizados += 1
                else:
                    # Crear nuevo cliente
                    conn.table("clientes").insert({'nombre': nombre_sync, 'email': email_sync, 'telefono': tel_sync, 'status': 'SUSCRITO'}).execute()
                    nuevos += 1
                procesados += 1

        st.success(f"🎉 Sincronización completada. Procesados: {procesados} | Nuevos: {nuevos} | Actualizados: {actualizados}")
    except Exception as e:
        st.error(f"Error crítico durante la sincronización: {e}")

def mostrar_herramientas():
    st.title("🛠️ Herramientas Administrativas")
    
    st.info("💡 **Tip de Seguridad:** La sincronización lee la planilla y actualiza tu catálogo de clientes. Los meses cerrados no se verán afectados porque sus asignaciones ya están bloqueadas en su respectiva pestaña.")
    
    with st.container(border=True):
        st.markdown("### 🔄 Sincronización con Google Sheets")
        st.markdown("Importa y actualiza los clientes desde el formulario de **Inscripciones Caja Mensual**.")
        if st.button("🚀 Iniciar Sincronización de Clientes", type="primary", use_container_width=True):
            sync_google_sheets()