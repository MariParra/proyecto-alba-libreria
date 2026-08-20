import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from utilidades import get_db_connection, log_error
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 📧 1. MOTOR INTELIGENTE DE CORREOS ---
def obtener_correo_destinatario(tipo):
    if "email" not in st.secrets: return None
    if "Logística" in tipo: return st.secrets["email"].get("dest_logistica")
    elif "Desarrollo" in tipo: return st.secrets["email"].get("dest_desarrollo")
    elif "Marketing" in tipo: return st.secrets["email"].get("dest_marketing")
    else: return st.secrets["email"].get("dest_admin")

def enviar_correo(titulo, tipo, prioridad, fecha_comprometida, es_alerta_vencimiento=False):
    try:
        if "email" not in st.secrets: return False
        remitente = st.secrets["email"]["remitente"]
        password = st.secrets["email"]["password"]
        destinatario = obtener_correo_destinatario(tipo)
        if not destinatario: return False
        
        msg = MIMEMultipart()
        msg['From'] = remitente
        msg['To'] = destinatario
        
        fecha_str = fecha_comprometida.strftime('%d-%m-%Y') if pd.notna(fecha_comprometida) else 'Sin fecha límite'
        
        if es_alerta_vencimiento:
            msg['Subject'] = f"⏳ URGENTE: Tarea por vencer [{tipo}] - {titulo}"
            cuerpo = f"Hola,\n\nLa siguiente tarea asignada a tu área está muy pronto a vencer (Due Date: {fecha_str}):\n\n📌 Tarea: {titulo}\n🚨 Prioridad: {prioridad}\n🏷️ Tipo: {tipo}\n\nPor favor, revisa el Tablero Kanban y actualiza su estado."
        else:
            msg['Subject'] = f"🆕 NUEVA TAREA [{tipo}] - {titulo}"
            cuerpo = f"Hola,\n\nSe ha registrado y asignado una nueva tarea para tu área:\n\n📌 Título: {titulo}\n🏷️ Tipo: {tipo}\n🚨 Prioridad: {prioridad}\n📅 Fecha Comprometida (Due Date): {fecha_str}\n\nRevisa el Kanban para más detalles."
            
        msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario.split(','), msg.as_string())
        server.quit()
        return True
    except Exception as e:
        error_detalle = (
            f"Fallo crítico en el motor de correo (SMTP). Tarea: '{titulo}'. "
            f"Destinatario intentado: '{destinatario}'. Detalle: {e}"
        )
        
        log_error(
            vista="Sistema de Notificaciones",
            funcion="enviar_correo",
            error=error_detalle,
            email_usuario="Sistema"
        )
        print(f"Error enviando correo: {e}")
        return False

# --- ⏱️ 2. ESCÁNER DE VENCIMIENTOS AUTOMÁTICO ---
def verificar_alertas_vencimiento(df_tareas):
    if df_tareas.empty or 'alerta_enviada' not in df_tareas.columns: return
    conn = get_db_connection()
    hoy = date.today()
    dias_aviso = 2 
    
    pendientes = df_tareas[(df_tareas['estado'] != 'COMPLETADO') & (df_tareas['fecha_fin'].notna()) & (df_tareas['alerta_enviada'] == False)]
    for _, tarea in pendientes.iterrows():
        f_fin = pd.to_datetime(tarea['fecha_fin']).date()
        if (f_fin - hoy).days <= dias_aviso:
            enviado = enviar_correo(tarea['titulo'], tarea['tipo'], tarea['prioridad'], f_fin, es_alerta_vencimiento=True)
            if enviado:
                try:
                    conn.table("tareas_internas").update({"alerta_enviada": True}).eq("id", int(tarea['id'])).execute()
                    st.toast(f"📧 Alerta de vencimiento enviada para: {tarea['titulo']}")
                except Exception as e:
                    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                    
                    error_detalle = (
                        f"¡Crítico! Se ENVIÓ correo para la tarea '{tarea['titulo']}' (ID: {tarea['id']}), "
                        f"pero FALLÓ al marcar 'alerta_enviada' como True. La alerta podría repetirse. Detalle: {e}"
                    )
                    
                    log_error(
                        vista="vista_kanban",
                        funcion="verificar_alertas_vencimiento",
                        error=error_detalle,
                        email_usuario=email_usuario
                    )
                    st.warning(f"Alerta enviada para '{tarea['titulo']}', pero no se pudo marcar como registrada. ¡Podría enviarse de nuevo!")

