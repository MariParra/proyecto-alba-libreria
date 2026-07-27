import streamlit as st
import pandas as pd
import json
from utilidades import get_db_connection

# --- FUNCIONES DE BASE DE DATOS ---

def obtener_historial_completo(cliente_id):
    conn = get_db_connection()
    historial = []

    res_hist = conn.table("librero_historico").select("libro_id, origen, autor_historico").eq("cliente_id", cliente_id).execute()
    if res_hist.data:
        df_hist = pd.DataFrame(res_hist.data).rename(columns={"origen": "Fuente"})
        historial.append(df_hist)

    res_asig = conn.table("asignaciones").select("libro_suscripcion_id, fecha_asignacion").eq("cliente_id", cliente_id).execute()
    if res_asig.data:
        df_asig = pd.DataFrame(res_asig.data).rename(columns={"libro_suscripcion_id": "libro_id"})
        df_asig['Fuente'] = "Suscripción (" + df_asig['fecha_asignacion'].astype(str) + ")"
        historial.append(df_asig)

    res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta").eq("cliente_id", cliente_id).execute()
    if res_ventas.data:
        libros_venta = []
        for v in res_ventas.data:
            try:
                items = json.loads(v['libros_vendidos'])
                for item in items:
                    libros_venta.append({"libro_id": item.get('libro_id'), "Fuente": f"Venta Directa ({v['fecha_venta']})"})
            except: pass
        if libros_venta:
            historial.append(pd.DataFrame(libros_venta))

        if not historial: return pd.DataFrame()

    # Consolidar los datos
    df_consolidado = pd.concat(historial, ignore_index=True).dropna(subset=['libro_id'])
    
    if not df_consolidado.empty:
        # --- 🛠️ CORRECCIÓN: LIMPIEZA ESTRICTA DE IDs ---
        ids_libros_limpios = []
        for val in df_consolidado['libro_id'].unique():
            try:
                # Convertimos a float primero por si viene como '1.0' y luego a int estricto
                id_entero = int(float(val))
                ids_libros_limpios.append(id_entero)
            except (ValueError, TypeError):
                # Si hay algún dato basura que no sea número, lo ignoramos
                continue
                
        # Si después de limpiar la lista quedó vacía, retornamos
        if not ids_libros_limpios:
            return pd.DataFrame()

        # Hacemos la consulta con la lista perfectamente limpia
        res_libros = conn.table("libros").select("libro_id, titulo, autor").in_("libro_id", ids_libros_limpios).execute()
        
        if res_libros.data:
            df_nombres = pd.DataFrame(res_libros.data)
            
            # Aseguramos que la columna original en el DataFrame también sea entera para que el cruce (merge) sea exacto
            df_consolidado['libro_id'] = pd.to_numeric(df_consolidado['libro_id'], errors='coerce').fillna(-1).astype(int)
            
            # Cruzamos los datos
            df_final = df_consolidado.merge(df_nombres, on="libro_id", how="left")
            return df_final[['titulo', 'autor', 'Fuente']].fillna("Desconocido")
            
    return pd.DataFrame()


def cargar_todos_los_clientes():
    conn = get_db_connection()
    res = conn.table("clientes").select("*").order("nombre").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

# --- VISTA PRINCIPAL ---

