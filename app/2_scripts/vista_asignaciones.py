import streamlit as st
import pandas as pd
import random
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto

def actualizar_estado_envio(asignacion_id, nuevo_estado):
    """Actualiza el estado del envío en la base de datos y refresca la vista."""
    conn = get_db_connection()
    try:
        conn.table("asignaciones").update({"estado_envio": nuevo_estado}).eq("asignacion_id", asignacion_id).execute()
        st.toast(f"✅ Envío actualizado a '{nuevo_estado}'")
        # Limpiamos la cache para que los datos se recarguen
        cargar_asignaciones_mes.clear()
    except Exception as e:
        st.error(f"Error al actualizar: {e}")

def cargar_datos_para_kanban(ano, mes):
    """Carga y une los datos de asignaciones y clientes para el Kanban."""
    conn = get_db_connection()
    try:
        # Traemos las asignaciones del mes con la info necesaria
        res_asig = conn.table("asignaciones").select("asignacion_id, cliente_id, fecha_asignacion, estado_envio").eq("ano", ano).eq("mes", mes).order("fecha_asignacion", desc=True).execute()
        df_asig = pd.DataFrame(res_asig.data) if res_asig.data else pd.DataFrame()

        if df_asig.empty:
            return pd.DataFrame()

        # Traemos clientes para cruzar nombres y direcciones
        ids_clientes = df_asig['cliente_id'].unique().tolist()
        res_clientes = conn.table("clientes").select("cliente_id, nombre, direccion").in_("cliente_id", ids_clientes).execute()
        df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()

        if not df_clientes.empty:
            df_completo = df_asig.merge(df_clientes, on="cliente_id", how="left")
            # Forzamos un estado por defecto si es nulo, para que aparezca en la primera columna
            df_completo['estado_envio'] = df_completo['estado_envio'].fillna('PENDIENTE PREPARACION').str.upper()
            return df_completo
            
        return df_asig # Devolvemos solo asignaciones si no hay clientes
    except:
        return pd.DataFrame()

# --- FUNCIONES DE BASE DE DATOS ---
@st.cache_data(ttl=60)
def cargar_clientes_suscritos():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, status").eq("status", "ACTIVA").execute()
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
def cargar_catalogo_completo_libros(incluir_sin_stock=False):
    """Carga los libros. Permite incluir los que no tienen stock si se solicita."""
    conn = get_db_connection()
    try:
        query = conn.table("libros").select("libro_id, titulo, autor, precio, stock")
        if not incluir_sin_stock:
            query = query.gt("stock", 0)
        res = query.execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_libros_filtrados_para_cliente(cliente_id, incluir_sin_stock=False):
    """Filtra el catálogo quitando los libros que el cliente ya tiene. Devuelve también sus gustos."""
    df_catalogo = cargar_catalogo_completo_libros(incluir_sin_stock)
    if df_catalogo.empty or not cliente_id:
        return df_catalogo, []

    conn = get_db_connection()
    try:
        # 1. Quitar libros que ya tiene
        res_historial = conn.table("librero_historico").select("libro_id").eq("cliente_id", cliente_id).execute()
        if res_historial.data:
            ids_poseidos = {item['libro_id'] for item in res_historial.data if item['libro_id']}
            df_catalogo = df_catalogo[~df_catalogo['libro_id'].isin(ids_poseidos)]

        # 2. Obtener géneros de preferencia de la clienta
        res_susc = conn.table("suscripciones").select("generos_preferencia").eq("cliente_id", cliente_id).execute()
        generos_pref = []
        if res_susc.data and res_susc.data[0].get('generos_preferencia'):
            generos_pref = [g.strip().upper() for g in res_susc.data[0]['generos_preferencia'].split(',')]
        
        return df_catalogo, generos_pref
    except:
        return df_catalogo, []

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
    except Exception as e: return pd.DataFrame()

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
    if df_suscritos.empty: return False, "No hay clientes activos."
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
    else: return False, "Todas las suscripciones ya estaban creadas."

def asignar_libro_principal(asignacion_id, cliente_id, libro_id, stock_actual, ano, mes, titulo, autor):
    conn = get_db_connection()
    try:
        a_id, c_id, l_id_py = int(asignacion_id), int(cliente_id), int(libro_id)
        
        conn.table("libros").update({"stock": int(stock_actual) - 1}).eq("libro_id", l_id_py).execute()
        conn.table("asignaciones").update({"libro_suscripcion_id": l_id_py}).eq("asignacion_id", a_id).execute()
        
        res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", c_id).eq("libro_id", l_id_py).execute()
        if not res_hist.data:
            conn.table("librero_historico").insert({"cliente_id": c_id, "libro_id": l_id_py, "autor_historico": limpiar_texto(autor), "origen": f"ASIGNACIÓN {mes}/{ano}"}).execute()
            
        cargar_asignaciones_mes.clear(); cargar_catalogo_completo_libros.clear(); cargar_libros_filtrados_para_cliente.clear()
        return True, ""
    except Exception as e: return False, str(e)

