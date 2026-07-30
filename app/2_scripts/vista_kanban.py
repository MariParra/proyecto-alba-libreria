import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from utilidades import get_db_connection
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 📧 1. MOTOR INTELIGENTE DE CORREOS (RUTEO POR TIPO) ---
def obtener_correo_destinatario(tipo):
    """Enruta el correo según el tipo de tarea."""
    if "email" not in st.secrets: return None
    
    if "Logística" in tipo: return st.secrets["email"].get("dest_logistica")
    elif "Desarrollo" in tipo: return st.secrets["email"].get("dest_desarrollo")
    elif "Marketing" in tipo: return st.secrets["email"].get("dest_marketing")
    else: return st.secrets["email"].get("dest_admin") # Por defecto, a Administración

def enviar_correo(titulo, tipo, prioridad, fecha_comprometida, es_alerta_vencimiento=False):
    """Construye y envía el correo usando la contraseña de aplicación."""
    try:
        if "email" not in st.secrets: return False
            
        remitente = st.secrets["email"]["remitente"]
        password = st.secrets["email"]["password"]
        destinatario = obtener_correo_destinatario(tipo)
        
        if not destinatario: return False # Si no hay destinatario para ese rol, no hace nada
        
        msg = MIMEMultipart()
        msg['From'] = remitente
        msg['To'] = destinatario
        
        fecha_str = fecha_comprometida.strftime('%d-%m-%Y') if pd.notna(fecha_comprometida) else 'Sin fecha límite'
        
        if es_alerta_vencimiento:
            msg['Subject'] = f"⏳ URGENTE: Tarea por vencer [{tipo}] - {titulo}"
            cuerpo = f"""
            Hola,
            
            La siguiente tarea asignada a tu área está muy pronto a vencer (Due Date: {fecha_str}):
            
            📌 Tarea: {titulo}
            🚨 Prioridad: {prioridad}
            🏷️ Tipo: {tipo}
            
            Por favor, revisa el Tablero Kanban y actualiza su estado.
            """
        else:
            msg['Subject'] = f"🆕 NUEVA TAREA [{tipo}] - {titulo}"
            cuerpo = f"""
            Hola,
            
            Se ha registrado y asignado una nueva tarea para tu área en el sistema:
            
            📌 Título: {titulo}
            🏷️ Tipo: {tipo}
            🚨 Prioridad: {prioridad}
            📅 Fecha Comprometida (Due Date): {fecha_str}
            
            Por favor, revisa el Tablero Kanban en la aplicación de Alba Librería.
            """
            
        msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario.split(','), msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error enviando correo: {e}")
        return False

# --- ⏱️ 2. ESCÁNER DE VENCIMIENTOS AUTOMÁTICO (DUE DATES) ---
def verificar_alertas_vencimiento(df_tareas):
    """Revisa si hay tareas que vencen en 2 días o menos y manda un correo."""
    if df_tareas.empty or 'alerta_enviada' not in df_tareas.columns: return
    
    conn = get_db_connection()
    hoy = date.today()
    dias_aviso = 2 # Avisar cuando falten 2 días o menos
    
    # Filtramos tareas no completadas, que tengan fecha límite, y que no se haya enviado alerta
    pendientes = df_tareas[(df_tareas['estado'] != 'COMPLETADO') & (df_tareas['fecha_fin'].notna()) & (df_tareas['alerta_enviada'] == False)]
    
    for _, tarea in pendientes.iterrows():
        f_fin = pd.to_datetime(tarea['fecha_fin']).date()
        dias_restantes = (f_fin - hoy).days
        
        if dias_restantes <= dias_aviso:
            # Enviamos el correo de urgencia ruteado
            enviado = enviar_correo(tarea['titulo'], tarea['tipo'], tarea['prioridad'], f_fin, es_alerta_vencimiento=True)
            if enviado:
                # Si se envió, marcamos en BD para no volver a hacer spam
                try:
                    conn.table("tareas_internas").update({"alerta_enviada": True}).eq("id", int(tarea['id'])).execute()
                    st.toast(f"📧 Alerta de vencimiento enviada para: {tarea['titulo']}")
                except: pass