def mostrar_clientes():
    st.title("👥 Gestión de Clientes")
    
    # Cargamos la base de datos de clientes una sola vez para usarla en las pestañas
    df_clientes = cargar_todos_los_clientes()
    lista_nombres = df_clientes['nombre'].tolist() if not df_clientes.empty else []

    # UI/UX: MENÚ HORIZONTAL CON PESTAÑAS
    tab_ficha, tab_nuevo, tab_editar, tab_eliminar = st.tabs([
        "🔍 Ficha e Historial", 
        "➕ Nuevo Cliente", 
        "✏️ Editar Datos", 
        "🗑️ Eliminar"
    ])

        # ---------------------------------------------------------
    # PESTAÑA 1: FICHA E HISTORIAL (CON FIDELIDAD POR COMPRAS REALES)
    # ---------------------------------------------------------
    with tab_ficha:
        st.markdown("### Consultar Información del Cliente")
        if df_clientes.empty:
            st.warning("No hay clientes registrados en la base de datos.")
        else:
            cliente_sel = st.selectbox("Selecciona o busca un cliente:", [""] + lista_nombres, key="sel_ficha")
            
            if cliente_sel:
                cliente_data = df_clientes[df_clientes['nombre'] == cliente_sel].iloc[0]
                c_id = cliente_data['cliente_id']
                
                # 1. Cargamos el historial completo para mostrarlo en la tabla
                df_historial = obtener_historial_completo(c_id)
                
                # 2. CALCULAR COMPRAS REALES (Excluyendo 'Librero Histórico')
                # Filtramos las filas cuyo origen NO sea de importación histórica
                if not df_historial.empty:
                    df_compras_reales = df_historial[
                        df_historial['Fuente'].str.contains("Suscripción", case=False, na=False) | 
                        df_historial['Fuente'].str.contains("Venta Directa", case=False, na=False)
                    ]
                    cantidad_compras = len(df_compras_reales)
                else:
                    cantidad_compras = 0
                
                # --- LÓGICA DE FIDELIZACIÓN UX (Basado solo en compras) ---
                if cantidad_compras == 0:
                    nivel, color, icono = "Nuevo Lector", "gray", "🌱"
                elif cantidad_compras <= 3:
                    nivel, color, icono = "Lector Bronce", "orange", "🥉"
                elif cantidad_compras <= 10:
                    nivel, color, icono = "Lector Plata", "blue", "🥈"
                elif cantidad_compras <= 20:
                    nivel, color, icono = "Lector Oro", "green", "🥇"
                else:
                    nivel, color, icono = "Lector Diamante", "violet", "💎"

                # Tarjeta de información de contacto y Fidelidad (Diseño UX)
                with st.container(border=True):
                    col_a, col_b, col_c = st.columns(3)
                    
                    col_a.markdown(f"**📧 Email:** {cliente_data.get('email', 'N/A')}")
                    col_a.markdown(f"**📱 Teléfono:** {cliente_data.get('telefono', 'N/A')}")
                    col_a.markdown(f"**🆔 RUT:** {cliente_data.get('rut', 'N/A')}")
                    
                    col_b.markdown(f"**📍 Dirección:** {cliente_data.get('direccion', 'N/A')}")
                    col_b.markdown(f"**📸 Instagram:** {cliente_data.get('instagram', 'N/A')}")
                    
                    estado = cliente_data.get('status', 'N/A')
                    color_estado = "green" if estado == "ACTIVA" else "red"
                    col_b.markdown(f"**Status:** :{color_estado}[{estado}]")
                    
                    # Panel destacado de Fidelidad (Muestra compras y nivel)
                    col_c.markdown(f"""
                    <div style='text-align:center; padding:10px; background-color:#f8f9fa; border-radius:10px; border: 1px solid #e9ecef;'>
                        <h3 style='margin:0;'>{icono}</h3>
                        <p style='margin:0; font-weight:bold; color:{color}; font-size:1.1em;'>{nivel}</p>
                        <p style='margin:3px 0 0 0; font-size:11px; color:#6c757d;'>{cantidad_compras} compras en Alba</p>
                    </div>
                    """, unsafe_allow_html=True)

                # Mostrar la tabla del historial completo (para que sigan viendo el librero histórico de consulta)
                st.markdown("#### 📚 Historial de Lectura Unificado")
                if df_historial.empty:
                    st.info("El cliente aún no tiene libros asociados en su historial.")
                else:
                    st.success(f"La clienta tiene un total de **{len(df_historial)}** libros registrados en su ficha unificada.")
                    st.dataframe(df_historial, use_container_width=True, hide_index=True)


    # ---------------------------------------------------------
    # PESTAÑA 2: NUEVO CLIENTE
    # ---------------------------------------------------------
    with tab_nuevo:
        st.markdown("### Registrar Nuevo Cliente")
        with st.form("form_nuevo_cliente", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nombre_n = col1.text_input("Nombre Completo *")
            email_n = col2.text_input("Email")
            tel_n = col1.text_input("Teléfono")
            rut_n = col2.text_input("RUT")
            dir_n = st.text_input("Dirección de Envío")
            ig_n = col1.text_input("Instagram")
            estado_n = col2.selectbox("Estado", ["ACTIVA", "INACTIVO"])
            
            st.markdown("*Campos obligatorios")
            submit_nuevo = st.form_submit_button("💾 Guardar Cliente", type="primary", use_container_width=True)
            
            if submit_nuevo:
                if not nombre_n:
                    st.error("El nombre es obligatorio.")
                else:
                    conn = get_db_connection()
                    try:
                        conn.table("clientes").insert({
                            "nombre": nombre_n, "email": email_n, "telefono": tel_n, 
                            "rut": rut_n, "direccion": dir_n, "instagram": ig_n, "status": estado_n
                        }).execute()
                        st.success(f"¡Cliente {nombre_n} registrado exitosamente!")
                        st.rerun() # Recarga la app para que aparezca en las listas
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

    # ---------------------------------------------------------
    # PESTAÑA 3: EDITAR CLIENTE
    # ---------------------------------------------------------
    with tab_editar:
        st.markdown("### Modificar Datos Existentes")
        cliente_editar = st.selectbox("Selecciona el cliente a editar:", [""] + lista_nombres, key="sel_editar")
        
        if cliente_editar:
            # Rellenar el formulario con los datos actuales
            datos_e = df_clientes[df_clientes['nombre'] == cliente_editar].iloc[0]
            
            with st.form("form_editar_cliente"):
                col1, col2 = st.columns(2)
                nombre_e = col1.text_input("Nombre Completo", value=datos_e['nombre'])
                email_e = col2.text_input("Email", value=datos_e.get('email', ''))
                tel_e = col1.text_input("Teléfono", value=datos_e.get('telefono', ''))
                rut_e = col2.text_input("RUT", value=datos_e.get('rut', ''))
                dir_e = st.text_input("Dirección de Envío", value=datos_e.get('direccion', ''))
                ig_e = col1.text_input("Instagram", value=datos_e.get('instagram', ''))
                
                # Preseleccionar el estado actual
                idx_estado = 0 if datos_e.get('status') == "ACTIVA" else 1
                estado_e = col2.selectbox("Estado", ["ACTIVA", "INACTIVO"], index=idx_estado)
                
                submit_editar = st.form_submit_button("🔄 Actualizar Datos", type="primary", use_container_width=True)
                
                if submit_editar:
                    conn = get_db_connection()
                    try:
                        conn.table("clientes").update({
                            "nombre": nombre_e, "email": email_e, "telefono": tel_e, 
                            "rut": rut_e, "direccion": dir_e, "instagram": ig_e, "status": estado_e
                        }).eq("cliente_id", int(datos_e['cliente_id'])).execute()
                        st.success("¡Datos actualizados correctamente!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar: {e}")

    # ---------------------------------------------------------
    # PESTAÑA 4: ELIMINAR CLIENTE
    # ---------------------------------------------------------
    with tab_eliminar:
        st.markdown("### ⚠️ Zona de Peligro")
        st.error("Borrar un cliente eliminará permanentemente su registro. Si tiene ventas o asignaciones previas, esta acción podría fallar por seguridad de la base de datos (dependiendo de tu configuración). Se recomienda editar y cambiar su estado a 'INACTIVO' en su lugar.")
        
        cliente_eliminar = st.selectbox("Selecciona el cliente a eliminar:", [""] + lista_nombres, key="sel_eliminar")
        
        if cliente_eliminar:
            id_eliminar = int(df_clientes[df_clientes['nombre'] == cliente_eliminar].iloc[0]['cliente_id'])
            
            # Checkbox de confirmación como medida extra de fricción UX
            confirmacion = st.checkbox(f"Estoy seguro de que quiero eliminar permanentemente a '{cliente_eliminar}'.")
            
            if st.button("🗑️ Eliminar Definitivamente", type="secondary", disabled=not confirmacion):
                conn = get_db_connection()
                try:
                    conn.table("clientes").delete().eq("cliente_id", id_eliminar).execute()
                    st.success("Cliente eliminado exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo eliminar al cliente. Posiblemente tenga registros asociados en ventas o historial. Error técnico: {e}")

if __name__ == '__main__':
    mostrar_clientes()