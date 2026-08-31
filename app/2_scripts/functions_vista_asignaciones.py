import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error
import json
import re
import pytz

# --- FUNCIONES DE BASE DE DATOS ---

@st.cache_data(ttl=60)
def cargar_clientes_suscritos():
    conn = get_db_connection()
    try:
        res = conn.table("clientes").select("cliente_id, nombre, status").eq("status", "ACTIVA").execute()
        return pd.DataFrame(res.data)
    except: 
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_valores_suscripcion():
    conn = get_db_connection()
    try:
        res = conn.table("suscripciones").select("cliente_id, valor_suscripcion, metodo_entrega").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_asignaciones",
            funcion="cargar_valores_suscripcion",
            error=e,
            email_usuario=email_usuario
        )
        st.error("⚠️ No se pudieron cargar los montos de suscripción desde la base de datos. Por favor, refresca la página.")
        print(f"Error crítico al cargar los valores de suscripción: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_catalogo_completo_libros(incluir_sin_stock=False, filtrar_aptos=False):
    """Carga los libros. Permite incluir los que no tienen stock si se solicita."""
    conn = get_db_connection()
    try:
        query = conn.table("libros").select("libro_id, titulo, autor, genero, precio, stock, apto_cajita")
        if not incluir_sin_stock:
            query = query.gt("stock", 0)
            
        if filtrar_aptos:
            query = query.eq("apto_cajita", True)
            
        res = query.execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            df['genero'] = df['genero'].fillna("").astype(str)
            
        return df
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_asignaciones",
            funcion="cargar_catalogo_completo_libros",
            error=e,
            email_usuario=email_usuario
        )
        st.error(f"Error cargando catálogo asignaciones: {e}")
        print(f"Error cargando catálogo asignaciones: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_libros_aptitud():
    """Carga libros con stock > 0 para gestionar si son aptos para cajitas."""
    conn = get_db_connection()
    try:
        res = conn.table("libros").select("libro_id, titulo, encuadernacion, stock, apto_cajita").gt("stock", 0).order("titulo").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def auto_descartar_tapa_dura():
    """Marca automáticamente apto_cajita = False a los Tapa Dura."""
    conn = get_db_connection()
    try:
        # Buscamos los que son TAPA DURA y están marcados como aptos (True o Is Null)
        res = conn.table("libros").select("libro_id").eq("encuadernacion", "TAPA DURA").neq("apto_cajita", False).execute()
        if res.data:
            ids_actualizar = [item['libro_id'] for item in res.data]
            # Los actualizamos masivamente a False
            conn.table("libros").update({"apto_cajita": False}).in_("libro_id", ids_actualizar).execute()
            return len(ids_actualizar)
        return 0
    except Exception as e:
        return -1

@st.cache_data(ttl=60)
def obtener_ids_libros_poseidos_por_cliente(cliente_id):
    if not cliente_id:
        return set()
    conn = get_db_connection()
    ids_poseidos = set()
    try:
        res_historial = conn.table("librero_historico").select("libro_id").eq("cliente_id", cliente_id).execute()
        if res_historial.data:
            ids_poseidos.update(item['libro_id'] for item in res_historial.data if item.get('libro_id') is not None)
            
        res_asignaciones = conn.table("asignaciones").select("libro_suscripcion_id").eq("cliente_id", cliente_id).execute()
        if res_asignaciones.data:
            ids_poseidos.update(item['libro_suscripcion_id'] for item in res_asignaciones.data if item.get('libro_suscripcion_id') is not None)
            
        res_ventas = conn.table("registro_ventas").select("libros_vendidos").eq("cliente_id", cliente_id).execute()
        if res_ventas.data:
            for venta in res_ventas.data:
                if venta.get('libros_vendidos'):
                    try:
                        libros_json = json.loads(venta['libros_vendidos'])
                        for libro in libros_json:
                            if libro.get('libro_id') is not None:
                                ids_poseidos.add(libro['libro_id'])
                    except (json.JSONDecodeError, TypeError):
                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                        
                        error_detalle = f"JSON corrupto en ventas del cliente {cliente_id}."
                        
                        log_error(
                            vista="vista_asignaciones",
                            funcion="obtener_ids_libros_poseidos_por_cliente (Lectura JSON)",
                            error=error_detalle,
                            email_usuario=email_usuario
                        )
                        
                        continue
                        
        return ids_poseidos
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_asignaciones",
            funcion="obtener_ids_libros_poseidos_por_cliente",
            error=e,
            email_usuario=email_usuario
        )
        st.error(f"Error crítico al obtener libros poseídos (ID Cliente: {cliente_id}): {e}")
        print(f"Error crítico al obtener libros poseídos (ID Cliente: {cliente_id}): {e}")
        return set()
    