# --- FUNCIONES DE BASE DE DATOS KANBAN ---
def parsear_fecha(fecha_str):
    if pd.isna(fecha_str) or not fecha_str: return None
    try: return pd.to_datetime(fecha_str).date()
    except: return None

def mover_tarea(tarea_id, nuevo_estado):
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").update({"estado": nuevo_estado}).eq("id", int(tarea_id)).execute()
        st.rerun()
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo al mover la tarea ID {tarea_id} al estado '{nuevo_estado}'. Detalle: {e}"
        )
        log_error(
            vista="vista_kanban",
            funcion="mover_tarea",
            error=error_detalle,
            email_usuario=email_usuario
        )
        st.error(f"Error al mover tarea: {e}")

def eliminar_tarea(tarea_id):
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").delete().eq("id", int(tarea_id)).execute()
        st.rerun()
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = f"Fallo al ELIMINAR la tarea ID {tarea_id}. Detalle: {e}"
        log_error(
            vista="vista_kanban",
            funcion="eliminar_tarea",
            error=error_detalle,
            email_usuario=email_usuario
        )
        st.error(f"Error al eliminar tarea: {e}")

def crear_tarea(titulo, descripcion, tipo, prioridad, dificultad, estado, f_ini, f_fin, dep_id):
    if not titulo:
        st.warning("⚠️ El título es obligatorio.")
        return
    conn = get_db_connection()
    try:
        id_dependencia = int(dep_id) if dep_id is not None else None
        nueva_tarea = {
            "titulo": titulo, "descripcion": descripcion, "tipo": tipo, 
            "prioridad": prioridad, "dificultad": dificultad,
            "estado": estado, "alerta_enviada": False,
            "fecha_inicio": f_ini.isoformat() if f_ini else None,
            "fecha_fin": f_fin.isoformat() if f_fin else None,
            "depende_de_id": id_dependencia,
            "fecha_creacion": datetime.now().isoformat()
        }
        conn.table("tareas_internas").insert(nueva_tarea).execute()
        enviar_correo(titulo, tipo, prioridad, f_fin, es_alerta_vencimiento=False)
        st.toast("✅ Tarea creada y notificada")
        st.rerun()
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo al crear la tarea '{titulo}'. Datos intentados: {str(nueva_tarea)}. Detalle: {e}"
        )
        log_error(
            vista="vista_kanban",
            funcion="crear_tarea",
            error=error_detalle,
            email_usuario=email_usuario
        )
        st.error(f"Error al crear tarea: {e}")

def editar_tarea(tarea_id, titulo, tipo, prioridad, dificultad, estado, f_ini, f_fin):
    if not titulo: return
    conn = get_db_connection()
    try:
        datos_update = {
            "titulo": titulo, "tipo": tipo, "prioridad": prioridad,
            "dificultad": dificultad, "estado": estado,
            "fecha_inicio": f_ini.isoformat() if f_ini else None,
            "fecha_fin": f_fin.isoformat() if f_fin else None
        }
        conn.table("tareas_internas").update(datos_update).eq("id", int(tarea_id)).execute()
        st.toast("✅ Tarea modificada con éxito")
        st.rerun()
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo al editar la tarea ID {tarea_id}. Datos intentados: {str(datos_update)}. Detalle: {e}"
        )
        log_error(
            vista="vista_kanban",
            funcion="editar_tarea",
            error=error_detalle,
            email_usuario=email_usuario
        )
        st.error(f"Error al editar: {e}")