# --- FUNCIONES DE BASE DE DATOS KANBAN ---
def mover_tarea(tarea_id, nuevo_estado):
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").update({"estado": nuevo_estado}).eq("id", int(tarea_id)).execute()
        st.rerun()
    except Exception as e: st.error(f"Error al mover tarea: {e}")

def eliminar_tarea(tarea_id):
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").delete().eq("id", int(tarea_id)).execute()
        st.rerun()
    except Exception as e: st.error(f"Error al eliminar tarea: {e}")

def crear_tarea(titulo, descripcion, tipo, prioridad, f_ini, f_fin, dep_id):
    if not titulo:
        st.warning("⚠️ El título es obligatorio.")
        return
    conn = get_db_connection()
    try:
        id_dependencia = int(dep_id) if dep_id is not None else None
        nueva_tarea = {
            "titulo": titulo, "descripcion": descripcion, "tipo": tipo, "prioridad": prioridad,
            "estado": "POR HACER", "alerta_enviada": False,
            "fecha_inicio": f_ini.isoformat() if f_ini else None,
            "fecha_fin": f_fin.isoformat() if f_fin else None,
            "depende_de_id": id_dependencia,
            "fecha_creacion": datetime.now().isoformat()
        }
        conn.table("tareas_internas").insert(nueva_tarea).execute()
        
        # Correo a la persona específica según el "Tipo" de tarea
        enviar_correo(titulo, tipo, prioridad, f_fin, es_alerta_vencimiento=False)
        st.toast("✅ Tarea creada y notificada")
        st.rerun()
    except Exception as e: st.error(f"Error al crear tarea: {e}")

def obtener_color_prioridad(prioridad):
    if prioridad == "Alta 🔴": return "#ffebee", "#c62828"
    if prioridad == "Media 🟡": return "#fff8e1", "#f57f17"
    return "#e8f5e9", "#2e7d32"

def obtener_color_tipo(tipo):
    colores = {"Administración 📋": ("#e3f2fd", "#1565c0"), "Desarrollo 💻": ("#f3e5f5", "#6a1b9a"), "Logística 📦": ("#e0f7fa", "#00838f"), "Marketing 📱": ("#fce4ec", "#ad1457")}
    return colores.get(tipo, ("#f5f5f5", "#424242"))

def dibujar_tarjeta(tarea, df_todas):
    bg_prio, txt_prio = obtener_color_prioridad(tarea.get('prioridad', 'Baja 🟢'))
    bg_tipo, txt_tipo = obtener_color_tipo(tarea.get('tipo', 'Administración 📋'))
    
    bloqueada, mensaje_bloqueo = False, ""
    if pd.notna(tarea.get('depende_de_id')):
        tarea_padre = df_todas[df_todas['id'] == int(tarea.get('depende_de_id'))]
        if not tarea_padre.empty and tarea_padre.iloc[0]['estado'] != 'COMPLETADO':
            bloqueada, mensaje_bloqueo = True, f"🔒 Bloqueada por: {tarea_padre.iloc[0]['titulo']}"
    
    with st.container(border=True):
        st.markdown(f"<div style='display: flex; gap: 5px; margin-bottom: 8px;'><span style='background-color: {bg_prio}; color: {txt_prio}; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold;'>{tarea.get('prioridad', '')}</span><span style='background-color: {bg_tipo}; color: {txt_tipo}; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold;'>{tarea.get('tipo', '')}</span></div>", unsafe_allow_html=True)
        st.markdown(f"**{tarea['titulo']}**")
        
        fechas_str = []
        if pd.notna(tarea.get('fecha_inicio')): fechas_str.append(f"🏁 Inicio: {tarea['fecha_inicio']}")
        if pd.notna(tarea.get('fecha_fin')): fechas_str.append(f"🚨 Due Date: {tarea['fecha_fin']}")
        if fechas_str: st.caption(" | ".join(fechas_str))
        if tarea.get('descripcion'): st.caption(tarea['descripcion'])
            
        if bloqueada: st.error(mensaje_bloqueo, icon="⏳")
        st.markdown("<br>", unsafe_allow_html=True)
        
        if tarea['estado'] == 'POR HACER':
            if st.button("➡️ Iniciar", key=f"ini_{tarea['id']}", use_container_width=True, disabled=bloqueada): mover_tarea(tarea['id'], "EN PROGRESO")
        elif tarea['estado'] == 'EN PROGRESO':
            c1, c2 = st.columns(2)
            if c1.button("⬅️ Pausar", key=f"pau_{tarea['id']}", use_container_width=True): mover_tarea(tarea['id'], "POR HACER")
            if c2.button("✅ Listo", key=f"fin_{tarea['id']}", type="primary", use_container_width=True): mover_tarea(tarea['id'], "COMPLETADO")
        elif tarea['estado'] == 'COMPLETADO':
            if st.button("🗑️ Eliminar", key=f"del_{tarea['id']}", type="secondary", use_container_width=True): eliminar_tarea(tarea['id'])

