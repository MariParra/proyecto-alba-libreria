import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=60)
def cargar_todos_los_clientes():
    conn = get_db_connection()
    try:
        response = conn.table("clientes").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error al cargar clientes: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_librero_total_cliente(cliente_id):
    """
    Busca libros en 3 tablas distintas (Histórico, Ventas y Asignaciones) 
    y construye el librero unificado del cliente.
    """
    conn = get_db_connection()
    libros_consolidados = []

    # 1. Búsqueda en LIBRERO HISTÓRICO
    try:
        res_hist = conn.table("librero_historico").select("*, libros(titulo)").eq("cliente_id", cliente_id).execute()
        for row in res_hist.data:
            titulo = row.get('libros', {}).get('titulo', 'Libro Externo / No en catálogo') if isinstance(row.get('libros'), dict) else 'Libro Externo'
            libros_consolidados.append({
                "Título del Libro": titulo.upper(),
                "Origen": row.get('origen', 'Histórico').upper(),
                "Detalle": f"Autor: {row.get('autor_historico', '-')}",
                "Fecha": "-"
            })
    except:
        pass

    # 2. Búsqueda en REGISTRO DE VENTAS (Caja)
    try:
        res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta, metodo_envio").eq("cliente_id", cliente_id).execute()
        for row in res_ventas.data:
            texto_libros = row.get('libros_vendidos', '')
            # Separamos la cantidad del título (ej: "1 x El Principito")
            partes = texto_libros.split(" x ", 1)
            titulo = partes[1] if len(partes) == 2 else texto_libros
            
            fecha = row.get('fecha_venta', '')
            fecha_formateada = pd.to_datetime(fecha).strftime('%d-%m-%Y') if fecha else "-"
            
            libros_consolidados.append({
                "Título del Libro": titulo.upper(),
                "Origen": "VENTA CAJA",
                "Detalle": f"Envío: {row.get('metodo_envio', '-')}",
                "Fecha": fecha_formateada
            })
    except:
        pass

    # 3. Búsqueda en ASIGNACIONES (Suscripciones)
    try:
        res_asig = conn.table("asignaciones").select("*").eq("cliente_id", cliente_id).execute()
        if res_asig.data:
            # Obtenemos los nombres de los libros buscando sus IDs
            ids_libros = [r['libro_suscripcion_id'] for r in res_asig.data if r.get('libro_suscripcion_id')]
            mapa_nombres = {}
            if ids_libros:
                res_nombres = conn.table("libros").select("libro_id, titulo").in_("libro_id", ids_libros).execute()
                mapa_nombres = {item['libro_id']: item['titulo'] for item in res_nombres.data}

            for row in res_asig.data:
                l_id = row.get('libro_suscripcion_id')
                titulo = mapa_nombres.get(l_id, f"LIBRO ID {l_id}")
                mes = row.get('mes', '')
                ano = row.get('ano', '')
                
                libros_consolidados.append({
                    "Título del Libro": titulo.upper(),
                    "Origen": f"ASIGNACIÓN {mes}/{ano}",
                    "Detalle": f"Estado: {row.get('estado_envio', '-')}",
                    "Fecha": row.get('fecha_asignacion', '-')
                })
    except:
        pass

    # Convertir a DataFrame y limpiar duplicados (para que sea un catálogo limpio)
    df = pd.DataFrame(libros_consolidados)
    if not df.empty:
        # Quitamos duplicados por si una venta se guardó en ventas y en histórico al mismo tiempo
        df = df.drop_duplicates(subset=['Título del Libro'])
    
    return df

def actualizar_datos_cliente(cliente_id, datos):
    conn = get_db_connection()
    try:
        conn.table("clientes").update(datos).eq("cliente_id", cliente_id).execute()
        cargar_todos_los_clientes.clear()
        return True, ""
    except Exception as e:
        return False, str(e)


# --- INTERFAZ PRINCIPAL ---

def mostrar_clientes():
    st.title("👥 Gestión de Clientes y Librero")
    
    df_clientes = cargar_todos_los_clientes()
    
    if df_clientes.empty:
        st.warning("No hay clientes registrados en el sistema.")
        return
        
    lista_clientes = [""] + df_clientes['nombre'].dropna().tolist()
    
    st.markdown("### 🔍 Buscar Cliente")
    cliente_seleccionado = st.selectbox("Escribe o selecciona el nombre del cliente:", lista_clientes)
    st.markdown("---")
    
    if cliente_seleccionado:
        # Obtener los datos del cliente seleccionado
        cliente_info = df_clientes[df_clientes['nombre'] == cliente_seleccionado].iloc[0]
        c_id = int(cliente_info['cliente_id'])
        
        tab_perfil, tab_librero = st.tabs(["👤 Perfil del Cliente", "📚 Librero del Cliente"])
        
        # --- PESTAÑA 1: PERFIL ---
        with tab_perfil:
            st.markdown(f"#### Datos Personales")
            with st.form("form_editar_cliente"):
                c_nombre = st.text_input("Nombre Completo:", value=cliente_info.get('nombre', ''))
                
                col1, col2 = st.columns(2)
                c_email = col1.text_input("Email:", value=cliente_info.get('email', ''))
                c_telefono = col2.text_input("Teléfono:", value=cliente_info.get('telefono', ''))
                
                col3, col4 = st.columns(2)
                c_instagram = col3.text_input("Instagram:", value=cliente_info.get('instagram', ''))
                c_rut = col4.text_input("RUT:", value=cliente_info.get('rut', ''))
                
                c_direccion = st.text_input("Dirección de Envío:", value=cliente_info.get('direccion', ''))
                
                if st.form_submit_button("💾 Guardar Cambios en el Perfil", type="primary", use_container_width=True):
                    datos_actualizados = {
                        "nombre": limpiar_texto(c_nombre),
                        "email": limpiar_texto(c_email),
                        "telefono": limpiar_texto(c_telefono),
                        "instagram": limpiar_texto(c_instagram),
                        "rut": limpiar_texto(c_rut),
                        "direccion": limpiar_texto(c_direccion)
                    }
                    exito, error = actualizar_datos_cliente(c_id, datos_actualizados)
                    if exito:
                        st.success("¡Perfil actualizado con éxito!")
                        st.rerun()
                    else:
                        st.error(f"Error al actualizar: {error}")
                        
        # --- PESTAÑA 2: LIBRERO HISTÓRICO CONSOLIDADO ---
        with tab_librero:
            st.markdown(f"#### 📚 Colección Total de {cliente_seleccionado}")
            st.caption("Esta vista busca automáticamente en Ventas, Asignaciones y el Librero Histórico.")
            
            df_librero = cargar_librero_total_cliente(c_id)
            
            if df_librero.empty:
                st.info("Este cliente aún no tiene libros registrados en su historial.")
            else:
                # Métrica rápida
                st.metric("Total de libros únicos adquiridos", len(df_librero))
                
                # Mostrar la tabla consolidada
                st.dataframe(df_librero, hide_index=True, use_container_width=True)
