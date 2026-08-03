import streamlit as st
import pandas as pd
import json
import time
from utilidades import get_db_connection

# --- FUNCIONES DE BASE DE DATOS ---

def obtener_historial_completo(cliente_id):
    columnas_finales = ['Título', 'Autor', 'Fuente']
    conn = get_db_connection()
    historial = []

    # 1. Librero Histórico
    res_hist = conn.table("librero_historico").select("libro_id, origen, autor_historico").eq("cliente_id", cliente_id).execute()
    if res_hist.data:
        df_hist = pd.DataFrame(res_hist.data).rename(columns={"origen": "Fuente", "autor_historico": "Autor"})
        historial.append(df_hist)

    # 2. Asignaciones
    res_asig = conn.table("asignaciones").select("libro_suscripcion_id, fecha_asignacion").eq("cliente_id", cliente_id).execute()
    if res_asig.data:
        df_asig = pd.DataFrame(res_asig.data).rename(columns={"libro_suscripcion_id": "libro_id"})
        df_asig['Fuente'] = "Suscripción (" + pd.to_datetime(df_asig['fecha_asignacion']).dt.strftime('%Y-%m-%d') + ")"
        df_asig['Autor'] = "N/A"
        historial.append(df_asig)

    # 3. Ventas Directas
    res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta").eq("cliente_id", cliente_id).execute()
    if res_ventas.data:
        libros_venta = []
        for v in res_ventas.data:
            try:
                items = json.loads(v['libros_vendidos'])
                for item in items:
                    libros_venta.append({
                        "libro_id": item.get('libro_id'),
                        "Autor": item.get('autor', 'N/A'),
                        "Fuente": f"Venta Directa ({v['fecha_venta']})"
                    })
            except (json.JSONDecodeError, TypeError):
                continue
        if libros_venta:
            historial.append(pd.DataFrame(libros_venta))

    if not historial:
        return pd.DataFrame(columns=columnas_finales)

    df_consolidado = pd.concat(historial, ignore_index=True)
    df_consolidado.dropna(subset=['libro_id'], inplace=True)

    if df_consolidado.empty:
        return pd.DataFrame(columns=columnas_finales)

    ids_libros_limpios = []
    for val in df_consolidado['libro_id'].unique():
        try:
            ids_libros_limpios.append(int(float(val)))
        except (ValueError, TypeError):
            continue

    if not ids_libros_limpios:
        return pd.DataFrame(columns=columnas_finales)

    res_libros = conn.table("libros").select("libro_id, titulo, autor").in_("libro_id", ids_libros_limpios).execute()

    if not res_libros.data:
        return pd.DataFrame(columns=columnas_finales)
        
    df_nombres = pd.DataFrame(res_libros.data).rename(columns={'titulo': 'Título', 'autor': 'autor_catalogo'})
    
    df_consolidado['libro_id'] = pd.to_numeric(df_consolidado['libro_id'], errors='coerce').fillna(-1).astype(int)
    
    df_final = df_consolidado.merge(df_nombres, on="libro_id", how="inner")
    
    # Lógica para usar el mejor autor disponible
    df_final['Autor'] = df_final.apply(
        lambda row: row['autor_catalogo'] if pd.notna(row['autor_catalogo']) and row['autor_catalogo'] != 'N/A' else row['Autor'],
        axis=1
    )
    
    return df_final[columnas_finales]

@st.cache_data
def cargar_todos_los_clientes():
    conn = get_db_connection()
    res = conn.table("clientes").select("*").order("nombre").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def actualizar_status_cliente(cliente_id, nuevo_status):
    """Actualiza el estado de un cliente en la base de datos."""
    try:
        conn = get_db_connection()
        conn.table("clientes").update({"status": nuevo_status}).eq("cliente_id", cliente_id).execute()
        return True, ""
    except Exception as e:
        return False, str(e)


# --- VISTA PRINCIPAL ---