@st.cache_data(ttl=120)  
def cargar_libros_filtrados_para_cliente(cliente_id, asig_row, incluir_sin_stock=False, usar_historica=False):
    """
    Carga los libros disponibles para un cliente, aplicando la jerarquía de preferencias:
    1. Preferencia Mensual (si existe y no se pide usar la histórica forzosamente)
    2. Preferencias Históricas (si no hay mensual o si se fuerza su uso)
    """
    df_catalogo = cargar_catalogo_completo_libros(incluir_sin_stock=incluir_sin_stock, filtrar_aptos=True)
    if df_catalogo.empty or not cliente_id:
        return df_catalogo, []

    conn = get_db_connection()
    try:
        ids_poseidos = obtener_ids_libros_poseidos_por_cliente(cliente_id)
        if ids_poseidos:
            df_catalogo = df_catalogo[~df_catalogo['libro_id'].isin(ids_poseidos)]

        # ========================================================
        # --- NUEVA LÓGICA DE JERARQUÍA DE PREFERENCIAS ---
        # ========================================================
        generos_pref = []
        
        preferencia_del_mes = asig_row.get('preferencia_mensual') if asig_row is not None else None
        
        # 1. Prioridad 1: Preferencia del Mes (SOLO si no forzamos la histórica)
        if not usar_historica and preferencia_del_mes and isinstance(preferencia_del_mes, str) and preferencia_del_mes.strip():
            generos_brutos = preferencia_del_mes.split(',')
            generos_pref = [limpiar_texto_para_busqueda(g.strip()).upper() for g in generos_brutos if g.strip()]
            
        # 2. Prioridad 2: Preferencia Histórica (si se fuerza o si no hay mensual)
        else:
            res_susc = conn.table("suscripciones").select("generos_preferencia").eq("cliente_id", cliente_id).execute()
            if res_susc.data and res_susc.data[0].get('generos_preferencia'):
                generos_brutos = res_susc.data[0]['generos_preferencia'].split(',')
                generos_pref = [limpiar_texto_para_busqueda(g.strip()).upper() for g in generos_brutos if g.strip()]
        # ========================================================

        return df_catalogo, generos_pref

    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_asignaciones",
            funcion="cargar_libros_filtrados_para_cliente",
            error=e,
            email_usuario=email_usuario
        )
        st.error("⚠️ No se pudo filtrar el catálogo de libros para este cliente. Se mostrará el catálogo completo como medida de seguridad.")
        print(f"Error en cargar_libros_filtrados_para_cliente: {e}")
        return cargar_catalogo_completo_libros(incluir_sin_stock), []

# --- 🚀 CARGA DE ASIGNACIONES OPTIMIZADA EN SEGUNDOS (FILTRADO EN BD) ---
@st.cache_data(ttl=120)
def cargar_asignaciones_mes(ano, mes):
    conn = get_db_connection()
    try:
        res_asig = conn.table("asignaciones").select("*").eq("ano", ano).eq("mes", mes).execute()
        if not res_asig.data:
            return pd.DataFrame()
        df_asig = pd.DataFrame(res_asig.data)

        ids_clientes_mes = df_asig['cliente_id'].dropna().unique().tolist()
        ids_libros_mes = df_asig['libro_suscripcion_id'].dropna().unique().tolist()

        if not ids_clientes_mes:
            return df_asig

        res_clientes = conn.table("clientes").select("cliente_id, nombre, rut, fecha_actualizacion_librero").in_("cliente_id", ids_clientes_mes).execute()
        df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()

        res_suscripciones = conn.table("suscripciones").select("cliente_id, generos_preferencia, metodo_entrega, fecha_pago").in_("cliente_id", ids_clientes_mes).execute()
        df_suscripciones = pd.DataFrame(res_suscripciones.data) if res_suscripciones.data else pd.DataFrame()
        
        df_libros = pd.DataFrame()
        if ids_libros_mes:
            ids_libros_int = [int(x) for x in ids_libros_mes]
            res_libros = conn.table("libros").select("libro_id, titulo").in_("libro_id", ids_libros_int).execute()
            df_libros = pd.DataFrame(res_libros.data) if res_libros.data else pd.DataFrame()

        df_merged = pd.merge(df_asig, df_clientes, on="cliente_id", how="left")
        if not df_suscripciones.empty:
            df_merged = pd.merge(df_merged, df_suscripciones, on="cliente_id", how="left")
        if not df_libros.empty:
            df_libros = df_libros.rename(columns={'libro_id': 'libro_suscripcion_id', 'titulo': 'titulo_libro'})
            df_merged = pd.merge(df_merged, df_libros, on="libro_suscripcion_id", how="left")

        columnas_esperadas = [
            'asignacion_id', 'cliente_id', 'libro_suscripcion_id', 'nombre', 'titulo_libro', 'ano', 'mes', 
            'extras', 'fecha_asignacion', 'estado_envio', 'pagado', 'envio_pagado', 'tipo_cobro_envio', 'comentario', 
            'valor_envio', 'monto_total', 'valor_extras', 'costo_caja', 'rut', 
            'fecha_actualizacion_librero', 'generos_preferencia', 'metodo_entrega',
            'fecha_pago'
        ]
        
        for col in columnas_esperadas:
            if col not in df_merged.columns:
                df_merged[col] = None

        df_merged['nombre'] = df_merged['nombre'].fillna('Cliente no encontrado')
        df_merged['titulo_libro'] = df_merged['titulo_libro'].fillna('⏳ PENDIENTE DE ASIGNAR')
        df_merged['generos_preferencia'] = df_merged['generos_preferencia'].fillna('Sin preferencias')
        
        return df_merged
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        log_error(
            vista="vista_asignaciones",
            funcion="cargar_asignaciones_mes",
            error=e,
            email_usuario=email_usuario
        )
        print(f"Error crítico al cargar datos de asignaciones: {e}")
        st.error(f"Error crítico al cargar datos de asignaciones: {e}")
        return pd.DataFrame()

