import streamlit as st
import gspread
import pandas as pd
import json
from utilidades import get_db_connection, limpiar_texto

def sync_google_sheets():
    """
    Sincroniza los clientes desde Google Sheets respetando la columna 'Estado cliente'
    y muestra un resumen detallado por estado al finalizar.
    """
    try:
        # Cargar credenciales de forma segura
        creds_json_str = st.secrets["gcp_service_account"]["credentials"]
        creds_dict = json.loads(creds_json_str)
        
        with st.spinner("Conectando con Google Sheets..."):
            gc = gspread.service_account_from_dict(creds_dict)
            spreadsheet = gc.open("INSCRIPCIONES CAJA MENSUAL") 
            worksheet = spreadsheet.worksheet("formulario")
            df = pd.DataFrame(worksheet.get_all_records())
        st.success("✅ Conexión exitosa con Google Sheets.")
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets. Revisa el nombre de tu hoja y los secretos. Error: {e}")
        return

    conn = get_db_connection()
    try:
        with st.spinner("Sincronizando clientes en la base de datos..."):
            # Mapeo flexible de columnas
            col_email = next((c for c in df.columns if 'correo' in c.lower() or 'email' in c.lower()), None)
            col_nombre = next((c for c in df.columns if 'nombre' in c.lower()), df.columns[0])
            col_telefono = next((c for c in df.columns if 'fono' in c.lower() or 'celular' in c.lower()), None)
            
            # Detección explícita de "Estado cliente"
            col_estado = next(
                (c for c in df.columns if 'estado cliente' in c.lower() or 'estado' in c.lower() or 'status' in c.lower()), 
                None
            )
            
            procesados, nuevos, actualizados = 0, 0, 0
            
            for index, row in df.iterrows():
                nombre_sync = limpiar_texto(row.get(col_nombre, ""))
                if not nombre_sync or nombre_sync == "SIN INFORMACION":
                    continue
                
                # Leemos el estado traído desde la fila
                estado_sync = limpiar_texto(str(row.get(col_estado, ""))) if col_estado else None
                
                # Buscamos si el cliente ya existe en nuestra base de datos
                res = conn.table("clientes").select("*").eq("nombre", nombre_sync).limit(1).execute()
                
                if res.data:
                    # CLIENTE EXISTENTE: Actualización protegida
                    cliente_existente = res.data[0]
                    c_id = cliente_existente['cliente_id']
                    datos_a_actualizar = {}
                    
                    # Actualiza el estado solo si viene en la planilla Y es distinto al actual
                    if estado_sync and estado_sync != cliente_existente.get('status'):
                        datos_a_actualizar['status'] = estado_sync

                    # Email y Teléfono protegidos
                    email_sync = limpiar_texto(str(row.get(col_email, "")))
                    if email_sync and email_sync != cliente_existente.get('email'):
                        datos_a_actualizar['email'] = email_sync
                    
                    tel_sync = limpiar_texto(str(row.get(col_telefono, "")))
                    if tel_sync and tel_sync != cliente_existente.get('telefono'):
                        datos_a_actualizar['telefono'] = tel_sync
                    
                    # Solo hace UPDATE si hay algún cambio real
                    if datos_a_actualizar:
                        conn.table("clientes").update(datos_a_actualizar).eq("cliente_id", c_id).execute()
                        actualizados += 1
                else:
                    # CLIENTE NUEVO
                    email_sync = limpiar_texto(str(row.get(col_email, "")))
                    tel_sync = limpiar_texto(str(row.get(col_telefono, "")))
                    
                    conn.table("clientes").insert({
                        'nombre': nombre_sync, 
                        'email': email_sync, 
                        'telefono': tel_sync, 
                        'status': estado_sync if estado_sync else 'ACTIVA'
                    }).execute()
                    nuevos += 1
                
                procesados += 1

        # Limpiar caché de datos para reflejar los cambios en Streamlit
        st.cache_data.clear()

        # Mensaje principal de éxito
        st.success(f"🎉 Sincronización completada. Total procesados: **{procesados}** | Nuevos: **{nuevos}** | Actualizados: **{actualizados}**")
        
        # --- DESGLOSE DE ESTADOS ---
        # Consultamos los estados de todos los clientes en la BD para armar el conteo
        res_estados = conn.table("clientes").select("status").execute()
        if res_estados.data:
            df_estados = pd.DataFrame(res_estados.data)
            conteo_estados = df_estados['status'].value_counts()

            st.markdown("#### 📊 Desglose total de clientes por estado en la Base de Datos:")
            
            # Mostramos métricas dinámicas en columnas
            cols = st.columns(len(conteo_estados))
            for i, (estado, cantidad) in enumerate(conteo_estados.items()):
                with cols[i]:
                    st.metric(label=f"Estado: {estado}", value=f"{cantidad} clientes")

    except Exception as e:
        st.error(f"Error crítico durante la sincronización con la base de datos: {e}")

# --- INTERFAZ PRINCIPAL DE LA VISTA ---
def mostrar_herramientas():
    st.title("🛠️ Herramientas Administrativas")
    
    with st.container(border=True):
        st.markdown("### 🔄 Sincronización con Google Sheets")
        st.info("💡 **Lógica de Sincronización:** Se actualizarán los datos y estados respetando exactamente lo que indique la columna **Estado cliente** de la planilla. RUT, dirección y datos limpios se mantienen intactos.")
        
        if st.button("🚀 Iniciar Sincronización de Clientes", type="primary", use_container_width=True):
            sync_google_sheets()
