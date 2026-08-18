import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

@st.cache_data(ttl=30)
def cargar_notas_db():
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        # Cargamos las notas que no han sido completadas
        res = conn.table("pizarra_recordatorios").select("*").eq("completada", False).order("fecha_limite", desc=False).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        log_error("vista_pizarra", "cargar_notas_db", e, email_usuario)
        return pd.DataFrame()

def guardar_nota_db(titulo, contenido, fecha_limite):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    datos = {
        "titulo": limpiar_texto_para_busqueda(titulo),
        "contenido": contenido.strip() if contenido else "",
        "fecha_limite": fecha_limite.strftime("%Y-%m-%d"),
        "completada": False
    }
    try:
        conn.table("pizarra_recordatorios").insert(datos).execute()
        st.cache_data.clear()
        return True, ""
    except Exception as e:
        log_error("vista_pizarra", "guardar_nota_db", e, email_usuario)
        return False, str(e)

def actualizar_nota_db(nota_id, titulo, contenido, fecha_limite):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    datos = {
        "titulo": limpiar_texto_para_busqueda(titulo),
        "contenido": contenido.strip() if contenido else "",
        "fecha_limite": fecha_limite.strftime("%Y-%m-%d")
    }
    try:
        conn.table("pizarra_recordatorios").update(datos).eq("nota_id", idx_a_editar).execute() # El idx_a_editar se pasa como nota_id
        conn.table("pizarra_recordatorios").update(datos).eq("nota_id", nota_id).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        log_error("vista_pizarra", "actualizar_nota_db", e, email_usuario)
        return False

def completar_nota_db(nota_id):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        conn.table("pizarra_recordatorios").update({"completada": True}).eq("nota_id", nota_id).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        log_error("vista_pizarra", "completar_nota_db", e, email_usuario)
        return False

def eliminar_nota_db(nota_id):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        conn.table("pizarra_recordatorios").delete().eq("nota_id", nota_id).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        log_error("vista_pizarra", "eliminar_nota_db", e, email_usuario)
        return False

