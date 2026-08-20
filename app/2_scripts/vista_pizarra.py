import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import urllib.parse
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

def calcular_siguiente_fecha(fecha_limite_str, recurrencia, hoy):
    """Calcula matemáticamente la próxima fecha del calendario cruzando años de forma segura."""
    try:
        f_lim = datetime.strptime(fecha_limite_str, "%Y-%m-%d").date()
    except:
        return hoy
        
    if recurrencia == "Semanal":
        next_date = f_lim
        while next_date <= hoy:
            next_date += timedelta(days=7)
        return next_date
    elif recurrencia == "Mensual":
        next_date = f_lim
        while next_date <= hoy:
            year = next_date.year
            month = next_date.month + 1
            if month == 13:
                month = 1
                year += 1
            try:
                next_date = date(year, month, f_lim.day)
            except ValueError:
                # Si cae un día fuera de rango (ej. 31), se topa al último día del mes
                next_month_first = date(year, month, 1) + timedelta(days=32)
                next_date = date(next_month_first.year, next_month_first.month, 1) - timedelta(days=1)
        return next_date
    return None

@st.cache_data(ttl=30)
def cargar_notas_db():
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        hoy = datetime.now().date()
        
        # --- 1. TAREA RECURRENTE AUTOMÁTICA DE FACTURAS (SEMANA EN CURSO) ---
        # Calcula el miércoles de la semana en curso (incluso si ya pasó)
        miercoles_esta_semana = hoy - timedelta(days=(hoy.weekday() - 2))
        proximo_miercoles_str = miercoles_esta_semana.strftime("%Y-%m-%d")
        
        res_exist = (conn.table("pizarra_recordatorios")
            .select("nota_id")
            .eq("titulo", "HACER FACTURAS DE LA SEMANA")
            .eq("fecha_limite", proximo_miercoles_str).execute())
            
        if not res_exist.data:
            datos_fac = {
                "titulo": "HACER FACTURAS DE LA SEMANA",
                "contenido": "Tarea recurrente semanal para la facturación de la librería. [Recurrencia: Semanal]",
                "fecha_limite": proximo_miercoles_str,
                "completada": False
            }
            conn.table("pizarra_recordatorios").insert(datos_fac).execute()

        # --- 2. LÓGICA INTELIGENTE DE AUTO-CLONACIÓN CON PASE DE ESTAFETA (CONCILIADO) ---
        res_completadas = (conn.table("pizarra_recordatorios")
            .select("nota_id, titulo, contenido, fecha_limite")
            .eq("completada", True).execute())
            
        if res_completadas.data:
            for nota in res_completadas.data:
                cont_str = str(nota.get('contenido', ''))
                recurrencia = "Semanal" if "[Recurrencia: Semanal]" in cont_str else ("Mensual" if "[Recurrencia: Mensual]" in cont_str else None)
                
                if recurrencia:
                    prox_fecha = calcular_siguiente_fecha(nota['fecha_limite'], recurrencia, hoy)
                    if prox_fecha:
                        prox_fecha_str = prox_fecha.strftime("%Y-%m-%d")
                        res_active_exist = (conn.table("pizarra_recordatorios")
                            .select("nota_id")
                            .eq("titulo", nota['titulo'])
                            .eq("fecha_limite", prox_fecha_str).execute())
                            
                        if not res_active_exist.data:
                            nueva_copia = {
                                "titulo": nota['titulo'],
                                "contenido": nota['contenido'],
                                "fecha_limite": prox_fecha_str,
                                "completada": False
                            }
                            conn.table("pizarra_recordatorios").insert(nueva_copia).execute()
                            
                        nuevo_contenido_viejo = cont_str.replace(f"[Recurrencia: {recurrencia}]", "[Recurrencia: Procesada]")
                        conn.table("pizarra_recordatorios").update({
                            "contenido": nuevo_contenido_viejo
                        }).eq("nota_id", int(nota['nota_id'])).execute()

        # --- 3. CARGA DE POST-ITS ACTIVOS (PAGINADO CON BYPASS DE 1000) ---
        all_notes = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table("pizarra_recordatorios")
                .select("*")
                .eq("completada", False)
                .order("fecha_limite", desc=False)
                .range(start, end).execute())
            if res.data:
                all_notes.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_notes) if all_notes else pd.DataFrame()
    except Exception as e:
        log_error("vista_pizarra", "cargar_notas_db", e, email_usuario)
        return pd.DataFrame()

