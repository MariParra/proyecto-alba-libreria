import streamlit as st
import pandas as pd
from datetime import datetime, date
from utilidades import get_db_connection

def mover_tarea(tarea_id, nuevo_estado):
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").update({"estado": nuevo_estado}).eq("id", int(tarea_id)).execute()
        st.rerun()
    except Exception as e:
        st.error(f"Error al mover tarea: {e}")

def eliminar_tarea(tarea_id):
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").delete().eq("id", int(tarea_id)).execute()
        st.rerun()
    except Exception as e:
        st.error(f"Error al eliminar tarea: {e}")

def crear_tarea(titulo, descripcion, tipo, prioridad, f_ini, f_fin, dep_id):
    if not titulo:
        st.warning("⚠️ El título es obligatorio.")
        return
    
    conn = get_db_connection()
    try:
        nueva_tarea = {
            "titulo": titulo,
            "descripcion": descripcion,
            "tipo": tipo,
            "prioridad": prioridad,
            "estado": "POR HACER",
            "fecha_inicio": f_ini.isoformat() if f_ini else None,
            "fecha_fin": f_fin.isoformat() if f_fin else None,
            "depende_de_id": int(dep_id) if dep_id else None,
            "fecha_creacion": datetime.now().isoformat()
        }
        conn.table("tareas_internas").insert(nueva_tarea).execute()
        st.toast("✅ Tarea creada con éxito")
        st.rerun()
    except Exception as e:
        st.error(f"Error al crear tarea: {e}")

def obtener_color_prioridad(prioridad):
    if prioridad == "Alta 🔴": return "#ffebee", "#c62828"
    if prioridad == "Media 🟡": return "#fff8e1", "#f57f17"
    return "#e8f5e9", "#2e7d32"

def obtener_color_tipo(tipo):
    colores = {
        "Administración 📋": ("#e3f2fd", "#1565c0"),
        "Desarrollo 💻": ("#f3e5f5", "#6a1b9a"),
        "Logística 📦": ("#e0f7fa", "#00838f"),
        "Marketing 📱": ("#fce4ec", "#ad1457")
    }
    return colores.get(tipo, ("#f5f5f5", "#424242"))