# --- 💬 FUNCIONES DE COMENTARIOS ---
def agregar_comentario(tarea_id, autor, tipo, texto):
    if not texto or not autor:
        st.warning("⚠️ El autor y el comentario son obligatorios.")
        return
    conn = get_db_connection()
    try:
        datos = {
            "tarea_id": int(tarea_id),
            "autor": autor,
            "tipo": tipo,
            "comentario": texto,
            "fecha": datetime.now().isoformat()
        }
        conn.table("tareas_comentarios").insert(datos).execute()
        st.toast("💬 Comentario guardado con éxito")
        st.rerun()
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo al guardar comentario en la tarea ID {tarea_id}. Autor: {autor}, Tipo: {tipo}. Detalle: {e}"
        )
        log_error(
            vista="vista_kanban",
            funcion="agregar_comentario",
            error=error_detalle,
            email_usuario=email_usuario
        )
        st.error(f"Error al guardar comentario: {e}")

# --- UTILIDADES VISUALES ---
def obtener_color_prioridad(prioridad):
    if "Alta" in str(prioridad): return "#ffebee", "#c62828"
    if "Media" in str(prioridad): return "#fff8e1", "#f57f17"
    return "#e8f5e9", "#2e7d32"

def obtener_color_dificultad(dificultad):
    if "Alta" in str(dificultad): return "#f3e5f5", "#7b1fa2" 
    if "Media" in str(dificultad): return "#e3f2fd", "#1976d2" 
    return "#e0f2f1", "#00796b"

def obtener_color_tipo(tipo):
    colores = {"Administración 📋": ("#e3f2fd", "#1565c0"), "Desarrollo 💻": ("#f3e5f5", "#6a1b9a"), "Logística 📦": ("#e0f7fa", "#00838f"), "Marketing 📱": ("#fce4ec", "#ad1457")}
    return colores.get(tipo, ("#f5f5f5", "#424242"))

