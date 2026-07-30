import streamlit as st
import pandas as pd
from utilidades import get_db_connection
from datetime import datetime

def mover_tarea(tarea_id, nuevo_estado):
    """Actualiza el estado de la tarea en la base de datos."""
    conn = get_db_connection()
    try:
        conn.table("tareas_internas").update({"estado": nuevo_estado}).eq("id", int(tarea_id)).execute()
        st.rerun() # Recargamos para ver el cambio de columna
    except Exception as e:
        st.error(f"Error al mover tarea: {e}")

def crear_tarea(titulo, descripcion):
    """Inserta una nueva tarea en la columna POR HACER."""
    if not titulo:
        st.warning("El título es obligatorio.")
        return
    conn = get_db_connection()
    try:
        nueva_tarea = {
            "titulo": titulo,
            "descripcion": descripcion,
            "estado": "POR HACER",
            "fecha_creacion": datetime.now().isoformat()
        }
        conn.table("tareas_internas").insert(nueva_tarea).execute()
        st.rerun()
    except Exception as e:
        st.error(f"Error al crear tarea: {e}")

def mostrar_kanban():
    st.markdown("<h2 style='color: #4A4D7E;'>📋 Tablero Kanban Interno</h2>", unsafe_allow_html=True)
    st.caption("Organiza el desarrollo y la administración de Alba Librería.")
    
    conn = get_db_connection()
    
    # 1. Formulario para Nueva Tarea (Arriba, plegable)
    with st.expander("➕ Crear Nueva Tarea", expanded=False):
        with st.form("form_nueva_tarea", clear_on_submit=True):
            t_tit = st.text_input("Título de la tarea:")
            t_desc = st.text_area("Descripción o detalles:")
            submit = st.form_submit_button("Añadir al Tablero", type="primary")
            if submit:
                crear_tarea(t_tit, t_desc)
                
    st.markdown("---")
    
    # 2. Obtenemos todas las tareas de Supabase
    try:
        res = conn.table("tareas_internas").select("*").execute()
        df_tareas = pd.DataFrame(res.data)
    except Exception as e:
        st.error("Error al cargar tareas.")
        return

    # Si no hay tareas, creamos un DataFrame vacío con las columnas necesarias
    if df_tareas.empty:
        df_tareas = pd.DataFrame(columns=['id', 'titulo', 'descripcion', 'estado'])

    # 3. Dibujamos las 3 Columnas del Kanban
    col_todo, col_progreso, col_done = st.columns(3)
    
    # --- COLUMNA 1: POR HACER ---
    with col_todo:
        st.markdown("### 📌 Por Hacer")
        st.markdown("<div style='height: 5px; background-color: #ff9800; margin-bottom: 15px;'></div>", unsafe_allow_html=True)
        tareas_todo = df_tareas[df_tareas['estado'] == 'POR HACER']
        
        for _, tarea in tareas_todo.iterrows():
            with st.container(border=True):
                st.markdown(f"**{tarea['titulo']}**")
                st.caption(tarea['descripcion'])
                # Botón para mover a la siguiente fase
                if st.button("➡️ Iniciar", key=f"btn_ini_{tarea['id']}", use_container_width=True):
                    mover_tarea(tarea['id'], "EN PROGRESO")

    # --- COLUMNA 2: EN PROGRESO ---
    with col_progreso:
        st.markdown("### ⏳ En Progreso")
        st.markdown("<div style='height: 5px; background-color: #2196f3; margin-bottom: 15px;'></div>", unsafe_allow_html=True)
        tareas_progreso = df_tareas[df_tareas['estado'] == 'EN PROGRESO']
        
        for _, tarea in tareas_progreso.iterrows():
            with st.container(border=True):
                st.markdown(f"**{tarea['titulo']}**")
                st.caption(tarea['descripcion'])
                c1, c2 = st.columns(2)
                # Opciones para retroceder o avanzar
                if c1.button("⬅️ Pausar", key=f"btn_pau_{tarea['id']}", use_container_width=True):
                    mover_tarea(tarea['id'], "POR HACER")
                if c2.button("✅ Listo", key=f"btn_fin_{tarea['id']}", type="primary", use_container_width=True):
                    mover_tarea(tarea['id'], "COMPLETADO")

    # --- COLUMNA 3: COMPLETADO ---
    with col_done:
        st.markdown("### ✅ Completado")
        st.markdown("<div style='height: 5px; background-color: #4caf50; margin-bottom: 15px;'></div>", unsafe_allow_html=True)
        tareas_done = df_tareas[df_tareas['estado'] == 'COMPLETADO']
        
        for _, tarea in tareas_done.iterrows():
            with st.container(border=True):
                st.markdown(f"~~{tarea['titulo']}~~") # Tachado visual
                if st.button("🗑️ Archivar/Borrar", key=f"btn_del_{tarea['id']}", use_container_width=True):
                    # Aquí podrías llamar a una función para eliminar de la DB
                    conn.table("tareas_internas").delete().eq("id", int(tarea['id'])).execute()
                    st.rerun()