def asignar_al_azar_inteligente(df_pendientes, ano, mes):
    if df_pendientes.empty: return False, "No hay pendientes para asignar."
    exitos = 0
    for _, asig in df_pendientes.iterrows():
        cliente_id = int(asig['cliente_id'])
        # La asignación al azar NUNCA usa libros con stock 0 por seguridad
        df_libros_seguros, generos_pref = cargar_libros_filtrados_para_cliente(cliente_id, incluir_sin_stock=False)
        if df_libros_seguros.empty: continue

        df_sugeridos = pd.DataFrame()
        if generos_pref:
            patron = '|'.join(generos_pref)
            df_sugeridos = df_libros_seguros[df_libros_seguros['titulo'].str.contains(patron, case=False, na=False)]

        if not df_sugeridos.empty: libro_elegido = df_sugeridos.sample(1).iloc[0]
        else: libro_elegido = df_libros_seguros.sample(1).iloc[0]
        
        success, _ = asignar_libro_principal(
            int(asig['asignacion_id']), cliente_id, int(libro_elegido['libro_id']),
            int(libro_elegido['stock']), ano, mes, libro_elegido['titulo'], libro_elegido.get('autor', '')
        )
        if success: exitos += 1
    
    if exitos > 0: return True, f"Se asignaron {exitos} libros al azar."
    else: return False, "No se pudo asignar ningún libro."

def gestionar_extras_y_envio(asignacion_id, cliente_id, ano, mes, libros_extras_cat, texto_libre, valor_total_extras_a_sumar, nuevo_envio):
    conn = get_db_connection()
    try:
        a_id, c_id = int(asignacion_id), int(cliente_id)
        nombres_extras = []
        
        for titulo in libros_extras_cat:
            res_le = conn.table("libros").select("libro_id, stock, autor").eq("titulo", titulo).execute()
            if res_le.data:
                le_id, le_stock, le_autor = res_le.data[0]['libro_id'], res_le.data[0]['stock'], res_le.data[0]['autor']
                conn.table("libros").update({"stock": le_stock - 1}).eq("libro_id", le_id).execute()
                res_hist_le = conn.table("librero_historico").select("registro_id").eq("cliente_id", c_id).eq("libro_id", le_id).execute()
                if not res_hist_le.data:
                    conn.table("librero_historico").insert({"cliente_id": c_id, "libro_id": le_id, "autor_historico": limpiar_texto(le_autor), "origen": f"ASIGNACIÓN EXTRA {mes}/{ano}"}).execute()
                nombres_extras.append(titulo)

        if texto_libre.strip():
            items_libres = [x.strip() for x in texto_libre.split(",")]
            for item in items_libres:
                if not item: continue
                titulo_cl = limpiar_texto(item)
                res_exist = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_cl).execute()
                if res_exist.data:
                    le_id, le_stock = res_exist.data[0]['libro_id'], res_exist.data[0]['stock']
                    conn.table("libros").update({"stock": le_stock - 1}).eq("libro_id", le_id).execute()
                else:
                    res_new = conn.table("libros").insert({"titulo": titulo_cl, "autor": "EXTRA/NUEVO", "precio": 0, "stock": 0}).execute()
                    le_id = res_new.data[0]['libro_id']
                
                res_hist_le = conn.table("librero_historico").select("registro_id").eq("cliente_id", c_id).eq("libro_id", le_id).execute()
                if not res_hist_le.data:
                    conn.table("librero_historico").insert({"cliente_id": c_id, "libro_id": le_id, "autor_historico": "EXTRA/NUEVO", "origen": f"ASIGNACIÓN EXTRA {mes}/{ano}"}).execute()
                nombres_extras.append(titulo_cl)

        res_asig = conn.table("asignaciones").select("extras, valor_extras").eq("asignacion_id", a_id).execute()
        extras_actual = str(res_asig.data[0].get('extras', ''))
        v_ext_actual = float(res_asig.data[0].get('valor_extras') or 0.0)
        
        res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", c_id).execute()
        val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
        
        nuevo_valor_extras = v_ext_actual + float(valor_total_extras_a_sumar)
        nuevo_monto_total = val_sub + float(nuevo_envio) + nuevo_valor_extras
        
        datos_update = {"valor_envio": float(nuevo_envio), "valor_extras": nuevo_valor_extras, "monto_total": nuevo_monto_total}
        
        if nombres_extras:
            if "EXTRAS:" in extras_actual: datos_update["extras"] = extras_actual + ", " + ", ".join(nombres_extras)
            else: datos_update["extras"] = "EXTRAS: " + ", ".join(nombres_extras)
                
        conn.table("asignaciones").update(datos_update).eq("asignacion_id", a_id).execute()
        cargar_asignaciones_mes.clear(); cargar_catalogo_completo_libros.clear(); cargar_libros_filtrados_para_cliente.clear()
        return True, ""
    except Exception as e: return False, str(e)

