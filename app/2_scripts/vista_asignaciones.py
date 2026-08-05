import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto
import json
import re
from utilidades import log_error

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
        res = conn.table("suscripciones").select("cliente_id, valor_suscripcion").execute()
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
def cargar_catalogo_completo_libros(incluir_sin_stock=False):
    """Carga los libros. Permite incluir los que no tienen stock si se solicita."""
    conn = get_db_connection()
    try:
        query = conn.table("libros").select("libro_id, titulo, autor, genero, precio, stock")
        if not incluir_sin_stock:
            query = query.gt("stock", 0)
            
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
                        
                        error_detalle = f"JSON corrupto en ventas del cliente {cliente_id}. Detalle: {e}"
                        
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
    
def cargar_libros_filtrados_para_cliente(cliente_id, incluir_sin_stock=False):
    df_catalogo = cargar_catalogo_completo_libros(incluir_sin_stock)
    if df_catalogo.empty or not cliente_id:
        return df_catalogo, []
    
    conn = get_db_connection()
    try:
        ids_poseidos = obtener_ids_libros_poseidos_por_cliente(cliente_id)
        if ids_poseidos:
            df_catalogo = df_catalogo[~df_catalogo['libro_id'].isin(ids_poseidos)]
            
        res_susc = conn.table("suscripciones").select("generos_preferencia").eq("cliente_id", cliente_id).execute()
        generos_pref = []
        if res_susc.data and res_susc.data[0].get('generos_preferencia'):
            generos_brutos = res_susc.data[0]['generos_preferencia'].split(',')
            generos_pref = [limpiar_texto(g.strip()).upper() for g in generos_brutos if g.strip()]
        
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
            'extras', 'fecha_asignacion', 'estado_envio', 'pagado', 'envio_pagado', 'comentario', 
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
    
    barra_progreso = progress_placeholder.progress(0, text=f"Iniciando creación de {total_a_crear} cajas...")
    for i, (_, cliente) in enumerate(df_faltantes.iterrows()):
        barra_progreso.progress((i + 1) / total_a_crear, text=f"📦 Creando caja para: {cliente['nombre']} ({i+1}/{total_a_crear})")
        try:
            c_id = int(cliente['cliente_id'])
            val_sub = 0.0
            if not df_valores.empty and c_id in df_valores['cliente_id'].values:
                val_sub = float(df_valores[df_valores['cliente_id'] == c_id]['valor_suscripcion'].iloc[0])
            
            datos = {
                "cliente_id": c_id, "ano": int(ano), "mes": int(mes),
                "estado_envio": "PENDIENTE PREPARACION", "pagado": "NO", "envio_pagado": "NO",
                "valor_envio": 0.0, "valor_extras": 0.0, "monto_total": val_sub,
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
        conn.table("libros").update({"stock": max(0, int(stock_actual) - 1)}).eq("libro_id", int(libro_id)).execute()
        conn.table("asignaciones").update({
            "libro_suscripcion_id": int(libro_id), 
            "estado_envio": "LIBRO ASIGNADO"
        }).eq("asignacion_id", int(asignacion_id)).execute()
        
        res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", int(cliente_id)).eq("libro_id", int(libro_id)).execute()
        if not res_hist.data:
            conn.table("librero_historico").insert({"cliente_id": int(cliente_id), "libro_id": int(libro_id), "autor_historico": limpiar_texto(autor), "origen": f"ASIGNACIÓN {mes}/{ano}"}).execute()
            
        return True, ""
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        error_detalle = (
            f"Fallo al asignar el libro '{titulo}' (ID: {libro_id}) a la asignación {asignacion_id} "
            f"(Cliente ID: {cliente_id}). Detalle técnico: {e}"
        )
        
        log_error(
            vista="vista_asignaciones",
            funcion="asignar_libro_principal",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

def generar_propuesta_azar(df_pendientes, incluir_sin_stock=False):
    conn = get_db_connection()
    
    df_catalogo = cargar_catalogo_completo_libros(incluir_sin_stock=incluir_sin_stock)
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
        
        res_susc = conn.table("suscripciones").select("generos_preferencia").eq("cliente_id", cliente_id).execute()
        generos_pref = []
        if res_susc.data and res_susc.data[0].get('generos_preferencia'):
            generos_brutos = res_susc.data[0]['generos_preferencia'].split(',')
            generos_pref = [limpiar_texto(g.strip()).upper() for g in generos_brutos if g.strip()]
            
        libros_disponibles = df_catalogo[~df_catalogo['libro_id'].isin(ids_poseidos)].copy()
        
        if not incluir_sin_stock:
            libros_disponibles = libros_disponibles[libros_disponibles['libro_id'].map(lambda x: stock_local.get(x, 0) > 0)]
            
        if libros_disponibles.empty:
            sin_asignar.append({"Cliente": nombre_cliente, "Motivo": "Ya tiene todos los libros del catálogo o no queda stock."})
            continue
            
        if generos_pref:
            libros_disponibles['genero_limpio'] = libros_disponibles['genero'].apply(lambda x: limpiar_texto(str(x)).upper())
            patron = '|'.join([re.escape(g) for g in generos_pref])
            mask_gustos = libros_disponibles['genero_limpio'].str.contains(patron, na=False)
            df_sugeridos = libros_disponibles[mask_gustos]
            
            if df_sugeridos.empty:
                sin_asignar.append({"Cliente": nombre_cliente, "Motivo": f"Sin stock disponible para sus géneros preferidos."})
                continue
            else:
                libro_elegido = df_sugeridos.sample(1).iloc[0]
        else:
            libro_elegido = libros_disponibles.sample(1).iloc[0]
            
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
                    "autor_historico": limpiar_texto(prop['Autor']), 
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
            "extras": limpiar_texto(texto_extras_manual),
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
            conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", l_id).execute()
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
        
        error_detalle = (
            f"Fallo al intentar quitar el libro '{titulo_quitar}' (Tipo: {tipo}) de la asignación {asignacion_id} "
            f"(Cliente ID: {cliente_id}). Detalle técnico: {e}"
        )
        
        log_error(
            vista="vista_asignaciones",
            funcion="quitar_un_libro",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

def eliminar_asignacion(asignacion_id, libro_id, cliente_id, ano, mes, texto_extras):
    conn = get_db_connection()
    try:
        if pd.notna(libro_id) and libro_id:
            res_l = conn.table("libros").select("stock").eq("libro_id", int(libro_id)).execute()
            if res_l.data: conn.table("libros").update({"stock": res_l.data[0]['stock'] + 1}).eq("libro_id", int(libro_id)).execute()
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
        return True, ""
    except Exception as e: 
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        error_detalle = (
            f"Fallo al ELIMINAR la asignación {asignacion_id} (Cliente ID: {cliente_id}). "
            f"Libro principal ID: {libro_id}, Extras: '{texto_extras}'. Detalle técnico: {e}"
        )
        
        log_error(
            vista="vista_asignaciones",
            funcion="eliminar_asignacion",
            error=error_detalle,
            email_usuario=email_usuario
        )
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
            
            datos = {
                "estado_envio": str(row['estado_envio']).upper(), "pagado": str(row['pagado']).upper(),
                "envio_pagado": str(row['envio_pagado']).upper(), "extras": str(row.get('extras', '')).upper(),
                "comentario": str(row.get('comentario', '')),
                "valor_envio": v_envio, "valor_extras": v_extras, "monto_total": m_total,
                "costo_caja": costo_c
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
    Diseñada para la edición en bloque.
    """
    if not lista_asignacion_ids:
        return False, "No se seleccionaron filas para actualizar."

    conn = get_db_connection()
    try:
        # Preparamos los datos para el update
        datos_update = {columna: nuevo_valor}
        
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
        "📋 Gestión (Tabla Editable)", 
        "📖 Asignar Libro Principal", 
        "🚚 Gestionar Envío y Ajuste Manual", 
        "🚀 Generar / Actualizar Mes", 
        "🗑️ Eliminar/Quitar Libros", 
        "🧹 Desasignar Libros del Mes",
        "🔒 Cierre de Mes"
    ]
    opcion_menu = st.selectbox("👉 SELECCIONA LA ACCIÓN QUE DESEAS REALIZAR:", opciones_menu)
    st.markdown("---")
    
    # ==========================================================
    # 1. TABLA EDITABLE (CON EDICIÓN EN BLOQUE INTEGRADA)
    # ==========================================================
    if opcion_menu == "📋 Gestión (Tabla Editable)":
        # --- 1. FILTROS DE BÚSQUEDA ---
        st.markdown("##### 🔽 Filtros de Búsqueda")
        col_fa1, col_fa2 = st.columns(2)
        f_nombre = col_fa1.text_input("🔍 Buscar por Nombre de Cliente:")
        f_libro_titulo = col_fa1.text_input("📖 Buscar por Título de Libro:")
        
        fechas_pago_unicas = df_mes['fecha_pago'].dropna().unique().tolist()
        filtro_fecha_pago = col_fa2.selectbox("Filtrar por Fecha de Pago:", ["Todas"] + fechas_pago_unicas)
        
        st.markdown("---")
        col_fa3, col_fa4, col_fa5 = st.columns(3)
        filtro_estado = col_fa3.selectbox("Estado Envío:", ["Todos"] + df_mes['estado_envio'].unique().tolist())
        filtro_pagado = col_fa4.selectbox("Estado de Pago:", ["Todos"] + df_mes['pagado'].unique().tolist())
        filtro_libro = col_fa5.selectbox("Asignación de Libro:", ["Todos", "Sin Libro", "Con Libro"])
        
        # Filtro de Visibilidad de Columnas
        st.markdown("---")
        columnas_opcionales = [
                'pagado', 'envio_pagado', 'nombre', 'titulo_libro', 'estado_envio', 
                'costo_caja', 'valor_envio', 'valor_extras', 'monto_total', 'extras', 'comentario'
            ]
        columnas_visibles = st.multiselect(
                "👁️ Ocultar/Mostrar Columnas en la Tabla:", 
                options=columnas_opcionales, 
                default=columnas_opcionales,
                help="Quita las columnas que no necesites ver para tener una vista más limpia."
            )
        st.markdown("---")

        # --- 2. APLICACIÓN DE FILTROS ---
        df_filtrado = df_mes.copy()
        if f_nombre: 
            df_filtrado = df_filtrado[df_filtrado['nombre'].str.contains(limpiar_texto(f_nombre), case=False, na=False)]
        if f_libro_titulo:
            df_filtrado = df_filtrado[df_filtrado['titulo_libro'].str.contains(limpiar_texto(f_libro_titulo), case=False, na=False)]
        if filtro_fecha_pago != "Todas":
            df_filtrado = df_filtrado[df_filtrado['fecha_pago'] == filtro_fecha_pago]
        if filtro_estado != "Todos": 
            df_filtrado = df_filtrado[df_filtrado['estado_envio'] == filtro_estado]
        if filtro_pagado != "Todos": 
            df_filtrado = df_filtrado[df_filtrado['pagado'] == filtro_pagado]
        if filtro_libro == "Sin Libro": 
            df_filtrado = df_filtrado[df_filtrado['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
        elif filtro_libro == "Con Libro": 
            df_filtrado = df_filtrado[df_filtrado['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR"]

        # --- 3. PREPARACIÓN DE COLUMNAS ---
        # Siempre mantenemos 'asignacion_id' por temas de base de datos, sumado a las que elija el usuario
        columnas_visibles_ordenadas = [col for col in columnas_opcionales if col in columnas_visibles]
        columnas_mostrar = ['asignacion_id'] + columnas_visibles_ordenadas
        
        columnas_seguras = [col for col in columnas_mostrar if col in df_filtrado.columns]
        df_mostrar = df_filtrado[columnas_seguras].copy()

        # --- 4. MODO EDICIÓN EN BLOQUE ---
        if 'edit_mode' not in st.session_state:
            st.session_state.edit_mode = False

        if st.button("✏️ Activar/Desactivar Edición en Bloque", use_container_width=True, help="Selecciona varias filas y aplica un cambio a todas a la vez."):
            st.session_state.edit_mode = not st.session_state.edit_mode
            if not st.session_state.edit_mode and 'propuesta_cambio' in st.session_state:
                del st.session_state.propuesta_cambio
            st.rerun()

        if st.session_state.edit_mode:
            # 🔴 NUEVO: Cuadro de instrucciones detallado
            st.info(
                "💡 **GUÍA RÁPIDA: ¿Cómo usar la Edición en Bloque?**\n"
                "1. **Selecciona a los clientes** marcando la casilla en la primera columna de la tabla (`Seleccionar`).\n"
                "2. **Ve al formulario** que está debajo de la tabla y elige qué columna deseas modificar.\n"
                "3. **Ingresa el nuevo valor** que quieres aplicarles a todos por igual y presiona `Previsualizar Cambios`.\n"
                "4. **Revisa la lista** final y escribe la palabra de seguridad para aplicar el cambio masivo.\n"
                "\n"
                "**_Nota: TI del sistema no se hace responsable si el resultado no es el esperado. Usar con precaución :D_**"
            )
            df_mostrar.insert(0, "Seleccionar", False)

        # --- 5. GUARDADO DE ESTADO ORIGINAL ---
        if 'asignaciones_original' not in st.session_state or not st.session_state.asignaciones_original.equals(df_mostrar):
            st.session_state.asignaciones_original = df_mostrar.copy()

        # --- 6. CONFIGURACIÓN Y DIBUJO DE LA TABLA ---
        st.caption("Doble clic en las celdas para modificar manualmente. Los totales se recalcularán al guardar.")
        
        config_cols = {
            "asignacion_id": None, # Oculta visualmente el ID
            "estado_envio": st.column_config.SelectboxColumn("Estado", options=["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO", "LIBRO ASIGNADO"], required=True),
            "pagado": st.column_config.SelectboxColumn("Pagado", options=["SI", "NO", "ABONO"], required=True),
            "envio_pagado": st.column_config.SelectboxColumn("Envío Pagado", options=["SI", "NO", "NO APLICA"], required=True),
            "costo_caja": st.column_config.NumberColumn("Costo Caja Fijo ($)", format="$%.0f"),
            "valor_envio": st.column_config.NumberColumn("Valor Envío ($)", format="$%.0f"),
            "valor_extras": st.column_config.NumberColumn("Valor Extras ($)", format="$%.0f"),
            "monto_total": st.column_config.NumberColumn("Monto Total a Cobrar ($)", format="$%.0f"),
            "comentario": st.column_config.TextColumn("Comentario", max_chars=300)
        }
        
        columnas_no_editables = ['asignacion_id', 'nombre', 'titulo_libro', 'monto_total']
        disabled_cols = columnas_mostrar if mes_esta_cerrado else [c for c in columnas_no_editables if c in columnas_mostrar]

        df_editado = st.data_editor(
            df_mostrar, 
            key='editor_asignaciones_unificado',
            disabled=disabled_cols, 
            column_config=config_cols, 
            hide_index=True, 
            use_container_width=True
        )

        # --- 7. FORMULARIO DE EDICIÓN EN BLOQUE (VERSIÓN SIMPLIFICADA Y FINAL) ---
        if st.session_state.edit_mode:
            st.markdown("---")
            col_limite, _ = st.columns([1, 2])
            limite_filas = col_limite.selectbox(
                "🛑 Límite de filas a editar a la vez:", 
                options=[5, 10, 15, 20], index=0
            )

            filas_seleccionadas = df_editado[df_editado["Seleccionar"] == True]
            excede_limite = len(filas_seleccionadas) > limite_filas
            
            st.markdown("##### ⚙️ Aplicar Cambios en Lote")
            st.warning("⚠️ **ACCIÓN DELICADA:** Revisa bien las filas seleccionadas antes de proceder.")
            
            # --- Divisor para separar la selección de la acción ---
            st.markdown("---")

            # --- LÓGICA DEL FORMULARIO Y PREVISUALIZACIÓN ---
            opciones_desplegables = {
                "estado_envio": ["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO", "LIBRO ASIGNADO"],
                "pagado": ["SI", "NO", "ABONO"],
                "envio_pagado": ["SI", "NO", "NO APLICA"]
            }
            columnas_modificables = ["estado_envio", "pagado", "envio_pagado", "valor_envio", "comentario"]

            col1, col2 = st.columns(2)
            
            with col1:
                columna_a_cambiar = st.selectbox("1. Columna a modificar:", columnas_modificables, key="col_a_cambiar")
            
            with col2:
                if columna_a_cambiar in opciones_desplegables:
                    nuevo_valor = st.selectbox("2. Nuevo valor:", options=opciones_desplegables[columna_a_cambiar], key="valor_selectbox")
                elif columna_a_cambiar == "valor_envio":
                    nuevo_valor = st.number_input("2. Nuevo valor ($):", min_value=0.0, step=100.0, format="%.0f", key="valor_number")
                else:
                    nuevo_valor = st.text_input("2. Nuevo valor:", value="", key="valor_text")

            # El botón de previsualización ahora está fuera del formulario
            if st.button("Previsualizar Cambios", disabled=(filas_seleccionadas.empty or excede_limite)):
                nombres_lista = filas_seleccionadas['nombre'].tolist() if 'nombre' in filas_seleccionadas.columns else [f"ID {x}" for x in filas_seleccionadas['asignacion_id'].tolist()]
                
                st.session_state.propuesta_cambio = {
                    "columna": columna_a_cambiar, "valor": nuevo_valor,
                    "ids_afectados": filas_seleccionadas['asignacion_id'].tolist(),
                    "nombres_afectados": nombres_lista
                }
                st.rerun()


        # --- 8. GUARDADO MANUAL (Si la edición masiva está APAGADA) ---
        elif not st.session_state.edit_mode:
            if not st.session_state.asignaciones_original.equals(df_editado) and not mes_esta_cerrado:
                if st.button("💾 Guardar Cambios Manuales (Recalcula Total)", type="primary"):
                    with st.spinner("Calculando totales..."):
                        resultado = actualizar_asignaciones_batch(df_editado, df_mes)
                        if isinstance(resultado, tuple):
                            num, errores = resultado
                            if errores:
                                st.error("Ocurrieron errores:")
                                for e in errores: st.write(e)
                        else:
                            num = resultado
                            
                        if num > 0:
                            st.success(f"¡Se actualizaron {num} registros!")
                            del st.session_state.asignaciones_original
                            time.sleep(1)
                            st.rerun()

        # --- 9. CONTENEDOR DE PREVISUALIZACIÓN Y CONFIRMACIÓN ---
        if 'propuesta_cambio' in st.session_state:
            propuesta = st.session_state.propuesta_cambio
            with st.container(border=True):
                st.error("🚨 **¡ESTÁS A UN PASO DE APLICAR CAMBIOS MASIVOS!** 🚨")
                st.markdown("### 🔍 Previsualización de Cambios")
                st.write(f"Vas a sobreescribir la columna **'{propuesta['columna']}'** con el valor **'{propuesta['valor']}'** en **{len(propuesta['ids_afectados'])}** filas:")
                
                nombres_preview = "- " + "\n- ".join(propuesta['nombres_afectados'][:10])
                st.code(nombres_preview, language=None)
                
                st.warning("⚠️ **Por favor, revisa la lista de arriba.**")
                st.markdown("---")
                
                with st.form("form_confirmacion_final"):
                    confirmacion_texto = st.text_input("Si estás seguro, escribe **CONFIRMAR CAMBIOS** en mayúsculas:")
                    submit_final = st.form_submit_button("✅ Confirmar y Ejecutar", type="primary", use_container_width=True)

                    if submit_final and confirmacion_texto == "CONFIRMAR CAMBIOS":
                        exito, error_msg = actualizar_asignaciones_masivo(propuesta['ids_afectados'], propuesta['columna'], propuesta['valor'])
                        if exito:
                            st.success("¡Cambios aplicados con éxito!")
                            del st.session_state.propuesta_cambio
                            if 'asignaciones_original' in st.session_state:
                                del st.session_state.asignaciones_original
                            st.session_state.edit_mode = False
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Error al aplicar los cambios: {error_msg}")
                
                if st.button("❌ Arrepentirse y Cancelar"):
                    del st.session_state.propuesta_cambio
                    st.rerun()

                            
    # ==========================================================
    # 2. ASIGNAR SOLO LIBRO PRINCIPAL
    # ==========================================================
    elif opcion_menu == "📖 Asignar Libro Principal":
        if mes_esta_cerrado: 
            st.warning("Mes cerrado.")
        else:
            if df_mes.empty: 
                st.info("No hay suscripciones en el mes.")
            else:
                df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]
                
                # --- ASIGNACIÓN MASIVA Y AUTOMÁTICA ---
                with st.container(border=True):
                    st.markdown("### 🎲 Asignación al Azar (Masiva y Segura)")
                    st.caption("Analiza stock y gustos en vivo. Solo asigna libros si existe coincidencia perfecta.")
                    
                    df_filtrado_final = df_pendientes.copy()
                    
                    # if not df_filtrado_final.empty:
                    #     df_filtrado_final['pagado'] = df_filtrado_final['pagado'].fillna("NO").astype(str).str.upper().str.strip()
                    #     df_filtrado_final = df_filtrado_final[df_filtrado_final['pagado'].isin(["SI", "SÍ"])]
                        
                    #     impagas = len(df_pendientes) - len(df_filtrado_final)
                    #     if impagas > 0:
                    #         st.warning(f"⚠️ Se omitieron **{impagas}** clientas de la asignación por tener su suscripción IMPAGA este mes.")
                    
                    descartar_antiguos = st.checkbox("🛡️ Solo incluir clientas que hayan actualizado su librero en los últimos 7 días")
                    if descartar_antiguos and not df_filtrado_final.empty:
                        df_filtrado_final['fecha_actualizacion_librero'] = pd.to_datetime(
                            df_filtrado_final['fecha_actualizacion_librero'], errors='coerce', utc=True
                        )
                        fecha_limite = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=7)
                        antes_de_fecha = len(df_filtrado_final)
                        df_filtrado_final = df_filtrado_final[df_filtrado_final['fecha_actualizacion_librero'] > fecha_limite]
                        
                        excluidas_fecha = antes_de_fecha - len(df_filtrado_final)
                        if excluidas_fecha > 0:
                            st.info(f"💡 Filtro activo: Se omitieron otras {excluidas_fecha} clientas por no actualizar su librero a tiempo.")
                        
                    st.metric("Cajas Pendientes", len(df_filtrado_final))
                    
                    if st.button("🔍 Generar Propuesta (Previsualización)", type="primary", use_container_width=True):
                        if not df_filtrado_final.empty:
                            with st.spinner("Analizando inventario y gustos..."):
                                prop, sin_asig = generar_propuesta_azar(df_filtrado_final)
                                st.session_state.propuesta_azar = prop
                                st.session_state.sin_asignar_azar = sin_asig
                        else: 
                            st.warning("No hay clientes pendientes que estén pagados (y que cumplan las condiciones de fecha si están activas).")
                            
                    if 'propuesta_azar' in st.session_state:
                        prop = st.session_state.propuesta_azar
                        sin_asig = st.session_state.sin_asignar_azar
                        
                        st.markdown("---")
                        st.markdown("#### 📝 Vista Previa de la Asignación")
                        
                        if prop:
                            st.success(f"✅ Se encontraron libros perfectos para **{len(prop)}** clientas.")
                            st.info("💡 **Tip UX:** Si no te convence alguna sugerencia, **desmarca la casilla 'Aprobar'** de esa fila. Ese libro no se asignará y la clienta quedará pendiente.")
                            
                            df_prop = pd.DataFrame(prop)
                            if 'Aprobar' not in df_prop.columns:
                                df_prop.insert(0, 'Aprobar', True)
                            
                            df_editado = st.data_editor(
                                df_prop,
                                column_config={
                                    "Aprobar": st.column_config.CheckboxColumn("✅ Aprobar", default=True),
                                    "asignacion_id": None, "cliente_id": None, "libro_id": None
                                },
                                disabled=['Cliente', 'Preferencias', 'Libro Asignado', 'Género del Libro', 'Autor'], 
                                hide_index=True, use_container_width=True, key="editor_azar"
                            )
                        else:
                            st.warning("El sistema no pudo encontrar ningún libro adecuado para las clientas pendientes.")
                            
                        if sin_asig:
                            st.error(f"⚠️ **{len(sin_asig)} clientas no recibirán libro en este proceso automático.**")
                            st.dataframe(pd.DataFrame(sin_asig), hide_index=True, use_container_width=True)
                            
                        col_conf1, col_conf2 = st.columns(2)
                        
                        if prop and col_conf1.button("✅ Confirmar Asignaciones Seleccionadas", type="primary", use_container_width=True):
                            with st.spinner("Guardando y descontando stock..."):
                                prop_aprobada = df_editado[df_editado['Aprobar'] == True].to_dict('records')
                                if prop_aprobada:
                                    exitos, errs = confirmar_propuesta_azar(prop_aprobada, ano_sel, mes_num)
                                    st.success(f"¡Se guardaron {exitos} asignaciones exitosamente!")
                                    st.balloons()
                                else:
                                    st.warning("Se descartaron todas las sugerencias. No se guardó nada.")
                                
                                del st.session_state.propuesta_azar
                                del st.session_state.sin_asignar_azar
                                time.sleep(2)
                                st.rerun()
                                
                        if col_conf2.button("❌ Cancelar Todo", use_container_width=True):
                            del st.session_state.propuesta_azar
                            del st.session_state.sin_asignar_azar
                            st.rerun()

                # --- ASIGNACIÓN INDIVIDUAL / MANUAL ---
                with st.container(border=True):
                    st.markdown("### 👤 Asignación Manual Individual")
                    
                    if df_pendientes.empty:
                        st.success("¡Todos los clientes ya tienen libro asignado para este mes!")
                    else:
                        with st.container(border=True):
                            st.markdown("##### 🔽 Filtrar Clientes Pendientes")
                            df_pendientes['metodo_entrega_limpio'] = df_pendientes['metodo_entrega'].apply(limpiar_texto)
                            metodos_disponibles = sorted(df_pendientes['metodo_entrega_limpio'].dropna().unique())
                            metodos_disponibles = [m for m in metodos_disponibles if m]
                            metodo_seleccionado = st.multiselect(
                                "Filtrar por Método de Envío:",
                                options=metodos_disponibles
                            )
                            
                        # Filtramos la lista de clientes según la selección
                        df_clientes_a_mostrar = df_pendientes.copy()
                        if metodo_seleccionado:
                            df_clientes_a_mostrar = df_clientes_a_mostrar[df_clientes_a_mostrar['metodo_entrega_limpio'].isin(metodo_seleccionado)]
                            
                        st.markdown("---")
                        
                        if df_clientes_a_mostrar.empty:
                            st.warning("No hay clientes pendientes que coincidan con ese método de envío.")
                        else:
                            dict_clientes = dict(zip(df_clientes_a_mostrar['nombre'], df_clientes_a_mostrar['cliente_id']))
                            cliente_nom = st.selectbox("Seleccionar Cliente Pendiente:", options=list(dict_clientes.keys()))
                            
                            if cliente_nom:
                                cliente_id = dict_clientes[cliente_nom]
                                filas_cliente = df_clientes_a_mostrar[df_clientes_a_mostrar['cliente_id'] == cliente_id]
                                
                                if filas_cliente.empty:
                                    st.warning("⚠️ No se pudieron cargar los datos de este cliente. Por favor, refresca la página.")
                                else:
                                    
                                    asig_row = df_clientes_a_mostrar[df_clientes_a_mostrar['cliente_id'] == cliente_id].iloc[0]
                                    
                                    col_chk1, col_chk2 = st.columns(2)
                                    ver_sin_stock = col_chk1.checkbox("📦 Mostrar también libros sin stock disponible", value=True)
                                    ver_todos_generos = col_chk2.checkbox("📚 Mostrar todos los géneros (Ignorar preferencias)", value=False)
                                    
                                    df_libros_disponibles, gustos_cliente = cargar_libros_filtrados_para_cliente(cliente_id, incluir_sin_stock=ver_sin_stock)
                                    
                                    if gustos_cliente:
                                        st.info(f"❤️ **Géneros preferidos del cliente:** {', '.join(gustos_cliente)}")
                                    else:
                                        st.caption("ℹ️ El cliente no registra géneros de preferencia específicos.")
                                        
                                    if df_libros_disponibles.empty:
                                        st.warning("No hay libros disponibles en el catálogo que el cliente no posea ya.")
                                    else:
                                        df_libros_a_mostrar = df_libros_disponibles.copy()
                                        
                                        if gustos_cliente:
                                            df_libros_a_mostrar['genero_limpio'] = df_libros_a_mostrar['genero'].apply(lambda x: limpiar_texto(str(x)).upper())
                                            
                                            def es_sugerido(row):
                                                return not set(gustos_cliente).isdisjoint(set(row['genero_limpio'].split()))
                                            df_libros_a_mostrar['es_sugerido'] = df_libros_a_mostrar.apply(es_sugerido, axis=1)
                                            
                                            if not ver_todos_generos:
                                                df_libros_a_mostrar = df_libros_a_mostrar[df_libros_a_mostrar['es_sugerido']]
                                                if df_libros_a_mostrar.empty:
                                                    st.warning("⚠️ No hay libros que coincidan con sus gustos. Marca 'Mostrar todos los géneros' para ver el resto del catálogo.")
                                                    
                                            df_libros_a_mostrar.sort_values(by=['es_sugerido', 'titulo'], ascending=[False, True], inplace=True)
                                        else:
                                            df_libros_a_mostrar['es_sugerido'] = False
                                            df_libros_a_mostrar.sort_values(by='titulo', inplace=True)
                                            
                                        if not df_libros_a_mostrar.empty:
                                            df_libros_a_mostrar['label_opcion'] = df_libros_a_mostrar.apply(
                                                lambda row: f"⭐ {row['titulo']} (Género: {row['genero']} | Stock: {row['stock']})" if row['es_sugerido'] else f"  {row['titulo']} (Género: {row['genero']} | Stock: {row['stock']})",
                                                axis=1
                                            )
                                            
                                            dict_libros = dict(zip(df_libros_a_mostrar['label_opcion'], df_libros_a_mostrar['libro_id']))
                                            libro_sel_label = st.selectbox("Seleccionar Libro para Asignar:", options=list(dict_libros.keys()))
                                            
                                            if libro_sel_label:
                                                libro_id_sel = dict_libros[libro_sel_label]
                                                libro_info = df_libros_a_mostrar[df_libros_a_mostrar['libro_id'] == libro_id_sel].iloc[0]
                                                
                                                if libro_info['stock'] <= 0:
                                                    st.warning("⚠️ **Atención:** El libro seleccionado tiene **0 o menos stock**.")
                                                
                                                if st.button("📌 Asignar Libro Seleccionado", type="primary", use_container_width=True):
                                                    ok, err = asignar_libro_principal(
                                                        asignacion_id=asig_row['asignacion_id'], cliente_id=cliente_id,
                                                        libro_id=libro_id_sel, stock_actual=libro_info['stock'],
                                                        ano=ano_sel, mes=mes_num, titulo=libro_info['titulo'], autor=libro_info.get('autor', '')
                                                    )
                                                    if ok:
                                                        st.success(f"¡Libro '{libro_info['titulo']}' asignado a {cliente_nom} con éxito!")
                                                        time.sleep(1.5)
                                                        st.rerun()
                                                    else:
                                                        st.error(f"Error al asignar: {err}")


    # ==========================================================
    # 3. GESTIONAR ENVÍO Y AJUSTE MANUAL
    # ==========================================================
    elif opcion_menu == "🚚 Gestionar Envío y Ajuste Manual":
        if mes_esta_cerrado: st.warning("Mes cerrado.")
        else:
            if df_mes.empty: st.info("No hay suscripciones.")
            else:
                with st.container(border=True):
                    st.markdown("### 🚚 Costo de Envío y Corrección de Extras")
                    st.info("💡 **Los libros extras ahora se añaden automáticamente desde la pestaña CAJA** (Ventana de Ventas). Usa esta sección solo para asignar manualmente el Costo de Envío o para hacer correcciones forzosas de texto en los Extras.")
                    
                    lista_clientes = [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} - {x['nombre']}", axis=1).tolist()
                    cliente_mod_sel = st.selectbox("1. Seleccionar Cliente:", lista_clientes)
                    
                    if cliente_mod_sel:
                        id_asig_tmp = int(cliente_mod_sel.split(" - ")[0].replace("ID:", ""))
                        row_caja = df_mes[df_mes['asignacion_id'] == id_asig_tmp].iloc[0]
                        
                        st.markdown("#### 🚚 Despacho y Envío")
                        cobro_envio_manual = st.number_input("Establecer Costo de Envío para esta caja ($):", min_value=0.0, step=500.0, value=float(row_caja.get('valor_envio', 0.0)))
                        
                        st.markdown("#### 📝 Ajuste Manual de Extras (Escape Hatch)")
                        st.warning("⚠️ Modifica estas casillas SOLAMENTE si necesitas corregir un error (ej: si anulaste una venta en caja y necesitas borrar el nombre del libro de esta lista).")
                        nuevo_extra_txt = st.text_input("Texto libre de Extras:", value=row_caja.get('extras', ''))
                        nuevo_valor_ext = st.number_input("Monto total acumulado por Extras ($):", min_value=0.0, step=500.0, value=float(row_caja.get('valor_extras', 0.0)))
                        
                        st.markdown("---")
                        if st.button("✅ Guardar Cambios en Logística", type="primary"):
                            ex, err = guardar_ajustes_logistica(id_asig_tmp, row_caja['cliente_id'], cobro_envio_manual, nuevo_extra_txt, nuevo_valor_ext)
                            if ex: 
                                st.success("¡Datos guardados! El Monto Total se recalculó automáticamente.")
                                st.rerun()
                            else: 
                                st.error(err)

    # ==========================================================
    # 4. COMENZAR MES
    # ==========================================================
    elif opcion_menu == "🚀 Generar / Actualizar Mes":
        if mes_esta_cerrado: 
            st.warning("Mes cerrado. No se pueden generar nuevos registros.")
        else:
            with st.container(border=True):
                st.markdown("### 🚀 Generar Cajas o Agregar Nuevos Clientes")
                
                df_suscritos_activos = cargar_clientes_suscritos()
                total_clientes_activos = len(df_suscritos_activos)
                
                if not df_mes.empty:
                    clientes_en_mes = df_mes['cliente_id'].nunique()
                    clientes_faltantes = total_clientes_activos - clientes_en_mes
                else:
                    clientes_en_mes = 0
                    clientes_faltantes = total_clientes_activos
                
                col1, col2, col3 = st.columns(3)
                col1.metric("👥 Total Clientes Activos", total_clientes_activos)
                col2.metric("📦 Cajas Creadas en el Mes", clientes_en_mes)
                col3.metric("⏳ Cajas Pendientes por Crear", max(0, clientes_faltantes), help="Clientes activos que aún no tienen una caja para este mes.")
                st.markdown("---")
                
                st.info(
                    "💡 **¿Cómo usar esta herramienta?**\n\n"
                    "1. **A principio de mes:** Crea las cajas en blanco para todas tus clientas en estado 'ACTIVA'.\n"
                    "2. **A mitad de mes:** Si se inscriben nuevas clientas, presiona este botón nuevamente para agregarlas.\n\n"
                    "🛡️ **Tranquilidad:** El sistema es inteligente y **solo agregará a las clientas faltantes** con un costo fijo de caja base de $10.000."
                )
                
                if st.button("Crear Registros Faltantes del Mes", type="primary", use_container_width=True):
                    df_mes_fresco = cargar_asignaciones_mes(ano_sel, mes_num)
                    progress_placeholder = st.empty()
                    ex, msg = comenzar_mes(ano_sel, mes_num, df_mes_fresco, progress_placeholder)
                    
                    if ex: 
                        st.success(msg)
                        st.balloons()
                        time.sleep(2)
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
                            asig_quitar = st.selectbox("Selecciona cliente:", [""] + df_con_algo.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre']}", axis=1).tolist())
                            
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
                                            if ex: st.success("Libro extra quitado."), st.balloons(), st.rerun()
                                            else: st.error(err)
                        else: st.info("No hay cajas con libros para quitar.")
                
                with col_e2:
                    with st.container(border=True):
                        st.markdown("##### 🟥 2. Eliminar Fila Completa")
                        st.caption("Borra definitivamente la fila del cliente para este mes.")
                        asig_eliminar = st.selectbox("Selecciona registro a borrar:", [""] + df_mes.apply(lambda x: f"ID:{x['asignacion_id']} | {x['nombre']} | {x['titulo_libro']}", axis=1).tolist())
                        if asig_eliminar and st.button("🟥 ELIMINAR FILA DEFINITIVAMENTE"):
                            id_asig = int(asig_eliminar.split(" | ")[0].replace("ID:", ""))
                            row = df_mes[df_mes['asignacion_id'] == id_asig].iloc[0]
                            ex, err = eliminar_asignacion(id_asig, row.get('libro_suscripcion_id'), row['cliente_id'], ano_sel, mes_num, row.get('extras', ''))
                            if ex: st.success("Registro eliminado."), st.balloons(), st.rerun()
                            else: st.error(err)
            else: st.info("No hay registros.")
            
        # ==========================================================
    # 6. DESASIGNAR LIBROS DEL MES (SOLO LIBRO PRINCIPAL)
    # ==========================================================
    elif opcion_menu == "🧹 Desasignar Libros del Mes":
        if mes_esta_cerrado: 
            st.warning("Mes cerrado. No se pueden modificar los registros.")
        else:
            with st.container(border=True):
                st.markdown("### 🧹 Desasignar Libros Principales del Mes")
                st.warning("⚠️ **ATENCIÓN:** Esta acción quitará el libro asignado de **TODAS** las cajas de este mes, devolviendo el stock al catálogo y limpiando el historial de lectura del cliente. **Las cajas y su información de pago se mantendrán intactas.**")
                
                # Filtramos para ver cuántas cajas tienen un libro asignado actualmente
                df_con_libro = df_mes[df_mes['titulo_libro'] != "⏳ PENDIENTE DE ASIGNAR"]
                
                if df_con_libro.empty:
                    st.success("🎉 Todas las cajas de este mes ya se encuentran en estado 'PENDIENTE DE ASIGNAR'.")
                else:
                    st.metric("Libros a Desasignar y Liberar", len(df_con_libro))
                    
                    st.markdown("Para confirmar esta acción, escribe la palabra **DESASIGNAR** en la casilla de abajo:")
                    confirmacion = st.text_input("Escribe DESASIGNAR:")
                    
                    if confirmacion == "DESASIGNAR":
                        if st.button("🚨 QUITAR TODOS LOS LIBROS DEL MES", type="primary", use_container_width=True):
                            with st.spinner("Liberando libros y actualizando stock..."):
                                exitos = 0
                                errores = []
                                
                                # Recorremos solo las cajas que tienen libros asignados
                                for _, row in df_con_libro.iterrows():
                                    # Usamos la función interna de desasignación principal
                                    ex, err = quitar_un_libro(
                                        row['asignacion_id'], 
                                        row['cliente_id'], 
                                        ano_sel, 
                                        mes_num, 
                                        "PRINCIPAL", 
                                        row['titulo_libro'], 
                                        0 # No aplicamos descuentos porque las cajas no se borran
                                    )
                                    if ex: 
                                        exitos += 1
                                    else: 
                                        errores.append(err)
                                
                                # Limpiamos cachés para ver el impacto inmediato en el stock y las tablas
                                cargar_catalogo_completo_libros.clear()
                                
                                if exitos > 0:
                                    st.success(f"✅ ¡Se liberaron {exitos} libros con éxito! El stock ha sido devuelto al inventario.")
                                    st.balloons()
                                if errores:
                                    st.error(f"Hubo {len(errores)} errores:")
                                    for e in errores: st.write(e)
                                    
                                time.sleep(2)
                                st.rerun()

    elif opcion_menu == "🔒 Cierre de Mes":
        if mes_esta_cerrado:
            st.success(f"El mes {mes_sel} {ano_sel} está **CERRADO**.")
            if st.button("🔓 Reabrir Mes"): cambiar_estado_mes(ano_sel, mes_num, False); st.rerun()
        else:
            st.info(f"El mes {mes_sel} {ano_sel} está **ABIERTO**.")
            if st.button("🔒 CERRAR MES DEFINITIVAMENTE", type="primary"): cambiar_estado_mes(ano_sel, mes_num, True); st.rerun()

if __name__ == "__main__":
    mostrar_asignaciones()