# --- CIERRE DE MES ---

@st.cache_data(ttl=60)
def verificar_mes_cerrado(ano, mes):
    conn = get_db_connection()
    try:
        res = conn.table("meses_cerrados").select("id").eq("ano", int(ano)).eq("mes", int(mes)).execute()
        return len(res.data) > 0
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        log_error(
            vista="vista_asignaciones",
            funcion="verificar_mes_cerrado",
            error=e,
            email_usuario=email_usuario
        )
        
        st.warning("⚠️ No se pudo verificar si este mes está cerrado. Por seguridad, se limitarán los cambios hasta restablecer la conexión.")
        print(f"Error crítico al verificar mes cerrado: {e}")
        return False

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
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        accion = "CERRAR" if cerrar else "REABRIR"
        
        log_error(
            vista="vista_asignaciones",
            funcion="cambiar_estado_mes",
            error=f"Fallo al intentar {accion} el mes {mes}/{ano}. Detalle: {e}",
            email_usuario=email_usuario
        )
        
        return False, str(e)

# --- ACCIONES ---

def comenzar_mes(ano, mes, df_mes_actual, progress_placeholder):
    df_suscritos = cargar_clientes_suscritos()
    df_valores = cargar_valores_suscripcion()
    
    if df_suscritos.empty:
        return False, "No hay clientes con estado 'ACTIVA' en tu base de datos."
    
    df_suscritos['cliente_id'] = pd.to_numeric(df_suscritos['cliente_id'], errors='coerce')
    if not df_mes_actual.empty:
        df_mes_actual['cliente_id'] = pd.to_numeric(df_mes_actual['cliente_id'], errors='coerce')
        clientes_ya_creados = df_mes_actual.dropna(subset=['cliente_id'])['cliente_id'].unique()
        df_faltantes = df_suscritos[~df_suscritos['cliente_id'].isin(clientes_ya_creados)]
    else:
        df_faltantes = df_suscritos
        
    if df_faltantes.empty:
        return True, "✅ ¡Todo al día! No se encontraron nuevos clientes activos para agregar al mes."
        
    conn = get_db_connection()
    
    
    creados, errores_visibles = 0, []
    total_a_crear = len(df_faltantes)
    
    # 📅 Calcular mes anterior para heredar tipo_cobro_envio
    if int(mes) == 1:
        mes_ant = 12
        ano_ant = int(ano) - 1
    else:
        mes_ant = int(mes) - 1
        ano_ant = int(ano)
        
    tipo_cobro_envio_ant_dict = {}
    try:
        res_ant = conn.table("asignaciones").select("cliente_id, tipo_cobro_envio").eq("ano", ano_ant).eq("mes", mes_ant).execute()
        if res_ant.data:
            tipo_cobro_envio_ant_dict = {item['cliente_id']: item['tipo_cobro_envio'] for item in res_ant.data if item.get('cliente_id') is not None}
    except Exception as e:
        print(f"Error cargando tipo_cobro_envio del mes anterior: {e}")

    creados, errores_visibles = 0, []
    total_a_crear = len(df_faltantes)
    
    barra_progreso = progress_placeholder.progress(0, text=f"Iniciando creación de {total_a_crear} cajas...")
    for i, (_, cliente) in enumerate(df_faltantes.iterrows()):
        barra_progreso.progress((i + 1) / total_a_crear, text=f"📦 Creando caja para: {cliente['nombre']} ({i+1}/{total_a_crear})")
        try:
            c_id = int(cliente['cliente_id'])
            val_sub = 0.0
            metodo_entrega_cliente = ""
            
            if not df_valores.empty and c_id in df_valores['cliente_id'].values:
                fila_susc = df_valores[df_valores['cliente_id'] == c_id].iloc[0]
                val_sub = float(fila_susc['valor_suscripcion'])
                metodo_entrega_cliente = str(fila_susc.get('metodo_entrega', '')).strip().upper()
            
            # 🚚 Clasificación automática basada en el método de entrega del mes anterior o actual
            if c_id in tipo_cobro_envio_ant_dict:
                tipo_cobro_envio_inicial = tipo_cobro_envio_ant_dict[c_id]
                if tipo_cobro_envio_inicial in ["POR PAGAR", "RETIRO EN TIENDA"]:
                    envio_pagado_inicial = "NO APLICA"
                else:
                    envio_pagado_inicial = "NO"
            else:
                # Fallback: Clasificación basada en el método de entrega actual
                if "RETIRO" in metodo_entrega_cliente:
                    tipo_cobro_envio_inicial = "RETIRO EN TIENDA"
                    envio_pagado_inicial = "NO APLICA"
                elif "PAKET" in metodo_entrega_cliente:
                    tipo_cobro_envio_inicial = "PAGADO"
                    envio_pagado_inicial = "NO"
                else:
                    # Caso contrario: Queda vacío (NULL) para ser llenado manualmente en el data_editor
                    tipo_cobro_envio_inicial = None  
                    envio_pagado_inicial = "NO"
            
            datos = {
                "cliente_id": c_id, 
                "ano": int(ano), 
                "mes": int(mes),
                "estado_envio": "PENDIENTE PREPARACION", 
                "pagado": "NO", 
                "envio_pagado": envio_pagado_inicial,
                "tipo_cobro_envio": tipo_cobro_envio_inicial,
                "valor_envio": 0.0, 
                "valor_extras": 0.0, 
                "monto_total": val_sub,
                "costo_caja": 10000.0, 
                "fecha_asignacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            conn.table("asignaciones").insert(datos).execute()
            creados += 1
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            error_detalle = f"Fallo al crear caja para cliente '{cliente['nombre']}' (ID: {cliente['cliente_id']}). Detalle: {e}"
            log_error(
                vista="vista_asignaciones",
                funcion="comenzar_mes (bucle de creación)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            errores_visibles.append(f"Error con cliente '{cliente['nombre']}' (ID: {cliente['cliente_id']}): {str(e)}")
            
    if errores_visibles:
        st.error("Se encontraron errores durante la creación:")
        with st.expander("Ver detalle de los errores", expanded=True):
            for err in errores_visibles: st.write(err)
        return False, f"Proceso finalizado con {len(errores_visibles)} errores de {total_a_crear} intentos."
        
    if creados > 0:
        return True, f"🎉 ¡Éxito! Se crearon {creados} nuevas cajas para el mes."
        
    return False, "No se realizó ninguna acción."

def asignar_libro_principal(asignacion_id, cliente_id, libro_id, stock_actual, ano, mes, titulo, autor):
    conn = get_db_connection()
    try:
        # --- MEJORA 1: NUNCA DEJAR STOCK NEGATIVO ---
        stock_entero = int(stock_actual)
        nuevo_stock = 0 if stock_entero <= 0 else stock_entero - 1
        
        conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", int(libro_id)).execute()
        conn.table("asignaciones").update({
            "libro_suscripcion_id": int(libro_id), 
            "estado_envio": "LIBRO ASIGNADO"
        }).eq("asignacion_id", int(asignacion_id)).execute()
        
        res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).execute()
        if not res_hist.data:
            conn.table("librero_historico").insert({"cliente_id": int(cliente_id), "libro_id": int(libro_id), "autor_historico": limpiar_texto_para_busqueda(autor), "origen": f"ASIGNACIÓN {mes}/{ano}"}).execute()
            
        return True, ""
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo al asignar el libro '{titulo}' (ID: {libro_id}) a la asignación {asignacion_id} "
            f"(Cliente ID: {cliente_id}). Detalle técnico: {e}"
        )
        log_error(vista="vista_asignaciones", funcion="asignar_libro_principal", error=error_detalle, email_usuario=email_usuario)
        return False, str(e)

