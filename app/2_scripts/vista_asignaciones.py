import streamlit as st
import pandas as pd
import random
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=60)
def cargar_clientes_suscritos():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, status").eq("status", "SUSCRITO").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_libros_disponibles():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, stock").gt("stock", 0).execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_asignaciones_mes(ano, mes):
    conn = get_db_connection()
    try:
        res_asig = conn.table("asignaciones").select("*").eq("ano", ano).eq("mes", mes).execute()
        df_asig = pd.DataFrame(res_asig.data)
        if df_asig.empty: return pd.DataFrame()
        
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        res_libros = conn.table("libros").select("libro_id, titulo").execute()
        
        df_clientes = pd.DataFrame(res_clientes.data)
        df_libros = pd.DataFrame(res_libros.data)
        
        if not df_clientes.empty:
            df_asig = df_asig.merge(df_clientes, on='cliente_id', how='left')
            df_asig.rename(columns={'nombre': 'nombre_cliente'}, inplace=True)
            
        if not df_libros.empty:
            df_asig = df_asig.merge(df_libros, left_on='libro_suscripcion_id', right_on='libro_id', how='left')
            df_asig.rename(columns={'titulo': 'titulo_libro'}, inplace=True)
            
        df_asig['titulo_libro'] = df_asig['titulo_libro'].fillna("⏳ PENDIENTE DE ASIGNAR")
        return df_asig
    except Exception as e:
        st.error(f"Error cargando asignaciones: {e}")
        return pd.DataFrame()

def comenzar_mes(ano, mes):
    """Crea filas en blanco para todos los clientes suscritos."""
    df_suscritos = cargar_clientes_suscritos()
    if df_suscritos.empty: return False, "No hay clientes con status 'SUSCRITO'."
    
    conn = get_db_connection()
    creados = 0
    errores = 0
    
    for _, cliente in df_suscritos.iterrows():
        try:
            datos = {
                "cliente_id": cliente['cliente_id'],
                "ano": ano, "mes": mes,
                "estado_envio": "Pendiente",
                "pagado": "No", "envio_pagado": "No",
                "fecha_asignacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            conn.table("asignaciones").insert(datos).execute()
            creados += 1
        except: errores += 1 # Falla si ya existe (unique constraint)
            
    cargar_asignaciones_mes.clear()
    if creados > 0: return True, f"Se iniciaron {creados} suscripciones para el mes {mes}/{ano}. ({errores} ya existían)."
    else: return False, f"Todos los clientes suscritos ya estaban creados para este mes."

def asignar_libro_a_suscripcion(asignacion_id, cliente_id, libro_id, titulo, autor, ano, mes, stock_actual):
    """Asigna un libro a una fila existente, descuenta stock y guarda en histórico."""
    conn = get_db_connection()
    try:
        # 1. Actualizar Asignación
        conn.table("asignaciones").update({"libro_suscripcion_id": libro_id}).eq("asignacion_id", asignacion_id).execute()
        
        # 2. Descontar Stock
        conn.table("libros").update({"stock": stock_actual - 1}).eq("libro_id", libro_id).execute()
        
        # 3. Guardar en Histórico
        res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", libro_id).execute()
        if not res_hist.data:
            datos_hist = {
                "cliente_id": cliente_id, "libro_id": libro_id,
                "autor_historico": limpiar_texto(autor),
                "origen": f"ASIGNACIÓN {mes}/{ano}"
            }
            conn.table("librero_historico").insert(datos_hist).execute()
            
        cargar_asignaciones_mes.clear()
        cargar_libros_disponibles.clear()
        return True, ""
    except Exception as e: return False, str(e)

def asignar_al_azar(df_pendientes, df_libros, ano, mes):
    """Recorre las asignaciones pendientes y les da un libro al azar con stock disponible."""
    if df_pendientes.empty: return False, "No hay suscripciones pendientes de libro."
    if df_libros.empty: return False, "No hay libros con stock disponible."
    
    exitos = 0
    libros_temp = df_libros.copy()
    
    for _, asig in df_pendientes.iterrows():
        libros_disponibles = libros_temp[libros_temp['stock'] > 0]
        if libros_disponibles.empty: break
        
        # Elegir uno al azar
        libro_elegido = libros_disponibles.sample(1).iloc[0]
        
        success, _ = asignar_libro_a_suscripcion(
            asig['asignacion_id'], asig['cliente_id'], libro_elegido['libro_id'], 
            libro_elegido['titulo'], libro_elegido['autor'], ano, mes, libro_elegido['stock']
        )
        
        if success:
            exitos += 1
            # Reducir stock temporalmente para la siguiente iteración
            libros_temp.loc[libros_temp['libro_id'] == libro_elegido['libro_id'], 'stock'] -= 1

    return True, f"Se asignaron {exitos} libros al azar exitosamente."

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes):
    """Borra la asignación. Si tenía libro, devuelve stock y quita del histórico."""
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            # Devolver stock
            res_l = conn.table("libros").select("stock").eq("libro_id", libro_id).execute()
            if res_l.data:
                conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", libro_id).execute()
            # Quitar del histórico (Solo si el origen es de esta suscripción específica)
            origen_str = f"ASIGNACIÓN {mes}/{ano}"
            conn.table("librero_historico").delete().eq("cliente_id", cliente_id).eq("libro_id", libro_id).eq("origen", origen_str).execute()
            
        conn.table("asignaciones").delete().eq("asignacion_id", asignacion_id).execute()
        cargar_asignaciones_mes.clear()
        return True, ""
    except Exception as e: return False, str(e)

