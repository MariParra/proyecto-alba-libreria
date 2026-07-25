import streamlit as st
import pandas as pd
import random
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto

# --- FUNCIONES DE BASE DE DATOS (CON LÓGICA DE CIERRE) ---

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
        df_clientes = pd.DataFrame(res_clientes.data)
        if not df_clientes.empty:
            df_asig = df_asig.merge(df_clientes, on='cliente_id', how='left').rename(columns={'nombre': 'nombre_cliente'})
        
        res_libros = conn.table("libros").select("libro_id, titulo").execute()
        df_libros = pd.DataFrame(res_libros.data)
        if not df_libros.empty:
            df_asig = df_asig.merge(df_libros, left_on='libro_suscripcion_id', right_on='libro_id', how='left').rename(columns={'titulo': 'titulo_libro'})
            
        df_asig['titulo_libro'] = df_asig['titulo_libro'].fillna("⏳ PENDIENTE")
        return df_asig
    except Exception: return pd.DataFrame()

# --- FUNCIONES PARA MANEJAR EL CIERRE DE MES ---
@st.cache_data(ttl=60)
def verificar_mes_cerrado(ano, mes):
    conn = get_db_connection()
    try:
        res = conn.table("meses_cerrados").select("id").eq("ano", ano).eq("mes", mes).execute()
        return len(res.data) > 0
    except: return False