def generar_propuesta_azar(df_pendientes, incluir_sin_stock=False):
    conn = get_db_connection()
    
    df_catalogo = cargar_catalogo_completo_libros(incluir_sin_stock=incluir_sin_stock, filtrar_aptos=True)
    stock_local = df_catalogo.set_index('libro_id')['stock'].to_dict() if not df_catalogo.empty else {}
    
    propuesta = []
    sin_asignar = []
    
    for _, asig in df_pendientes.iterrows():
        cliente_id = int(asig['cliente_id'])
        nombre_cliente = asig['nombre']
        
        if df_catalogo.empty:
            sin_asignar.append({"Cliente": nombre_cliente, "Motivo": "Catálogo vacío o sin stock."})
            continue
            
        ids_poseidos = obtener_ids_libros_poseidos_por_cliente(cliente_id)
        
        # ========================================================
        # --- NUEVA LÓGICA DE JERARQUÍA DE PREFERENCIAS ---
        # ========================================================
        generos_pref = []
        origen_preferencia = ""
        
        preferencia_del_mes = asig.get('preferencia_mensual')
        
        # 1. Prioridad 1: Preferencia del Mes
        if pd.notna(preferencia_del_mes) and str(preferencia_del_mes).strip():
            generos_brutos = str(preferencia_del_mes).split(',')
            generos_pref = [limpiar_texto_para_busqueda(g.strip()).upper() for g in generos_brutos if g.strip()]
            origen_preferencia = "🌟 MENSUAL"
            
        # 2. Prioridad 2: Preferencia Histórica (Fallback)
        else:
            res_susc = conn.table("suscripciones").select("generos_preferencia").eq("cliente_id", cliente_id).execute()
            if res_susc.data and res_susc.data[0].get('generos_preferencia'):
                generos_brutos = res_susc.data[0]['generos_preferencia'].split(',')
                generos_pref = [limpiar_texto_para_busqueda(g.strip()).upper() for g in generos_brutos if g.strip()]
                origen_preferencia = "📜 HISTÓRICA"
            else:
                origen_preferencia = "Sin Preferencias"
        # ========================================================
            
        libros_disponibles = df_catalogo[~df_catalogo['libro_id'].isin(ids_poseidos)].copy()
        
        if not incluir_sin_stock:
            libros_disponibles = libros_disponibles[libros_disponibles['libro_id'].map(lambda x: stock_local.get(x, 0) > 0)]
            
        if libros_disponibles.empty:
            sin_asignar.append({"Cliente": nombre_cliente, "Motivo": "Ya tiene todos los libros del catálogo o no queda stock."})
            continue
            
        if generos_pref:
            libros_disponibles['genero_limpio'] = libros_disponibles['genero'].apply(lambda x: limpiar_texto_para_busqueda(str(x)).upper())
            patron = '|'.join([re.escape(g) for g in generos_pref])
            mask_gustos = libros_disponibles['genero_limpio'].str.contains(patron, na=False)
            df_sugeridos = libros_disponibles[mask_gustos]
            
            if df_sugeridos.empty:
                sin_asignar.append({"Cliente": nombre_cliente, "Motivo": f"Sin stock disponible para sus géneros preferidos."})
                continue
            else:
                # --- PRIORIZAR EL MAYOR STOCK ---
                df_sugeridos = df_sugeridos.sort_values(by="stock", ascending=False)
                max_stock = df_sugeridos['stock'].iloc[0]
                libro_elegido = df_sugeridos[df_sugeridos['stock'] == max_stock].sample(1).iloc[0]
        else:
            # --- PRIORIZAR EL MAYOR STOCK ---
            libros_disponibles = libros_disponibles.sort_values(by="stock", ascending=False)
            max_stock = libros_disponibles['stock'].iloc[0]
            libro_elegido = libros_disponibles[libros_disponibles['stock'] == max_stock].sample(1).iloc[0]
            
        l_id = int(libro_elegido['libro_id'])
        stock_local[l_id] -= 1
        
        propuesta.append({
            "asignacion_id": int(asig['asignacion_id']),
            "cliente_id": cliente_id,
            "Cliente": nombre_cliente,
            "libro_id": l_id,
            "Libro Asignado": libro_elegido['titulo'],
            "Género del Libro": str(libro_elegido.get('genero', '')),
            "Preferencias": ", ".join(generos_pref) if generos_pref else "Sin preferencias específicas",
            "Autor": libro_elegido.get('autor', ''),
            "Origen Preferencia": origen_preferencia
        })
        
    return propuesta, sin_asignar


