import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import time
import io
import os
import urllib.request
import re
from PIL import Image, ImageDraw, ImageFont
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

def unificar_formatos_fecha(serie_fechas):
    """
    Función de parseo de fechas a prueba de balas, capaz de interpretar
    múltiples formatos (YYYY-MM-DD y DD-MM-YYYY).
    """
    def parsear_valor(val):
        if pd.isna(val) or not str(val).strip() or str(val).strip().lower() in ['nan', 'nat']:
            return pd.NaT
        
        val_str = str(val).strip()
        try:
            if len(val_str.split('-')[0]) == 4 or len(val_str.split('/')[0]) == 4:
                return pd.to_datetime(val_str, dayfirst=False, errors='coerce')
            else:
                return pd.to_datetime(val_str, dayfirst=True, errors='coerce')
        except:
            return pd.to_datetime(val_str, errors='coerce')
            
    try:
        return serie_fechas.apply(parsear_valor)
    except Exception as e:
        log_error("vista_caja", "unificar_formatos_fecha", f"Error inesperado al parsear fechas. Detalle: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return pd.to_datetime(serie_fechas, errors='coerce')

@st.cache_data(ttl=300)
def cargar_libros_caja():
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table("libros")
                   .select("libro_id, titulo, autor, precio, costo, stock, editorial, encuadernacion, precio_original")
                   .order("libro_id")
                   .range(start, end).execute())
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        df = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df.empty:
            df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0.0)
            df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0.0)
            df['precio_original'] = pd.to_numeric(df.get('precio_original', df['precio']), errors='coerce').fillna(df['precio'])
            df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e: 
        log_error("vista_caja", "cargar_libros_caja", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error("Error crítico: No se pudo cargar el catálogo de libros.")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_clientes_caja():
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table("clientes")
                   .select("cliente_id, nombre, email, telefono, status, rut, direccion")
                   .order("cliente_id")
                   .range(start, end).execute())
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception as e:
        log_error("vista_caja", "cargar_clientes_caja", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error("Error crítico: No se pudo cargar el listado de clientes.")
        return pd.DataFrame(columns=['cliente_id', 'nombre', 'email', 'telefono', 'status', 'rut', 'direccion'])

def check_exclusivity(client_id, exclusive_ids_raw):
    """
    Evalúa si un cliente está dentro de la lista de exclusividad del cupón.
    Soporta formato JSON [1, 2], coma-separado '1, 2' o IDs únicos.
    """
    if pd.isna(exclusive_ids_raw) or exclusive_ids_raw is None or str(exclusive_ids_raw).strip() == "" or str(exclusive_ids_raw).lower() in ["none", "nan", "null", "[]"]:
        return True  # Es público para todos (corrige el bug de '[]')
        
    val_str = str(exclusive_ids_raw).strip()
    
    # Intenta parsear como lista JSON
    if val_str.startswith('[') and val_str.endswith(']'):
        try:
            allowed_ids = json.loads(val_str)
            if isinstance(allowed_ids, list):
                if not allowed_ids:
                    return True # Lista vacía es público para todos
                return int(client_id) in [int(x) for x in allowed_ids]
        except Exception:
            pass
            
    # Intenta parsear como lista separada por comas
    if ',' in val_str:
        try:
            allowed_ids = [int(x.strip()) for x in val_str.split(',') if x.strip()]
            return int(client_id) in allowed_ids
        except Exception:
            pass
            
    # Intenta comparar como ID único
    try:
        return int(client_id) == int(float(val_str))
    except Exception:
        pass
        
    return False

def evaluar_restricciones_libro(libro_item, cupon):
    """
    Evalúa si un libro del carrito cumple con las restricciones del cupón.
    Retorna True si califica para el descuento, False en caso contrario.
    """
    if not cupon:
        return True
        
    # 1. Restricción de Encuadernación
    enc = str(libro_item.get('encuadernacion', '')).strip().upper()
    rest_enc = str(cupon.get('restriccion_encuadernacion', 'Todos')).strip().upper()
    
    if rest_enc == "SOLO TAPA BLANDA" and enc != "TAPA BLANDA":
        return False
    if rest_enc == "SOLO TAPA DURA" and enc != "TAPA DURA":
        return False
    if rest_enc == "EXCLUIR TAPA DURA" and enc == "TAPA DURA":
        return False
        
    # 2. Restricción de Editorial (Soporta una o múltiples editoriales guardadas como JSON list)
    rest_edit_raw = cupon.get('restriccion_editorial')
    if rest_edit_raw and str(rest_edit_raw).strip() != "" and str(rest_edit_raw).lower() not in ["none", "nan", "null"]:
        try:
            allowed_edits = json.loads(rest_edit_raw)
            if isinstance(allowed_edits, list) and allowed_edits:
                item_edit = str(libro_item.get('editorial', '')).strip().upper()
                if item_edit not in [str(e).strip().upper() for e in allowed_edits]:
                    return False
        except Exception:
            pass
            
    # 3. Restricción de Autor (Soporta uno o múltiples autores guardados como JSON list)
    rest_autor_raw = cupon.get('restriccion_autor')
    if rest_autor_raw and str(rest_autor_raw).strip() != "" and str(rest_autor_raw).lower() not in ["none", "nan", "null"]:
        try:
            allowed_autores = json.loads(rest_autor_raw)
            if isinstance(allowed_autores, list) and allowed_autores:
                item_autor = str(libro_item.get('autor', '')).strip().upper()
                if item_autor not in [str(a).strip().upper() for a in allowed_autores]:
                    return False
        except Exception:
            pass
            
    return True

@st.cache_data(ttl=120)
def cargar_cupones_caja():
    """Obtiene los cupones desde la base de datos aplicando el bypass de límite de 1000 registros."""
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = (conn.table("cupones")
                   .select("*")
                   .order("cupon_id")
                   .range(start, end).execute())
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def cargar_listas_desplegables_caja():
    """Obtiene Autores y Editoriales únicos para los desplegables de caja."""
    try:
        df_libros = cargar_libros_caja()
        if df_libros.empty:
            return [], []
        
        autores = sorted(df_libros['autor'].dropna().unique().tolist())
        editoriales = sorted(df_libros['editorial'].dropna().unique().tolist())
        
        autores = [a for a in autores if str(a).strip()]
        editoriales = [e for e in editoriales if str(e).strip()]
        
        return autores, editoriales
    except Exception as e:
        log_error("vista_caja", "cargar_listas_desplegables_caja", f"Error: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return [], []

def gestionar_cliente(nombre, correo, telefono, rut, direccion, cliente_id_existente=None):
    if not nombre: return None, "El nombre del cliente es obligatorio."
    conn = get_db_connection()
    
    nombre_limpio = limpiar_texto_para_busqueda(nombre)
    datos = {
        "nombre": nombre_limpio, 
        "email": limpiar_texto_para_busqueda(correo), 
        "telefono": limpiar_texto_para_busqueda(telefono),
        "rut": limpiar_texto_para_busqueda(rut),
        "direccion": limpiar_texto_para_busqueda(direccion)
    }
    
    try:
        if cliente_id_existente:
            conn.table("clientes").update(datos).eq("cliente_id", cliente_id_existente).execute()
            return cliente_id_existente, ""
        else:
            res_check = conn.table("clientes").select("cliente_id").eq("nombre", nombre_limpio).execute()
            if res_check.data:
                return None, f"¡DUPLICADO DETENIDO! Ya existe un cliente registrado con el nombre '{nombre_limpio}'."
                
            datos["status"] = "CLIENTE REGULAR"
            response = conn.table("clientes").insert(datos).execute()
            return response.data[0]['cliente_id'], ""
    except Exception as e: 
        log_error("vista_caja", "gestionar_cliente", f"Error: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return None, f"No se pudo {'actualizar' if cliente_id_existente else 'crear'} al cliente '{nombre}'. Detalle: {e}"

@st.cache_data(ttl=300)
def cargar_historial_completo():
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        for bloque in range(200): 
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res_ventas = (conn.table("registro_ventas")
                          .select("*, cliente:clientes(cliente_id, nombre, rut, email, telefono, direccion)")
                          .order("venta_id", desc=True)
                          .range(start, end).execute())
                
            if res_ventas.data:
                all_data.extend(res_ventas.data)
                if len(res_ventas.data) < chunk_size:
                    break
            else:
                break
                
        if not all_data: 
            return pd.DataFrame()
        df_ventas = pd.DataFrame(all_data)
        if 'cliente' in df_ventas.columns:
            df_clientes_data = pd.json_normalize(df_ventas['cliente']).add_prefix('cliente_')
            df_ventas = pd.concat([df_ventas.drop(columns=['cliente']), df_clientes_data], axis=1)
            df_ventas['cliente_nombre'] = df_ventas['cliente_nombre'].fillna('Cliente Eliminado')
        else: 
            df_ventas['cliente_nombre'] = 'Sin Cliente'
            df_ventas['cliente_rut'] = ''
            df_ventas['cliente_email'] = ''
            df_ventas['cliente_telefono'] = ''
            df_ventas['cliente_direccion'] = ''
            df_ventas['cliente_id'] = None
            
        def formatear_libros(libros_data):
            if not isinstance(libros_data, str) or not libros_data.strip(): return "Sin Detalle"
            if libros_data.strip().startswith('['):
                try:
                    libros = json.loads(libros_data)
                    return " | ".join([f"{item.get('cantidad', 1)} x {item.get('titulo', 'N/A')}" for item in libros])
                except: return libros_data
            else: return libros_data
                
        df_ventas['libros_vendidos'] = df_ventas['libros_vendidos'].apply(formatear_libros)
        df_ventas['nombre_cliente'] = df_ventas['cliente_nombre']
        
        df_ventas['monto_final'] = pd.to_numeric(df_ventas['monto_final'], errors='coerce').fillna(0)
        df_ventas['abono'] = pd.to_numeric(df_ventas.get('abono', 0), errors='coerce').fillna(0)
        df_ventas['costo_venta'] = pd.to_numeric(df_ventas.get('costo_venta', 0), errors='coerce').fillna(0)
        df_ventas['valor_envio'] = pd.to_numeric(df_ventas.get('valor_envio', 0), errors='coerce').fillna(0)
        df_ventas['estado_pago'] = df_ventas.get('estado_pago', 'PENDIENTE').fillna('PENDIENTE')
        df_ventas['deuda'] = df_ventas['monto_final'] - df_ventas['abono']
        df_ventas['utilidad'] = (df_ventas['monto_final'] - df_ventas['valor_envio']) - df_ventas['costo_venta']
        
        if 'fecha_pago' not in df_ventas.columns:
            df_ventas['fecha_pago'] = pd.NaT
        df_ventas['fecha_pago'] = pd.to_datetime(df_ventas['fecha_pago'], errors='coerce').dt.date
        
        return df_ventas
    except Exception as e:
        log_error("vista_caja", "cargar_historial_completo", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error(f"Error crítico al cargar el historial de ventas: {e}")
        return pd.DataFrame()

def gestionar_libro(titulo, autor, precio_catalogo, stock_a_sumar, libro_id_existente=None, encuadernacion="", editorial="", apto_cajita=True, costo=None):
    conn = get_db_connection()
    datos = {
        "titulo": limpiar_texto_para_busqueda(titulo), 
        "autor": limpiar_texto_para_busqueda(autor), 
        "precio": float(precio_catalogo),
        "encuadernacion": limpiar_texto_para_busqueda(encuadernacion),
        "editorial": limpiar_texto_para_busqueda(editorial),
        "apto_cajita": apto_cajita
    }
    
    if costo is not None:
        datos["costo"] = float(costo)
    
    if libro_id_existente:
        # Usamos filtros más robustos que eviten omitir valores numéricos de 0.0 o booleanos False
        datos_actualizar = {k: v for k, v in datos.items() if v is not None and v != ""}
        if datos_actualizar:
            conn.table("libros").update(datos_actualizar).eq("libro_id", libro_id_existente).execute()
        return libro_id_existente
    else:
        datos["stock"] = int(stock_a_sumar)
        datos["precio_original"] = float(precio_catalogo)
        response = conn.table("libros").insert(datos).execute()
        return response.data[0]['libro_id']

def check_elegibilidad_cliente_cupon(cliente_id, df_clientes, df_ventas_global, monto_minimo=100000, plazo_dias=365):
    if df_clientes.empty or cliente_id is None:
        return False, 0.0, "Nunca"
    
    cli_rows = df_clientes[df_clientes['cliente_id'] == int(cliente_id)]
    if cli_rows.empty:
        return False, 0.0, "Nunca"
    
    cli = cli_rows.iloc[0]
    status_str = str(cli.get('status', ''))
    
    fecha_canje = None
    if "CANJE_CUPON:" in status_str:
        try:
            fecha_canje_str = status_str.split("CANJE_CUPON:")[1].strip()
            fecha_canje = datetime.strptime(fecha_canje_str, "%Y-%m-%d")
        except Exception:
            pass
            
    # Determinar la fecha base de comparación de forma inteligente (máxima de la base o fallback de desarrollo)
    if not df_ventas_global.empty:
        if 'fecha_limpia' in df_ventas_global.columns:
            ref_date = df_ventas_global['fecha_limpia'].max()
        else:
            ref_date = pd.to_datetime(df_ventas_global['fecha_venta'], errors='coerce').max()
        
        if pd.isna(ref_date):
            ref_date = pd.to_datetime("2026-08-27")
    else:
        ref_date = pd.to_datetime("2026-08-27")
        
    if hasattr(ref_date, 'tz') and ref_date.tz is not None:
        ref_date = ref_date.tz_localize(None)
        
    fecha_limite = ref_date - timedelta(days=plazo_dias)
    
    if not df_ventas_global.empty and 'cliente_id' in df_ventas_global.columns:
        df_cli_ventas = df_ventas_global[df_ventas_global['cliente_id'] == int(cliente_id)].copy()
        if not df_cli_ventas.empty:
            df_cli_ventas['fecha_dt'] = unificar_formatos_fecha(df_cli_ventas['fecha_venta'])
            df_cli_ventas = df_cli_ventas.dropna(subset=['fecha_dt'])
            
            # Quitar offsets
            def safe_to_naive(val):
                if pd.isna(val): return pd.NaT
                ts = pd.to_datetime(val)
                return ts.tz_localize(None) if ts.tz is not None else ts
                
            df_cli_ventas['fecha_dt'] = df_cli_ventas['fecha_dt'].apply(safe_to_naive)
            df_cli_ventas = df_cli_ventas[df_cli_ventas['fecha_dt'] >= fecha_limite]
            
            if fecha_canje:
                df_cli_ventas = df_cli_ventas[df_cli_ventas['fecha_dt'] > fecha_canje]
            
            df_completas = df_cli_ventas[
                (df_cli_ventas['estado'] == 'FINALIZADO') | 
                (df_cli_ventas['estado_pago'] == 'PAGADO')
            ]
            total_compras = df_completas['monto_final'].sum()
        else:
            total_compras = 0.0
    else:
        total_compras = 0.0
        
    clasifica = total_compras >= monto_minimo
    fecha_canje_label = fecha_canje.strftime("%d/%m/%Y") if fecha_canje else "Nunca"
    
    return clasifica, total_compras, fecha_canje_label

def validar_cupon_sistema(codigo, cliente_id, df_cupones):
    """Evalúa la validez del cupón respecto al cliente, vigencia y límites."""
    if df_cupones.empty:
        return False, "No se encontraron cupones registrados o la tabla no está creada."
        
    codigo_limpio = str(codigo).strip().upper()
    match = df_cupones[df_cupones['codigo'].str.upper() == codigo_limpio]
    
    if match.empty:
        return False, f"El cupón '{codigo_limpio}' no existe en el sistema."
        
    cupon = match.iloc[0]
    
    if not cupon.get('activo', True):
        return False, "Este cupón ha sido desactivado."
        
    usos = int(cupon.get('usos_actuales', 0))
    limite = int(cupon.get('limite_usos', 1))
    if usos >= limite:
        return False, f"Este cupón de un solo uso ya ha sido canjeado ({usos}/{limite})."
        
    hoy = date.today()
    fi = cupon.get('fecha_inicio')
    ff = cupon.get('fecha_fin')
    
    if pd.notna(fi) and fi:
        try:
            fi_dt = pd.to_datetime(fi).date()
            if hoy < fi_dt:
                return False, f"Este cupón entra en vigencia el {fi_dt.strftime('%d/%m/%Y')}."
        except Exception:
            pass
            
    if pd.notna(ff) and ff:
        try:
            ff_dt = pd.to_datetime(ff).date()
            if hoy > ff_dt:
                return False, f"El cupón expiró el {ff_dt.strftime('%d/%m/%Y')}."
        except Exception:
            pass
            
    cliente_exclusivo = cupon.get('cliente_id_exclusivo')
    if pd.notna(cliente_exclusivo) and cliente_exclusivo is not None:
        if cliente_id is None or int(cliente_id) != int(cliente_exclusivo):
            return False, "Este cupón es exclusivo para otra clienta."
            
    return True, cupon

def procesar_venta_carrito(carrito, cliente_id, valor_envio, metodo_envio, metodo_pago, comentario, fecha_venta, estado_venta, estado_pago, fecha_pago, abono_venta, tipo_cobro_envio, asignacion_id=None, venta_id_asociada=None):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    
    try:
        # --- PASO 1: INSERTAR/ACTUALIZAR LIBROS EN EL CATÁLOGO Y ASIGNAR ID DEFINITIVO ---
        costo_total_venta = 0.0
        for item in carrito:
            l_id = item['libro_id']
            if item.get('es_nuevo', False): 
                # Insertar libro nuevo en Supabase y obtener su ID definitivo
                l_id = gestionar_libro(
                    item['titulo'], item['autor'], item['precio_catalogo'], 
                    item['cantidad'], None, item.get('encuadernacion', ''), 
                    item.get('editorial', ''), item.get('apto_cajita', True), 
                    costo=item.get('costo')
                )
                # Actualizamos el libro_id en el carrito para que se registre correctamente en el JSON de la venta
                item['libro_id'] = l_id
            else:
                # Libro existente: actualizamos catálogo y stock
                gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], 0, l_id, costo=item.get('costo'))
                nuevo_stock = item['stock_actual'] - item['cantidad']
                if item['stock_actual'] <= 0 or nuevo_stock < 0:
                    nuevo_stock = 0
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
            
            costo_unitario = item.get('costo', 0.0)
            if pd.isna(costo_unitario) or costo_unitario is None: 
                costo_unitario = 0.0
            costo_total_venta += float(costo_unitario) * int(item['cantidad'])

        # --- PASO 2: CONSTRUIR LA LISTA DE VENTA CON LOS IDS DE LIBRO TOTALMENTE RESUELTOS ---
        libros_nuevos_list = []
        for item in carrito:
            libros_nuevos_list.append({
                "libro_id": item['libro_id'], 
                "titulo": item['titulo'], 
                "autor": item['autor'],
                "cantidad": item['cantidad'], 
                "precio": item['precio_cobrado']
            })

        subtotal_libros = sum([item['subtotal'] for item in carrito])

        # --- PASO 3: REGISTRAR O FUSIONAR LA VENTA EN REGISTRO_VENTAS ---
        if venta_id_asociada:
            res_old = conn.table("registro_ventas").select("*").eq("venta_id", int(venta_id_asociada)).execute()
            if not res_old.data:
                return False, f"No se pudo encontrar la venta de origen #{venta_id_asociada} para fusionar."
            venta_old = res_old.data[0]
            try:
                libros_old_list = json.loads(venta_old.get('libros_vendidos', '[]'))
            except:
                libros_old_list = []
                
            for n_item in libros_nuevos_list:
                found = False
                for o_item in libros_old_list:
                    if o_item.get('libro_id') == n_item['libro_id'] and o_item['titulo'] == n_item['titulo']:
                        o_item['cantidad'] = int(o_item.get('cantidad', 1)) + int(n_item['cantidad'])
                        found = True
                        break
                if not found:
                    libros_old_list.append(n_item)
            
            nuevo_subtotal_libros = float(venta_old.get('subtotal_libros', 0.0)) + float(subtotal_libros)
            nuevo_costo_venta = float(venta_old.get('costo_venta', 0.0)) + float(costo_total_venta)
            
            old_tipo_cobro = venta_old.get('tipo_cobro_envio', 'envio pagado')
            if old_tipo_cobro == "envio por pagar":
                nuevo_monto_final = nuevo_subtotal_libros
            else:
                nuevo_monto_final = nuevo_subtotal_libros + float(venta_old.get('valor_envio', 0.0))
                
            nuevo_abono = float(venta_old.get('abono', 0.0)) + float(abono_venta)
            
            datos_fusion = {
                "libros_vendidos": json.dumps(libros_old_list, ensure_ascii=False),
                "subtotal_libros": nuevo_subtotal_libros,
                "costo_venta": nuevo_costo_venta,
                "monto_final": nuevo_monto_final,
                "abono": nuevo_abono,
                "comentario": f"{venta_old.get('comentario', '')} | Fusionada: {comentario}".strip()
            }
            conn.table("registro_ventas").update(datos_fusion).eq("venta_id", int(venta_id_asociada)).execute()
            
        else:
            monto_final = subtotal_libros + valor_envio if tipo_cobro_envio != "envio por pagar" else subtotal_libros
            datos_venta = {
                "cliente_id": cliente_id, "fecha_venta": fecha_venta.strftime("%Y-%m-%d %H:%M:%S"),
                "libros_vendidos": json.dumps(libros_nuevos_list, ensure_ascii=False), 
                "subtotal_libros": float(subtotal_libros), "valor_envio": float(valor_envio), 
                "monto_final": float(monto_final), "metodo_envio": metodo_envio, 
                "comentario": f"Pago: {metodo_pago}. {comentario}".strip(), "estado": estado_venta,
                "estado_pago": estado_pago, 
                "fecha_pago": fecha_pago.isoformat() if fecha_pago else None,
                "abono": float(abono_venta), "costo_venta": float(costo_total_venta),
                "tipo_cobro_envio": tipo_cobro_envio
            }
            conn.table("registro_ventas").insert(datos_venta).execute()
            
        # --- PASO 4: REGISTRAR LIBRERO HISTÓRICO ---
        for item in carrito:
            l_id = item['libro_id']
            if cliente_id and l_id:
                res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", l_id).execute()
                if not res_hist.data:
                    datos_historico = {"cliente_id": cliente_id, "libro_id": l_id, "autor_historico": limpiar_texto_para_busqueda(item['autor']), "origen": "VENTA CAJA"}
                    conn.table("librero_historico").insert(datos_historico).execute()

        # --- PASO 5: EXTRAS DE ASIGNACIONES (CLUB DE SUSCRIPCIÓN) ---
        if asignacion_id:
            try:
                res_asig = conn.table("asignaciones").select("extras, valor_extras").eq("asignacion_id", asignacion_id).execute()
                if res_asig.data:
                    asig_actual = res_asig.data[0]
                    extras_previos_raw = asig_actual.get('extras') or ""
                    valor_previo = float(asig_actual.get('valor_extras') or 0.0)
                    
                    lista_extras_previos = []
                    if extras_previos_raw:
                        items = extras_previos_raw.replace('\\n', '|').split('|')
                        for item in items:
                            item_limpio = item.strip()
                            if '.' in item_limpio:
                                item_limpio = item_limpio.split('.', 1)[-1].strip()
                            if item_limpio:
                                lista_extras_previos.append(item_limpio.upper())
                                
                    nuevos_extras_list = [f"{item['cantidad']} x {item['titulo']}".upper() for item in carrito]
                    lista_completa = lista_extras_previos + nuevos_extras_list
                    extras_final_enumerado = "\\n".join([f"{i+1}. {libro}" for i, libro in enumerate(lista_completa)])
                    valor_final = valor_previo + subtotal_libros
                    
                    conn.table("asignaciones").update({
                        "extras": extras_final_enumerado, 
                        "valor_extras": valor_final
                    }).eq("asignacion_id", asignacion_id).execute()
                    
            except Exception as ex_asig:
                log_error("vista_caja", "procesar_venta_carrito (actualizar extras)", f"Error {ex_asig}", email_usuario)
                st.warning(f"⚠️ Venta procesada, pero no se registraron extras en la suscripción. Detalle: {ex_asig}")
        return True, ""
    except Exception as e:
        error_detalle = f"Fallo crítico registrando venta. Detalle técnico: {e}"
        log_error("vista_caja", "procesar_venta_carrito", error_detalle, email_usuario)
        return False, str(e)

def anular_venta(venta_id, texto_libros_vendidos):
    conn = get_db_connection()
    try:
        items = texto_libros_vendidos.split(" | ")
        for item in items:
            partes = item.split(" x ", 1)
            if len(partes) == 2:
                try:
                    cantidad_devuelta = int(partes[0].strip())
                    titulo_libro = partes[1].strip()
                except ValueError:
                    continue
                res_l = conn.table("libros").select("libro_id, stock").eq("titulo", titulo_libro).execute()
                if res_l.data:
                    l_id = res_l.data[0]['libro_id']
                    stock_bd = res_l.data[0]['stock']
                    
                    if stock_bd <= 0:
                        nuevo_stock = 0
                    else:
                        nuevo_stock = stock_bd + cantidad_devuelta
                        
                    conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
                    
        conn.table("registro_ventas").delete().eq("venta_id", venta_id).execute()
        return True, ""
    except Exception as e:
        log_error("vista_caja", "anular_venta", e, st.session_state.get('email_usuario', 'Desconocido'))
        return False, str(e)

def actualizar_historial_caja(df_editado):
    df_original = st.session_state.get('historial_original', pd.DataFrame())
    if df_original.empty: return 0
    
    df_original_str = df_original.astype(str)
    df_editado_str = df_editado.astype(str)
    diff_mask = df_original_str.ne(df_editado_str).any(axis=1)
    filas_cambiadas = df_editado[diff_mask]
    
    if filas_cambiadas.empty:
        st.info("No se detectaron cambios para guardar.")
        return 0
    conn = get_db_connection()
    updates = 0
    
    for _, row in filas_cambiadas.iterrows():
        try:
            venta_id = int(row['venta_id'])
            cliente_id = row.get('cliente_cliente_id') 
            if cliente_id and pd.notna(cliente_id):
                datos_cliente = {
                    'nombre': limpiar_texto_para_busqueda(row.get('cliente_nombre')),
                    'rut': limpiar_texto_para_busqueda(row.get('cliente_rut')),
                    'email': limpiar_texto_para_busqueda(row.get('cliente_email')),
                    'telefono': limpiar_texto_para_busqueda(row.get('cliente_telefono'))
                }
                datos_cliente_limpios = {k: v for k, v in datos_cliente.items() if pd.notna(v) and v != 'nan'}
                if datos_cliente_limpios:
                    conn.table("clientes").update(datos_cliente_limpios).eq("cliente_id", int(cliente_id)).execute()
            
            datos_venta_raw = {k: v for k, v in row.items() if not k.startswith('cliente_')}
            tipo_cobro = str(datos_venta_raw.get('tipo_cobro_envio', 'envio pagado')).lower().strip()
            subtotal = float(row.get('subtotal_libros', 0.0))
            envio = float(row.get('valor_envio', 0.0))
            
            if tipo_cobro == "envio por pagar":
                monto_final_actual = subtotal  
            elif tipo_cobro == "retiro":
                monto_final_actual = subtotal
            else:
                monto_final_actual = subtotal + envio
                
            datos_venta_raw['monto_final'] = monto_final_actual
            
            if datos_venta_raw.get('estado') == 'FINALIZADO' or datos_venta_raw.get('estado_pago') == 'PAGADO':
                datos_venta_raw['estado_pago'] = 'PAGADO'
                datos_venta_raw['abono'] = monto_final_actual
            else:
                datos_venta_raw['abono'] = float(row.get('abono', 0.0))
                
            datos_venta_final = {}
            columnas_venta_validas = ['monto_final', 'abono', 'costo_venta', 'estado', 'estado_pago', 'fecha_pago', 'metodo_envio', 'comentario', 'tipo_cobro_envio', 'valor_envio']
            for col in columnas_venta_validas:
                if col in datos_venta_raw:
                    valor = datos_venta_raw[col]
                    if col == 'fecha_pago':
                        datos_venta_final[col] = pd.to_datetime(valor).isoformat() if pd.notna(valor) and str(valor).strip() != '' else None
                    else:
                        datos_venta_final[col] = valor
                        
            if datos_venta_final:
                conn.table("registro_ventas").update(datos_venta_final).eq("venta_id", venta_id).execute()
            
            updates += 1
        except Exception as e:
            log_error("vista_caja", "actualizar_historial_caja", f"Error en venta #{row.get('venta_id', 'Desconocido')}: {e}", st.session_state.get('email_usuario', 'Desconocido'))
            st.warning(f"No se pudo guardar la fila de la venta #{row.get('venta_id', '')}.")
            continue
            
    return updates

def cambiar_logistica_venta_existente(venta_id, nuevo_metodo, valor_envio, asignacion_id=None):
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        res_v = conn.table("registro_ventas").select("*").eq("venta_id", int(venta_id)).execute()
        if not res_v.data:
            return False, "No se encontró la venta especificada."
        
        venta = res_v.data[0]
        cliente_id = venta.get("cliente_id")
        subtotal_libros = float(venta.get("subtotal_libros", 0.0))
        
        if nuevo_metodo == "Añadir a caja de suscripción" and asignacion_id:
            res_asig = conn.table("asignaciones").select("extras, valor_extras, mes").eq("asignacion_id", int(asignacion_id)).execute()
            if not res_asig.data:
                return False, "No se pudo encontrar la asignación seleccionada."
            
            asig_actual = res_asig.data[0]
            extras_previos_raw = asig_actual.get('extras') or ""
            valor_previo = float(asig_actual.get('valor_extras') or 0.0)
            mes_caja = asig_actual.get("mes", "")
            
            libros_raw = venta.get("libros_vendidos", "")
            nuevos_extras_list = []
            if libros_raw:
                try:
                    libros = json.loads(libros_raw)
                    nuevos_extras_list = [f"{item.get('cantidad', 1)} x {item.get('titulo', 'N/A')}".upper() for item in libros]
                except Exception:
                    nuevos_extras_list = [f"1 x {libros_raw}".upper()]
            
            lista_extras_previos = []
            if extras_previos_raw:
                items = extras_previos_raw.replace('\\n', '|').split('|')
                for item in items:
                    item_limpio = item.strip()
                    if '.' in item_limpio:
                        item_limpio = item_limpio.split('.', 1)[-1].strip()
                    if item_limpio:
                        lista_extras_previos.append(item_limpio.upper())
            
            lista_completa = lista_extras_previos + nuevos_extras_list
            extras_final_enumerado = "\\n".join([f"{i+1}. {libro}" for i, libro in enumerate(lista_completa)])
            valor_final = valor_previo + subtotal_libros
            
            conn.table("asignaciones").update({
                "extras": extras_final_enumerado,
                "valor_extras": valor_final
            }).eq("asignacion_id", int(asignacion_id)).execute()
            
            metodo_envio_final = f"Agregado a Suscripción {mes_caja}"
            monto_final_nuevo = subtotal_libros
            conn.table("registro_ventas").update({
                "metodo_envio": metodo_envio_final,
                "valor_envio": 0.0,
                "monto_final": monto_final_nuevo,
                "abono": monto_final_nuevo if venta.get("estado_pago") == "PAGADO" else float(venta.get("abono", 0.0)),
                "tipo_cobro_envio": "retiro"
            }).eq("venta_id", int(venta_id)).execute()
            
        else:
            monto_final_nuevo = subtotal_libros + float(valor_envio)
            conn.table("registro_ventas").update({
                "metodo_envio": nuevo_metodo,
                "valor_envio": float(valor_envio),
                "monto_final": monto_final_nuevo,
                "abono": monto_final_nuevo if venta.get("estado_pago") == "PAGADO" else float(venta.get("abono", 0.0))
            }).eq("venta_id", int(venta_id)).execute()
            
        return True, "¡Método de envío, extras de suscripción y finanzas de venta actualizados con éxito!"
    except Exception as e:
        log_error("vista_caja", "cambiar_logistica_venta_existente", e, email_usuario)
        return False, str(e)

def asegurar_fuente_comprobante(nombre_fuente):
    if not os.path.exists("assets"):
        os.makedirs("assets")
        
    nombre_limpio = nombre_fuente.strip().replace(" ", "")
    ruta_font = os.path.join("assets", f"{nombre_limpio}.ttf")
    
    if os.path.exists(ruta_font):
        return ruta_font
    formatos_url = [
        f"https://github.com/google/fonts/raw/main/ofl/{nombre_limpio.lower()}/{nombre_limpio}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_limpio}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/static/{nombre_limpio}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_fuente.replace(' ', '')}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/static/{nombre_fuente.replace(' ', '')}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_limpio}-VariableFont_wght.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_limpio}.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/apache/{nombre_limpio.lower()}/{nombre_limpio}-Regular.ttf"
    ]
    
    for url in formatos_url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                with open(ruta_font, "wb") as f:
                    f.write(response.read())
            return ruta_font
        except Exception:
            continue
            
    return None

def find_any_system_ttf():
    import glob
    import sys
    
    for p in sys.path:
        mpl_path = os.path.join(p, "matplotlib", "mpl-data", "fonts", "ttf")
        if os.path.isdir(mpl_path):
            found = glob.glob(os.path.join(mpl_path, "*.ttf"))
            if found:
                for f in found:
                    if "dejavusans.ttf" in f.lower() or "dejavusans-regular.ttf" in f.lower():
                        return f
                return found[0]
                
    system_paths = [
        "/usr/share/fonts/**/*.ttf",
        "/usr/share/fonts/**/*.otf",
        "/usr/local/share/fonts/**/*.ttf",
        "/usr/share/fonts/truetype/**/*.ttf"
    ]
    for path in system_paths:
        found = glob.glob(path, recursive=True)
        if found:
            for f in found:
                f_lower = f.lower()
                if "bold" not in f_lower and "italic" not in f_lower and ("sans" in f_lower or "dejavu" in f_lower or "liberation" in f_lower):
                    return f
            return found[0]
            
    return None

def obtener_fuente_comprobante(nombre_fuente, tamanio, bold=False, italic=False):
    estilo = "Regular"
    if bold and italic:
        estilo = "BoldItalic"
    elif bold:
        estilo = "Bold"
    elif italic:
        estilo = "Italic"
        
    nombre_limpio = "Lato"  
    ruta_local = os.path.join("assets", f"{nombre_limpio}-{estilo}.ttf")
    
    if not os.path.exists(ruta_local):
        if not os.path.exists("assets"):
            os.makedirs("assets")
        
        urls = [
            f"https://github.com/google/fonts/raw/main/ofl/lato/{nombre_limpio}-{estilo}.ttf",
            f"https://raw.githubusercontent.com/google/fonts/main/ofl/lato/{nombre_limpio}-{estilo}.ttf",
            f"https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/{nombre_limpio}-{estilo}.ttf"
        ]
        
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    with open(ruta_local, "wb") as f:
                        f.write(response.read())
                break
            except Exception:
                continue

    if os.path.exists(ruta_local):
        try:
            return ImageFont.truetype(ruta_local, tamanio)
        except Exception:
            pass

    try:
        import matplotlib
        font_name_mpl = "DejaVuSans.ttf"
        if bold and italic:
            font_name_mpl = "DejaVuSans-BoldOblique.ttf"
        elif bold:
            font_name_mpl = "DejaVuSans-Bold.ttf"
        elif italic:
            font_name_mpl = "DejaVuSans-Oblique.ttf"
            
        mpl_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", font_name_mpl)
        if os.path.exists(mpl_ttf):
            return ImageFont.truetype(mpl_ttf, tamanio)
    except Exception:
        pass

    candidatas = [
        os.path.join("assets", "Lato-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "Arial.ttf"
    ]
    for ruta in candidatas:
        try:
            if os.path.exists(ruta):
                return ImageFont.truetype(ruta, tamanio)
        except Exception:
            continue

    try:
        ruta_sistema = find_any_system_ttf()
        if ruta_sistema and os.path.exists(ruta_sistema):
            return ImageFont.truetype(ruta_sistema, tamanio)
    except Exception:
        pass

    try:
        return ImageFont.load_default(size=tamanio)
    except:
        return ImageFont.load_default()

def extraer_pago_y_comentario(comentario_raw):
    comentario_raw = str(comentario_raw).strip().replace("\\\\\\\\n", " ").replace("\\\\\\\\r", " ").replace("\\\\n", " ").replace("\\\\r", " ")
    
    match = re.search(r"Pago:\\s\*([^.]+)\\.", comentario_raw, re.IGNORECASE)
    if match:
        pago = match.group(1).strip()
        resto = re.sub(r"Pago:\\s\*[^.]+\\.\\s\*", "", comentario_raw, flags=re.IGNORECASE).strip()
    else:
        pago = "N/A"
        for kw in ["Transferencia", "Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Débito", "Crédito"]:
            if kw.lower() in comentario_raw.lower():
                pago = kw
                break
        resto = comentario_raw
        
    resto_limpio = resto
    resto_limpio = re.sub(r"^(Transferencia|Efectivo|Tarjeta Débito|Tarjeta Crédito|Débito|Crédito)\\.?\\s\*\\|\\s\*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = re.sub(r"Fusionada:\\s\*Pago:\\s\*[^.]+\\.\\s\*\\|\\s\*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = re.sub(r"Fusionada:\\s\*\\|?\\s\*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = re.sub(r"Comentario:\\s\*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = resto_limpio.strip(" |")
    
    return pago, resto_limpio

def draw_total_row(label, val_float, y_pos, font_lbl, font_val, color_val, draw, box_x1, box_x2, color_lbl='#555555'):
    """
    Dibuja de forma alineada a la derecha los valores financieros dentro de la tarjeta del comprobante.
    """
    draw.text((box_x1 + 20, y_pos), label, fill=color_lbl, font=font_lbl)
    val_str = f"${val_float:,.0f}"
    try:
        x0, y0, x1, y1 = draw.textbbox((0, 0), val_str, font=font_val)
        w_val = x1 - x0
    except Exception:
        w_val = len(val_str) * 9
    draw.text((box_x2 - 20 - w_val, y_pos), val_str, fill=color_val, font=font_val)

def generar_comprobante(
    carrito, cliente_nombre, cliente_rut, cliente_email, cliente_telefono, cliente_direccion,
    fecha, metodo_envio, valor_envio, metodo_pago, subtotal, monto_final, abono, deuda, venta_id=None
):
    """
    Genera un comprobante premium sobre plantilla con márgenes alineados al cuaderno.
    Utiliza Lato para los textos de datos.
    Conserva la resolución física de 800x1200 para máxima nitidez sin requerir zoom en pantalla.
    """
    url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/comprobante.jpg"
    img = None
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as r:
            img = Image.open(io.BytesIO(r.read())).convert('RGB')
            try:
                resample_filter = Image.Resampling.LANCZOS
            except AttributeError:
                resample_filter = Image.ANTIALIAS
            img = img.resize((800, 1200), resample_filter)
    except Exception:
        pass
        
    if img is None:
        img = Image.new('RGB', (800, 1200), color='#FAF8FC')
        
    width, height = img.size
    draw = ImageDraw.Draw(img)
    
    font_title = obtener_fuente_comprobante("Lato", 32, bold=True)
    font_section = obtener_fuente_comprobante("Lato", 20, bold=True)
    font_body = obtener_fuente_comprobante("Lato", 15)
    font_body_bold = obtener_fuente_comprobante("Lato", 15, bold=True)
    font_price_accent = obtener_fuente_comprobante("Lato", 15, bold=True)
    font_footer = obtener_fuente_comprobante("Lato", 18, italic=True)
    
    x_margin = 130
    x_right = 740
    
    draw.text((x_margin, 60), "Alba Librería", fill='#7C0C3F', font=font_title)
    
    id_str = f"COMPROBANTE DE VENTA #{venta_id}" if venta_id else "COMPROBANTE DE VENTA (PREVIO)"
    draw.text((x_margin, 105), id_str, fill='#555555', font=font_body_bold)
    
    draw.line([x_margin, 135, x_right, 135], fill='#BA96A5', width=2)
    draw.text((x_margin, 150), "Datos del Cliente", fill='#7C0C3F', font=font_section)
    
    pago_limpio, comentario_limpio = extraer_pago_y_comentario(metodo_pago)
    
    draw.text((x_margin, 190), "Cliente:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_margin + 90, 190), str(cliente_nombre).upper(), fill='#333333', font=font_body)
    
    draw.text((x_margin, 220), "RUT:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_margin + 90, 220), str(cliente_rut or 'No registrado').upper(), fill='#333333', font=font_body)
    
    email_c = str(cliente_email or 'No registrado')
    if len(email_c) > 31:
        email_c = email_c[:28] + "..."
    draw.text((x_margin, 250), "Email:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_margin + 90, 250), email_c, fill='#333333', font=font_body)
    
    tel_c = str(cliente_telefono or 'No registrado')
    if len(tel_c) > 31:
        tel_c = tel_c[:28] + "..."
    draw.text((x_margin, 280), "Teléfono:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_margin + 90, 280), tel_c, fill='#333333', font=font_body)
    
    direccion_c = str(cliente_direccion or 'No especificado')
    if len(direccion_c) > 65:
        direccion_c = direccion_c[:62] + "..."
    draw.text((x_margin, 340), "Dirección:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_margin + 100, 340), direccion_c, fill='#333333', font=font_body)
    
    x_col2 = 510
    draw.text((x_col2, 190), "Fecha:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_col2 + 80, 190), str(fecha), fill='#333333', font=font_body)
    
    envio_c = str(metodo_envio)
    if len(envio_c) > 30:
        envio_c = envio_c[:27] + "..."
    draw.text((x_col2, 220), "Envío:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_col2 + 80, 220), envio_c, fill='#333333', font=font_body)
    
    draw.text((x_col2, 250), "Pago:", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_col2 + 80, 250), str(pago_limpio).upper(), fill='#333333', font=font_body)
    
    if comentario_limpio:
        nota_c = str(comentario_limpio).upper()
        if len(nota_c) > 20:
            nota_c = nota_c[:17] + "..."
        draw.text((x_col2, 280), "Nota:", fill='#7C0C3F', font=font_body_bold)
        draw.text((x_col2 + 80, 280), nota_c, fill='#333333', font=font_body)
    
    draw.line([x_margin, 380, x_right, 380], fill='#BA96A5', width=2)
    draw.text((x_margin, 395), "Detalle de la Compra", fill='#7C0C3F', font=font_section)
    
    y_table = 440
    draw.text((x_margin, y_table), "CANT", fill='#7C0C3F', font=font_body_bold)
    draw.text((x_margin + 60, y_table), "DESCRIPCIÓN / LIBRO", fill='#7C0C3F', font=font_body_bold)
    draw.text((560, y_table), "P. UNIT", fill='#7C0C3F', font=font_body_bold)
    draw.text((660, y_table), "SUBTOTAL", fill='#7C0C3F', font=font_body_bold)
    
    draw.line([x_margin, y_table + 25, x_right, y_table + 25], fill='#BA96A5', width=1)
    
    y_item = y_table + 35
    for item in carrito:
        qty = int(item.get('cantidad') or item.get('qty') or 1)
        qty_str = str(qty)
        draw.text((x_margin, y_item), qty_str, fill='#333333', font=font_body)
        
        titulo = str(item.get('titulo', 'N/A')).upper()
        if len(titulo) > 28:
            titulo = titulo[:25] + "..."
            
        draw.text((x_margin + 60, y_item), titulo, fill='#333333', font=font_body)
        
        # Robust retrieval of unit price and subtotal
        precio_val = float(item.get('precio_cobrado') or item.get('precio') or item.get('precio_catalogo') or 0.0)
        draw.text((560, y_item), f"${precio_val:,.0f}", fill='#333333', font=font_body)
        
        subtotal_val = float(item.get('subtotal') or (precio_val * qty) or 0.0)
        draw.text((660, y_item), f"${subtotal_val:,.0f}", fill='#333333', font=font_body)
        
        y_item += 35
        if y_item > 850:
            draw.text((x_margin + 60, y_item), "... (Otros libros omitidos)", fill='#777777', font=font_body)
            break
            
    draw.line([x_margin, 880, x_right, 880], fill='#BA96A5', width=2)
    
    box_x1, box_y1, box_x2, box_y2 = 410, 900, 740, 1110
    draw.rounded_rectangle([box_x1 + 6, box_y1 + 6, box_x2 + 6, box_y2 + 6], radius=15, fill=None, outline='#F4CCD4', width=2)
    draw.rounded_rectangle([box_x1, box_y1, box_x2, box_y2], radius=15, fill=None, outline='#7C0C3F', width=2)
    
    draw_total_row("Subtotal Libros:", float(subtotal), 915, font_body_bold, font_body, '#333333', draw, box_x1, box_x2)
    draw_total_row("Costo Envío:", float(valor_envio), 945, font_body_bold, font_body, '#333333', draw, box_x1, box_x2)
    draw_total_row("Monto Final:", float(monto_final), 980, font_body_bold, font_price_accent, '#7C0C3F', draw, box_x1, box_x2, color_lbl='#7C0C3F')
    draw_total_row("Abono Registrado:", float(abono), 1015, font_body_bold, font_price_accent, '#2E7D32', draw, box_x1, box_x2)
    draw_total_row("Deuda Pendiente:", float(deuda), 1050, font_body_bold, font_price_accent, '#C62828', draw, box_x1, box_x2)
    
    draw.text((435, 1140), "¡Gracias por tu preferencia! - Alba Librería", fill='#7C0C3F', font=font_footer, anchor="mm")
    
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    return buf.getvalue()