def mostrar_pizarra():
    st.title("📌 Pizarra de Recordatorios")
    st.markdown("---")

    df_notas = cargar_notas_db()
    hoy = datetime.now().date()

    # --- CONTROL DE ALERTAS DE ALTA INTENSIDAD (MOLESTAR) ---
    notas_vencidas = []
    if not df_notas.empty:
        df_notas['fecha_dt'] = pd.to_datetime(df_notas['fecha_limite']).dt.date
        notas_vencidas = df_notas[df_notas['fecha_dt'] < hoy].copy()

    if len(notas_vencidas) > 0:
        st.markdown(
            f"""
            <div style="background-color:#ffebee; border:2px solid #f44336; padding:15px; border-radius:8px; margin-bottom:25px; text-align:center;">
                <h3 style="color:#c62828; margin:0;">⚠️ ¡ATENCIÓN IVONNE! Tienes {len(notas_vencidas)} recordatorios vencidos ⚠️</h3>
                <p style="color:#b71c1c; margin:5px 0 0 0; font-weight:bold; font-size:15px;">
                    ¡Deja de postergar tus tareas! Revisa los Post-its rojos y complétalos hoy mismo.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # --- SECCIÓN SUPERIOR DE CREACIÓN (Ubicada en la pantalla principal) ---
    with st.expander("➕ CLAVAR NUEVO POST-IT (CREAR NOTA)", expanded=False):
        with st.container(border=True):
            n_titulo = st.text_input("¿Qué tienes que hacer?:", placeholder="Ej: Comprar papel glossy", key="new_note_title")
            n_contenido = st.text_area("Detalles o notas adicionales:", placeholder="Ej: Comprar de 180g...", key="new_note_content")
            n_fecha = st.date_input("¿Para cuándo es?:", value=datetime.now(), key="new_note_date")
            
            st.write("")
            if st.button("📌 Clavar Nota en la Pizarra", type="primary", use_container_width=True):
                if not n_titulo:
                    st.error("Por favor, ingresa el título del recordatorio.")
                else:
                    ok, err = guardar_nota_db(n_titulo, n_contenido, n_fecha)
                    if ok:
                        st.success("✅ ¡Nota clavada con éxito!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error: {err}")

    st.markdown("### 📋 Tus Post-its Activos")

    # --- TABLERO PRINCIPAL DE POST-ITS (SIN ANIDAR COLUMNAS) ---
    if df_notas.empty:
        st.info("🎉 ¡Pizarra limpia! No tienes recordatorios pendientes por hacer.")
    else:
        # Usamos columnas a nivel raíz (máximo 3 por fila en PC, adaptativo en móviles)
        grid_cols = st.columns(3)
        
        for index, row in df_notas.iterrows():
            col_target = grid_cols[index % 3]
            n_id = row['nota_id']
            fecha_lim = row['fecha_dt']
            titulo_nota = row['titulo']
            contenido_nota = row['contenido']
            
            # Definir color del Post-it según urgencia
            if fecha_lim < hoy:
                bg_color = "#ffcdd2"
                border_color = "#e53935"
                text_color = "#b71c1c"
                badge = "⏰ ¡VENCIDO!"
            elif fecha_lim == hoy:
                bg_color = "#ffe0b2"
                border_color = "#fb8c00"
                text_color = "#e65100"
                badge = "🔥 ¡PARA HOY!"
            else:
                bg_color = "#fff9c4"
                border_color = "#fdd835"
                text_color = "#f57f17"
                badge = f"📅 {fecha_lim.strftime('%d/%m/%Y')}"

            # --- PREPARACIÓN DE ENLACES EXTERNOS ---
            # 1. Google Calendar URL
            f_cal_str = fecha_lim.strftime("%Y%m%d")
            g_cal_url = (
                f"https://www.google.com/calendar/render?action=TEMPLATE"
                f"&text={urllib.parse.quote(titulo_nota)}"
                f"&dates={f_cal_str}/{f_cal_str}"
                f"&details={urllib.parse.quote(contenido_nota)}"
                f"&sf=true&output=xml"
            )
            
            # 2. WhatsApp Auto-Recordatorio (Número de la dueña de los secrets)
            dueña_tel = st.secrets.get("catalogo_publico", {}).get("whatsapp_numero", "56963531241")
            msg_wa = f"📌 RECORDATORIO ALBA: {titulo_nota} - {contenido_nota} (Fecha Límite: {fecha_lim.strftime('%d/%m/%Y')})"
            wa_url = f"https://api.whatsapp.com/send?phone={dueña_tel}&text={urllib.parse.quote(msg_wa)}"

            with col_target:
                st.markdown(
                    f"""
                    <div style="background-color:{bg_color}; border-left:8px solid {border_color}; padding:15px; border-radius:5px; margin-bottom:10px; min-height:165px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
                        <span style="background-color:{border_color}; color:white; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:bold;">{badge}</span>
                        <h4 style="color:{text_color}; margin:10px 0 5px 0; font-size:17px;">{titulo_nota}</h4>
                        <p style="color:#424242; font-size:13px; margin:0 0 10px 0;">{contenido_nota}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                # --- MENÚ DE CONTROL ÚNICO ---
                with st.popover("⚙️ Acciones / Control", use_container_width=True):
                    # 1. Marcar como completada
                    if st.button("✅ Marcar como Hecho", key=f"btn_done_{n_id}", use_container_width=True, type="primary"):
                        if completar_nota_db(n_id):
                            st.toast("✅ ¡Completado!", icon="👍")
                            time.sleep(1)
                            st.rerun()

                    st.markdown("---")
                    st.markdown("**🔗 Sincronizaciones**")
                    # 2. Google Calendar
                    st.markdown(f'<a href="{g_cal_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#4285F4; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer; font-size:13px; font-weight:bold; margin-bottom:8px;">📅 Google Calendar</button></a>', unsafe_allow_html=True)
                    # 3. WhatsApp
                    st.markdown(f'<a href="{wa_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#25D366; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer; font-size:13px; font-weight:bold; margin-bottom:8px;">💬 WhatsApp Dueña</button></a>', unsafe_allow_html=True)
                    
                    st.markdown("---")
                    st.markdown("**✏️ Edición e Historial**")
                    # 4. Formulario de Edición en Expander
                    with st.expander("✏️ Editar contenido"):
                        e_titulo = st.text_input("Título:", value=titulo_nota, key=f"edit_tit_{n_id}")
                        e_content = st.text_area("Detalles:", value=contenido_nota, key=f"edit_cont_{n_id}")
                        e_fecha = st.date_input("Fecha límite:", value=fecha_lim, key=f"edit_date_{n_id}")
                        if st.button("💾 Guardar cambios", key=f"btn_save_edit_{n_id}", use_container_width=True):
                            if actualizar_nota_db(n_id, e_titulo, e_content, e_fecha):
                                st.success("Guardado con éxito.")
                                time.sleep(1)
                                st.rerun()
                                
                    # 5. Eliminar nota permanentemente
                    if st.button("🗑️ Eliminar Nota", key=f"btn_del_{n_id}", use_container_width=True, type="secondary"):
                        if eliminar_nota_db(n_id):
                            st.toast("Nota eliminada.")
                            time.sleep(1)
                            st.rerun()