def confirmar_propuesta_azar(propuesta, ano, mes):
    conn = get_db_connection()
    exitos = 0
    errores_visibles = []
    
    for prop in propuesta:
        try:
            res_l = conn.table("libros").select("stock").eq("libro_id", prop['libro_id']).execute()
            stock_real = res_l.data[0]['stock'] if res_l.data else 0
            
            conn.table("libros").update({"stock": max(0, int(stock_real) - 1)}).eq("libro_id", prop['libro_id']).execute()
            conn.table("asignaciones").update({"libro_suscripcion_id": prop['libro_id'], "estado_envio": "LIBRO ASIGNADO"}).eq("asignacion_id", prop['asignacion_id']).execute()
            
            res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", prop['cliente_id']).eq("libro_id", prop['libro_id']).execute()
            if not res_hist.data:
                conn.table("librero_historico").insert({
                    "cliente_id": prop['cliente_id'], 
                    "libro_id": prop['libro_id'], 
                    "autor_historico": limpiar_texto_para_busqueda(prop['Autor']), 
                    "origen": f"ASIGNACIÓN {mes}/{ano}"
                }).execute()
            exitos += 1
        except Exception as e:
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            
            error_detalle = (
                f"Fallo al confirmar propuesta para cliente '{prop.get('nombre', 'Desconocido')}' (ID: {prop.get('cliente_id', 'N/A')}) "
                f"con el libro (ID: {prop.get('libro_id', 'N/A')}). Detalle: {e}"
            )
            
            log_error(
                vista="vista_asignaciones",
                funcion="confirmar_propuesta_azar (bucle de confirmación)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            
            errores_visibles.append(f"Error con cliente '{prop.get('nombre', 'Desconocido')}': {str(e)}")
            
    # Limpieza de caché que SÍ tiene decoradores de forma segura
    cargar_catalogo_completo_libros.clear()
    return exitos, errores_visibles

def guardar_ajustes_logistica(asignacion_id, cliente_id, nuevo_envio, texto_extras_manual, valor_extras_manual):
    conn = get_db_connection()
    try:
        res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", int(cliente_id)).execute()
        val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
        
        nuevo_monto_total = val_sub + float(nuevo_envio) + float(valor_extras_manual)
        
        datos_update = {
            "valor_envio": float(nuevo_envio), 
            "extras": limpiar_texto_para_busqueda(texto_extras_manual),
            "valor_extras": float(valor_extras_manual), 
            "monto_total": nuevo_monto_total
        }
        
        conn.table("asignaciones").update(datos_update).eq("asignacion_id", int(asignacion_id)).execute()
        return True, ""
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        error_detalle = (
            f"Fallo al ajustar logística para la asignación {asignacion_id} (Cliente ID: {cliente_id}). "
            f"Valores intentados: Envio={nuevo_envio}, Extras={valor_extras_manual}. Detalle: {e}"
        )
        
        log_error(
            vista="vista_asignaciones",
            funcion="guardar_ajustes_logistica",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

def quitar_un_libro(asignacion_id, cliente_id, ano, mes, tipo, titulo_quitar, monto_descuento=0.0):
    conn = get_db_connection()
    try:
        res_l = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_quitar).execute()
        if res_l.data:
            l_id = res_l.data[0]['libro_id']
            # ---NO SUMAR SI EL STOCK ES CERO O MENOR ---
            stock_bd = int(res_l.data[0]['stock'])
            nuevo_stock = 0 if stock_bd <= 0 else stock_bd + 1
            
            conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
            origen = f"ASIGNACIÓN {mes}/{ano}" if tipo == "PRINCIPAL" else f"ASIGNACIÓN EXTRA {mes}/{ano}"
            conn.table("librero_historico").delete().eq("cliente_id", cliente_id).eq("libro_id", l_id).eq("origen", origen).execute()
            
        res_asig_exec = conn.table("asignaciones").select("*").eq("asignacion_id", asignacion_id).execute()
        if not res_asig_exec.data: return False, "No se encontró la asignación."
        res_asig = res_asig_exec.data[0]
        
        if tipo == "PRINCIPAL":
            conn.table("asignaciones").update({"libro_suscripcion_id": None, "estado_envio": "PENDIENTE PREPARACION"}).eq("asignacion_id", asignacion_id).execute()
        else:
            extras_str = str(res_asig.get('extras', ''))
            if "EXTRAS:" in extras_str:
                limpio = extras_str.replace("EXTRAS:", "").strip()
                delimitador = "|" if "|" in limpio else ","
                lista_extras = [x.strip() for x in limpio.split(delimitador) if x.strip()]
                nueva_lista = [x for x in lista_extras if x.upper() != titulo_quitar.upper()]
                nuevo_texto = "EXTRAS: " + " | ".join(nueva_lista) if nueva_lista else ""
                
                v_extras_actual = float(res_asig.get('valor_extras') or 0.0)
                nuevo_v_extras = max(0.0, v_extras_actual - float(monto_descuento))
                
                res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", cliente_id).execute()
                val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
                nuevo_total = val_sub + float(res_asig.get('valor_envio', 0.0) or 0.0) + nuevo_v_extras
                
                conn.table("asignaciones").update({"extras": nuevo_texto, "valor_extras": nuevo_v_extras, "monto_total": nuevo_total}).eq("asignacion_id", asignacion_id).execute()
                
        cargar_catalogo_completo_libros.clear()
        return True, ""
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = f"Fallo al intentar quitar el libro '{titulo_quitar}' (Tipo: {tipo}) de la asignación {asignacion_id} (Cliente ID: {cliente_id}). Detalle técnico: {e}"
        log_error(vista="vista_asignaciones", funcion="quitar_un_libro", error=error_detalle, email_usuario=email_usuario)
        return False, str(e)

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes, texto_extras):
    conn = get_db_connection()
    try:
        # 1. Validación de nulidad ultra-segura para el libro principal
        if pd.notna(libro_id) and str(libro_id).strip() != "" and str(libro_id).lower() != "none":
            l_id_int = int(float(libro_id))
            res_l = conn.table("libros").select("stock").eq("libro_id", l_id_int).execute()
            if res_l.data: 
                # Devolvemos stock al catálogo
                stock_bd = int(res_l.data[0]['stock'])
                nuevo_stock = stock_bd + 1
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id_int).execute()
            
            # Borramos del historial de lectura
            origen_p = f"ASIGNACIÓN {mes}/{ano}"
            conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", l_id_int).eq("origen", origen_p).execute()
            
        # 2. Parseo inteligente de libros extras soportando delimitadores múltiples (| y ,) y numeraciones (1. Título)
        if texto_extras and str(texto_extras).strip() != "" and str(texto_extras).lower() != "none":
            # Limpiamos el prefijo de extras
            limpio = str(texto_extras).replace("EXTRAS:", "").strip()
            # Dividimos por plepa | o por coma
            delimitador = "|" if "|" in limpio else ","
            items_extras = [x.strip() for x in limpio.split(delimitador) if x.strip()]
            
            for item in items_extras:
                # Limpiamos la numeración si existe (ej: de "1. AMI" a "AMI")
                titulo_extra = item
                if '.' in item:
                    partes_t = item.split('.', 1)
                    if len(partes_t) == 2 and partes_t[0].strip().isdigit():
                        titulo_extra = partes_t[1].strip()
                
                titulo_extra_limpio = limpiar_texto_para_busqueda(titulo_extra)
                if not titulo_extra_limpio:
                    continue
                
                # Buscamos en catálogo para restaurar stock de ese extra
                res_le = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_extra_limpio).execute()
                if res_le.data:
                    le_id = res_le.data[0]['libro_id']
                    le_stock = int(res_le.data[0]['stock'])
                    nuevo_stock_ext = le_stock + 1
                    conn.table("libros").update({"stock": nuevo_stock_ext}).eq("libro_id", le_id).execute()
                    
                    # Eliminamos el extra del librero histórico
                    origen_e = f"ASIGNACIÓN EXTRA {mes}/{ano}"
                    conn.table("librero_historico").delete().eq("cliente_id", int(cliente_id)).eq("libro_id", le_id).eq("origen", origen_e).execute()

        # 3. Borrado definitivo de la fila de la asignación en Supabase
        conn.table("asignaciones").delete().eq("asignacion_id", int(asignacion_id)).execute()
        
        # 🌟 NUEVO: Limpiamos la caché global de asignaciones al instante para que desaparezca de la pantalla
        st.cache_data.clear()
        return True, ""
        
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = f"Fallo al ELIMINAR la asignación {asignacion_id} (Cliente ID: {cliente_id}). Detalle técnico: {e}"
        log_error(vista="vista_asignaciones", funcion="eliminar_asignacion", error=error_detalle, email_usuario=email_usuario)
        return False, str(e)

