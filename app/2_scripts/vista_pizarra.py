import streamlit as st
import pandas as pd
from datetime import datetime
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

@st.cache_data(ttl=60)
def cargar_notas_db():
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
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
        "contenido": limpiar_texto_para_busqueda(contenido) if contenido else "",
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
                    ¡Deja de postergar tus tareas! Revisa los Post-its rojos y complétalos ahora mismo.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Distribución en dos columnas: Entrada de notas (Izquierda) y Pizarra (Derecha)
    col_crear, col_board = st.columns([1, 2])

    with col_crear:
        st.markdown("### ➕ Clavar Nuevo Post-it")
        with st.container(border=True):
            n_titulo = st.text_input("¿Qué tienes que hacer?:", placeholder="Ej: Comprar papel glossy")
            n_contenido = st.text_area("Detalles o notas adicionales:", placeholder="Ej: Comprar de 180g en la tienda del centro...")
            n_fecha = st.date_input("¿Para cuándo es?:", value=datetime.now())
            
            st.write("")
            if st.button("📌 Clavar Nota", type="primary", use_container_width=True):
                if not n_titulo:
                    st.error("Por favor, ingresa el título del recordatorio.")
                else:
                    ok, err = guardar_nota_db(n_titulo, n_contenido, n_fecha)
                    if ok:
                        st.success("✅ ¡Nota clavada con éxito!")
                        st.balloons()
                        time.sleep(1.2)
                        st.rerun()
                    else:
                        st.error(f"Error al guardar: {err}")

    with col_board:
        st.markdown("### 📋 Tus Post-its Activos")
        if df_notas.empty:
            st.info("🎉 ¡Pizarra limpia! No tienes recordatorios pendientes por hacer.")
        else:
            # Renderizamos las notas en una grilla de columnas dinámica (2 post-its por fila)
            grid_cols = st.columns(2)
            
            for index, row in df_notas.iterrows():
                col_target = grid_cols[index % 2]
                n_id = row['nota_id']
                fecha_lim = row['fecha_dt']
                
                # Definir color del Post-it según urgencia
                if fecha_lim < hoy:
                    # VENCIDO (Rojo)
                    bg_color = "#ffcdd2"
                    border_color = "#e53935"
                    text_color = "#b71c1c"
                    badge = "⏰ ¡VENCIDO!"
                elif fecha_lim == hoy:
                    # HOY (Naranja)
                    bg_color = "#ffe0b2"
                    border_color = "#fb8c00"
                    text_color = "#e65100"
                    badge = "🔥 ¡PARA HOY!"
                else:
                    # FUTURO (Amarillo tradicional)
                    bg_color = "#fff9c4"
                    border_color = "#fdd835"
                    text_color = "#f57f17"
                    badge = f"📅 {fecha_lim.strftime('%d/%m/%Y')}"

                with col_target:
                    st.markdown(
                        f"""
                        <div style="background-color:{bg_color}; border-left:8px solid {border_color}; padding:15px; border-radius:5px; margin-bottom:15px; min-height:160px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
                            <span style="background-color:{border_color}; color:white; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:bold;">{badge}</span>
                            <h4 style="color:{text_color}; margin:10px 0 5px 0; font-size:18px;">{row['titulo']}</h4>
                            <p style="color:#424242; font-size:13px; margin:0 0 10px 0;">{row['contenido']}</p>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    # Botón para completar y archivar la nota
                    if st.button(f"🗑️ Listo / Quitar #{n_id}", key=f"btn_done_{n_id}", use_container_width=True):
                        if completar_nota_db(n_id):
                            st.toast("✅ ¡Recordatorio archivado!", icon="👍")
                            time.sleep(1)
                            st.rerun()