def mostrar_clientes():
    st.title("👥 Gestión de Clientes")
    
    # --- NOTA DE INSTRUCCIONES OCULTA ---
    with st.expander("💡 Guía de Estados de Clientes (Haz clic para desplegar)"):
        st.markdown("""
        **¿Qué significa cada estado en el sistema?**
        * 🟢 **ACTIVA:** La clienta está suscrita al club. **Recibirá una caja** automáticamente cuando presiones "Generar Mes" en Asignaciones.
        * ⏸️ **PAUSADO:** Suscripción detenida temporalmente (ej. por vacaciones o se saltó un mes). **No recibirá caja** hasta que la vuelvas a cambiar a ACTIVA.
        * 🔴 **INACTIVO:** La suscripción fue cancelada definitivamente.
        * 🛍️ **CLIENTE REGULAR:** Es un cliente de la tienda que solo hace compras directas y nunca ha estado suscrito al club.
        """)

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn2:
        if st.button("🔄 Refrescar Datos", use_container_width=True):
            cargar_todos_los_clientes.clear()
            st.toast("Lista de clientes actualizada.")
            time.sleep(1)
            st.rerun()

    df_clientes = cargar_todos_los_clientes()

    # --- FILTRO GLOBAL PARA TODAS LAS PESTAÑAS ---
    st.markdown("### 🔍 Filtrar Directorio")
    estados_disponibles = ["Todos", "ACTIVA", "PAUSADO", "INACTIVO", "CLIENTE REGULAR"]
    filtro_estado = st.selectbox("Mostrar clientes con estado:", estados_disponibles)
    
    # Aplicar el filtro a la tabla principal
    if filtro_estado != "Todos":
        df_clientes_filtrado = df_clientes[df_clientes['status'] == filtro_estado]
    else:
        df_clientes_filtrado = df_clientes

    lista_nombres = df_clientes_filtrado['nombre'].tolist() if not df_clientes_filtrado.empty else []
    
    st.markdown("---")

    tab_ficha, tab_nuevo, tab_editar, tab_eliminar = st.tabs([
        "🔍 Ficha e Historial", 
        "➕ Nuevo Cliente", 
        "✏️ Editar Datos", 
        "🗑️ Eliminar"
    ])

    with tab_ficha:
        st.markdown("### Consultar Información del Cliente")
        if df_clientes_filtrado.empty:
            st.warning(f"No hay clientes registrados bajo el filtro actual ({filtro_estado}).")
        else:
            cliente_sel = st.selectbox("Selecciona o busca un cliente:", [""] + lista_nombres, key="sel_ficha")
            
            if cliente_sel:
                cliente_data = df_clientes_filtrado[df_clientes_filtrado['nombre'] == cliente_sel].iloc[0]
                c_id = cliente_data['cliente_id']
                estado_actual = cliente_data.get('status', 'INACTIVO')
                
                # --- Selector Rápido de Estado ---
                with st.container(border=True):
                    col_status, col_info = st.columns([1, 2])
                    
                    with col_status:
                        estados_totales = ["ACTIVA", "PAUSADO", "INACTIVO", "CLIENTE REGULAR"]
                        try:
                            idx_estado = estados_totales.index(estado_actual)
                        except ValueError:
                            idx_estado = 2 # INACTIVO por defecto
                            
                        nuevo_estado_rapido = st.selectbox(
                            "Cambiar Estado Rápidamente:", 
                            options=estados_totales,
                            index=idx_estado,
                            key=f"status_rapido_{c_id}"
                        )

                    # Comparamos si el usuario seleccionó un estado distinto al que ya tenía
                    if nuevo_estado_rapido != estado_actual:
                        with st.spinner(f"Cambiando estado a {nuevo_estado_rapido}..."):
                            exito, error = actualizar_status_cliente(c_id, nuevo_estado_rapido)
                            if exito:
                                st.success(f"¡Estado actualizado a {nuevo_estado_rapido}!")
                                cargar_todos_los_clientes.clear()
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"Error al actualizar: {error}")
                    
                    with col_info:
                        if estado_actual == 'ACTIVA':
                            st.info("✅ La clienta **recibirá una caja** en la próxima generación del mes.")
                        elif estado_actual == 'PAUSADO':
                            st.warning("⏸️ Suscripción en pausa. **NO recibirá caja** hasta que la vuelvas a cambiar a ACTIVA.")
                        else:
                            st.markdown("La clienta **NO recibirá caja** de suscripción (puede seguir haciendo compras directas).")
                
                st.markdown("---")
                
                df_historial = obtener_historial_completo(c_id)
                
                if not df_historial.empty:
                    df_compras_reales = df_historial[
                        df_historial['Fuente'].str.contains("Suscripción", case=False, na=False) | 
                        df_historial['Fuente'].str.contains("Venta Directa", case=False, na=False)
                    ]
                    cantidad_compras = len(df_compras_reales)
                else:
                    cantidad_compras = 0
                
                if cantidad_compras == 0:
                    nivel, color, icono = "Nuevo Lector", "gray", "🌱"
                elif cantidad_compras <= 10:
                    nivel, color, icono = "Lector Bronce", "orange", "🥉"
                elif cantidad_compras <= 30:
                    nivel, color, icono = "Lector Plata", "blue", "🥈"
                elif cantidad_compras <= 50:
                    nivel, color, icono = "Lector Oro", "green", "🥇"
                else:
                    nivel, color, icono = "Lector Diamante", "violet", "💎"

                with st.container(border=True):
                    col_a, col_b, col_c = st.columns(3)
                    
                    col_a.markdown(f"**📧 Email:** {cliente_data.get('email', 'N/A')}")
                    col_a.markdown(f"**📱 Teléfono:** {cliente_data.get('telefono', 'N/A')}")
                    col_a.markdown(f"**🆔 RUT:** {cliente_data.get('rut', 'N/A')}")
                    
                    col_b.markdown(f"**📍 Dirección:** {cliente_data.get('direccion', 'N/A')}")
                    col_b.markdown(f"**📸 Instagram:** {cliente_data.get('instagram', 'N/A')}")
                    
                    estado = cliente_data.get('status', 'N/A')
                    color_estado = "green" if estado == "ACTIVA" else "orange" if estado == "PAUSADO" else "red"
                    col_b.markdown(f"**Status:** :{color_estado}[{estado}]")
                    
                    col_c.markdown(f"""
                    <div style='text-align:center; padding:10px; background-color:#f8f9fa; border-radius:10px; border: 1px solid #e9ecef;'>
                        <h3 style='margin:0;'>{icono}</h3>
                        <p style='margin:0; font-weight:bold; color:{color}; font-size:1.1em;'>{nivel}</p>
                        <p style='margin:3px 0 0 0; font-size:11px; color:#6c757d;'>{cantidad_compras} compras en Alba</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("#### 📚 Historial de Lectura Unificado")
                if df_historial.empty:
                    st.info("El cliente aún no tiene libros asociados en su historial.")
                else:
                    def categorizar_fuente(fuente_texto):
                        if "suscripción" in fuente_texto.lower(): return "Suscripción"
                        if "venta" in fuente_texto.lower(): return "Venta Directa"
                        if "importación" in fuente_texto.lower(): return "Importación Histórica"
                        return "Otro"
                    
                    df_historial['Origen'] = df_historial['Fuente'].apply(categorizar_fuente)
                    
                    origenes_unicos = sorted(df_historial['Origen'].unique())
                    
                    with st.expander("🔍 Filtrar historial por origen"):
                        origenes_seleccionados = st.multiselect(
                            "Selecciona uno o más orígenes:",
                            options=origenes_unicos,
                            default=origenes_unicos
                        )
                    
                    if origenes_seleccionados:
                        df_historial_filtrado = df_historial[df_historial['Origen'].isin(origenes_seleccionados)]
                    else:
                        df_historial_filtrado = df_historial
                        
                    st.success(f"Mostrando **{len(df_historial_filtrado)}** de **{len(df_historial)}** libros registrados.")
                    
                    st.dataframe(
                        df_historial_filtrado[['Título', 'Autor', 'Fuente']], 
                        use_container_width=True, 
                        hide_index=True
                    )

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
            estado_n = col2.selectbox("Estado", ["ACTIVA", "PAUSADO", "INACTIVO", "CLIENTE REGULAR"])
            
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
                        cargar_todos_los_clientes.clear()
                        time.sleep(1.5)
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

    with tab_editar:
        st.markdown("### Modificar Datos Existentes")
        if df_clientes_filtrado.empty:
            st.info("No hay clientes en el filtro actual para editar.")
        else:
            cliente_editar = st.selectbox("Selecciona el cliente a editar:", [""] + lista_nombres, key="sel_editar")
            
            if cliente_editar:
                datos_e = df_clientes_filtrado[df_clientes_filtrado['nombre'] == cliente_editar].iloc[0]
                c_id_editar = int(datos_e['cliente_id'])
                
                # --- 🔍 NUEVO: Buscamos el valor de su suscripción actual ---
                conn = get_db_connection()
                valor_suscripcion_actual = 0.0
                registro_suscripcion_existe = False
                
                try:
                    res_susc = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", c_id_editar).execute()
                    if res_susc.data:
                        valor_suscripcion_actual = float(res_susc.data[0].get('valor_suscripcion') or 0.0)
                        registro_suscripcion_existe = True
                except Exception as e:
                    print(f"Error al consultar valor suscripción: {e}")
                
                # --- Formulario de Edición ---
                with st.form("form_editar_cliente"):
                    col1, col2 = st.columns(2)
                    nombre_e = col1.text_input("Nombre Completo", value=datos_e['nombre'])
                    email_e = col2.text_input("Email", value=datos_e.get('email', ''))
                    tel_e = col1.text_input("Teléfono", value=datos_e.get('telefono', ''))
                    rut_e = col2.text_input("RUT", value=datos_e.get('rut', ''))
                    dir_e = st.text_input("Dirección de Envío", value=datos_e.get('direccion', ''))
                    ig_e = col1.text_input("Instagram", value=datos_e.get('instagram', ''))
                    
                    estados_posibles = ["ACTIVA", "PAUSADO", "INACTIVO", "CLIENTE REGULAR"]
                    try:
                        idx_estado_e = estados_posibles.index(datos_e.get('status'))
                    except ValueError:
                        idx_estado_e = 2 # INACTIVO por defecto
                    estado_e = col2.selectbox("Estado", estados_posibles, index=idx_estado_e)
                    
                    # --- 💸 NUEVO CAMPO: Edición del Valor de Suscripción ---
                    st.markdown("#### 💳 Detalles de Suscripción")
                    col_susc1, col_susc2 = st.columns(2)
                    nuevo_valor_susc = col_susc1.number_input(
                        "Valor Mensual de la Suscripción ($):", 
                        min_value=0.0, 
                        step=500.0, 
                        value=valor_suscripcion_actual,
                        help="Si se registra como $0 o queda vacío, se asumirá que no tiene cobro mensual activo."
                    )
                    col_susc2.info("💡 Este monto se usará de forma automática para calcular el cobro de su caja al iniciar cada mes en la pestaña Asignaciones.")
                    
                    submit_editar = st.form_submit_button("🔄 Actualizar Datos", type="primary", use_container_width=True)
                    
                    if submit_editar:
                        try:
                            # 1. Actualizar datos básicos del cliente
                            conn.table("clientes").update({
                                "nombre": nombre_e, "email": email_e, "telefono": tel_e, 
                                "rut": rut_e, "direccion": dir_e, "instagram": ig_e, "status": estado_e
                            }).eq("cliente_id", c_id_editar).execute()
                            
                            # 2. Guardar o actualizar el valor en la tabla 'suscripciones'
                            if registro_suscripcion_existe:
                                # Si ya tenía un registro, lo actualizamos
                                conn.table("suscripciones").update({
                                    "valor_suscripcion": float(nuevo_valor_susc)
                                }).eq("cliente_id", c_id_editar).execute()
                            else:
                                # Si no existía (estaba vacío/nulo), creamos el registro base
                                conn.table("suscripciones").insert({
                                    "cliente_id": c_id_editar,
                                    "valor_suscripcion": float(nuevo_valor_susc),
                                    "metodo_entrega": "RETIRO", # Valor por defecto seguro
                                    "generos_preferencia": ""
                                }).execute()
                                
                            st.success("¡Datos del cliente y valor de suscripción actualizados correctamente!")
                            cargar_todos_los_clientes.clear()
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar datos: {e}")

    with tab_eliminar:
        st.markdown("### ⚠️ Zona de Peligro")
        st.error("Borrar un cliente eliminará permanentemente su registro. Si tiene ventas o asignaciones previas, esta acción podría fallar por seguridad de la base de datos. Se recomienda editar y cambiar su estado a 'INACTIVO' en su lugar.")
        
        if df_clientes_filtrado.empty:
            st.info("No hay clientes en el filtro actual para eliminar.")
        else:
            cliente_eliminar = st.selectbox("Selecciona el cliente a eliminar:", [""] + lista_nombres, key="sel_eliminar")
            
            if cliente_eliminar:
                id_eliminar = int(df_clientes_filtrado[df_clientes_filtrado['nombre'] == cliente_eliminar].iloc[0]['cliente_id'])
                
                confirmacion = st.checkbox(f"Estoy seguro de que quiero eliminar permanentemente a '{cliente_eliminar}'.")
                
                if st.button("🗑️ Eliminar Definitivamente", type="secondary", disabled=not confirmacion):
                    conn = get_db_connection()
                    try:
                        conn.table("clientes").delete().eq("cliente_id", id_eliminar).execute()
                        st.success("Cliente eliminado exitosamente.")
                        cargar_todos_los_clientes.clear()
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo eliminar al cliente. Posiblemente tenga registros asociados en ventas o historial. Error técnico: {e}")

if __name__ == '__main__':
    mostrar_clientes()