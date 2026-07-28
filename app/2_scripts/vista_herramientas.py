import streamlit as st
import gspread
import pandas as pd
import json
import base64
import time
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIÓN: RESUMEN DE CLIENTES ---
def obtener_resumen_clientes():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("status").execute()
        df = pd.DataFrame(res.data)
        if df.empty: return 0, 0, 0
        total, activos, inactivos = len(df), len(df[df['status'] == 'ACTIVA']), len(df[df['status'] == 'NO ACTIVA'])
        return total, activos, inactivos
    except:
        return 0, 0, 0

def sync_google_sheets():
    """
    Sincronización Total (Clientes + Suscripciones).
    Adaptada para leer formularios con preguntas muy largas como encabezados.
    """
    exito = False
    try:
        # 1. Leemos la clave desde la estructura correcta
        b64_str = st.secrets["gcp_service_account"]["creds_json_b64"]
        
        # 2. Decodificamos
        json_str = base64.b64decode(b64_str).decode('utf-8')
        creds_dict = json.loads(json_str)

        with st.spinner("Conectando con Google Sheets..."):
            gc = gspread.service_account_from_dict(creds_dict)
            spreadsheet = gc.open("INSCRIPCIONES CAJA MENSUAL") 
            worksheet = spreadsheet.worksheet("formulario")
            df = pd.DataFrame(worksheet.get_all_records())
        
        st.success("✅ ¡Conexión exitosa con Google Sheets!")
        exito = True 
        
    except Exception as e:
        st.error(f"Error de conexión con Google: {e}")
        return False 

    conn = get_db_connection()
    try:
        with st.spinner("Sincronizando Clientes y Suscripciones..."):
            
            # --- MAPEO INTELIGENTE DE COLUMNAS (SOPORTA PREGUNTAS LARGAS) ---
            col_nombre, col_estado, col_telefono, col_email = None, None, None, None
            col_fecha, col_generos, col_metodo = None, None, None
            
            for c in df.columns:
                cl = str(c).lower()
                if 'nombre' in cl and 'datos de envío' not in cl: col_nombre = c
                elif 'estado' in cl: col_estado = c
                elif 'teléfono' in cl or 'telefono' in cl: col_telefono = c
                elif 'correo' in cl or 'email' in cl: col_email = c
                elif 'fecha de pago' in cl: col_fecha = c
                elif 'género' in cl or 'genero' in cl: col_generos = c
                elif 'entrega' in cl: col_metodo = c

            # Si por alguna razón no encuentra la de nombre, asume que es la segunda (después de Marca Temporal)
            if not col_nombre and len(df.columns) > 2: col_nombre = df.columns[2]
            
            procesados, clientes_nuevos, clientes_actualizados = 0, 0, 0
            
            for index, row in df.iterrows():
                # Extracción súper segura con validación de existencia de columnas
                nombre_raw = row[col_nombre] if col_nombre in df.columns else ""
                nombre_sync = limpiar_texto(str(nombre_raw))
                if not nombre_sync or nombre_sync == "SIN INFORMACION" or nombre_sync == "NAN": continue
                
                estado_raw = row[col_estado] if col_estado in df.columns else "ACTIVA"
                estado_sync = str(estado_raw).strip().upper()
                if not estado_sync or estado_sync in ["", "NONE", "NAN"]: estado_sync = "ACTIVA"
                if estado_sync == "INACTIVO": estado_sync = "NO ACTIVA"

                tel_raw = row[col_telefono] if col_telefono in df.columns else ""
                tel_sync = limpiar_texto(str(tel_raw))

                email_raw = row[col_email] if col_email and col_email in df.columns else ""
                email_sync = limpiar_texto(str(email_raw))

                fecha_raw = row[col_fecha] if col_fecha in df.columns else ""
                fecha_sync = str(fecha_raw).strip()

                generos_raw = row[col_generos] if col_generos in df.columns else ""
                generos_sync = str(generos_raw).strip()

                metodo_raw = row[col_metodo] if col_metodo in df.columns else ""
                metodo_sync = str(metodo_raw).strip()
                
                # Búsqueda e inserción
                res_nombre = conn.table("clientes").select("*").eq("nombre", nombre_sync).execute()
                res_email = conn.table("clientes").select("*").eq("email", email_sync).execute() if email_sync else None
                
                cliente_existente = None
                if res_nombre.data: cliente_existente = res_nombre.data[0]
                elif res_email and res_email.data: cliente_existente = res_email.data[0]
                
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
                
                # Actualización de Suscripciones (Manejo de strings seguros)
                res_sub = conn.table("suscripciones").select("suscripcion_id").eq("cliente_id", c_id).execute()
                datos_sub = {
                    "fecha_pago": fecha_sync if fecha_sync != "nan" else "", 
                    "metodo_entrega": metodo_sync if metodo_sync != "nan" else "", 
                    "generos_preferencia": generos_sync if generos_sync != "nan" else ""
                }
                
                if res_sub.data:
                    conn.table("suscripciones").update(datos_sub).eq("cliente_id", c_id).execute()
                else:
                    datos_sub.update({"cliente_id": c_id, "valor_suscripcion": 0.0})
                    conn.table("suscripciones").insert(datos_sub).execute()
                procesados += 1
                
        st.success(f"🎉 Sincronización Finalizada. Filas procesadas: {procesados} | Clientes nuevos: {clientes_nuevos} | Clientes actualizados: {clientes_actualizados}")
        st.cache_data.clear()
        return True
        
    except Exception as e:
        st.error(f"Error crítico durante la sincronización a la BD: {e}")
        return False

def mostrar_herramientas():
    st.title("🛠️ Herramientas Administrativas")
    total_cli, activos_cli, inactivos_cli = obtener_resumen_clientes()
    st.markdown("### 👥 Resumen del Directorio")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Clientes Registrados", total_cli)
    c2.metric("🟢 Activos", activos_cli)
    c3.metric("🔴 No Activos", inactivos_cli)
    st.markdown("---")
    
    with st.container(border=True):
        st.markdown("### 🔄 Sincronización Total con Google Sheets")
        st.info("💡 **Lógica 2.0:** Actualiza datos de contacto y preferencias de suscripción leyendo tu formulario dinámico.")
        
        if st.button("🚀 Iniciar Sincronización", type="primary", use_container_width=True):
            exito = sync_google_sheets()
            if exito:
                mensaje_cuenta_regresiva = st.empty()
                for segundos in range(3, 0, -1):
                    mensaje_cuenta_regresiva.info(f"🔄 Actualizando métricas en {segundos} segundos...")
                    time.sleep(10)
                st.rerun()
    
    st.markdown("---")
                