def quitar_un_libro(asignacion_id, cliente_id, ano, mes, tipo, titulo_quitar, monto_descuento=0.0):
    conn = get_db_connection()
    try:
        res_l = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_quitar).execute()
        if res_l.data:
            l_id = res_l.data[0]['libro_id']
            conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", l_id).execute()
            origen = f"ASIGNACIÓN {mes}/{ano}" if tipo == "PRINCIPAL" else f"ASIGNACIÓN EXTRA {mes}/{ano}"
            conn.table("librero_historico").delete().eq("cliente_id", cliente_id).eq("libro_id", l_id).eq("origen", origen).execute()

        res_asig = conn.table("asignaciones").select("*").eq("asignacion_id", asignacion_id).execute()[0]
        
        if tipo == "PRINCIPAL":
            conn.table("asignaciones").update({"libro_suscripcion_id": None}).eq("asignacion_id", asignacion_id).execute()
        else:
            extras_str = str(res_asig.get('extras', ''))
            if "EXTRAS:" in extras_str:
                lista_extras = extras_str.replace("EXTRAS:", "").split(",")
                nueva_lista = [x.strip() for x in lista_extras if x.strip() != titulo_quitar]
                nuevo_texto = "EXTRAS: " + ", ".join(nueva_lista) if nueva_lista else ""
                
                v_extras_actual = float(res_asig.get('valor_extras') or 0.0)
                nuevo_v_extras = max(0.0, v_extras_actual - float(monto_descuento))
                
                res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", cliente_id).execute()
                val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
                nuevo_total = val_sub + float(res_asig.get('valor_envio', 0.0) or 0.0) + nuevo_v_extras
                
                conn.table("asignaciones").update({"extras": nuevo_texto, "valor_extras": nuevo_v_extras, "monto_total": nuevo_total}).eq("asignacion_id", asignacion_id).execute()
                
        cargar_asignaciones_mes.clear(); cargar_catalogo_completo_libros.clear(); cargar_libros_filtrados_para_cliente.clear()
        return True, ""
    except Exception as e: return False, str(e)