def actualizar_asignaciones_batch(df_editado, df_mes_completo):
    df_original = st.session_state.get('asignaciones_original')
    if df_original is None: return 0
    diff_mask = df_original.set_index('asignacion_id').ne(df_editado.set_index('asignacion_id')).any(axis=1)
    filas_cambiadas = df_editado.set_index('asignacion_id')[diff_mask]
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates = 0
    errores = []
    for a_id, row in filas_cambiadas.iterrows():
        try:
            c_id = df_mes_completo[df_mes_completo['asignacion_id'] == a_id].iloc[0]['cliente_id']
            res_sub = conn.table("suscripciones").select("valor_suscripcion").eq("cliente_id", int(c_id)).execute()
            val_sub = float(res_sub.data[0]['valor_suscripcion']) if res_sub.data else 0.0
            
            v_envio = float(row.get('valor_envio', 0.0) or 0.0)
            v_extras = float(row.get('valor_extras', 0.0) or 0.0)
            costo_c = float(row.get('costo_caja', 10000.0) or 10000.0) 
            m_total = val_sub + v_envio + v_extras 
            
            c_envio_raw = row.get('tipo_cobro_envio')
            c_envio = str(c_envio_raw).upper().strip() if pd.notna(c_envio_raw) else ""
            if c_envio in ["", "NONE"]:
                c_envio_db = None
            else:
                c_envio_db = c_envio
                
            e_pagado = str(row['envio_pagado']).upper().strip()
            if c_envio in ["POR PAGAR", "RETIRO EN TIENDA"]:
                e_pagado = "NO APLICA"
            
            datos = {
                "estado_envio": str(row['estado_envio']).upper(), 
                "pagado": str(row['pagado']).upper(),
                "envio_pagado": e_pagado, 
                "tipo_cobro_envio": c_envio_db,
                "extras": str(row.get('extras', '')).upper(),
                "comentario": str(row.get('comentario', '')),
                "valor_envio": v_envio, "valor_extras": v_extras, "monto_total": m_total,
                "costo_caja": costo_c,
                "preferencia_mensual": str(row.get('preferencia_mensual', ''))
            }
            
            conn.table("asignaciones").update(datos).eq("asignacion_id", int(a_id)).execute()
            updates += 1
        except Exception as e: 
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            nombre_cliente = df_mes_completo.loc[df_mes_completo['asignacion_id'] == a_id, 'nombre'].iloc[0]
            
            error_detalle = (
                f"Fallo al actualizar la fila de la asignación {a_id} (Cliente: {nombre_cliente}). Detalle: {e}"
            )
            
            log_error(
                vista="vista_asignaciones",
                funcion="actualizar_asignaciones_batch (bucle)",
                error=error_detalle,
                email_usuario=email_usuario
            )
            errores.append(f"Error en la fila del cliente '{nombre_cliente}': {str(e)}")
            continue
        
    return updates, errores

