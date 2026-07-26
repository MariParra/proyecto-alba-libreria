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
        return pd.DataFrame()

# --- CIERRE DE MES ---
@st.cache_data(ttl=60)
def verificar_mes_cerrado(ano, mes):
    conn = get_db_connection()
    try:
        res = conn.table("meses_cerrados").select("id").eq("ano", int(ano)).eq("mes", int(mes)).execute()
        return len(res.data) > 0
    except: return False

def cambiar_estado_mes(ano, mes, cerrar=True):
    conn = get_db_connection()
    try:
        if cerrar:
            # Usamos isoformat() que es el estándar perfecto para campos 'timestamp'
            datos = {
                "ano": int(ano), 
                "mes": int(mes), 
                "fecha_cierre": datetime.now().isoformat()
            }
            conn.table("meses_cerrados").insert(datos).execute()
            verificar_mes_cerrado.clear()
            return True, f"El mes {mes}/{ano} ha sido CERRADO con éxito."
        else:
            # Al reabrir, borramos el registro. Al volver a cerrar, se creará uno nuevo con la nueva hora.
            conn.table("meses_cerrados").delete().eq("ano", int(ano)).eq("mes", int(mes)).execute()
            verificar_mes_cerrado.clear()
            return True, f"El mes {mes}/{ano} ha sido REABIERTO."
    except Exception as e:
        return False, str(e)


# --- ACCIONES ---
def comenzar_mes(ano, mes):
    df_suscritos = cargar_clientes_suscritos()
    if df_suscritos.empty: return False, "No hay clientes con status 'SUSCRITO'."
    conn = get_db_connection()
    creados, errores = 0, 0
    for _, cliente in df_suscritos.iterrows():
        try:
            datos = {
                "cliente_id": int(cliente['cliente_id']), "ano": int(ano), "mes": int(mes),
                "estado_envio": "PENDIENTE PREPARACION", "pagado": "NO", "envio_pagado": "NO",
                "fecha_asignacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            conn.table("asignaciones").insert(datos).execute()
            creados += 1
        except: errores += 1
    cargar_asignaciones_mes.clear()
    if creados > 0: return True, f"Se iniciaron {creados} suscripciones. {errores} ya existían."
    else: return False, "Todos los clientes suscritos ya estaban creados para este mes."

def asignar_libro_a_suscripcion(asignacion_id, cliente_id, libro_id, titulo, autor, ano, mes, stock_actual):
    conn = get_db_connection()
    try:
        id_asig_py = int(asignacion_id)
        id_cliente_py = int(cliente_id)
        id_libro_py = int(libro_id)
        stock_actual_py = int(stock_actual)
        
        conn.table("asignaciones").update({"libro_suscripcion_id": id_libro_py}).eq("asignacion_id", id_asig_py).execute()
        conn.table("libros").update({"stock": stock_actual_py - 1}).eq("libro_id", id_libro_py).execute()
        
        res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", id_cliente_py).eq("libro_id", id_libro_py).execute()
        if not res_hist.data:
            datos_hist = {
                "cliente_id": id_cliente_py, "libro_id": id_libro_py,
                "autor_historico": limpiar_texto(autor), "origen": f"ASIGNACIÓN {mes}/{ano}"
            }
            conn.table("librero_historico").insert(datos_hist).execute()
            
        cargar_asignaciones_mes.clear()
        cargar_libros_disponibles.clear()
        return True, ""
    except Exception as e: return False, str(e)

def asignar_al_azar(df_pendientes, df_libros, ano, mes):
    if df_pendientes.empty or df_libros.empty: return False, "No hay pendientes o no hay libros disponibles."
    exitos = 0
    libros_temp = df_libros.copy()
    
    for _, asig in df_pendientes.iterrows():
        libros_disp = libros_temp[libros_temp['stock'] > 0]
        if libros_disp.empty: break
        
        libro_elegido = libros_disp.sample(1).iloc[0]
        success, _ = asignar_libro_a_suscripcion(
            int(asig['asignacion_id']), int(asig['cliente_id']), int(libro_elegido['libro_id']), 
            libro_elegido['titulo'], libro_elegido.get('autor', ''), ano, mes, int(libro_elegido['stock'])
        )
        if success:
            exitos += 1
            libros_temp.loc[libros_temp['libro_id'] == libro_elegido['libro_id'], 'stock'] -= 1
    return True, f"Se asignaron {exitos} libros al azar."

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes):
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            res_l = conn.table("libros").select("stock").eq("libro_id", int(libro_id)).execute()
            if res_l.data:
                conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", int(libro_id)).execute()
            origen_str = f"ASIGNACIÓN {mes}/{ano}"
            conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).eq("origen", origen_str).execute()
            
        conn.table("asignaciones").delete().eq("asignacion_id", int(asignacion_id)).execute()
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
                "estado_envio": str(row['estado_envio']).upper(), 
                "pagado": str(row['pagado']).upper(),
                "envio_pagado": str(row['envio_pagado']).upper(), 
                "extras": str(row.get('extras', '')).upper(),
                "comentario": str(row.get('comentario', '')).upper()
            }
            conn.table("asignaciones").update(datos).eq("asignacion_id", int(a_id)).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_asignaciones_mes.clear()
    return updates