def desasignar_libros(asignacion_id, libro_id, cliente_id, ano, mes, texto_extras):
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            res_l = conn.table("libros").select("stock").eq("libro_id", int(libro_id)).execute()
            if res_l.data:
                conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", int(libro_id)).execute()
            conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).eq("origen", f"ASIGNACIÓN {mes}/{ano}").execute()
            
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

        res_asig = conn.table("asignaciones").select("valor_envio").eq("asignacion_id", int(asignacion_id)).execute()
        v_envio = float(res_asig.data[0].get('valor_envio', 0.0)) if res_asig.data else 0.0
        
        res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", int(cliente_id)).execute()
        val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
        
        conn.table("asignaciones").update({"libro_suscripcion_id": None, "extras": "", "valor_extras": 0.0, "monto_total": val_sub + v_envio}).eq("asignacion_id", int(asignacion_id)).execute()
        cargar_asignaciones_mes.clear(); cargar_catalogo_completo_libros.clear(); cargar_libros_filtrados_para_cliente.clear()
        return True, ""
    except Exception as e: return False, str(e)

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes, texto_extras):
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            res_l = conn.table("libros").select("stock").eq("libro_id", int(libro_id)).execute()
            if res_l.data:
                conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", int(libro_id)).execute()
            conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).eq("origen", f"ASIGNACIÓN {mes}/{ano}").execute()
            
        if texto_extras and "EXTRAS:" in str(texto_extras):
            titulos = str(texto_extras).replace("EXTRAS:", "").split(",")
            for t in titulos:
                if not t.strip(): continue
                res_le = conn.table("libros").select("libro_id, stock").eq("titulo", t.strip()).execute()
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
    diff_mask = df_original.set_index('asignacion_id').ne(df_editado.set_index('asignacion_id')).any(axis=1)
    filas_cambiadas = df_editado.set_index('asignacion_id')[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates = 0
    for a_id, row in filas_cambiadas.iterrows():
        try:
            c_id = df_mes_completo[df_mes_completo['asignacion_id'] == a_id].iloc[0]['cliente_id']
            res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", int(c_id)).execute()
            val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
            
            v_envio = float(row.get('valor_envio', 0.0) or 0.0)
            v_extras = float(row.get('valor_extras', 0.0) or 0.0)
            m_total = val_sub + v_envio + v_extras 
            
            datos = {
                "estado_envio": str(row['estado_envio']).upper(), "pagado": str(row['pagado']).upper(),
                "envio_pagado": str(row['envio_pagado']).upper(), "extras": str(row.get('extras', '')).upper(),
                "comentario": str(row.get('comentario', '')),
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
        df_mes['pagado'] = df_mes['pagado'].apply(mapear_sino)
        df_mes['envio_pagado'] = df_mes['envio_pagado'].apply(mapear_sino)
        df_mes['estado_envio'] = df_mes['estado_envio'].apply(lambda x: str(x).upper())
        df_mes['extras'] = df_mes['extras'].fillna("").astype(str)
        df_mes['comentario'] = df_mes['comentario'].apply(lambda x: "" if pd.isna(x) or str(x).upper() == "NONE" else str(x))
        
        df_mes['valor_envio'] = pd.to_numeric(df_mes.get('valor_envio', 0), errors='coerce').fillna(0.0)
        df_mes['valor_extras'] = pd.to_numeric(df_mes.get('valor_extras', 0), errors='coerce').fillna(0.0)
        df_mes['monto_total'] = pd.to_numeric(df_mes.get('monto_total', 0), errors='coerce').fillna(0.0)

        cajas_pagadas = len(df_mes[df_mes['pagado'] == 'SI'])
        cajas_pendientes = len(df_mes[df_mes['estado_envio'].isin(['PENDIENTE PREPARACION', 'EN PREPARACION'])])
        cajas_listas = len(df_mes[df_mes['estado_envio'].isin(['POR ENVIAR', 'POR RETIRAR'])])

        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        c_res1.metric("📦 Total Cajas", len(df_mes))
        c_res2.metric("💳 Pagadas", f"{cajas_pagadas} / {len(df_mes)}")
        c_res3.metric("⏳ Por Preparar", cajas_pendientes)
        c_res4.metric("✅ Listas para Enviar", cajas_listas)
        st.markdown("---")

    if mes_esta_cerrado: st.error(f"🔒 **MES CERRADO:** {mes_sel.upper()} {ano_sel} está bloqueado.", icon="🔒")

    opciones_menu = [
        "🚚 Tablero de Logística (Kanban)",
        "📋 Gestión (Tabla Editable)", 
        "📖 Asignar Libro Principal", 
        "➕ Agregar Extras y Envío", 
        "🚀 🚀 Generar / Actualizar Mes", 
        "🗑️ Eliminar/Quitar Libros", 
        "🔒 Cierre de Mes"
    ]
    opcion_menu = st.selectbox("👉 SELECCIONA LA ACCIÓN QUE DESEAS REALIZAR:", opciones_menu)
    st.markdown("---")
    # ==========================================================
    # K. VISTA KANBAN DE LOGÍSTICA
    # ==========================================================
    if opcion_menu == "🚚 Tablero de Logística (Kanban)":
        st.info("Gestiona los despachos de forma visual. Mueve las tarjetas entre columnas con los botones de acción.")
        df_kanban = cargar_datos_para_kanban(ano_sel, mes_num)

        if df_kanban.empty:
            st.warning("No hay asignaciones en este mes para mostrar en el tablero.")
        else:
            # Definimos las columnas visuales del Kanban
            col_pendientes, col_listas, col_finalizadas = st.columns(3)

            # Columna 1: Pendientes de Preparación
            with col_pendientes:
                st.markdown("<h4 style='text-align: center; color: #D32F2F; background-color: #FFEBEE; padding: 10px; border-radius: 5px;'>⏳ POR PREPARAR</h4>", unsafe_allow_html=True)
                # Filtramos los estados que corresponden a esta columna
                df_filtrado = df_kanban[df_kanban['estado_envio'].isin(['PENDIENTE PREPARACION', 'EN PREPARACION'])]
                for _, row in df_filtrado.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{row.get('nombre', 'Cliente Desconocido')}**")
                        st.caption(f"📍 {row.get('direccion', 'Sin dirección')}")
                        if st.button("▶️ Mover a 'Listo'", key=f"btn_p_{row['asignacion_id']}", use_container_width=True):
                            actualizar_estado_envio(row['asignacion_id'], 'POR ENVIAR')
                            st.rerun()

            # Columna 2: Listas para Enviar/Retirar
            with col_listas:
                st.markdown("<h4 style='text-align: center; color: #1976D2; background-color: #E3F2FD; padding: 10px; border-radius: 5px;'>✅ LISTO</h4>", unsafe_allow_html=True)
                df_filtrado = df_kanban[df_kanban['estado_envio'].isin(['POR ENVIAR', 'POR RETIRAR'])]
                for _, row in df_filtrado.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{row.get('nombre_cliente', 'Cliente Desconocido')}**")
                        st.caption(f"📦 Estado actual: {row['estado_envio']}")
                        c1, c2 = st.columns(2)
                        # Botón para retroceder
                        if c1.button("◀️ Volver", key=f"btn_l_back_{row['asignacion_id']}", use_container_width=True):
                            actualizar_estado_envio(row['asignacion_id'], 'EN PREPARACION')
                            st.rerun()
                        # Botón para avanzar
                        if c2.button("▶️ Finalizar", key=f"btn_l_fwd_{row['asignacion_id']}", type="primary", use_container_width=True):
                            nuevo_estado = 'ENVIADO' if row['estado_envio'] == 'POR ENVIAR' else 'RETIRADO'
                            actualizar_estado_envio(row['asignacion_id'], nuevo_estado)
                            st.rerun()
            
            # Columna 3: Finalizadas
            with col_finalizadas:
                st.markdown("<h4 style='text-align: center; color: #388E3C; background-color: #E8F5E9; padding: 10px; border-radius: 5px;'>🏁 FINALIZADO</h4>", unsafe_allow_html=True)
                df_filtrado = df_kanban[df_kanban['estado_envio'].isin(['ENVIADO', 'RETIRADO'])]
                # Mostramos solo las últimas 15 para no saturar la vista
                for _, row in df_filtrado.head(15).iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{row.get('nombre_cliente', 'Cliente Desconocido')}**")
                        st.caption(f"🎉 {row['estado_envio']}")
                        if st.button(" deshacer", key=f"btn_f_back_{row['asignacion_id']}", use_container_width=True):
                            nuevo_estado = 'POR ENVIAR' if row['estado_envio'] == 'ENVIADO' else 'POR RETIRAR'
                            actualizar_estado_envio(row['asignacion_id'], nuevo_estado)
                            st.rerun()
                if len(df_filtrado) > 15:
                    st.caption(f"...y {len(df_filtrado) - 15} más.")
    # ==========================================================
    # 1. TABLA EDITABLE
    # ==========================================================
    if opcion_menu == "📋 Gestión (Tabla Editable)":
        if df_mes.empty: st.warning("No hay registros para este mes.")
        else:
            col_fa1, col_fa2, col_fa3, col_fa4 = st.columns(4)
            f_nombre = col_fa1.text_input("🔍 Buscar Cliente:")
            filtro_estado = col_fa2.selectbox("Estado Envío:", ["Todos"] + df_mes['estado_envio'].unique().tolist())
            filtro_pagado = col_fa3.selectbox("Pago:", ["Todos"] + df_mes['pagado'].unique().tolist())
            filtro_libro = col_fa4.selectbox("Asignación:", ["Todos", "Sin Libro", "Con Libro"])
            
            df_filtrado = df_mes.copy()
            if f_nombre: df_filtrado = df_filtrado[df_filtrado['nombre_cliente'].str.contains(limpiar_texto(f_nombre), case=False, na=False)]
            if filtro_estado != "Todos": df_filtrado = df_filtrado[df_filtrado['estado_envio'] == filtro_estado]
            if filtro_pagado != "Todos": df_filtrado = df_filtrado[df_filtrado['pagado'] == filtro_pagado]
            if filtro_libro == "Sin Libro": df_filtrado = df_filtrado[df_filtrado['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
            elif filtro_libro == "Con Libro": df_filtrado = df_filtrado[df_filtrado['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR"]
            
            st.caption("Doble clic en las celdas para modificar. Los totales se recalcularán automáticamente.")
            columnas_mostrar = ['asignacion_id', 'nombre_cliente', 'titulo_libro', 'estado_envio', 'pagado', 'envio_pagado', 'valor_envio', 'valor_extras', 'monto_total', 'extras', 'comentario']
            df_mostrar = df_filtrado[columnas_mostrar].copy()
            
            if 'asignaciones_original' not in st.session_state or not st.session_state.asignaciones_original.equals(df_mostrar):
                st.session_state.asignaciones_original = df_mostrar.copy()
                
            config_cols = {
                "estado_envio": st.column_config.SelectboxColumn("Estado", options=["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO"], required=True),
                "pagado": st.column_config.SelectboxColumn("Pagado", options=["SI", "NO", "ABONO"], required=True),
                "envio_pagado": st.column_config.SelectboxColumn("Envío Pagado", options=["SI", "NO", "NO APLICA"], required=True),
                "valor_envio": st.column_config.NumberColumn("Valor Envío ($)", format="$%.0f"),
                "valor_extras": st.column_config.NumberColumn("Valor Extras ($)", format="$%.0f"),
                "monto_total": st.column_config.NumberColumn("Monto Total ($)", format="$%.0f"),
                "comentario": st.column_config.TextColumn("Comentario", max_chars=300)
            }
                
            df_editado = st.data_editor(
                df_mostrar, disabled=columnas_mostrar if mes_esta_cerrado else ['asignacion_id', 'nombre_cliente', 'titulo_libro', 'monto_total'], 
                column_config=config_cols, hide_index=True, use_container_width=True
            )
            
            if not df_mostrar.equals(df_editado) and not mes_esta_cerrado:
                if st.button("💾 Guardar Cambios (Recalcula Total)", type="primary"):
                    with st.spinner("Calculando totales..."):
                        num = actualizar_asignaciones_batch(df_editado, df_mes)
                        st.success(f"¡Se actualizaron {num} registros!"), st.rerun()

    # ==========================================================
    # 2. ASIGNAR SOLO LIBRO PRINCIPAL
    # ==========================================================
    elif opcion_menu == "📖 Asignar Libro Principal":
        if mes_esta_cerrado: st.warning("Mes cerrado.")
        else:
            if df_mes.empty: st.info("No hay suscripciones en el mes.")
            else:
                df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
                
                with st.container(border=True):
                    st.markdown("### 🎲 Asignación al Azar (Masiva)")
                    st.caption("Reparte libros disponibles a los clientes pendientes, respetando su historial.")
                    st.metric("Cajas Pendientes", len(df_pendientes))
                    if st.button("Aplicar al Azar a los Pendientes", type="primary", use_container_width=True):
                        if not df_pendientes.empty:
                            ex, msg = asignar_al_azar_inteligente(df_pendientes, ano_sel, mes_num)
                            if ex: st.success(msg), st.balloons(), st.rerun()
                            else: st.error(msg)
                        else: st.warning("No hay clientes pendientes.")

                with st.container(border=True):
                    st.markdown("### ✏️ Asignación Manual")
                    st.info("La lista se filtra por historial y se ordena según los gustos de la clienta.")
                    
                    mostrar_sin_stock = st.checkbox("📦 Mostrar libros sin stock (Permite encargar y dejar stock negativo)", value=False)
                    
                    if not df_pendientes.empty:
                        lista_clientes = [""] + df_pendientes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']}", axis=1).tolist()
                        asig_manual_sel = st.selectbox("1. Seleccionar Cliente Sin Libro:", lista_clientes)
                        
                        opciones_libros_sugeridos = []
                        opciones_libros_otros = []
                        df_libros_seguros = pd.DataFrame()
                        
                        if asig_manual_sel:
                            id_cliente_sel = int(df_pendientes[df_pendientes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']}" == asig_manual_sel, axis=1)].iloc[0]['cliente_id'])
                            df_libros_seguros, generos_pref = cargar_libros_filtrados_para_cliente(id_cliente_sel, mostrar_sin_stock)

                            if not df_libros_seguros.empty:
                                df_libros_seguros['titulo_visual'] = df_libros_seguros.apply(lambda r: f"{r['titulo']} (Stock: {r['stock']})", axis=1)
                                
                                if generos_pref:
                                    st.success(f"Gustos de la clienta: **{', '.join(generos_pref)}**")
                                    patron = '|'.join(generos_pref)
                                    sugeridos_df = df_libros_seguros[df_libros_seguros['titulo'].str.contains(patron, case=False, na=False)]
                                    otros_df = df_libros_seguros[~df_libros_seguros['titulo'].str.contains(patron, case=False, na=False)]
                                    opciones_libros_sugeridos = sugeridos_df['titulo_visual'].tolist()
                                    opciones_libros_otros = otros_df['titulo_visual'].tolist()
                                else:
                                    opciones_libros_otros = df_libros_seguros['titulo_visual'].tolist()

                        todas_las_opciones = []
                        if opciones_libros_sugeridos:
                            todas_las_opciones.append("--- SUGERIDOS ---")
                            todas_las_opciones.extend(opciones_libros_sugeridos)
                        if opciones_libros_otros:
                            todas_las_opciones.append("--- OTROS DISPONIBLES ---")
                            todas_las_opciones.extend(opciones_libros_otros)
                        
                        libro_manual_sel = st.selectbox("2. Seleccionar Libro Principal:", todas_las_opciones)
                        
                        if st.button("✅ Confirmar Asignación de Libro", type="primary"):
                            if asig_manual_sel and libro_manual_sel and "---" not in libro_manual_sel:
                                id_asig = int(asig_manual_sel.split(" - ")[0].replace("ID:", ""))
                                id_cliente = int(df_pendientes[df_pendientes['asignacion_id'] == id_asig].iloc[0]['cliente_id'])
                                
                                l_data = df_libros_seguros[df_libros_seguros['titulo_visual'] == libro_manual_sel].iloc[0]
                                
                                ex, err = asignar_libro_principal(
                                    id_asig, id_cliente, l_data['libro_id'], l_data['stock'], 
                                    ano_sel, mes_num, l_data['titulo'], l_data.get('autor', '')
                                )
                                if ex: st.success("¡Libro asignado con éxito!"), st.rerun()
                                else: st.error(err)
                            else: st.error("Debes seleccionar un cliente y un libro válido.")
                    else: st.success("¡Todos los clientes ya tienen su libro principal!")

    # ==========================================================
    # 3. AGREGAR EXTRAS Y ENVÍO
    # ==========================================================
    elif opcion_menu == "➕ Agregar Extras y Envío":
        if mes_esta_cerrado: st.warning("Mes cerrado.")
        else:
            if df_mes.empty: st.info("No hay suscripciones.")
            else:
                mostrar_sin_stock_ext = st.checkbox("📦 Mostrar libros sin stock en el catálogo", value=False)
                df_catalogo_completo = cargar_catalogo_completo_libros(mostrar_sin_stock_ext)
                
                with st.container(border=True):
                    st.markdown("### ➕ Logística: Libros Extras y Costo de Envío")
                    
                    lista_clientes = [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre_cliente']} ({'SIN LIBRO' if x['titulo_libro']=='⏳ PENDIENTE DE ASIGNAR' else 'CON LIBRO'})", axis=1).tolist()
                    cliente_mod_sel = st.selectbox("1. Seleccionar Cliente:", lista_clientes)
                    
                    st.markdown("#### 📚 Libros Extras")
                    
                    if not df_catalogo_completo.empty:
                        df_catalogo_completo['titulo_visual'] = df_catalogo_completo.apply(lambda r: f"{r['titulo']} (Stock: {r['stock']})", axis=1)
                        opciones_extras = df_catalogo_completo['titulo_visual'].tolist()
                    else: opciones_extras = []
                    
                    libros_extras_sel_vis = st.multiselect("Seleccionar extras del catálogo (Descuenta stock):", [t for t in opciones_extras if t != ""])
                    
                    nuevo_extra_tit = st.text_input("Crear Nuevo Libro Extra (Si no está en catálogo):")
                    nuevo_extra_precio = st.number_input("Precio Oficial del Nuevo Libro ($):", 0) if nuevo_extra_tit else 0
                    
                    st.markdown("#### 🚚 Despacho y Envío")
                    envio_sugerido = 0.0
                    if cliente_mod_sel:
                        id_asig_tmp = int(cliente_mod_sel.split(" - ")[0].replace("ID:", ""))
                        envio_sugerido = float(df_mes[df_mes['asignacion_id'] == id_asig_tmp].iloc[0].get('valor_envio', 0.0))
                        
                    cobro_envio_manual = st.number_input("Establecer Costo de Envío para esta caja ($):", min_value=0.0, step=500.0, value=envio_sugerido)
                    
                    st.markdown("---")
                    if libros_extras_sel_vis or nuevo_extra_tit:
                        st.markdown("#### 💰 Calculadora de Extras")
                        total_cobro_extras = 0.0
                        
                        libros_extras_reales = []
                        for tit_vis in libros_extras_sel_vis:
                            l_data = df_catalogo_completo[df_catalogo_completo['titulo_visual'] == tit_vis].iloc[0]
                            precio_cat = float(l_data['precio'])
                            cobro = st.number_input(f"Cobro por '{l_data['titulo']}':", value=precio_cat)
                            total_cobro_extras += cobro
                            libros_extras_reales.append(l_data['titulo'])
                            
                        if nuevo_extra_tit:
                            cobro_n = st.number_input(f"Cobro por '{nuevo_extra_tit}':", value=float(nuevo_extra_precio))
                            total_cobro_extras += cobro_n
                            
                        st.success(f"**Total a sumar por extras: ${total_cobro_extras:,.0f}**")
                    else:
                        total_cobro_extras = 0.0
                        libros_extras_reales = []
                        st.info("Solo se actualizará el costo de envío.")
                    
                    if st.button("✅ Guardar Extras y Envío", type="primary"):
                        if cliente_mod_sel:
                            id_asig = int(cliente_mod_sel.split(" - ")[0].replace("ID:", ""))
                            id_cliente = int(df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]['cliente_id'])
                            
                            ex, err = gestionar_extras_y_envio(
                                id_asig, id_cliente, ano_sel, mes_num,
                                libros_extras_reales, nuevo_extra_tit, total_cobro_extras, cobro_envio_manual
                            )
                            if ex: st.success("¡Datos guardados! Monto total recalculado."), st.rerun()
                            else: st.error(err)
                        else: st.error("Debes seleccionar un cliente.")

    # ==========================================================
    # 4. COMENZAR MES
    # ==========================================================
    elif opcion_menu == "🚀 Generar / Actualizar Mes":
        if mes_esta_cerrado: 
            st.warning("Mes cerrado. No se pueden generar nuevos registros.")
        else:
            with st.container(border=True):
                st.markdown("### 🚀 Generar Cajas o Agregar Nuevos Clientes")
                st.info(
                    "💡 **¿Cómo usar esta herramienta?**\n\n"
                    "1. **A principio de mes:** Crea las cajas en blanco para todas tus clientas en estado 'ACTIVA'.\n"
                    "2. **A mitad de mes (Clientes Rezagados):** Si se inscriben nuevas clientas y ya hiciste el 'Sync' con Google Sheets, presiona este botón nuevamente.\n\n"
                    "🛡️ **Tranquilidad:** El sistema es inteligente. **Solo agregará a las personas nuevas** sin duplicar, borrar, ni alterar los libros de las cajas que ya tenías armadas.\n\n"
                    "*¡Puedes presionarlo las veces que necesites con total seguridad!*"
                )
                
                if st.button("Crear Registros Faltantes del Mes", type="primary", use_container_width=True):
                    ex, msg = comenzar_mes(ano_sel, mes_num)
                    if ex: 
                        st.success(msg)
                        st.rerun()
                    else: 
                        st.warning(msg)

    # ==========================================================
    # 5. ELIMINAR O QUITAR LIBROS
    # ==========================================================
    elif opcion_menu == "🗑️ Eliminar/Quitar Libros":
        if mes_esta_cerrado: st.warning("Mes cerrado.")
        else:
            st.markdown("#### 🗑️ Opciones de Corrección y Eliminación")
            if not df_mes.empty:
                col_e1, col_e2 = st.columns(2)
                
                with col_e1:
                    with st.container(border=True):
                        st.markdown("##### 🧹 1. Quitar Libros Específicos")
                        st.caption("Quita el libro principal o un extra específico y devuelve el stock.")
                        
                        df_con_algo = df_mes[(df_mes['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR") | (df_mes['extras'] != "")]
                        if not df_con_algo.empty:
                            asig_quitar = st.selectbox("Selecciona cliente:", [""] + df_con_algo.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre_cliente']}", axis=1).tolist())
                            
                            if asig_quitar:
                                id_asig = int(asig_quitar.split(" | ")[0].replace("ID:", ""))
                                row = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                                
                                opciones = []
                                if row['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR":
                                    opciones.append(f"📖 Principal: {row['titulo_libro']}")
                                
                                extras_str = str(row.get('extras', ''))
                                if "EXTRAS:" in extras_str:
                                    titulos = extras_str.replace("EXTRAS:", "").split(",")
                                    for t in titulos:
                                        if t.strip(): opciones.append(f"➕ Extra: {t.strip()}")
                                
                                item_quitar = st.selectbox("¿Qué libro deseas quitar y devolver al stock?", [""] + opciones)
                                
                                if item_quitar:
                                    if "📖 Principal" in item_quitar:
                                        if st.button("🗑️ Quitar Libro Principal", type="primary"):
                                            titulo_prin = item_quitar.replace("📖 Principal: ", "")
                                            ex, err = quitar_un_libro(id_asig, row['cliente_id'], ano_sel, mes_num, "PRINCIPAL", titulo_prin, 0)
                                            if ex: st.success("Libro quitado."), st.rerun()
                                            else: st.error(err)
                                    else:
                                        titulo_ext = item_quitar.replace("➕ Extra: ", "")
                                        precio_cat = 0.0
                                        try:
                                            conn = get_db_connection()
                                            res_le = conn.table("libros").select("precio").eq("titulo", titulo_ext).execute()
                                            if res_le.data: precio_cat = float(res_le.data[0]['precio'])
                                        except: pass
                                        
                                        descuento = st.number_input(f"¿Cuánto dinero descontar de la caja por '{titulo_ext}'?", value=precio_cat)
                                        
                                        if st.button("🗑️ Quitar Libro Extra", type="primary"):
                                            ex, err = quitar_un_libro(id_asig, row['cliente_id'], ano_sel, mes_num, "EXTRA", titulo_ext, descuento)
                                            if ex: st.success("Libro extra quitado."), st.rerun()
                                            else: st.error(err)
                        else: st.info("No hay cajas con libros para quitar.")
                
                with col_e2:
                    with st.container(border=True):
                        st.markdown("##### 🟥 2. Eliminar Fila Completa")
                        st.caption("Borra definitivamente la fila del cliente para este mes.")
                        asig_eliminar = st.selectbox("Selecciona registro a borrar:", [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre_cliente']} | {x['titulo_libro']}", axis=1).tolist())
                        if asig_eliminar and st.button("🟥 ELIMINAR FILA DEFINITIVAMENTE"):
                            id_asig = int(asig_eliminar.split(" | ")[0].replace("ID:", ""))
                            row = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                            ex, err = eliminar_asignacion(id_asig, row.get('libro_suscripcion_id'), row['cliente_id'], ano_sel, mes_num, row.get('extras', ''))
                            if ex: st.success("Registro eliminado."), st.rerun()
                            else: st.error(err)
            else: st.info("No hay registros.")

    elif opcion_menu == "🔒 Cierre de Mes":
        if mes_esta_cerrado:
            st.success(f"El mes {mes_sel} {ano_sel} está **CERRADO**.")
            if st.button("🔓 Reabrir Mes"): cambiar_estado_mes(ano_sel, mes_num, False); st.rerun()
        else:
            st.info(f"El mes {mes_sel} {ano_sel} está **ABIERTO**.")
            if st.button("🔒 CERRAR MES DEFINITIVAMENTE", type="primary"): cambiar_estado_mes(ano_sel, mes_num, True); st.rerun()