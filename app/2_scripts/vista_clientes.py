import streamlit as st
import pandas as pd
import json
from utilidades import get_db_connection

def eliminar_cliente(cliente_id):
    conn = get_db_connection()
    # Eliminar al cliente (Asegúrate de que tu BD permita borrado en cascada o elimina sus dependencias primero)
    conn.table("clientes").delete().eq("cliente_id", cliente_id).execute()
    st.success("Cliente eliminado exitosamente.")
    st.rerun()

def obtener_historial_completo(cliente_id):
    conn = get_db_connection()
    historial = []

    # 1. Librero Histórico
    res_hist = conn.table("librero_historico").select("libro_id, origen, autor_historico").eq("cliente_id", cliente_id).execute()
    if res_hist.data:
        df_hist = pd.DataFrame(res_hist.data).rename(columns={"origen": "Fuente"})
        historial.append(df_hist)

    # 2. Asignaciones
    res_asig = conn.table("asignaciones").select("libro_suscripcion_id, fecha_asignacion").eq("cliente_id", cliente_id).execute()
    if res_asig.data:
        df_asig = pd.DataFrame(res_asig.data).rename(columns={"libro_suscripcion_id": "libro_id"})
        df_asig['Fuente'] = "Suscripción (" + df_asig['fecha_asignacion'].astype(str) + ")"
        historial.append(df_asig)

    # 3. Ventas Directas
    res_ventas = conn.table("registro_ventas").select("libros_vendidos, fecha_venta").eq("cliente_id", cliente_id).execute()
    if res_ventas.data:
        libros_venta = []
        for v in res_ventas.data:
            try:
                # Asumiendo que libros_vendidos es un JSON con listado de libros
                items = json.loads(v['libros_vendidos'])
                for item in items:
                    libros_venta.append({"libro_id": item.get('libro_id'), "Fuente": f"Venta Directa ({v['fecha_venta']})"})
            except: pass
        if libros_venta:
            historial.append(pd.DataFrame(libros_venta))

    if not historial:
        return pd.DataFrame()

    # Consolidar y buscar nombres de libros
    df_consolidado = pd.concat(historial, ignore_index=True)
    df_consolidado = df_consolidado.dropna(subset=['libro_id'])
    
    if not df_consolidado.empty:
        ids_libros = df_consolidado['libro_id'].unique().tolist()
        res_libros = conn.table("libros").select("libro_id, titulo, autor").in_("libro_id", ids_libros).execute()
        if res_libros.data:
            df_nombres = pd.DataFrame(res_libros.data)
            df_final = df_consolidado.merge(df_nombres, on="libro_id", how="left")
            return df_final[['titulo', 'autor', 'Fuente']].fillna("Desconocido")
            
    return pd.DataFrame()

def mostrar_clientes():
    st.title("👥 Gestión de Clientes")
    
    conn = get_db_connection()
    res_clientes = conn.table("clientes").select("*").execute()
    df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()

    if df_clientes.empty:
        st.warning("No hay clientes registrados.")
        return

    # UI/UX Toggle de Vista
    vista = st.radio("Disposición visual:", ["Vista PC (Tabla)", "Vista Móvil (Tarjetas)"], horizontal=True)

    if vista == "Vista PC (Tabla)":
        st.dataframe(df_clientes[['nombre', 'email', 'telefono', 'status']], use_container_width=True)
    else:
        for _, row in df_clientes.iterrows():
            with st.expander(f"👤 {row['nombre']} - {row['status']}"):
                st.write(f"**Email:** {row['email']} | **Teléfono:** {row['telefono']}")

    st.markdown("---")
    st.subheader("Ficha Detallada del Cliente")
    cliente_sel = st.selectbox("Selecciona un cliente para ver su historial o eliminarlo:", df_clientes['nombre'].tolist())
    
    if cliente_sel:
        cliente_data = df_clientes[df_clientes['nombre'] == cliente_sel].iloc[0]
        c_id = cliente_data['cliente_id']
        
        st.write(f"**RUT:** {cliente_data['rut']} | **Dirección:** {cliente_data['direccion']}")
        
        # Historial de libros
        st.markdown("#### 📚 Historial de Lectura")
        df_historial = obtener_historial_completo(c_id)
        if df_historial.empty:
            st.info("Este cliente no tiene libros en su historial histórico, asignaciones ni ventas.")
        else:
            st.success(f"Se encontraron {len(df_historial)} libros en el historial.")
            st.dataframe(df_historial, use_container_width=True, hide_index=True)
            
        # Acción de Eliminar (Zona de Peligro)
        st.markdown("#### ⚠️ Zona de Peligro")
        if st.button("🗑️ Eliminar Cliente", type="primary", use_container_width=True):
            eliminar_cliente(c_id)