def mostrar_kanban():
    st.markdown("<h2 style='color: #4A4D7E;'>📋 Tablero de Proyectos y Tareas</h2>", unsafe_allow_html=True)
    
    conn = get_db_connection()
    try:
        res = conn.table("tareas_internas").select("*").execute()
        df_tareas = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=['id', 'titulo', 'descripcion', 'tipo', 'prioridad', 'estado', 'fecha_inicio', 'fecha_fin', 'depende_de_id', 'alerta_enviada'])
    except Exception as e:
        st.error("Error al cargar la base de datos."); return

    # --- ESCANEO SILENCIOSO DE VENCIMIENTOS ---
    verificar_alertas_vencimiento(df_tareas)

    # --- ALERTAS VISUALES EN PANTALLA ---
    if not df_tareas.empty:
        hoy = date.today()
        pendientes = df_tareas[(df_tareas['estado'] != 'COMPLETADO') & (df_tareas['fecha_fin'].notna())]
        vencidas = [t['titulo'] for _, t in pendientes.iterrows() if pd.to_datetime(t['fecha_fin']).date() < hoy]
        vencen_hoy = [t['titulo'] for _, t in pendientes.iterrows() if pd.to_datetime(t['fecha_fin']).date() == hoy]
        
        if vencidas: st.error(f"🚨 **¡ATENCIÓN!** Tienes {len(vencidas)} tarea(s) **VENCIDA(S)**: {', '.join(vencidas)}")
        if vencen_hoy: st.warning(f"⚠️ Tienes {len(vencen_hoy)} tarea(s) que vencen **HOY**: {', '.join(vencen_hoy)}")

    # --- FORMULARIO NUEVA TAREA ---
    with st.expander("➕ Crear Nueva Tarea", expanded=False):
        with st.form("form_kanban", clear_on_submit=True):
            st.markdown("##### Detalles Básicos")
            t_tit = st.text_input("Título de la Tarea*")
            t_desc = st.text_area("Descripción detallada (opcional)")
            
            c1, c2 = st.columns(2)
            t_tipo = c1.selectbox("Tipo de Tarea (Define a quién notifica)", ["Administración 📋", "Desarrollo 💻", "Logística 📦", "Marketing 📱"])
            t_prio = c2.selectbox("Prioridad", ["Alta 🔴", "Media 🟡", "Baja 🟢"], index=1)
            
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
                crear_tarea(t_tit, t_desc, t_tipo, t_prio, t_ini, t_fin, t_dep_id)

    # --- DIBUJAR TABLERO KANBAN ---
    st.markdown("---")
    col_todo, col_progreso, col_done = st.columns(3)
    
    with col_todo:
        st.markdown("### 📌 Por Hacer")
        st.markdown("<div style='height: 4px; background-color: #ffb74d; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_tareas.empty:
            for _, t in df_tareas[df_tareas['estado'] == 'POR HACER'].iterrows(): dibujar_tarjeta(t, df_tareas)

    with col_progreso:
        st.markdown("### ⏳ En Progreso")
        st.markdown("<div style='height: 4px; background-color: #4fc3f7; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_tareas.empty:
            for _, t in df_tareas[df_tareas['estado'] == 'EN PROGRESO'].iterrows(): dibujar_tarjeta(t, df_tareas)

    with col_done:
        st.markdown("### ✅ Completado")
        st.markdown("<div style='height: 4px; background-color: #81c784; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_tareas.empty:
            for _, t in df_tareas[df_tareas['estado'] == 'COMPLETADO'].iterrows(): dibujar_tarjeta(t, df_tareas)