def guardar_nota_db(titulo, contenido, fecha_limite, recurrencia="Única vez"):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    
    contenido_final = contenido.strip() if contenido else ""
    if recurrencia != "Única vez":
        contenido_final += f" [Recurrencia: {recurrencia}]"
        
    datos = {
        "titulo": limpiar_texto_para_busqueda(titulo),
        "contenido": contenido_final,
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
        conn.table("pizarra_recordatorios").update(datos).eq("nota_id", int(nota_id)).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        log_error("vista_pizarra", "actualizar_nota_db", e, email_usuario)
        return False

def completar_nota_db(nota_id):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        conn.table("pizarra_recordatorios").update({"completada": True}).eq("nota_id", int(nota_id)).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        log_error("vista_pizarra", "completar_nota_db", e, email_usuario)
        return False

def eliminar_nota_db(nota_id):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        conn.table("pizarra_recordatorios").delete().eq("nota_id", int(nota_id)).execute()
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

    if 'pizarra_limit_view' not in st.session_state:
        st.session_state.pizarra_limit_view = 3

    # ================= BANNER DE PRODUCTIVIDAD (HÁMSTER) =================
    col_ham1, col_ham2 = st.columns([1, 2.5])
    
    if not df_notas.empty:
        with col_ham1:
            st.image("https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster%20vigilando.jpg", width=180)
        with col_ham2:
            st.markdown(
                """
                <div style="background-color:#ffebee; border:3px solid #f44336; padding:20px; border-radius:10px; display:flex; flex-direction:column; justify-content:center; height:100%;">
                    <h3 style="color:#c62828; margin:0; font-size:24px;">🐹👁️ EL HÁMSTER TE VIGILA...</h3>
                    <p style="color:#b71c1c; font-size:18px; font-weight:bold; margin:8px 0 0 0; line-height: 1.4;">
                        IVONNE, TIENES TAREAS PENDIENTES POR HACER, PONTE A TRABAJAR LUEGO PODRAS DORMIR Y TOMAR.
                    </p>
                </div>
                """, 
                unsafe_allow_html=True
            )
    else:
        with col_ham1:
            st.image("https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamstertrabajando.jpg", width=180)
        with col_ham2:
            st.markdown(
                """
                <div style="background-color:#e8f5e9; border:3px solid #4caf50; padding:20px; border-radius:10px; display:flex; flex-direction:column; justify-content:center; height:100%;">
                    <h3 style="color:#2e7d32; margin:0; font-size:24px;">🐹🍻 ¡HAZAÑA COMPLETADA!</h3>
                    <p style="color:#1b5e20; font-size:18px; font-weight:bold; margin:8px 0 0 0; line-height: 1.4;">
                        ¡Pizarra limpia! Ivonne, ya terminaste tu trabajo del día. ¡El hámster te da permiso para ir a dormir, tomar un copete y descansar bien merecido! 🎉🍹
                    </p>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
    st.markdown("---")

    # --- CONTROL AUXILIAR DE NOTAS VENCIDAS ---
    notas_vencidas = []
    if not df_notas.empty:
        df_notas['fecha_dt'] = pd.to_datetime(df_notas['fecha_limite']).dt.date
        notas_vencidas = df_notas[df_notas['fecha_dt'] < hoy].copy()

        if len(notas_vencidas) > 0:
            df_notas_vencidas = df_notas[df_notas['fecha_dt'] < hoy].copy()
            df_notas_vencidas['retraso'] = df_notas_vencidas['fecha_dt'].apply(lambda x: (hoy - x).days)
            peor_retraso = df_notas_vencidas['retraso'].max()
            
            if peor_retraso > 14:
                drama_msg = f"Hola Ivonne... Veo que ignoras esta tarea desde hace {peor_retraso} días. Está bien, supongo que el papel glossy no era tan importante... El hámster se siente muy decepcionado de ti. 🐹💔"
            else:
                drama_msg = "Ivonne, la flojera te está ganando. Tienes cosas pendientes que debías hacer AYER. ¡Muévete antes de que el hámster se enoje de verdad! 🐹"

            st.markdown(
                f"""
                <div style="background-color:#ffebee; border:2px dashed #ef5350; padding:15px; border-radius:8px; margin-bottom:20px; text-align:center; animation: parpadeo 1.5s infinite;">
                    <h3 style="color:#c62828; margin:0; font-size:20px;">🚨 ¡PÁNICO EN LA PIZARRA! Tienes {len(notas_vencidas)} tareas vencidas 🚨</h3>
                    <p style="color:#b71c1c; margin:5px 0 0 0; font-weight:bold; font-size:14px;">
                        {drama_msg}
                    </p>
                </div>
                <style>
                    @keyframes parpadeo {{
                        0% {{ opacity: 1.0; border-color: #ef5350; }}
                        50% {{ opacity: 0.5; border-color: transparent; }}
                        100% {{ opacity: 1.0; border-color: #ef5350; }}
                    }}
                </style>
                """, 
                unsafe_allow_html=True
            )

    # --- SECCIÓN SUPERIOR DE CREACIÓN ---
    with st.expander("➕ CLAVAR NUEVO POST-IT (CREAR NOTA)", expanded=False):
        with st.container(border=True):
            n_titulo = st.text_input("¿Qué tienes que hacer?:", placeholder="Ej: Comprar papel glossy", key="new_note_title")
            n_contenido = st.text_area("Detalles o notas adicionales:", placeholder="Ej: Comprar de 180g...", key="new_note_content")
            
            c_p1, c_p2 = st.columns(2)
            n_fecha = c_p1.date_input("¿Para cuándo es?:", value=datetime.now(), key="new_note_date")
            
            n_recurrencia = c_p2.selectbox(
                "⚙️ Frecuencia de Repetición:",
                options=["Única vez", "Semanal", "Mensual"],
                index=0,
                help="Elige si deseas que la tarea se autoregenere automáticamente al completarse."
            )
            
            st.write("")
            if st.button("📌 Clavar Nota en la Pizarra", type="primary", use_container_width=True):
                if not n_titulo:
                    st.error("Por favor, ingresa el título del recordatorio.")
                else:
                    ok, err = guardar_nota_db(n_titulo, n_contenido, n_fecha, n_recurrencia)
                    if ok:
                        st.success("✅ ¡Nota clavada con éxito!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error: {err}")

    st.markdown("### 📋 Tus Post-its Activos")

    # --- TABLERO PRINCIPAL DE POST-ITS (CON PAGINACIÓN DE 3 EN 3) ---
    if df_notas.empty:
        st.info("🎉 ¡Pizarra limpia! No tienes recordatorios pendientes por hacer.")
    else:
        total_notas = len(df_notas)
        limite_actual = st.session_state.pizarra_limit_view
        df_paginado = df_notas.head(limite_actual)

        st.caption(f"Mostrando **{len(df_paginado)}** post-its activos de un total de **{total_notas}** pendientes.")

        grid_cols = st.columns(3)
        
        for index, row in df_paginado.reset_index(drop=True).iterrows():
            col_target = grid_cols[index % 3]
            n_id = row['nota_id']
            fecha_lim = row['fecha_dt']
            titulo_nota = row['titulo']
            contenido_raw = str(row['contenido'])
            
            recurrencia_nota = "Semanal" if "[Recurrencia: Semanal]" in contenido_raw else ("Mensual" if "[Recurrencia: Mensual]" in contenido_raw else None)
            contenido_limpio = contenido_raw.replace("[Recurrencia: Semanal]", "").replace("[Recurrencia: Mensual]", "").strip()
            
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
            f_cal_str = fecha_lim.strftime("%Y%m%d")
            g_cal_url = (
                f"https://www.google.com/calendar/render?action=TEMPLATE"
                f"&text={urllib.parse.quote(titulo_nota)}"
                f"&dates={f_cal_str}/{f_cal_str}"
                f"&details={urllib.parse.quote(contenido_limpio)}"
                f"&sf=true&output=xml"
            )
            
            dueña_tel = st.secrets.get("catalogo_publico", {}).get("whatsapp_numero", "56963531241")
            msg_wa = f"📌 RECORDATORIO ALBA: {titulo_nota} - {contenido_limpio} (Fecha Límite: {fecha_lim.strftime('%d/%m/%Y')})"
            wa_url = f"https://api.whatsapp.com/send?phone={dueña_tel}&text={urllib.parse.quote(msg_wa)}"

            with col_target:
                # 🌟 ULTRA BLINDAJE: Concatenamos como string plano de una sola línea sin saltos de línea ni tabuladores
                html_postit = (
                    f'<div style="background-color:{bg_color}; border-left:8px solid {border_color}; padding:15px; border-radius:5px; margin-bottom:10px; min-height:165px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">'
                    f'<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 5px;">'
                    f'<span style="background-color:{border_color}; color:white; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:bold;">{badge}</span>'
                )
                if recurrencia_nota:
                    html_postit += f'<span style="background-color:#7e57c2; color:white; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:bold;">🔁 {recurrencia_nota.upper()}</span>'
                
                html_postit += (
                    f'</div>'
                    f'<h4 style="color:{text_color}; margin:10px 0 5px 0; font-size:17px;">{titulo_nota}</h4>'
                    f'<p style="color:#424242; font-size:13px; margin:0 0 10px 0;">{contenido_limpio}</p>'
                    f'</div>'
                )
                
                # Renderizamos con st.html nativo, inmune a errores de sangría de Markdown
                st.html(html_postit)
                
                # --- MENÚ DE CONTROL ÚNICO ---
                with st.popover("⚙️ Acciones / Control", use_container_width=True):
                    if st.button("✅ Marcar como Hecho", key=f"btn_done_{n_id}", use_container_width=True, type="primary"):
                        if completar_nota_db(n_id):
                            st.toast("✅ ¡Completado!", icon="👍")
                            time.sleep(1)
                            st.rerun()

                    st.markdown("---")
                    st.markdown("**🔗 Sincronizaciones**")
                    st.markdown(f'<a href="{g_cal_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#4285F4; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer; font-size:13px; font-weight:bold; margin-bottom:8px;">📅 Google Calendar</button></a>', unsafe_allow_html=True)
                    st.markdown(f'<a href="{wa_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; background-color:#25D366; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer; font-size:13px; font-weight:bold; margin-bottom:8px;">💬 WhatsApp Dueña</button></a>', unsafe_allow_html=True)
                    
                    st.markdown("---")
                    st.markdown("**✏️ Edición e Historial**")
                    with st.expander("✏️ Editar contenido"):
                        e_titulo = st.text_input("Título:", value=titulo_nota, key=f"edit_tit_{n_id}")
                        e_content = st.text_area("Detalles:", value=contenido_limpio, key=f"edit_cont_{n_id}")
                        e_fecha = st.date_input("Fecha límite:", value=fecha_lim, key=f"edit_date_{n_id}")
                        if st.button("💾 Guardar cambios", key=f"btn_save_edit_{n_id}", use_container_width=True):
                            contenido_actualizado = e_content.strip()
                            if recurrencia_nota:
                                contenido_actualizado += f" [Recurrencia: {recurrencia_nota}]"
                                
                            if actualizar_nota_db(n_id, e_titulo, contenido_actualizado, e_fecha):
                                st.success("Guardado con éxito.")
                                time.sleep(1)
                                st.rerun()
                                
                    if st.button("🗑️ Eliminar Nota", key=f"btn_del_{n_id}", use_container_width=True, type="secondary"):
                        if eliminar_nota_db(n_id):
                            st.toast("Nota eliminada.")
                            time.sleep(1)
                            st.rerun()

        # Botón dinámico de paginación progresiva (+3)
        if total_notas > limite_actual:
            st.write("")
            col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
            with col_pag2:
                remanente = total_notas - limite_actual
                if st.button(f"🔄 Ver más recordatorios (+3) — Quedan {remanente} por ver", use_container_width=True, key="btn_load_more_pizarra"):
                    st.session_state.pizarra_limit_view += 3
                    st.rerun()

if __name__ == '__main__':
    mostrar_pizarra()