def actualizar_asignaciones_batch(df_editado):
    df_original = st.session_state.get('asignaciones_original')
    if df_original is None: return 0
    df_original_comp = df_original.set_index('asignacion_id')
    df_editado_comp = df_editado.set_index('asignacion_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates = 0
    for a_id, row in filas_cambiadas.iterrows():
        try:
            datos = {
                "estado_envio": str(row['estado_envio']), "pagado": str(row['pagado']),
                "envio_pagado": str(row['envio_pagado']), "extras": str(row.get('extras', '')),
                "comentario": str(row.get('comentario', ''))
            }
            conn.table("asignaciones").update(datos).eq("asignacion_id", a_id).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_asignaciones_mes.clear()
    return updates

# --- INTERFAZ PRINCIPAL ---

def mostrar_asignaciones():
    st.title("📦 Gestión de Suscripciones")
    
    meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
    
    # Selector Global de Mes y Año
    with st.container(border=True):
        st.markdown("### 📅 Mes de Trabajo")
        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mes:", list(meses_dict.values()), index=datetime.now().month - 1)
        ano_sel = c2.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1)
        mes_num = list(meses_dict.keys())[list(meses_dict.values()).index(mes_sel)]

    df_mes = cargar_asignaciones_mes(ano_sel, mes_num)

    tab_gestion, tab_asignar, tab_comenzar, tab_eliminar = st.tabs(["📋 Tabla Editable", "📚 Asignar Libros / Azar", "🚀 Comenzar Mes", "🗑️ Eliminar"])

    # --- 1. TABLA EDITABLE ---
    with tab_gestion:
        st.markdown(f"#### Estado de Suscripciones ({mes_sel} {ano_sel})")
        if df_mes.empty:
            st.warning("No hay registros creados para este mes. Ve a 'Comenzar Mes'.")
        else:
            columnas_mostrar = ['asignacion_id', 'nombre_cliente', 'titulo_libro', 'estado_envio', 'pagado', 'envio_pagado', 'extras', 'comentario']
            for col in columnas_mostrar:
                if col not in df_mes.columns: df_mes[col] = ""
                
            df_mostrar = df_mes[columnas_mostrar].copy()
            if 'asignaciones_original' not in st.session_state or not st.session_state.asignaciones_original.equals(df_mostrar):
                st.session_state.asignaciones_original = df_mostrar.copy()
            
            st.caption("Haz doble clic en estado, pagado, extras o comentario para modificarlos masivamente.")
            df_editado = st.data_editor(df_mostrar, disabled=['asignacion_id', 'nombre_cliente', 'titulo_libro'], hide_index=True, use_container_width=True)
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios", type="primary"):
                    num = actualizar_asignaciones_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} registros!"), st.rerun()

    # --- 2. ASIGNAR LIBROS ---
    with tab_asignar:
        st.markdown("#### 📚 Asignar Libros al Mes")
        if df_mes.empty: st.info("No hay suscripciones creadas para este mes.")
        else:
            df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
            st.metric("Suscripciones pendientes de libro", len(df_pendientes))
            
            if not df_pendientes.empty:
                st.markdown("---")
                col_m1, col_m2 = st.columns(2)
                
                with col_m1:
                    st.markdown("**🎲 Asignación Masiva**")
                    if st.button("Aplicar Libros al Azar a todos los pendientes", type="primary"):
                        df_libros = cargar_libros_disponibles()
                        with st.spinner("Asignando al azar..."):
                            ex, msg = asignar_al_azar(df_pendientes, df_libros, ano_sel, mes_num)
                            if ex: st.success(msg), st.balloons(), st.rerun()
                            else: st.error(msg)
                
                with col_m2:
                    st.markdown("**✏️ Asignación Manual**")
                    df_libros = cargar_libros_disponibles()
                    lista_pendientes = [""] + df_pendientes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']}", axis=1).tolist()
                    asig_manual_sel = st.selectbox("Seleccionar Cliente Pendiente:", lista_pendientes)
                    libro_manual_sel = st.selectbox("Seleccionar Libro a asignar:", [""] + df_libros['titulo'].tolist())
                    
                    if st.button("Asignar este libro", use_container_width=True):
                        if asig_manual_sel and libro_manual_sel:
                            id_asig = int(asig_manual_sel.split(" - ")[0].replace("ID:", ""))
                            id_cliente = int(df_pendientes[df_pendientes['asignacion_id'] == id_asig].iloc[0]['cliente_id'])
                            l_data = df_libros[df_libros['titulo'] == libro_manual_sel].iloc[0]
                            
                            ex, err = asignar_libro_a_suscripcion(id_asig, id_cliente, l_data['libro_id'], l_data['titulo'], l_data['autor'], ano_sel, mes_num, l_data['stock'])
                            if ex: st.success("¡Libro asignado!"), st.rerun()
                            else: st.error(err)
            else:
                st.success("¡Todos los clientes de este mes ya tienen su libro asignado!")

    # --- 3. COMENZAR MES ---
    with tab_comenzar:
        st.markdown("#### 🚀 Inicializar Mes")
        st.info(f"Se crearán filas en blanco para todos los clientes que tengan estado 'SUSCRITO' para {mes_sel} de {ano_sel}.")
        if st.button("Generar Registros del Mes", type="primary", use_container_width=True):
            with st.spinner("Buscando clientes y generando tabla..."):
                ex, msg = comenzar_mes(ano_sel, mes_num)
                if ex: st.success(msg), st.balloons(), st.rerun()
                else: st.warning(msg)

    # --- 4. ELIMINAR ---
    with tab_eliminar:
        st.markdown("#### 🗑️ Anular / Eliminar Suscripción")
        if not df_mes.empty:
            lista_eliminar = [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre_cliente']} | {x['titulo_libro']}", axis=1).tolist()
            asig_eliminar = st.selectbox("Selecciona el registro a borrar:", lista_eliminar)
            if asig_eliminar:
                if st.button("🟥 ELIMINAR DEFINITIVAMENTE", type="primary"):
                    id_asig = int(asig_eliminar.split(" | ")[0].replace("ID:", ""))
                    row_data = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                    l_id = row_data.get('libro_suscripcion_id')
                    c_id = row_data['cliente_id']
                    
                    ex, err = eliminar_asignacion(id_asig, l_id, c_id, ano_sel, mes_num)
                    if ex: st.success("Registro eliminado y stock devuelto."), st.rerun()
                    else: st.error(err)