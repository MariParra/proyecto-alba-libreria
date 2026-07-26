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
def cargar_valores_suscripcion():
    conn = get_db_connection()
    try:
        res = conn.table("suscripciones").select("cliente_id, valor_suscripcion").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_libros_disponibles():
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, autor, precio, stock").gt("stock", 0).execute()
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
            conn.table("meses_cerrados").insert({"ano": int(ano), "mes": int(mes), "fecha_cierre": datetime.now().isoformat()}).execute()
            verificar_mes_cerrado.clear()
            return True, f"El mes {mes}/{ano} ha sido CERRADO con éxito."
        else:
            conn.table("meses_cerrados").delete().eq("ano", int(ano)).eq("mes", int(mes)).execute()
            verificar_mes_cerrado.clear()
            return True, f"El mes {mes}/{ano} ha sido REABIERTO."
    except Exception as e: return False, str(e)

# --- ACCIONES ---
def comenzar_mes(ano, mes):
    df_suscritos = cargar_clientes_suscritos()
    df_valores = cargar_valores_suscripcion()
    if df_suscritos.empty: return False, "No hay clientes 'SUSCRITO'."
    conn = get_db_connection()
    creados, errores = 0, 0
    
    for _, cliente in df_suscritos.iterrows():
        try:
            c_id = int(cliente['cliente_id'])
            val_sub = 0.0
            if not df_valores.empty and c_id in df_valores['cliente_id'].values:
                val_sub = float(df_valores[df_valores['cliente_id'] == c_id]['valor_suscripcion'].iloc[0])
            
            datos = {
                "cliente_id": c_id, "ano": int(ano), "mes": int(mes),
                "estado_envio": "PENDIENTE PREPARACION", "pagado": "NO", "envio_pagado": "NO",
                "valor_envio": 0.0, "valor_extras": 0.0, "monto_total": val_sub,
                "fecha_asignacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            conn.table("asignaciones").insert(datos).execute()
            creados += 1
        except: errores += 1
    cargar_asignaciones_mes.clear()
    if creados > 0: return True, f"Se iniciaron {creados} suscripciones."
    else: return False, "Todos los clientes suscritos ya estaban creados para este mes."

def asignar_libro_a_suscripcion(asignacion_id, cliente_id, libro_id, titulo, autor, ano, mes, stock_actual, libros_extras=[], valor_extras_calculado=0.0, extras_texto_libre=""):
    conn = get_db_connection()
    try:
        id_asig_py, id_cliente_py, id_libro_py = int(asignacion_id), int(cliente_id), int(libro_id)
        
        # 1. Descontar libro principal
        conn.table("libros").update({"stock": int(stock_actual) - 1}).eq("libro_id", id_libro_py).execute()
        
        # 2. Gestionar Libros Extras (del catálogo)
        nombres_extras = []
        for extra_titulo in libros_extras:
            res_le = conn.table("libros").select("libro_id, stock, autor").eq("titulo", extra_titulo).execute()
            if res_le.data:
                le_id, le_stock, le_autor = res_le.data[0]['libro_id'], res_le.data[0]['stock'], res_le.data[0]['autor']
                conn.table("libros").update({"stock": le_stock - 1}).eq("libro_id", le_id).execute()
                res_hist_le = conn.table("librero_historico").select("registro_id").eq("cliente_id", id_cliente_py).eq("libro_id", le_id).execute()
                if not res_hist_le.data:
                    conn.table("librero_historico").insert({
                        "cliente_id": id_cliente_py, "libro_id": le_id,
                        "autor_historico": limpiar_texto(le_autor), "origen": f"ASIGNACIÓN EXTRA {mes}/{ano}"
                    }).execute()
                nombres_extras.append(extra_titulo)

        # Añadir también los extras en texto libre a la lista de nombres
        if extras_texto_libre.strip():
            nombres_extras.append(limpiar_texto(extras_texto_libre))

        # 3. Traer datos actuales de asignación para sumar
        res_asig = conn.table("asignaciones").select("extras, valor_extras, valor_envio").eq("asignacion_id", id_asig_py).execute()
        extras_actual = res_asig.data[0].get('extras', '') or ''
        v_ext_actual = float(res_asig.data[0].get('valor_extras') or 0.0)
        v_env_actual = float(res_asig.data[0].get('valor_envio') or 0.0)
        
        # Recalcular Total
        res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", id_cliente_py).execute()
        val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
        
        nuevo_valor_extras = v_ext_actual + valor_extras_calculado
        nuevo_monto_total = val_sub + v_env_actual + nuevo_valor_extras
        
        # Actualizar Asignación
        datos_update = {
            "libro_suscripcion_id": id_libro_py,
            "valor_extras": nuevo_valor_extras,
            "monto_total": nuevo_monto_total
        }
        if nombres_extras:
            datos_update["extras"] = extras_actual + (" | " if extras_actual else "") + "EXTRAS: " + ", ".join(nombres_extras)
            
        conn.table("asignaciones").update(datos_update).eq("asignacion_id", id_asig_py).execute()
        
        # 4. Guardar principal en histórico
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

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes, texto_extras):
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            res_l = conn.table("libros").select("stock").eq("libro_id", int(libro_id)).execute()
            if res_l.data:
                conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", int(libro_id)).execute()
            conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).eq("origen", f"ASIGNACIÓN {mes}/{ano}").execute()
            
        # Intentar devolver stock de extras del catálogo
        if texto_extras and "EXTRAS:" in str(texto_extras):
            partes = str(texto_extras).split("EXTRAS:")
            if len(partes) > 1:
                titulos = partes[1].split(",")
                for t in titulos:
                    t = t.strip()
                    res_le = conn.table("libros").select("libro_id, stock").eq("titulo", t).execute()
                    if res_le.data:
                        le_id, le_stock = res_le.data[0]['libro_id'], res_le.data[0]['stock']
                        conn.table("libros").update({"stock": le_stock + 1}).eq("libro_id", le_id).execute()
                        conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", le_id).eq("origen", f"ASIGNACIÓN EXTRA {mes}/{ano}").execute()

        conn.table("asignaciones").delete().eq("asignacion_id", int(asignacion_id)).execute()
        cargar_asignaciones_mes.clear()
        return True, ""
    except Exception as e: return False, str(e)