def mapear_sino(val):
    v = str(val).upper()
    if v in ["TRUE", "T", "1"]: return "SI"
    if v in ["FALSE", "F", "0"]: return "NO"
    return v

def actualizar_asignaciones_masivo(lista_asignacion_ids, columna, nuevo_valor):
    """
    Actualiza una columna específica con un nuevo valor para una lista de asignaciones.
    Diseñada para la edición en bloque aplicando la integridad de datos de despacho.
    """
    if not lista_asignacion_ids:
        return False, "No se seleccionaron filas para actualizar."
    conn = get_db_connection()
    try:
        # Preparamos los datos para el update
        datos_update = {}
        
        # 🚚 Lógica auto-curativa y conversión a NULL
        if columna == "tipo_cobro_envio":
            val_str = str(nuevo_valor).upper().strip() if pd.notna(nuevo_valor) else ""
            if val_str in ["", "NONE"]:
                datos_update["tipo_cobro_envio"] = None  # Guardar como NULL en Supabase
            else:
                datos_update["tipo_cobro_envio"] = val_str
                
            # Si el tipo de envío es por pagar o retiro, forzamos "NO APLICA"
            if val_str in ["POR PAGAR", "RETIRO EN TIENDA"]:
                datos_update["envio_pagado"] = "NO APLICA"
        else:
            datos_update[columna] = nuevo_valor
            
        # Ejecutamos la actualización masiva para todos los IDs de la lista
        conn.table("asignaciones").update(datos_update).in_("asignacion_id", lista_asignacion_ids).execute()
        
        return True, ""
    except Exception as e:
        # --- BLOQUE DE LOGGING DE ERRORES ---
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo en EDICIÓN EN BLOQUE. Columna: '{columna}', Valor: '{nuevo_valor}'. "
            f"IDs afectados: {str(lista_asignacion_ids[:5])}... ({len(lista_asignacion_ids)} total). Detalle: {e}"
        )
        log_error(
            vista="vista_asignaciones",
            funcion="actualizar_asignaciones_masivo",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

@st.cache_data(ttl=60)
def cargar_historial_cambios():
    """Carga los últimos 5 registros del historial de cambios masivos desde Supabase."""
    conn = get_db_connection()
    try:
        res = conn.table("historial_cambios_masivos").select("*").order("fecha_cambio", desc=True).limit(5).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.toast(f"⚠️ No se pudo cargar el historial: {e}")
        return pd.DataFrame()

def registrar_cambio_masivo(email, columna, valor, ids_afectados, nombres_afectados, valores_antiguos, mes, ano):
    """Guarda un registro de la operación de edición en bloque en la tabla de auditoría."""
    conn = get_db_connection()
    try:
        lista_clientes = [{"id": i, "nombre": n, "valor_antiguo": str(v)} for i, n, v in zip(ids_afectados, nombres_afectados, valores_antiguos)]
        datos_log = {
            "email_usuario": email,
            "columna_afectada": columna,
            "valor_nuevo": str(valor),
            "clientes_afectados": json.dumps(lista_clientes),
            "total_filas_afectadas": len(ids_afectados),
            "mes_afectado": int(mes),
            "ano_afectado": int(ano)
        }
        conn.table("historial_cambios_masivos").insert(datos_log).execute()
        cargar_historial_cambios.clear()
        return True
    except Exception as e:
        log_error("vista_asignaciones", "registrar_cambio_masivo", f"Fallo CRÍTICO al guardar log de auditoría: {e}", email)
        return False
@st.cache_data(ttl=120)
def cargar_historico_asignaciones_completo():
    """
    Carga todo el histórico de asignaciones desde la base de datos de forma dinámica
    desde el año de inicio (2025) hasta el año actual, libre de bucles infinitos y sin mantenimiento.
    """
    conn = get_db_connection()
    try:
        # 1. 📅 Calcular el rango de años dinámicamente desde el inicio de Alba (2025) hasta el año actual en curso
        ano_inicio = 2025
        ano_actual = datetime.now().year
        rango_anios = list(range(ano_inicio, ano_actual + 1)) # En 2026: [2025, 2026]. En 2027: [2025, 2026, 2027]
        
        datos_totales = []
        chunk_size = 1000
        
        # 2. 🚀 Bucle acotado por año para burlar el límite de Supabase
        for anio in rango_anios:
            # Limitamos a un máximo de 3 bloques por año (máximo 3.000 filas/año, garantizando que el loop siempre termine)
            for bloque in range(3):
                start = bloque * chunk_size
                end = start + chunk_size - 1
                
                # Consultamos el año específico y la tanda correspondiente
                res_anio = conn.table("asignaciones").select("*")\
                    .eq("ano", anio)\
                    .order("fecha_asignacion", desc=True)\
                    .range(start, end).execute()
                
                if res_anio.data:
                    datos_totales.extend(res_anio.data)
                    # Si devolvió menos de 1.000, significa que ya no quedan más registros para ese año
                    if len(res_anio.data) < chunk_size:
                        break
                else:
                    break
        
        if not datos_totales:
            return pd.DataFrame()
            
        df_asig = pd.DataFrame(datos_totales)
        
        # 3. Traemos la tabla de clientes para asociar los nombres
        res_clientes = conn.table("clientes").select("cliente_id, nombre").execute()
        df_clientes = pd.DataFrame(res_clientes.data) if res_clientes.data else pd.DataFrame()
        
        # 4. Traemos la tabla de suscripciones para el valor de suscripcion base
        res_susc = conn.table("suscripciones").select("cliente_id, valor_suscripcion").execute()
        df_susc = pd.DataFrame(res_susc.data) if res_susc.data else pd.DataFrame()
        
        # Merges en memoria con Pandas (Fusión robusta y veloz)
        if not df_clientes.empty:
            df_merged = pd.merge(df_asig, df_clientes, on="cliente_id", how="left")
        else:
            df_merged = df_asig
            df_merged['nombre'] = 'Cliente Desconocido'
            
        if not df_susc.empty:
            df_merged = pd.merge(df_merged, df_susc, on="cliente_id", how="left")
        else:
            df_merged['valor_suscripcion'] = 18500.0
            
        df_merged['nombre'] = df_merged['nombre'].fillna('Cliente Eliminado')
        df_merged['valor_suscripcion'] = df_merged['valor_suscripcion'].fillna(18500.0)
        
        # RECALCULO DE MONTOS ANTIGUOS QUE ESTABAN EN 0 O NULOS
        df_merged['monto_total'] = pd.to_numeric(df_merged['monto_total'], errors='coerce').fillna(0.0)
        df_merged['valor_envio'] = pd.to_numeric(df_merged['valor_envio'], errors='coerce').fillna(0.0)
        df_merged['valor_extras'] = pd.to_numeric(df_merged['valor_extras'], errors='coerce').fillna(0.0)
        
        mask_recalc = (df_merged['monto_total'] == 0.0)
        if mask_recalc.any():
            df_merged.loc[mask_recalc, 'monto_total'] = (
                df_merged.loc[mask_recalc, 'valor_suscripcion'] + 
                df_merged.loc[mask_recalc, 'valor_envio'] + 
                df_merged.loc[mask_recalc, 'valor_extras']
            )
        
        return df_merged
    except Exception as e:
        log_error("vista_asignaciones", "cargar_historico_asignaciones_completo", e, st.session_state.get('email_usuario', 'Desconocido'))
        return pd.DataFrame()