# --- FUNCIÓN DE LIMPIEZA DE DATOS (TRUE a SI) ---
def mapear_sino(val):
    v = str(val).upper()
    if v in ["TRUE", "T", "1"]: return "SI"
    if v in ["FALSE", "F", "0"]: return "NO"
    return v

# --- INTERFAZ PRINCIPAL ---
def mostrar_asignaciones():
    st.title("📦 Gestión de Suscripciones")
    
    meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
    
    with st.container(border=True):
        st.markdown("### 📅 Mes de Trabajo")
        c1, c2 = st.columns(2)
        mes_sel = c1.selectbox("Mes:", list(meses_dict.values()), index=datetime.now().month - 1)
        ano_sel = c2.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1)
        mes_num = list(meses_dict.keys())[list(meses_dict.values()).index(mes_sel)]

    df_mes = cargar_asignaciones_mes(ano_sel, mes_num)
    mes_esta_cerrado = verificar_mes_cerrado(ano_sel, mes_num)
    
    if not df_mes.empty:
        df_mes['pagado'] = df_mes['pagado'].apply(mapear_sino)
        df_mes['envio_pagado'] = df_mes['envio_pagado'].apply(mapear_sino)
        df_mes['estado_envio'] = df_mes['estado_envio'].apply(lambda x: str(x).upper())
        df_mes['extras'] = df_mes['extras'].fillna("")
        df_mes['comentario'] = df_mes['comentario'].fillna("")

        total_cajas = len(df_mes)
        cajas_pagadas = len(df_mes[df_mes['pagado'] == 'SI'])
        cajas_pendientes = len(df_mes[df_mes['estado_envio'].isin(['PENDIENTE PREPARACION', 'EN PREPARACION'])])
        cajas_listas = len(df_mes[df_mes['estado_envio'].isin(['POR ENVIAR', 'POR RETIRAR'])])

        st.markdown("### 📊 Resumen del Mes")
        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        c_res1.metric("📦 Total Cajas", total_cajas)
        c_res2.metric("💳 Pagadas", f"{cajas_pagadas} / {total_cajas}")
        c_res3.metric("⏳ Por Preparar", cajas_pendientes)
        c_res4.metric("✅ Listas para Enviar", cajas_listas)
        st.markdown("---")

    if mes_esta_cerrado:
        st.error(f"🔒 **MES CERRADO:** El mes de {mes_sel.upper()} {ano_sel} está bloqueado. Para modificarlo, debes reabrirlo en la opción '🔒 Cierre de Mes'.", icon="🔒")

    opcion_menu = st.selectbox(
        "👉 SELECCIONA LA ACCIÓN QUE DESEAS REALIZAR:",
        ["📋 Gestión (Tabla Editable)", "📚 Asignar Libros", "🚀 Comenzar Mes", "🗑️ Eliminar Registro", "🔒 Cierre de Mes"]
    )
    st.markdown("---")

    # --- 1. TABLA EDITABLE ---
    if opcion_menu == "📋 Gestión (Tabla Editable)":
        st.markdown(f"#### 📋 Gestión del Mes ({mes_sel} {ano_sel})")
        if df_mes.empty: st.warning("No hay registros para este mes. Ve a 'Comenzar Mes'.")
        else:
            # AÑADIMOS EL TERCER FILTRO DE LIBRO AQUÍ
            col_fa1, col_fa2, col_fa3 = st.columns(3)
            filtro_estado = col_fa1.selectbox("Estado del Envío:", ["Todos"] + df_mes['estado_envio'].unique().tolist())
            filtro_pagado = col_fa2.selectbox("Estado de Pago:", ["Todos"] + df_mes['pagado'].unique().tolist())
            filtro_libro = col_fa3.selectbox("Libro Asignado:", ["Todos", "Sin Libro Asignado", "Con Libro Asignado"])
            
            df_filtrado = df_mes.copy()
            if filtro_estado != "Todos": df_filtrado = df_filtrado[df_filtrado['estado_envio'] == filtro_estado]
            if filtro_pagado != "Todos": df_filtrado = df_filtrado[df_filtrado['pagado'] == filtro_pagado]
            if filtro_libro == "Sin Libro Asignado":
                df_filtrado = df_filtrado[df_filtrado['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
            elif filtro_libro == "Con Libro Asignado":
                df_filtrado = df_filtrado[df_filtrado['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR"]
            
            st.caption("Doble clic en las celdas para modificar. Los menús desplegables te ayudarán a no equivocarte.")
            
            columnas_mostrar = ['asignacion_id', 'nombre_cliente', 'titulo_libro', 'estado_envio', 'pagado', 'envio_pagado', 'extras', 'comentario']
            df_mostrar = df_filtrado[columnas_mostrar].copy()
            if 'asignaciones_original' not in st.session_state or not st.session_state.asignaciones_original.equals(df_mostrar):
                st.session_state.asignaciones_original = df_mostrar.copy()
                
            configuracion_columnas = {
                "estado_envio": st.column_config.SelectboxColumn("Estado Envío", options=["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO"], required=True),
                "pagado": st.column_config.SelectboxColumn("Pagado", options=["SI", "NO", "ABONO"], required=True),
                "envio_pagado": st.column_config.SelectboxColumn("Envío Pagado", options=["SI", "NO", "NO APLICA"], required=True)
            }
                
            df_editado = st.data_editor(
                df_mostrar, 
                disabled=columnas_mostrar if mes_esta_cerrado else ['asignacion_id', 'nombre_cliente', 'titulo_libro'], 
                column_config=configuracion_columnas,
                hide_index=True, use_container_width=True
            )
            
            if not df_mostrar.equals(df_editado) and not mes_esta_cerrado:
                if st.button("💾 Guardar Cambios", type="primary"):
                    with st.spinner("Actualizando..."):
                        num = actualizar_asignaciones_batch(df_editado)
                        st.success(f"¡Se actualizaron {num} registros!"), st.rerun()

    # --- 2. ASIGNAR LIBROS ---
    elif opcion_menu == "📚 Asignar Libros":
        st.markdown("#### 📚 Asignar Libros")
        if mes_esta_cerrado:
            st.warning("El mes está cerrado. No puedes asignar libros.")
        else:
            if df_mes.empty: st.info("No hay suscripciones creadas para este mes.")
            else:
                df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
                st.metric("Suscripciones pendientes de libro", len(df_pendientes))
                
                if not df_pendientes.empty:
                    with st.container(border=True):
                        st.markdown("**🎲 Asignación Masiva**")
                        if st.button("Aplicar Libros al Azar a todos", type="primary", use_container_width=True):
                            df_libros = cargar_libros_disponibles()
                            ex, msg = asignar_al_azar(df_pendientes, df_libros, ano_sel, mes_num)
                            if ex: st.success(msg), st.balloons(), st.rerun()
                            else: st.error(msg)
                    
                    with st.container(border=True):
                        st.markdown("**✏️ Asignación Manual**")
                        df_libros = cargar_libros_disponibles()
                        lista_pendientes = [""] + df_pendientes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']}", axis=1).tolist()
                        asig_manual_sel = st.selectbox("Seleccionar Cliente Pendiente:", lista_pendientes)
                        libro_manual_sel = st.selectbox("Seleccionar Libro:", [""] + df_libros['titulo'].tolist())
                        
                        if st.button("Asignar este libro", use_container_width=True):
                            if asig_manual_sel and libro_manual_sel:
                                id_asig = int(asig_manual_sel.split(" - ")[0].replace("ID:", ""))
                                id_cliente = int(df_pendientes[df_pendientes['asignacion_id'] == id_asig].iloc[0]['cliente_id'])
                                l_data = df_libros[df_libros['titulo'] == libro_manual_sel].iloc[0]
                                
                                ex, err = asignar_libro_a_suscripcion(id_asig, id_cliente, l_data['libro_id'], l_data['titulo'], l_data.get('autor', ''), ano_sel, mes_num, l_data['stock'])
                                if ex: st.success("¡Libro asignado con éxito!"), st.rerun()
                                else: st.error(f"Error: {err}")
                else:
                    st.success("¡Todos los clientes de este mes ya tienen su libro asignado!")

    # --- 3. COMENZAR MES ---
    elif opcion_menu == "🚀 Comenzar Mes":
        st.markdown("#### 🚀 Inicializar Mes")
        if mes_esta_cerrado: st.warning("El mes está cerrado. No puedes generar nuevas filas.")
        else:
            st.info(f"Se crearán filas en blanco para todos los clientes que tengan estado 'SUSCRITO' para {mes_sel} de {ano_sel}.")
            if st.button("Generar Registros del Mes", type="primary", use_container_width=True):
                with st.spinner("Generando tabla..."):
                    ex, msg = comenzar_mes(ano_sel, mes_num)
                    if ex: st.success(msg), st.balloons(), st.rerun()
                    else: st.warning(msg)

    # --- 4. ELIMINAR ---
    elif opcion_menu == "🗑️ Eliminar Registro":
        st.markdown("#### 🗑️ Anular / Eliminar Suscripción")
        if mes_esta_cerrado: st.warning("El mes está cerrado. No puedes eliminar registros.")
        else:
            if not df_mes.empty:
                lista_eliminar = [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre_cliente']} | {x['titulo_libro']}", axis=1).tolist()
                asig_eliminar = st.selectbox("Selecciona el registro a borrar:", lista_eliminar)
                if asig_eliminar:
                    if st.button("🟥 ELIMINAR DEFINITIVAMENTE", type="primary"):
                        id_asig = int(asig_eliminar.split(" | ")[0].replace("ID:", ""))
                        row_data = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                        ex, err = eliminar_asignacion(id_asig, row_data.get('libro_suscripcion_id'), row_data['cliente_id'], ano_sel, mes_num)
                        if ex: st.success("Registro eliminado y stock devuelto."), st.rerun()
                        else: st.error(err)
            else:
                st.info("No hay registros para eliminar este mes.")

    # --- 5. CIERRE DE MES ---
    elif opcion_menu == "🔒 Cierre de Mes":
        st.markdown("#### 🔒 Control de Cierre")
        if mes_esta_cerrado:
            st.success(f"El mes de {mes_sel} {ano_sel} se encuentra actualmente **CERRADO**.")
            st.caption("Al reabrir el mes podrás editar estados, asignar libros y hacer sincronizaciones nuevamente.")
            if st.button("🔓 Reabrir Mes", type="secondary"):
                ex, msg = cambiar_estado_mes(ano_sel, mes_num, cerrar=False)
                if ex: st.success(msg), st.rerun()
                else: st.error(msg)
        else:
            st.info(f"El mes de {mes_sel} {ano_sel} se encuentra **ABIERTO**.")
            st.caption("Al cerrar el mes, se bloquearán todas las ediciones para proteger los datos históricos.")
            if st.button("🔒 CERRAR MES DEFINITIVAMENTE", type="primary"):
                ex, msg = cambiar_estado_mes(ano_sel, mes_num, cerrar=True)
                if ex: st.success(msg), st.balloons(), st.rerun()
                else: st.error(msg)