def dibujar_tarjeta(tarea, df_todas):
    """Renderiza la tarjeta Kanban con fechas y dependencias."""
    bg_prio, txt_prio = obtener_color_prioridad(tarea.get('prioridad', 'Baja 🟢'))
    bg_tipo, txt_tipo = obtener_color_tipo(tarea.get('tipo', 'Administración 📋'))
    
    # Evaluar dependencia
    bloqueada = False
    mensaje_bloqueo = ""
    dep_id = tarea.get('depende_de_id')
    
    if pd.notna(dep_id):
        # Buscar la tarea de la que depende
        tarea_padre = df_todas[df_todas['id'] == int(dep_id)]
        if not tarea_padre.empty:
            padre = tarea_padre.iloc[0]
            if padre['estado'] != 'COMPLETADO':
                bloqueada = True
                mensaje_bloqueo = f"🔒 Bloqueada por: {padre['titulo']}"
    
    with st.container(border=True):
        # 1. Etiquetas Superiores
        st.markdown(f"""
        <div style='display: flex; gap: 5px; margin-bottom: 8px;'>
            <span style='background-color: {bg_prio}; color: {txt_prio}; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold;'>{tarea.get('prioridad', '')}</span>
            <span style='background-color: {bg_tipo}; color: {txt_tipo}; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold;'>{tarea.get('tipo', '')}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 2. Título y Fechas
        st.markdown(f"**{tarea['titulo']}**")
        
        fechas_str = []
        if pd.notna(tarea.get('fecha_inicio')): fechas_str.append(f"🏁 {tarea['fecha_inicio']}")
        if pd.notna(tarea.get('fecha_fin')): fechas_str.append(f"🎯 {tarea['fecha_fin']}")
        if fechas_str:
            st.caption(" | ".join(fechas_str))
            
        if tarea.get('descripcion'):
            st.caption(tarea['descripcion'])
            
        # 3. Aviso de Dependencia
        if bloqueada:
            st.error(mensaje_bloqueo, icon="⏳")
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 4. Botones de Acción
        if tarea['estado'] == 'POR HACER':
            # Si está bloqueada, el botón se desactiva visualmente
            if st.button("➡️ Iniciar", key=f"ini_{tarea['id']}", use_container_width=True, disabled=bloqueada, help="Termina la tarea previa para habilitar" if bloqueada else ""):
                mover_tarea(tarea['id'], "EN PROGRESO")
                
        elif tarea['estado'] == 'EN PROGRESO':
            c1, c2 = st.columns(2)
            if c1.button("⬅️ Pausar", key=f"pau_{tarea['id']}", use_container_width=True):
                mover_tarea(tarea['id'], "POR HACER")
            if c2.button("✅ Listo", key=f"fin_{tarea['id']}", type="primary", use_container_width=True):
                mover_tarea(tarea['id'], "COMPLETADO")
                
        elif tarea['estado'] == 'COMPLETADO':
            if st.button("🗑️ Eliminar", key=f"del_{tarea['id']}", type="secondary", use_container_width=True):
                eliminar_tarea(tarea['id'])

def mostrar_kanban():
    st.markdown("<h2 style='color: #4A4D7E;'>📋 Tablero de Proyectos y Tareas</h2>", unsafe_allow_html=True)
    
    conn = get_db_connection()
    
    # --- 1. CARGAR TAREAS EXISTENTES (Para el desplegable de dependencias) ---
    try:
        res = conn.table("tareas_internas").select("*").execute()
        df_tareas = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=['id', 'titulo', 'descripcion', 'tipo', 'prioridad', 'estado', 'fecha_inicio', 'fecha_fin', 'depende_de_id'])
    except Exception as e:
        st.error("Error al cargar la base de datos.")
        return

    # --- 2. FORMULARIO NUEVA TAREA ---
    with st.expander("➕ Crear Nueva Tarea", expanded=False):
        with st.form("form_kanban", clear_on_submit=True):
            st.markdown("##### Detalles Básicos")
            t_tit = st.text_input("Título de la Tarea*")
            t_desc = st.text_area("Descripción detallada (opcional)")
            
            c1, c2 = st.columns(2)
            t_tipo = c1.selectbox("Tipo", ["Administración 📋", "Desarrollo 💻", "Logística 📦", "Marketing 📱"])
            t_prio = c2.selectbox("Prioridad", ["Alta 🔴", "Media 🟡", "Baja 🟢"], index=1)
            
            st.markdown("##### Planificación y Dependencias")
            cf1, cf2, cf3 = st.columns(3)
            t_ini = cf1.date_input("Fecha Inicio", value=None)
            t_fin = cf2.date_input("Fecha Fin (Límite)", value=None)
            
            # Construir opciones de dependencia
            opciones_dep = {"Ninguna": None}
            if not df_tareas.empty:
                for _, row in df_tareas[df_tareas['estado'] != 'COMPLETADO'].iterrows():
                    opciones_dep[f"ID:{row['id']} - {row['titulo']}"] = row['id']
            
            t_dep_label = cf3.selectbox("Debe hacerse después de:", list(opciones_dep.keys()))
            t_dep_id = opciones_dep[t_dep_label]
            
            if st.form_submit_button("Añadir al Tablero", type="primary", use_container_width=True):
                crear_tarea(t_tit, t_desc, t_tipo, t_prio, t_ini, t_fin, t_dep_id)

    st.markdown("---")
    
    # --- 3. DIBUJAR TABLERO KANBAN ---
    col_todo, col_progreso, col_done = st.columns(3)
    
    with col_todo:
        st.markdown("### 📌 Por Hacer")
        st.markdown("<div style='height: 4px; background-color: #ffb74d; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_tareas.empty:
            for _, tarea in df_tareas[df_tareas['estado'] == 'POR HACER'].iterrows():
                dibujar_tarjeta(tarea, df_tareas)

    with col_progreso:
        st.markdown("### ⏳ En Progreso")
        st.markdown("<div style='height: 4px; background-color: #4fc3f7; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_tareas.empty:
            for _, tarea in df_tareas[df_tareas['estado'] == 'EN PROGRESO'].iterrows():
                dibujar_tarjeta(tarea, df_tareas)

    with col_done:
        st.markdown("### ✅ Completado")
        st.markdown("<div style='height: 4px; background-color: #81c784; margin-bottom: 10px; border-radius: 2px;'></div>", unsafe_allow_html=True)
        if not df_tareas.empty:
            for _, tarea in df_tareas[df_tareas['estado'] == 'COMPLETADO'].iterrows():
                dibujar_tarjeta(tarea, df_tareas)