def cambiar_estado_mes(ano, mes, cerrar=True):
    conn = get_db_connection()
    try:
        if cerrar:
            datos = {"ano": ano, "mes": mes, "fecha_cierre": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            conn.table("meses_cerrados").insert(datos).execute()
        else:
            conn.table("meses_cerrados").delete().eq("ano", ano).eq("mes", mes).execute()
        
        verificar_mes_cerrado.clear()
        return True, f"El mes {mes}/{ano} ha sido {'CERRADO' if cerrar else 'REABIERTO'}."
    except Exception as e: return False, str(e)

# --- (Resto de funciones: comenzar_mes, asignar_libro, etc. con la corrección del int64) ---
def comenzar_mes(ano, mes):
    df_suscritos = cargar_clientes_suscritos()
    if df_suscritos.empty: return False, "No hay clientes 'SUSCRITO'."
    conn = get_db_connection()
    creados, errores = 0, 0
    for _, cliente in df_suscritos.iterrows():
        try:
            conn.table("asignaciones").insert({
                "cliente_id": int(cliente['cliente_id']), "ano": ano, "mes": mes,
                "estado_envio": "Pendiente", "pagado": "No", "envio_pagado": "No",
                "fecha_asignacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }).execute()
            creados += 1
        except: errores += 1
    cargar_asignaciones_mes.clear()
    return True, f"Se iniciaron {creados} suscripciones. {errores} ya existían."

def asignar_libro_a_suscripcion(asignacion_id, cliente_id, libro_id, autor, ano, mes, stock_actual):
    conn = get_db_connection()
    try:
        id_asig_py, id_cliente_py, id_libro_py = int(asignacion_id), int(cliente_id), int(libro_id)
        conn.table("asignaciones").update({"libro_suscripcion_id": id_libro_py}).eq("asignacion_id", id_asig_py).execute()
        conn.table("libros").update({"stock": int(stock_actual) - 1}).eq("libro_id", id_libro_py).execute()
        res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", id_cliente_py).eq("libro_id", id_libro_py).execute()
        if not res_hist.data:
            conn.table("librero_historico").insert({
                "cliente_id": id_cliente_py, "libro_id": id_libro_py,
                "autor_historico": limpiar_texto(autor), "origen": f"ASIGNACIÓN {mes}/{ano}"
            }).execute()
        cargar_asignaciones_mes.clear(); cargar_libros_disponibles.clear()
        return True, ""
    except Exception as e: return False, str(e)

def asignar_al_azar(df_pendientes, df_libros, ano, mes):
    if df_pendientes.empty or df_libros.empty: return False, "No hay pendientes o no hay libros con stock."
    exitos = 0
    libros_temp = df_libros.copy()
    for _, asig in df_pendientes.iterrows():
        libros_disponibles = libros_temp[libros_temp['stock'] > 0]
        if libros_disponibles.empty: break
        libro_elegido = libros_disponibles.sample(1).iloc[0]
        success, _ = asignar_libro_a_suscripcion(
            asig['asignacion_id'], asig['cliente_id'], libro_elegido['libro_id'], 
            libro_elegido['autor'], ano, mes, libro_elegido['stock']
        )
        if success:
            exitos += 1
            libros_temp.loc[libros_temp['libro_id'] == libro_elegido['libro_id'], 'stock'] -= 1
    return True, f"Se asignaron {exitos} libros al azar."

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes):
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            conn.table("libros").update({"stock": int(conn.table("libros").select("stock").eq("libro_id", int(libro_id)).execute().data[0]['stock']) + 1}).eq("libro_id", int(libro_id)).execute()
            conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).eq("origen", f"ASIGNACIÓN {mes}/{ano}").execute()
        conn.table("asignaciones").delete().eq("asignacion_id", int(asignacion_id)).execute()
        cargar_asignaciones_mes.clear()
        return True, ""
    except Exception as e: return False, str(e)

def actualizar_asignaciones_batch(df_editado):
    # ... (sin cambios, ya es robusta)
    df_original = st.session_state.get('asignaciones_original')
    if df_original is None: return 0
    df_original_comp = df_original.set_index('asignacion_id')
    df_editado_comp = df_editado.set_index('asignacion_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    if filas_cambiadas.empty: return 0
    conn, updates = get_db_connection(), 0
    for a_id, row in filas_cambiadas.iterrows():
        try:
            datos = {"estado_envio": str(row['estado_envio']), "pagado": str(row['pagado']), "envio_pagado": str(row['envio_pagado']), "extras": str(row.get('extras', '')), "comentario": str(row.get('comentario', ''))}
            conn.table("asignaciones").update(datos).eq("asignacion_id", int(a_id)).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_asignaciones_mes.clear()
    return updates

# --- INTERFAZ PRINCIPAL CON PESTAÑA DE CIERRE ---
def mostrar_asignaciones():
    st.title("📦 Gestión de Suscripciones")
    meses_dict = {i+1: v for i, v in enumerate(["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])}
    
    with st.container(border=True):
        st.markdown("### 📅 Mes de Trabajo")
        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mes:", list(meses_dict.values()), index=datetime.now().month - 1)
        ano_sel = c2.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1)
        mes_num = list(meses_dict.keys())[list(meses_dict.values()).index(mes_sel)]

    df_mes = cargar_asignaciones_mes(ano_sel, mes_num)
    mes_esta_cerrado = verificar_mes_cerrado(ano_sel, mes_num)

    if mes_esta_cerrado:
        st.error(f"🔒 **MES CERRADO:** El mes de {mes_sel.upper()} {ano_sel} está bloqueado. Para modificarlo, debes ir a la pestaña 'Cierre de Mes' y reabrirlo.", icon="🔒")

    tab_gestion, tab_asignar, tab_comenzar, tab_eliminar, tab_cierre = st.tabs(["📋 Gestión", "📚 Asignar Libros", "🚀 Comenzar Mes", "🗑️ Eliminar", "🔒 Cierre de Mes"])

    with tab_gestion:
        if df_mes.empty: st.warning("No hay registros para este mes. Ve a 'Comenzar Mes'.")
        else:
            df_editado = st.data_editor(df_mes[['asignacion_id', 'nombre_cliente', 'titulo_libro', 'estado_envio', 'pagado', 'envio_pagado', 'extras', 'comentario']], 
                                        disabled=mes_esta_cerrado or ['asignacion_id', 'nombre_cliente', 'titulo_libro'], hide_index=True, use_container_width=True)
            if not df_mes[['asignacion_id', 'estado_envio', 'pagado', 'envio_pagado', 'extras', 'comentario']].equals(df_editado[['asignacion_id', 'estado_envio', 'pagado', 'envio_pagado', 'extras', 'comentario']]):
                st.session_state['asignaciones_original'] = df_mes
                if st.button("💾 Guardar Cambios", type="primary", disabled=mes_esta_cerrado):
                    num = actualizar_asignaciones_batch(df_editado)
                    st.success(f"¡Se actualizaron {num} registros!"), st.rerun()
    with tab_asignar:
        if mes_esta_cerrado: st.warning("El mes está cerrado. No puedes asignar libros.")
        else:
            df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE"]
            st.metric("Suscripciones pendientes de libro", len(df_pendientes))
            if not df_pendientes.empty:
                if st.button("🎲 Aplicar Libros al Azar", type="primary"):
                    ex, msg = asignar_al_azar(df_pendientes, cargar_libros_disponibles(), ano_sel, mes_num)
                    if ex: st.success(msg), st.balloons(), st.rerun()
                    else: st.error(msg)
                asig_sel = st.selectbox("Asignación Manual:", [""] + df_pendientes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']}", axis=1).tolist())
                libro_sel = st.selectbox("Libro a asignar:", [""] + cargar_libros_disponibles()['titulo'].tolist())
                if st.button("Asignar este libro"):
                    if asig_sel and libro_sel:
                        id_asig = int(asig_sel.split(" - ")[0][3:])
                        cliente_row = df_pendientes[df_pendientes['asignacion_id'] == id_asig].iloc[0]
                        libro_row = cargar_libros_disponibles()[cargar_libros_disponibles()['titulo'] == libro_sel].iloc[0]
                        ex, err = asignar_libro_a_suscripcion(id_asig, cliente_row['cliente_id'], libro_row['libro_id'], libro_row['autor'], ano_sel, mes_num, libro_row['stock'])
                        if ex: st.success("¡Libro asignado!"), st.rerun()
                        else: st.error(err)
    with tab_comenzar:
        if mes_esta_cerrado: st.warning("El mes está cerrado.")
        else:
            if st.button("🚀 Generar Registros del Mes", type="primary"):
                ex, msg = comenzar_mes(ano_sel, mes_num)
                if ex: st.success(msg), st.balloons(), st.rerun()
                else: st.warning(msg)
    with tab_eliminar:
        if mes_esta_cerrado: st.warning("El mes está cerrado.")
        else:
            asig_eliminar = st.selectbox("Selecciona registro a borrar:", [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre_cliente']} | {x['titulo_libro']}", axis=1).tolist())
            if asig_eliminar and st.button("🟥 ELIMINAR", type="primary"):
                id_asig = int(asig_eliminar.split(" | ")[0][3:])
                row = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                ex, err = eliminar_asignacion(id_asig, row.get('libro_suscripcion_id'), row['cliente_id'], ano_sel, mes_num)
                if ex: st.success("Registro eliminado."), st.rerun()
                else: st.error(err)
    with tab_cierre:
        st.markdown("#### 🔒 Control de Cierre")
        if mes_esta_cerrado:
            st.success(f"El mes {mes_sel} {ano_sel} está **CERRADO**.")
            if st.button("🔓 Reabrir Mes"):
                ex, msg = cambiar_estado_mes(ano_sel, mes_num, cerrar=False)
                st.success(msg), st.rerun()
        else:
            st.info(f"El mes {mes_sel} {ano_sel} está **ABIERTO**.")
            if st.button("🔒 CERRAR MES"):
                ex, msg = cambiar_estado_mes(ano_sel, mes_num, cerrar=True)
                st.success(msg), st.rerun()