def dibujar_tarjeta(tarea, df_todas, df_comentarios):
    bg_prio, txt_prio = obtener_color_prioridad(tarea.get('prioridad', 'Baja 🟢'))
    bg_tipo, txt_tipo = obtener_color_tipo(tarea.get('tipo', 'Administración 📋'))
    bg_dif, txt_dif = obtener_color_dificultad(tarea.get('dificultad', 'Media 🔸'))
    
    bloqueada, mensaje_bloqueo = False, ""
    if pd.notna(tarea.get('depende_de_id')):
        tarea_padre = df_todas[df_todas['id'] == int(tarea.get('depende_de_id'))]
        if not tarea_padre.empty and tarea_padre.iloc[0]['estado'] != 'COMPLETADO':
            bloqueada, mensaje_bloqueo = True, f"🔒 Bloqueada por: {tarea_padre.iloc[0]['titulo']}"
    
    with st.container(border=True):
        st.markdown(f"""
        <div style='display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px;'>
            <span style='background-color: {bg_prio}; color: {txt_prio}; padding: 2px 8px; border-radius: 10px; font-size: 0.70em; font-weight: bold;'>Prio: {tarea.get('prioridad', '')}</span>
            <span style='background-color: {bg_dif}; color: {txt_dif}; padding: 2px 8px; border-radius: 10px; font-size: 0.70em; font-weight: bold;'>Dif: {tarea.get('dificultad', 'Media 🔸')}</span>
            <span style='background-color: {bg_tipo}; color: {txt_tipo}; padding: 2px 8px; border-radius: 10px; font-size: 0.70em; font-weight: bold;'>{tarea.get('tipo', '')}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"**{tarea['titulo']}**")
        
        fechas_str = []
        if pd.notna(tarea.get('fecha_inicio')): fechas_str.append(f"🏁 Inicio: {tarea['fecha_inicio']}")
        if pd.notna(tarea.get('fecha_fin')): fechas_str.append(f"🚨 Due Date: {tarea['fecha_fin']}")
        if fechas_str: st.caption(" | ".join(fechas_str))
        if tarea.get('descripcion'): st.caption(tarea['descripcion'])
            
        if bloqueada: st.error(mensaje_bloqueo, icon="⏳")
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Botones Rápidos de Estado
        if tarea['estado'] == 'POR HACER':
            if st.button("➡️ Iniciar", key=f"ini_{tarea['id']}", use_container_width=True, disabled=bloqueada): mover_tarea(tarea['id'], "EN PROGRESO")
        elif tarea['estado'] == 'EN PROGRESO':
            if st.button("✅ Listo", key=f"fin_{tarea['id']}", type="primary", use_container_width=True): mover_tarea(tarea['id'], "COMPLETADO")
            if st.button("⬅️ Pausar Tarea", key=f"pau_{tarea['id']}", use_container_width=True): mover_tarea(tarea['id'], "POR HACER")
            
        # --- 💬 SECCIÓN DE COMENTARIOS (JIRA STYLE) ---
        comentarios_tarea = df_comentarios[df_comentarios['tarea_id'] == tarea['id']].sort_values('fecha', ascending=False)
        num_coms = len(comentarios_tarea)
        
        with st.expander(f"💬 Comentarios y Actividad ({num_coms})", expanded=False):
            if not comentarios_tarea.empty:
                for _, com in comentarios_tarea.iterrows():
                    fecha_utc = pd.to_datetime(com['fecha'])
                    
                    if fecha_utc.tzinfo is None:
                        fecha_chile = fecha_utc.tz_localize('UTC').tz_convert('America/Santiago')
                    else:
                        fecha_chile = fecha_utc.tz_convert('America/Santiago')
                        
                    fecha_com = fecha_chile.strftime("%d/%m/%Y %H:%M")
                    color_borde = "#1976d2" if "Nota" in com['tipo'] else ("#c62828" if "Error" in com['tipo'] or "Bloqueo" in com['tipo'] else "#388e3c")
                    
                    st.markdown(f"""
                    <div style='background-color: #f8f9fa; padding: 10px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid {color_borde};'>
                        <small style='color: #555;'><b>👤 {com['autor']}</b> • 🕒 {fecha_com} • <i>{com['tipo']}</i></small><br>
                        <span style='font-size: 0.9em; color: #333;'>{com['comentario']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("Aún no hay comentarios en esta tarea.")
            
            st.markdown("---")
            with st.form(f"form_com_{tarea['id']}"):
                autor_com = st.text_input("Tu Nombre", placeholder="Ej: Mariana P.")
                tipo_com = st.selectbox("Tipo de Nota", ["Nota Informativa 📝", "Resolución de Error 🐛", "Avance 🚀", "Duda / Consulta ❓", "Bloqueo 🛑"])
                texto_com = st.text_area("Comentario", placeholder="Escribe tu actualización aquí...")
                if st.form_submit_button("Publicar Comentario", use_container_width=True):
                    agregar_comentario(tarea['id'], autor_com, tipo_com, texto_com)

        # --- ✏️ MENÚ DE EDICIÓN RÁPIDA ---
        with st.expander("✏️ Editar Detalles", expanded=False):
            with st.form(f"form_edit_{tarea['id']}"):
                e_tit = st.text_input("Título", value=tarea['titulo'])
                
                ops_tipo = ["Administración 📋", "Desarrollo 💻", "Logística 📦", "Marketing 📱"]
                idx_t = ops_tipo.index(tarea['tipo']) if tarea['tipo'] in ops_tipo else 0
                e_tipo = st.selectbox("Cambiar Tipo", ops_tipo, index=idx_t)
                
                ops_est = ["POR HACER", "EN PROGRESO", "COMPLETADO"]
                idx_est = ops_est.index(tarea['estado']) if tarea['estado'] in ops_est else 0
                e_estado = st.selectbox("Cambiar Estado", ops_est, index=idx_est)
                
                ops_prio = ["Alta 🔴", "Media 🟡", "Baja 🟢"]
                idx_p = ops_prio.index(tarea['prioridad']) if tarea.get('prioridad') in ops_prio else 1
                e_prio = st.selectbox("Prioridad", ops_prio, index=idx_p)
                
                ops_dif = ["Alta 🔺", "Media 🔸", "Baja 🔹"]
                dificultad_actual = tarea.get('dificultad', 'Media 🔸')
                idx_d = ops_dif.index(dificultad_actual) if dificultad_actual in ops_dif else 1
                e_dif = st.selectbox("Dificultad", ops_dif, index=idx_d)
                
                e_ini = st.date_input("Nueva Fecha Inicio", value=parsear_fecha(tarea.get('fecha_inicio')))
                e_fin = st.date_input("Nuevo Due Date", value=parsear_fecha(tarea.get('fecha_fin')))
                
                if st.form_submit_button("💾 Guardar Cambios", use_container_width=True):
                    editar_tarea(tarea['id'], e_tit, e_tipo, e_prio, e_dif, e_estado, e_ini, e_fin)
                
            st.markdown("---")
            st.markdown("e_error 🔴 Zona de Peligro")
            confirmar_borrado = st.checkbox("Estoy segura de que quiero eliminar esta tarea permanentemente.", key=f"check_del_{tarea['id']}")
                
            if st.button("🗑️ Eliminar Tarea", type="primary", use_container_width=True, disabled=not confirmar_borrado, key=f"btn_del_{tarea['id']}"):
                eliminar_tarea(tarea['id'])

def mostrar_kanban():
    st.markdown("<h2 style='color: #4A4D7E;'>📋 Tablero de Proyectos y Tareas</h2>", unsafe_allow_html=True)
    
    # Inicialización de limitadores visuales progresivos (3 en 3 por columna)
    if 'kanban_todo_limit' not in st.session_state:
        st.session_state.kanban_todo_limit = 3
    if 'kanban_progress_limit' not in st.session_state:
        st.session_state.kanban_progress_limit = 3
    if 'kanban_done_limit' not in st.session_state:
        st.session_state.kanban_done_limit = 3

    conn = get_db_connection()
    try:
        # 🚀 BYPASS DE 1000 REGISTROS: Cargamos todas las tareas del Tablero Kanban
        all_tasks = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("tareas_internas").select("*").order("id").range(start, end).execute()
            if res.data:
                all_tasks.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        df_tareas = pd.DataFrame(all_tasks) if all_tasks else pd.DataFrame(columns=['id', 'titulo', 'descripcion', 'tipo', 'prioridad', 'dificultad', 'estado', 'fecha_inicio', 'fecha_fin', 'depende_de_id', 'alerta_enviada', 'fecha_creacion'])
        
        # 🚀 BYPASS DE 1000 REGISTROS: Cargamos todos los comentarios históricos en masa
        all_comments = []
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_com = conn.table("tareas_comentarios").select("*").order("id").range(start, end).execute()
            if res_com.data:
                all_comments.extend(res_com.data)
                if len(res_com.data) < chunk_size:
                    break
            else:
                break
                
        df_comentarios = pd.DataFrame(all_comments) if all_comments else pd.DataFrame(columns=['id', 'tarea_id', 'autor', 'tipo', 'comentario', 'fecha'])
    except Exception as e:
        st.error("Error al cargar la base de datos."); return

    verificar_alertas_vencimiento(df_tareas)

    if not df_tareas.empty:
        hoy = date.today()
        pendientes = df_tareas[(df_tareas['estado'] != 'COMPLETADO') & (df_tareas['fecha_fin'].notna())]
        vencidas = [t['titulo'] for _, t in pendientes.iterrows() if pd.to_datetime(t['fecha_fin']).date() < hoy]
        vencen_hoy = [t['titulo'] for _, t in pendientes.iterrows() if pd.to_datetime(t['fecha_fin']).date() == hoy]
        if vencidas: st.error(f"🚨 **¡ATENCIÓN!** Tienes {len(vencidas)} tarea(s) **VENCIDA(S)**: {', '.join(vencidas)}")
        if vencen_hoy: st.warning(f"⚠️ Tienes {len(vencen_hoy)} tarea(s) que vencen **HOY**: {', '.join(vencen_hoy)}")

    with st.expander("➕ Crear Nueva Tarea", expanded=False):
        with st.form("form_kanban", clear_on_submit=True):
            st.markdown("##### Detalles Básicos")
            t_tit = st.text_input("Título de la Tarea*")
            t_desc = st.text_area("Descripción detallada (opcional)")
            c1, c2, c3, c4 = st.columns(4)
            t_tipo = c1.selectbox("Tipo de Tarea", ["Administración 📋", "Desarrollo 💻", "Logística 📦", "Marketing 📱"])
            t_prio = c2.selectbox("Prioridad", ["Alta 🔴", "Media 🟡", "Baja 🟢"], index=1)
            t_dif = c3.selectbox("Dificultad", ["Alta 🔺", "Media 🔸", "Baja 🔹"], index=1)
            # 🌟 NUEVA CARACTERÍSTICA: Selección del estado inicial para el formulario de creación
            t_est = c4.selectbox("Estado Inicial", ["POR HACER", "EN PROGRESO", "COMPLETADO"], index=0)
            
            st.markdown("##### Planificación y Dependencias")
            cf1, cf2, cf3 = st.columns(3)
            t_ini = cf1.date_input("Fecha Inicio", value=None)
            t_fin = cf2.date_input("Due Date (Fecha Límite)", value=None)
            opciones_dep = {"Ninguna": None}
            if not df_tareas.empty:
                for _, row in df_tareas[df_tareas['estado'] != 'COMPLETADO'].iterrows():
                    opciones_dep[f"ID:{row['id']} - {row['titulo']}"] = row['id']
            t_dep_label = cf3.selectbox("Debe hacerse después de:", list(opciones_dep.keys()))
            t_dep_id = opciones_dep[t_dep_label]
            
            if st.form_submit_button("Añadir al Tablero y Notificar", type="primary", use_container_width=True):
                crear_tarea(t_tit, t_desc, t_tipo, t_prio, t_dif, t_est, t_ini, t_fin, t_dep_id)

    st.markdown("---")
    
    # --- VISTAS RÁPIDAS ---
    vista_actual = st.radio(
        "👁️ Selecciona tu Vista de Trabajo:", 
        ["🎯 Esta Semana", "📥 Backlog (Sin planificar)", "🌍 Ver Todo"], 
        horizontal=True, index=0
    )
    
    df_filtrado = df_tareas.copy()
    
    if not df_filtrado.empty:
        hoy = date.today()
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        
        df_filtrado['f_ini_dt'] = pd.to_datetime(df_filtrado['fecha_inicio'], errors='coerce').dt.date
        df_filtrado['f_fin_dt'] = pd.to_datetime(df_filtrado['fecha_fin'], errors='coerce').dt.date
        df_filtrado['f_crea_dt'] = pd.to_datetime(df_filtrado['fecha_creacion'], errors='coerce').dt.date
        
        if vista_actual == "🎯 Esta Semana":
            mask_prog = df_filtrado['estado'] == 'EN PROGRESO'
            mask_por_hacer = (df_filtrado['estado'] == 'POR HACER') & ((df_filtrado['f_ini_dt'] <= fin_semana) | (df_filtrado['f_fin_dt'] <= fin_semana))
            mask_completadas = (df_filtrado['estado'] == 'COMPLETADO') & ((df_filtrado['f_fin_dt'] >= inicio_semana) | (df_filtrado['f_ini_dt'] >= inicio_semana) | (df_filtrado['f_crea_dt'] >= inicio_semana))
            df_filtrado = df_filtrado[mask_prog | mask_por_hacer | mask_completadas]
            
        elif vista_actual == "📥 Backlog (Sin planificar)":
            mask_sin_fecha = df_filtrado['f_ini_dt'].isna() & df_filtrado['f_fin_dt'].isna()
            mask_futuras = (df_filtrado['f_ini_dt'] > fin_semana) | (df_filtrado['f_fin_dt'] > fin_semana)
            df_filtrado = df_filtrado[(df_filtrado['estado'] == 'POR HACER') & (mask_sin_fecha | mask_futuras)]

        with st.expander("🔍 Añadir Filtros Específicos (Buscar, Tipo, Prioridad, Dificultad)", expanded=False):
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            f_texto = col_f1.text_input("🔍 Título:")
            f_tipo = col_f2.multiselect("🏷️ Área / Tipo:", options=df_tareas['tipo'].unique().tolist())
            f_prio = col_f3.multiselect("🚨 Prioridad:", options=df_tareas['prioridad'].unique().tolist())
            f_dif = col_f4.multiselect("⚙️ Dificultad:", options=df_tareas['dificultad'].dropna().unique().tolist())

            if f_texto: df_filtrado = df_filtrado[df_filtrado['titulo'].str.contains(f_texto, case=False, na=False)]
            if f_tipo: df_filtrado = df_filtrado[df_filtrado['tipo'].isin(f_tipo)]
            if f_prio: df_filtrado = df_filtrado[df_filtrado['prioridad'].isin(f_prio)]
            if f_dif: df_filtrado = df_filtrado[df_filtrado['dificultad'].isin(f_dif)]

    # --- DIBUJAR TABLERO KANBAN CON RESULTADOS FINALES ---
    st.markdown("<br>", unsafe_allow_html=True)
    col_todo, col_progreso, col_done = st.columns(3)
    
    with col_todo:
        df_todo = df_filtrado[df_filtrado['estado'] == 'POR HACER'] if not df_filtrado.empty else pd.DataFrame()
        total_todo = len(df_todo)
        limite_todo = st.session_state.kanban_todo_limit
        df_todo_pag = df_todo.head(limite_todo) if not df_todo.empty else pd.DataFrame()

        st.markdown(f"### 📌 Por Hacer ({total_todo})")
        st.markdown("<div style='height: 4px; background-color: #ffb74d; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_todo_pag.empty:
            for _, t in df_todo_pag.iterrows(): 
                dibujar_tarjeta(t, df_tareas, df_comentarios)
                
        # Botón de carga progresiva
        if total_todo > limite_todo:
            remanente_todo = total_todo - limite_todo
            if st.button(f"🔄 Ver más pendientes (+3) — Quedan {remanente_todo} por ver", key="btn_more_todo", use_container_width=True):
                st.session_state.kanban_todo_limit += 3
                st.rerun()

    with col_progreso:
        df_prog = df_filtrado[df_filtrado['estado'] == 'EN PROGRESO'] if not df_filtrado.empty else pd.DataFrame()
        total_prog = len(df_prog)
        limite_prog = st.session_state.kanban_progress_limit
        df_prog_pag = df_prog.head(limite_prog) if not df_prog.empty else pd.DataFrame()

        st.markdown(f"### ⏳ En Progreso ({total_prog})")
        st.markdown("<div style='height: 4px; background-color: #4fc3f7; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_prog_pag.empty:
            for _, t in df_prog_pag.iterrows(): 
                dibujar_tarjeta(t, df_tareas, df_comentarios)

        # Botón de carga progresiva
        if total_prog > limite_prog:
            remanente_prog = total_prog - limite_prog
            if st.button(f"🔄 Ver más en progreso (+3) — Quedan {remanente_prog} por ver", key="btn_more_prog", use_container_width=True):
                st.session_state.kanban_progress_limit += 3
                st.rerun()

    with col_done:
        df_done = df_filtrado[df_filtrado['estado'] == 'COMPLETADO'] if not df_filtrado.empty else pd.DataFrame()
        total_done = len(df_done)
        limite_done = st.session_state.kanban_done_limit
        df_done_pag = df_done.head(limite_done) if not df_done.empty else pd.DataFrame()

        st.markdown(f"### ✅ Completado ({total_done})")
        st.markdown("<div style='height: 4px; background-color: #81c784; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_done_pag.empty:
            for _, t in df_done_pag.iterrows(): 
                dibujar_tarjeta(t, df_tareas, df_comentarios)

        # Botón de carga progresiva
        if total_done > limite_done:
            remanente_done = total_done - limite_done
            if st.button(f"🔄 Ver más completados (+3) — Quedan {remanente_done} por ver", key="btn_more_done", use_container_width=True):
                st.session_state.kanban_done_limit += 3
                st.rerun()

if __name__ == "__main__":
    mostrar_kanban()