def actualizar_asignaciones_batch(df_editado, df_mes_completo):
    df_original = st.session_state.get('asignaciones_original')
    if df_original is None: return 0
    df_original_comp = df_original.set_index('asignacion_id')
    df_editado_comp = df_editado.set_index('asignacion_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    df_valores = cargar_valores_suscripcion()
    updates = 0
    
    for a_id, row in filas_cambiadas.iterrows():
        try:
            c_id = df_mes_completo[df_mes_completo['asignacion_id'] == a_id].iloc[0]['cliente_id']
            val_sub = 0.0
            if not df_valores.empty and c_id in df_valores['cliente_id'].values:
                val_sub = float(df_valores[df_valores['cliente_id'] == c_id]['valor_suscripcion'].iloc[0])
            
            # Aseguramos que son números reales
            v_envio = float(row.get('valor_envio', 0.0))
            v_extras = float(row.get('valor_extras', 0.0))
            m_total = val_sub + v_envio + v_extras
            
            datos = {
                "estado_envio": str(row['estado_envio']).upper(), 
                "pagado": str(row['pagado']).upper(),
                "envio_pagado": str(row['envio_pagado']).upper(), 
                "extras": str(row.get('extras', '')).upper(),
                "comentario": str(row.get('comentario', '')).upper(),
                "valor_envio": v_envio, "valor_extras": v_extras, "monto_total": m_total
            }
            conn.table("asignaciones").update(datos).eq("asignacion_id", int(a_id)).execute()
            updates += 1
        except: continue
    if updates > 0: cargar_asignaciones_mes.clear()
    return updates

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
        # Formateo estricto para evitar errores en st.data_editor
        df_mes['pagado'] = df_mes['pagado'].apply(mapear_sino)
        df_mes['envio_pagado'] = df_mes['envio_pagado'].apply(mapear_sino)
        df_mes['estado_envio'] = df_mes['estado_envio'].apply(lambda x: str(x).upper())
        df_mes['extras'] = df_mes['extras'].fillna("").astype(str)
        df_mes['comentario'] = df_mes['comentario'].fillna("").astype(str)
        
        # FORZAMOS A TIPO FLOAT PARA QUE STREAMLIT PERMITA EDITAR COMO NÚMEROS
        df_mes['valor_envio'] = pd.to_numeric(df_mes.get('valor_envio', 0), errors='coerce').fillna(0.0)
        df_mes['valor_extras'] = pd.to_numeric(df_mes.get('valor_extras', 0), errors='coerce').fillna(0.0)
        df_mes['monto_total'] = pd.to_numeric(df_mes.get('monto_total', 0), errors='coerce').fillna(0.0)

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

    if mes_esta_cerrado: st.error(f"🔒 **MES CERRADO:** {mes_sel.upper()} {ano_sel} está bloqueado.", icon="🔒")

    opcion_menu = st.selectbox("👉 SELECCIONA LA ACCIÓN QUE DESEAS REALIZAR:", ["📋 Gestión (Tabla Editable)", "📚 Asignar Libros", "🚀 Comenzar Mes", "🗑️ Eliminar Registro", "🔒 Cierre de Mes"])
    st.markdown("---")

    if opcion_menu == "📋 Gestión (Tabla Editable)":
        st.markdown(f"#### 📋 Gestión del Mes ({mes_sel} {ano_sel})")
        if df_mes.empty: st.warning("No hay registros para este mes.")
        else:
            col_fa1, col_fa2, col_fa3 = st.columns(3)
            filtro_estado = col_fa1.selectbox("Estado del Envío:", ["Todos"] + df_mes['estado_envio'].unique().tolist())
            filtro_pagado = col_fa2.selectbox("Estado de Pago:", ["Todos"] + df_mes['pagado'].unique().tolist())
            filtro_libro = col_fa3.selectbox("Libro Asignado:", ["Todos", "Sin Libro Asignado", "Con Libro Asignado"])
            
            df_filtrado = df_mes.copy()
            if filtro_estado != "Todos": df_filtrado = df_filtrado[df_filtrado['estado_envio'] == filtro_estado]
            if filtro_pagado != "Todos": df_filtrado = df_filtrado[df_filtrado['pagado'] == filtro_pagado]
            if filtro_libro == "Sin Libro Asignado": df_filtrado = df_filtrado[df_filtrado['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
            elif filtro_libro == "Con Libro Asignado": df_filtrado = df_filtrado[df_filtrado['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR"]
            
            st.caption("Doble clic en las celdas para modificar. El Monto Total se calculará automáticamente al guardar.")
            
            columnas_mostrar = ['asignacion_id', 'nombre_cliente', 'titulo_libro', 'estado_envio', 'pagado', 'envio_pagado', 'valor_envio', 'valor_extras', 'monto_total', 'extras', 'comentario']
            df_mostrar = df_filtrado[columnas_mostrar].copy()
            if 'asignaciones_original' not in st.session_state or not st.session_state.asignaciones_original.equals(df_mostrar):
                st.session_state.asignaciones_original = df_mostrar.copy()
                
            config_cols = {
                "estado_envio": st.column_config.SelectboxColumn("Estado", options=["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO"], required=True),
                "pagado": st.column_config.SelectboxColumn("Pagado", options=["SI", "NO", "ABONO"], required=True),
                "envio_pagado": st.column_config.SelectboxColumn("Envío Pagado", options=["SI", "NO", "NO APLICA"], required=True),
                "valor_envio": st.column_config.NumberColumn("Valor Envío ($)", format="$%.0f", min_value=0.0),
                "valor_extras": st.column_config.NumberColumn("Valor Extras ($)", format="$%.0f", min_value=0.0),
                "monto_total": st.column_config.NumberColumn("Monto Total ($)", format="$%.0f")
            }
                
            df_editado = st.data_editor(
                df_mostrar, 
                disabled=columnas_mostrar if mes_esta_cerrado else ['asignacion_id', 'nombre_cliente', 'titulo_libro', 'monto_total'], 
                column_config=config_cols, 
                hide_index=True, use_container_width=True
            )
            
            if not df_mostrar.equals(df_editado) and not mes_esta_cerrado:
                if st.button("💾 Guardar Cambios", type="primary"):
                    with st.spinner("Calculando totales..."):
                        num = actualizar_asignaciones_batch(df_editado, df_mes)
                        st.success(f"¡Se actualizaron {num} registros!"), st.rerun()

    elif opcion_menu == "📚 Asignar Libros":
        if mes_esta_cerrado: st.warning("Mes cerrado. No puedes asignar.")
        else:
            if df_mes.empty: st.info("No hay suscripciones.")
            else:
                df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
                st.metric("Pendientes", len(df_pendientes))
                if not df_pendientes.empty:
                    with st.container(border=True):
                        st.markdown("**🎲 Asignación Masiva**")
                        if st.button("Aplicar al Azar a todos", type="primary"):
                            ex, msg = asignar_al_azar(df_pendientes, cargar_libros_disponibles(), ano_sel, mes_num)
                            if ex: st.success(msg), st.balloons(), st.rerun()
                            else: st.error(msg)
                    
                    with st.container(border=True):
                        st.markdown("**✏️ Asignación Manual (con extras)**")
                        df_libros = cargar_libros_disponibles()
                        asig_manual_sel = st.selectbox("Cliente Pendiente:", [""] + df_pendientes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']}", axis=1).tolist())
                        libro_manual_sel = st.selectbox("Libro Principal:", [""] + df_libros['titulo'].tolist())
                        
                        st.markdown("---")
                        st.markdown("**Libros Extras (Del Catálogo)**")
                        st.caption("Si eliges libros de aquí, se cobrarán y descontarán de tu stock automáticamente.")
                        libros_extras_sel = st.multiselect("Seleccionar extras del catálogo:", [t for t in df_libros['titulo'].tolist() if t != ""])
                        
                        st.markdown("**Extras Libres (No en Catálogo)**")
                        st.caption("Ejemplo: 'Lápiz varita mágica, Libro XYZ'. Se agregarán como texto y podrás sumar su valor manual.")
                        extras_texto_libre = st.text_input("Extras fuera de catálogo (separados por coma):")
                        valor_extras_libres = st.number_input("Valor a cobrar por estos extras libres ($):", min_value=0.0, step=500.0)
                        
                        if st.button("Asignar estos libros", type="primary"):
                            if asig_manual_sel and libro_manual_sel:
                                id_asig = int(asig_manual_sel.split(" - ")[0].replace("ID:", ""))
                                id_cliente = int(df_pendientes[df_pendientes['asignacion_id'] == id_asig].iloc[0]['cliente_id'])
                                l_data = df_libros[df_libros['titulo'] == libro_manual_sel].iloc[0]
                                
                                val_calculado_extras = valor_extras_libres
                                for extr in libros_extras_sel: val_calculado_extras += float(df_libros[df_libros['titulo'] == extr].iloc[0]['precio'])
                                
                                ex, err = asignar_libro_a_suscripcion(
                                    id_asig, id_cliente, l_data['libro_id'], l_data['titulo'], 
                                    l_data.get('autor', ''), ano_sel, mes_num, l_data['stock'], 
                                    libros_extras_sel, val_calculado_extras, extras_texto_libre
                                )
                                if ex: st.success("¡Asignación completada!"), st.rerun()
                                else: st.error(err)
                else: st.success("¡Todos listos!")

    elif opcion_menu == "🚀 Comenzar Mes":
        if mes_esta_cerrado: st.warning("Mes cerrado.")
        else:
            st.info(f"Se crearán filas para clientes 'SUSCRITO' y se cargará su cobro base en Monto Total.")
            if st.button("Generar Registros del Mes", type="primary"):
                ex, msg = comenzar_mes(ano_sel, mes_num)
                if ex: st.success(msg), st.balloons(), st.rerun()
                else: st.warning(msg)

    elif opcion_menu == "🗑️ Eliminar Registro":
        if mes_esta_cerrado: st.warning("Mes cerrado.")
        else:
            if not df_mes.empty:
                asig_eliminar = st.selectbox("Selecciona registro:", [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre_cliente']} | {x['titulo_libro']}", axis=1).tolist())
                if asig_eliminar and st.button("🟥 ELIMINAR DEFINITIVAMENTE", type="primary"):
                    id_asig = int(asig_eliminar.split(" | ")[0].replace("ID:", ""))
                    row = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                    ex, err = eliminar_asignacion(id_asig, row.get('libro_suscripcion_id'), row['cliente_id'], ano_sel, mes_num, row.get('extras', ''))
                    if ex: st.success("Registro eliminado."), st.rerun()
                    else: st.error(err)

    elif opcion_menu == "🔒 Cierre de Mes":
        st.markdown("#### 🔒 Control de Cierre")
        if mes_esta_cerrado:
            st.success(f"El mes {mes_sel} {ano_sel} está **CERRADO**.")
            if st.button("🔓 Reabrir Mes", type="secondary"):
                ex, msg = cambiar_estado_mes(ano_sel, mes_num, False)
                if ex: st.success(msg), st.rerun()
                else: st.error(msg)
        else:
            st.info(f"El mes {mes_sel} {ano_sel} está **ABIERTO**.")
            if st.button("🔒 CERRAR MES DEFINITIVAMENTE", type="primary"):
                ex, msg = cambiar_estado_mes(ano_sel, mes_num, True)
                if ex: st.success(msg), st.balloons(), st.rerun()
                else: st.error(msg)