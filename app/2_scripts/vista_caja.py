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
            res = conn.table("libros")\
                .select("libro_id, titulo, autor, precio, costo, stock, editorial, encuadernacion, precio_original")\
                .order("libro_id")\
                .range(start, end).execute()
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
            res = conn.table("clientes")\
                .select("cliente_id, nombre, email, telefono, status, rut, direccion")\
                .order("cliente_id")\
                .range(start, end).execute()
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
            res = conn.table("cupones")\
                .select("*")\
                .order("cupon_id")\
                .range(start, end).execute()
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
            res_ventas = conn.table("registro_ventas")\
                .select("*, cliente:clientes(cliente_id, nombre, rut, email, telefono, direccion)")\
                .order("venta_id", desc=True)\
                .range(start, end).execute()
                
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

def gestionar_libro(titulo, autor, precio_catalogo, stock_a_sumar, libro_id_existente=None, encuadernacion="", editorial="", apto_cajita=True):
    conn = get_db_connection()
    datos = {
        "titulo": limpiar_texto_para_busqueda(titulo), 
        "autor": limpiar_texto_para_busqueda(autor), 
        "precio": float(precio_catalogo),
        "encuadernacion": limpiar_texto_para_busqueda(encuadernacion),
        "editorial": limpiar_texto_para_busqueda(editorial),
        "apto_cajita": apto_cajita
    }
    
    if libro_id_existente:
        datos_actualizar = {k: v for k, v in datos.items() if v}
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
            df_cli_ventas['fecha_dt'] = pd.to_datetime(df_cli_ventas['fecha_venta'], errors='coerce')
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
    
    libros_nuevos_list = []
    costo_total_venta = 0.0
    for item in carrito:
        libros_nuevos_list.append({
            "libro_id": item['libro_id'], "titulo": item['titulo'], "autor": item['autor'],
            "cantidad": item['cantidad'], "precio": item['precio_cobrado']
        })
        costo_unitario = item.get('costo', 0.0)
        if pd.isna(costo_unitario) or costo_unitario is None: costo_unitario = 0.0
        costo_total_venta += float(costo_unitario) * int(item['cantidad'])
        
    subtotal_libros = sum([item['subtotal'] for item in carrito])
    try:
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
            
        for item in carrito:
            l_id = item['libro_id']
            if item['es_nuevo']: 
                l_id = gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], item['cantidad'], None, item.get('encuadernacion', ''), item.get('editorial', ''), item.get('apto_cajita', True) )
            else:
                gestionar_libro(item['titulo'], item['autor'], item['precio_catalogo'], 0, l_id)
                nuevo_stock = item['stock_actual'] - item['cantidad']
                if item['stock_actual'] <= 0 or nuevo_stock < 0:
                    nuevo_stock = 0
                    
                conn.table("libros").update({"stock": nuevo_stock}).eq("libro_id", l_id).execute()
            
            if cliente_id and l_id:
                res_hist = conn.table("librero_historico").select("registro_id").eq("cliente_id", cliente_id).eq("libro_id", l_id).execute()
                if not res_hist.data:
                    datos_historico = {"cliente_id": cliente_id, "libro_id": l_id, "autor_historico": limpiar_texto_para_busqueda(item['autor']), "origen": "VENTA CAJA"}
                    conn.table("librero_historico").insert(datos_historico).execute()
                    
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
        url = f"https://raw.githubusercontent.com/google/fonts/main/ofl/lato/{nombre_limpio}-{estilo}.ttf"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                with open(ruta_local, "wb") as f:
                    f.write(response.read())
        except Exception:
            pass
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
        "Arial.ttf"
    ]
    for ruta in candidatas:
        try:
            if os.path.exists(ruta):
                return ImageFont.truetype(ruta, tamanio)
        except Exception:
            continue
            
    try:
        return ImageFont.load_default(size=tamanio)
    except:
        return ImageFont.load_default()

def extraer_pago_y_comentario(comentario_raw):
    comentario_raw = str(comentario_raw).strip().replace("\\\\n", " ").replace("\\\\r", " ").replace("\\n", " ").replace("\\r", " ")
    
    match = re.search(r"Pago:\s*([^.]+)\.", comentario_raw, re.IGNORECASE)
    if match:
        pago = match.group(1).strip()
        resto = re.sub(r"Pago:\s*[^.]+\.\s*", "", comentario_raw, flags=re.IGNORECASE).strip()
    else:
        pago = "N/A"
        for kw in ["Transferencia", "Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Débito", "Crédito"]:
            if kw.lower() in comentario_raw.lower():
                pago = kw
                break
        resto = comentario_raw
        
    resto_limpio = resto
    resto_limpio = re.sub(r"^(Transferencia|Efectivo|Tarjeta Débito|Tarjeta Crédito|Débito|Crédito)\.?\s*\|\s*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = re.sub(r"Fusionada:\s*Pago:\s*[^.]+\.\s*\|\s*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = re.sub(r"Fusionada:\s*\|?\s*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = re.sub(r"Comentario:\s*", "", resto_limpio, flags=re.IGNORECASE)
    resto_limpio = resto_limpio.strip(" |")
    
    return pago, resto_limpio

# ==========================================
# --- VISTA PRINCIPAL (CAJA) ---
# ==========================================
def mostrar_caja():
    if 'caja_limit_view' not in st.session_state:
        st.session_state.caja_limit_view = 30
        
    if 'clientes_limit_view' not in st.session_state:
        st.session_state.clientes_limit_view = 300
        
    if 'carrito_caja' not in st.session_state: st.session_state.carrito_caja = []
    if 'historial_original' not in st.session_state: st.session_state.historial_original = pd.DataFrame()
    
    if 'aplicar_cupon_sistema_obj' not in st.session_state:
        st.session_state.aplicar_cupon_sistema_obj = None
        
    st.title("🛒 Caja y Ventas Rápidas")
    
    df_libros = cargar_libros_caja()
    df_clientes = cargar_clientes_caja()
    df_cupones = cargar_cupones_caja()
    estados_posibles = ["NO COMENZADO", "PENDIENTE STOCK", "PENDIENTE ARMADO PAQUETE", "PAQUETE LISTO", "PENDIENTE PAGO", "FINALIZADO"]
    
    df_ventas_global_raw = cargar_historial_completo()
    df_ventas_global = df_ventas_global_raw.copy() if not df_ventas_global_raw.empty else pd.DataFrame()
    df_deudores_global = pd.DataFrame()
    
    if not df_ventas_global.empty:
        df_ventas_global['fecha_limpia'] = unificar_formatos_fecha(df_ventas_global['fecha_venta'])
        df_deudores_global = df_ventas_global[df_ventas_global['deuda'] > 0].copy()
        if not df_deudores_global.empty:
            df_deudores_global = df_deudores_global.dropna(subset=['fecha_limpia'])
            hoy_global = datetime.now().date()
            df_deudores_global['dias_mora'] = df_deudores_global['fecha_limpia'].apply(lambda x: (hoy_global - x.date()).days if pd.notna(x) else 0)
            deudas_criticas = df_deudores_global[df_deudores_global['dias_mora'] > 14]
            if not deudas_criticas.empty:
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 🚨 ALERTAS DE COBRANZA")
                st.sidebar.error(f"Tienes **{len(deudas_criticas)}** deudas con más de 2 semanas.")
                for _, row in deudas_criticas.iterrows():
                    st.sidebar.warning(f"👤 **{row['cliente_nombre']}**\n💰 Deuda: ${row['deuda']:,.0f}\n⏳ {row['dias_mora']} días")
                st.error(f"🚨 **¡ATENCIÓN!** Tienes {len(deudas_criticas)} cuenta(s) crítica(s) con más de 14 días de mora.")
    
    tab_venta, tab_historial, tab_cobranza, tab_alertas, tab_comprobantes, tab_anular, tab_cupones = st.tabs([
        "🛒 Nueva Venta", "📜 Historial", "💸 Cobranza", "🚨 Alertas (>5 días)", "🧾 Comprobantes", "🚫 Anular", "🎟️ Cupones y Fidelización"
    ])
    
    with tab_venta:
        # --- GUÍA PASO A PASO PARA COBRAR CON DESCUENTO ---
        with st.expander("💡 ¿Cómo aplicar un descuento a esta venta? (Guía Rápida)", expanded=False):
            st.info("""
            📋 **Sigue estos simples pasos para vender con descuento:**
            
            1️⃣ **Selecciona al Cliente:** 
               - Si el cliente califica para el **10% de Fidelidad**, aparecerá un banner verde brillante.
               - Marca la casilla *'Aplicar Cupón de Fidelidad del 10% automáticamente'* si deseas usarlo.
            
            2️⃣ **Busca el Libro:**
               - Elige el libro que vas a vender.
            
            3️⃣ **Aplica el Descuento (Despliega la pestaña '🎟️ Descuentos, Fidelidad y Cupones del Sistema'):**
               * **Opción A (Manual / Fidelidad):** Selecciona esta opción si marcaste el cupón automático del cliente, o si quieres inventar un código en el momento (ej: `ALBA10`, escribes `10` en porcentaje).
               * **Opción B (Cupón del Sistema):** Selecciona esta opción si el cliente te muestra un código de base de datos (ej: `ALBA15`). Escríbelo, haz clic en **🔍 Validar Cupón** y el sistema verificará si está vigente y no ha expirado.
            
            4️⃣ **Revisa el 'Precio a Cobrar':**
               - El sistema recalculará el precio final con el descuento aplicado.
            
            5️⃣ **¡Añade al Carrito!**
               - Haz clic en **➕ AÑADIR AL CARRITO** para guardar el libro con su precio rebajado.
            """)

        st.markdown("### 1️⃣ Datos del Cliente")
        modo_cliente = st.radio("Cliente:", ["👤 Buscar Existente", "➕ Nuevo"], horizontal=True, label_visibility="collapsed")
        
        c_id, c_nombre, c_correo, c_telefono, c_rut, c_direccion = None, "", "", "", "", ""
        
        if modo_cliente == "👤 Buscar Existente":
            if not df_clientes.empty:
                limite_cli = st.session_state.clientes_limit_view
                clientes_filtrados = df_clientes.head(limite_cli)
                
                sel_cliente = st.selectbox(
                    f"Buscar cliente (mostrando {len(clientes_filtrados)} de {len(df_clientes)}):", 
                    options=clientes_filtrados['nombre'].tolist(),
                    index=None,
                    placeholder="👤 Busca o selecciona un cliente...",
                    key="sel_cliente_caja"
                )
                
                if len(df_clientes) > limite_cli:
                    if st.button(f"🔍 Cargar más clientes en el buscador (+200)", use_container_width=True):
                        st.session_state.clientes_limit_view += 200
                        st.rerun()
                if sel_cliente:
                    datos_c = df_clientes[df_clientes['nombre'] == sel_cliente].iloc[0]
                    c_id = int(datos_c['cliente_id'])
                    c_nombre = datos_c['nombre']
                    c_correo = datos_c.get('email', '')
                    c_telefono = datos_c.get('telefono', '')
                    c_rut = datos_c.get('rut', '')
                    c_direccion = datos_c.get('direccion', '')
                    
                    # Fidelización Automática 10%
                    monto_min_cfg = st.session_state.get('monto_minimo_cupon_cfg', 100000.0)
                    plazo_dias_cfg = st.session_state.get('plazo_dias_cupon_cfg', 365)
                    
                    clasifica_cupon, compras_acum, ultimo_canje = check_elegibilidad_cliente_cupon(
                        c_id, df_clientes, df_ventas_global, monto_min_cfg, plazo_dias_cfg
                    )
                    
                    if clasifica_cupon:
                        st.markdown(
                            f"""
                            <div style="background-color:#d4edda; border:3px solid #28a745; padding:15px; border-radius:8px; margin-bottom:15px; margin-top:10px;">
                                <h4 style="color:#155724; margin:0; font-size:16px;">🏆 ¡CLIENTA CALIFICA PARA CUPÓN DE FIDELIDAD DEL 10%!</h4>
                                <p style="color:#155724; margin:5px 0 0 0; font-size:13px; font-weight:bold;">
                                    La clienta {c_nombre} califica por compras acumuladas de ${compras_acum:,.0f} en el plazo de {plazo_dias_cfg} días (Último canje: {ultimo_canje}).
                                </p>
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                        aplicar_cupon_auto = st.checkbox("🎟️ Aplicar Cupón de Fidelidad del 10% automáticamente a esta venta", value=False, key="chk_aplicar_cupon_fidelidad_auto")
                        if aplicar_cupon_auto:
                            st.session_state['cupon_codigo_input'] = "FIDELIDAD10"
                            st.session_state['cupon_porcentaje_input'] = 10
                    
                    with st.expander(f"✏️ Ver/Editar datos (Status: {datos_c.get('status', 'REGULAR')})", expanded=False):
                        col_cd1, col_cd2 = st.columns(2)
                        c_nombre = col_cd1.text_input("Nombre:", value=c_nombre)
                        c_rut = col_cd2.text_input("RUT:", value=c_rut)
                        c_correo = col_cd1.text_input("Correo:", value=c_correo)
                        c_telefono = col_cd2.text_input("Teléfono:", value=c_telefono)
                        c_direccion = st.text_input("Dirección de Despacho:", value=c_direccion)
            else: 
                st.warning("No hay clientes registrados.")
        else:
            with st.container(border=True):
                col_cn1, col_cn2 = st.columns(2)
                c_nombre = col_cn1.text_input("Nombre del nuevo cliente:")
                c_rut = col_cn2.text_input("RUT (Opcional):")
                c_correo = col_cn1.text_input("Correo (Opcional):")
                c_telefono = col_cn2.text_input("Teléfono (Opcional):")
                c_direccion = st.text_input("Dirección de Despacho (Opcional):")
                
        st.markdown("---")
        st.markdown("### 2️⃣ Añadir Libros al Carrito")
        with st.container(border=True):
            modo_libro = st.radio("Libro:", ["📚 Buscar Existente", "➕ Rápido (No en catálogo)"], horizontal=True, label_visibility="collapsed")
            autores_db, editoriales_db = cargar_listas_desplegables_caja()
    
            l_id, l_titulo, l_autor, l_editorial, l_precio_catalogo, l_stock_actual, l_costo, es_nuevo, l_encuadernacion, l_apto_cajita = None, "", "", "", 0.0, 0, 0.0, False, "", True
            l_precio_original = 0.0
            
            if modo_libro == "📚 Buscar Existente":
                if not df_libros.empty:
                    sel_libro = st.selectbox(
                        "Buscar libro:", 
                        options=df_libros['titulo'].tolist(),
                        index=None,
                        placeholder="📚 Busca o selecciona un libro...",
                        key="sel_libro_caja"
                    )
                    if sel_libro:
                        datos_l = df_libros[df_libros['titulo'] == sel_libro].iloc[0]
                        l_id = int(datos_l['libro_id'])
                        l_stock_actual = int(datos_l['stock'])
                        l_titulo = datos_l['titulo']
                        l_precio_catalogo = float(datos_l['precio'])
                        l_costo = float(datos_l['costo'])
                        l_autor = datos_l.get('autor', '')
                        l_editorial = datos_l.get('editorial', '')
                        l_encuadernacion = datos_l.get('encuadernacion', '')
                        
                        l_precio_original = float(datos_l.get('precio_original', l_precio_catalogo))
                        if pd.isna(l_precio_original):
                            l_precio_original = l_precio_catalogo
                            
                        with st.expander("✏️ Actualizar Catálogo (Opcional)", expanded=False):
                            l_autor = st.text_input("Autor:", value=l_autor, key="autor_edit_caja_2")
                            l_precio_catalogo = st.number_input("Precio Oficial ($):", value=l_precio_catalogo, step=100.0, key="precio_edit_caja_2")
                else:
                    st.warning("El inventario está vacío.")
            else: 
                es_nuevo = True
                l_titulo = st.text_input("Título del libro:")
                col_rap1, col_rap2 = st.columns(2)
                
                opciones_autor = ["➕ Crear Nuevo Autor"] + autores_db
                sel_autor = col_rap1.selectbox("Autor:", options=opciones_autor, placeholder="Busca o selecciona...", index=None, key="sel_autor_caja")
                if st.session_state.sel_autor_caja == "➕ Crear Nuevo Autor":
                    l_autor = col_rap1.text_input("Nombre del nuevo autor:", key="nuevo_autor_caja")
                elif st.session_state.sel_autor_caja:
                    l_autor = st.session_state.sel_autor_caja
                else:
                    l_autor = ""
                    
                opciones_editorial = ["➕ Crear Nueva Editorial"] + editoriales_db
                sel_edit = col_rap2.selectbox("Editorial:", options=opciones_editorial, placeholder="Busca o selecciona...", index=None, key="sel_edit_caja")
                if st.session_state.sel_edit_caja == "➕ Crear Nueva Editorial":
                    l_editorial = col_rap2.text_input("Nombre de la nueva editorial:", key="nueva_editorial_caja")
                elif st.session_state.sel_edit_caja:
                    l_editorial = st.session_state.sel_edit_caja
                else:
                    l_editorial = ""
                l_encuadernacion = st.selectbox("Encuadernación:", ["", "TAPA BLANDA", "TAPA DURA", "BOLSILLO"])
                es_tapa_dura = (l_encuadernacion == "TAPA DURA")
                l_apto_cajita = st.checkbox("🎁 Apto para enviar en Cajitas de Suscripción", value=not es_tapa_dura)
                
                col_num1, col_num2 = st.columns(2)
                l_precio_catalogo = col_num1.number_input("Precio Oficial ($):", min_value=0.0, step=100.0)
                l_costo = col_num2.number_input("Costo del libro nuevo ($):", min_value=0.0, step=100.0)
                l_stock_actual = 999  
                l_precio_original = l_precio_catalogo

            # --- NUEVO MOTOR AVANZADO DE CUPONES ---
            precio_inicial_caja = l_precio_catalogo
            with st.expander("🎟️ Descuentos, Fidelidad y Cupones del Sistema", expanded=False):
                modo_desc = st.radio("Método de descuento:", ["Manual Libre / Fidelidad", "Validar Cupón del Sistema (DB)"], horizontal=True)
                
                if modo_desc == "Manual Libre / Fidelidad":
                    col_cup1, col_cup2, col_cup3 = st.columns(3)
                    cupon_codigo = col_cup1.text_input("Código o Etiqueta:", placeholder="Ej: ALBA10, ALBA15...", key="cupon_codigo_input")
                    cupon_porcentaje = col_cup2.number_input("Porcentaje Descuento (%):", min_value=0, max_value=100, step=5, value=0, key="cupon_porcentaje_input")
                    base_descuento = col_cup3.selectbox("Aplicar sobre:", ["Precio de Catálogo ($)", "Precio Original ($)"], key="base_descuento_input")
                    
                    precio_base_elegido = l_precio_original if base_descuento == "Precio Original ($)" else l_precio_catalogo
                    
                    if cupon_porcentaje > 0:
                        precio_sugerido_con_descuento = precio_base_elegido * (1 - (cupon_porcentaje / 100))
                        st.success(f"💡 Descuento del {cupon_porcentaje}% sugerido. Precio final: **${precio_sugerido_con_descuento:,.0f}**")
                        precio_inicial_caja = precio_sugerido_con_descuento
                        st.session_state.aplicar_cupon_sistema_obj = None 
                else:
                    col_validar1, col_validar2 = st.columns([2, 1])
                    codigo_db_input = col_validar1.text_input("Ingresa el código del cupón:", placeholder="Escribe el código aquí...", key="codigo_db_field").upper().strip()
                    
                    if col_validar2.button("🔍 Validar Cupón", use_container_width=True):
                        if not codigo_db_input:
                            st.warning("Escribe un código.")
                        else:
                            ok_cupon, res_cupon = validar_cupon_sistema(codigo_db_input, c_id, df_cupones)
                            if ok_cupon:
                                st.session_state.aplicar_cupon_sistema_obj = res_cupon
                                st.success(f"✅ ¡Cupón '{codigo_db_input}' VÁLIDO! Otorga un {res_cupon['porcentaje_descuento']}% de descuento.")
                            else:
                                st.session_state.aplicar_cupon_sistema_obj = None
                                st.error(f"❌ {res_cupon}")
                                
                    if st.session_state.aplicar_cupon_sistema_obj:
                        cupon_db = st.session_state.aplicar_cupon_sistema_obj
                        pct = int(cupon_db['porcentaje_descuento'])
                        base_desc_db = st.selectbox("Aplicar descuento del cupón sobre:", ["Precio de Catálogo ($)", "Precio Original ($)"])
                        precio_base_elegido = l_precio_original if base_desc_db == "Precio Original ($)" else l_precio_catalogo
                        precio_inicial_caja = precio_base_elegido * (1 - (pct / 100))
                        st.info(f"🏆 Cupón Activo: **{cupon_db['codigo']}** ({pct}% Descuento). Precio sugerido: **${precio_inicial_caja:,.0f}**")
            
            st.markdown("👇 **Precio Especial y Cantidad para esta venta**")
            permitir_sin_stock = st.checkbox("🔓 Permitir sobreventa (omitir límite de stock disponible)", value=False)
            
            col_c1, col_c2 = st.columns(2)
            precio_a_cobrar = col_c1.number_input("Precio a Cobrar ($):", value=float(precio_inicial_caja), step=500.0)
            limite_maximo = None if (l_stock_actual <= 0 or permitir_sin_stock) else max(1, l_stock_actual)
            amount_val = col_c2.number_input("Cantidad:", min_value=1, max_value=limite_maximo, step=1)
            
            if not es_nuevo:
                if l_stock_actual <= 0:
                    st.warning("⚠️ Atención: Estás vendiendo un libro sin stock físico (Stock: 0).")
                elif amount_val > l_stock_actual:
                    st.warning(f"⚠️ Atención: Stock insuficiente. Dispones de {l_stock_actual} unidad(es) e intentas vender {amount_val}.")
            
            if st.button("➕ AÑADIR AL CARRITO", use_container_width=True):
                if not l_titulo: st.error("Debes seleccionar un libro.")
                else:
                    titulo_final = limpiar_texto_para_busqueda(l_titulo)
                    autor_final = limpiar_texto_para_busqueda(l_autor)
                    editorial_final = limpiar_texto_para_busqueda(l_editorial)
                    encuadernacion_final = limpiar_texto_para_busqueda(l_encuadernacion)
                    
                    st.session_state.carrito_caja.append({
                        'libro_id': l_id, 
                        'titulo': titulo_final,          
                        'autor': autor_final,            
                        'editorial': editorial_final,      
                        'encuadernacion': encuadernacion_final, 
                        'precio_catalogo': l_precio_catalogo, 
                        'precio_cobrado': precio_a_cobrar, 
                        'cantidad': amount_val, 
                        'subtotal': precio_a_cobrar * amount_val,
                        'stock_actual': l_stock_actual, 
                        'costo': l_costo, 
                        'es_nuevo': es_nuevo,
                        'apto_cajita': l_apto_cajita
                    })
                    
                    if 'sel_libro_caja' in st.session_state:
                        del st.session_state.sel_libro_caja
                        
                    st.success(f"{l_titulo} añadido.")
                    st.rerun()
                    
        subtotal_carrito = 0
        if len(st.session_state.carrito_caja) > 0:
            st.markdown("#### 🛒 Tu Carrito Actual")
            alertas_sobreventa = []
            for item in st.session_state.carrito_caja:
                if not item.get('es_nuevo', False):
                    stock_f = int(item.get('stock_actual', 0))
                    cant_v = int(item.get('cantidad', 0))
                    if stock_f <= 0:
                        alertas_sobreventa.append(f"• **{item['titulo']}**: Sin stock en catálogo. Se venderán {cant_v} unidades.")
                    elif cant_v > stock_f:
                        alertas_sobreventa.append(f"• **{item['titulo']}**: Stock insuficiente. Solicitas {cant_v} de {stock_f} disponibles.")
            
            if alertas_sobreventa:
                with st.expander("⚠️ ADVERTENCIA: DETALLES DE SOBREVENTA", expanded=True):
                    for alerta in alertas_sobreventa:
                        st.info(alerta)
                        
            df_carrito = pd.DataFrame(st.session_state.carrito_caja)
            df_carrito.insert(0, 'Quitar', False)
            
            df_editado_carrito = st.data_editor(
                df_carrito[['Quitar', 'cantidad', 'titulo', 'precio_cobrado', 'subtotal']], 
                hide_index=True, 
                use_container_width=True,
                column_config={"Quitar": st.column_config.CheckboxColumn("Quitar ❌", default=False)}
            )
            
            subtotal_carrito = df_carrito['subtotal'].sum()
            
            col_cart1, col_cart2 = st.columns(2)
            if col_cart1.button("🗑️ Quitar Seleccionados"):
                indices_a_quitar = df_editado_carrito[df_editado_carrito['Quitar'] == True].index.tolist()
                if indices_a_quitar:
                    for i in sorted(indices_a_quitar, reverse=True):
                        st.session_state.carrito_caja.pop(i)
                    st.rerun()
                else:
                    st.warning("Marca la casilla 'Quitar ❌' en los libros que desees eliminar.")
                    
            if col_cart2.button("🗑️ Vaciar Todo el Carrito"):
                st.session_state.carrito_caja = []
                st.rerun()
                
        st.markdown("---")
        st.markdown("### 3️⃣ Envío, Pago y Confirmación")
        fecha_venta_manual = st.date_input("Fecha de la Venta:", value=datetime.now())
        
        col_e1, col_e2 = st.columns(2)
        opciones_envio = ["Retiro en tienda", "Paket", "Bluexpress", "Añadir a compra anterior", "Añadir a caja de suscripción"]
        modo_envio = col_e1.selectbox("Modo de Envío:", opciones_envio)
        
        valor_envio = 0.0
        metodo_envio_final = modo_envio
        bloquear_venta = False 
        asignacion_id_target = None
        
        mostrar_ticket_cobro = modo_envio not in ["Retiro en tienda", "Añadir a compra anterior", "Añadir a caja de suscripción", "Paket"]
        es_por_pagar = False
        
        if mostrar_ticket_cobro:
            es_por_pagar = col_e1.checkbox("📦 Envío por Pagar (Se cobra en destino)", value=False)
        
        if modo_envio == "Añadir a caja de suscripción":
            if c_id is not None:
                conn = get_db_connection()
                res_cajas = conn.table("asignaciones").select("asignacion_id, mes, estado_envio").eq("cliente_id", c_id).execute()
                cajas_abiertas = [c for c in res_cajas.data if c.get('estado_envio', '') not in ["ENVIADO", "ENTREGADO/RETIRADO", "RETIRADO"]]
                if cajas_abiertas:
                    opciones_cajas = [f"Suscripción {c['mes']} - {c.get('estado_envio','')} (ID: {c['asignacion_id']})" for c in cajas_abiertas]
                    caja_sel = col_e2.selectbox("Caja de Suscripción abierta:", opciones_cajas)
                    asignacion_id_target = int(caja_sel.split("(ID: ")[-1].strip(")"))
                    metodo_envio_final = f"Agregado a {caja_sel.split(' -')[0]}"
                    st.info("Los libros se agregarán como Extras a la caja seleccionada (Envío $0).")
                else:
                    col_e2.warning("El cliente no tiene cajas de suscripción abiertas para añadir.")
                    bloquear_venta = True
            else:
                col_e2.error("Selecciona un cliente existente primero.")
                bloquear_venta = True
                
        elif modo_envio == "Añadir a compra anterior":
            if c_id is not None:
                ventas_abiertas = [v for v in df_ventas_global.to_dict('records') if v['cliente_id'] == c_id and v.get('estado', '') not in ["PAQUETE LISTO", "FINALIZADO"]]
                if ventas_abiertas:
                    opciones_ventas = [f"Venta #{v['venta_id']} ({v['fecha_venta']}) - {v.get('estado', 'Sin Estado')}" for v in ventas_abiertas]
                    venta_asociada_str = col_e2.selectbox("Compra asociada (No Finalizadas):", opciones_ventas)
                    v_id_asociada = venta_asociada_str.split("#")[1].split(" ")[0]
                    metodo_envio_final = f"Añadido a Venta #{v_id_asociada}"
                    st.info(f"El envío será gratuito. Esta compra se anexará a la Venta #{v_id_asociada}.")
                    
                    st.markdown(
                        f"""
                        <div style="background-color:#fff3cd; border:3px solid #ffc107; padding:15px; border-radius:8px; margin-bottom:15px;">
                            <h4 style="color:#856404; margin:0; font-size:18px;">⚠️ ¡ALERTA: ESTA VENTA SE FUSIONARÁ!</h4>
                            <p style="color:#856404; margin:5px 0 0 0; font-size:14px; font-weight:bold;">
                                Los libros de este carrito se integrarán directamente dentro de la <b>Venta #{v_id_asociada}</b>. 
                                No se creará una venta nueva, sino que se sumará el stock, el abono y el subtotal en la orden original del historial.
                            </p>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                else:
                    col_e2.warning("No hay compras anteriores abiertas para anexar.")
                    bloquear_venta = True
            else:
                col_e2.error("Selecciona un cliente primero.")
                bloquear_venta = True
                
        elif modo_envio != "Retiro en tienda":
            valor_envio = col_e2.number_input("Costo de Envío ($):", min_value=0.0, step=500.0)
            
        metodo_pago = st.selectbox("Método de Pago:", ["Transferencia", "Efectivo", "Tarjeta Débito", "Tarjeta Crédito"])
        comentario_venta = st.text_area("Comentario (Opcional):", placeholder="Ej: Entregar por conserjería...")
        
        st.markdown("---")
        st.markdown("#### ⚙️ Estado y Abono")
        col_abono1, col_abono2, col_abono3, col_abono4 = st.columns(4)
        
        estado_venta_sel = col_abono1.selectbox("Estado de la Venta:", estados_posibles, index=0)
        estado_pago_sel = col_abono2.selectbox("Estado del Pago:", ["PENDIENTE", "PAGADO"], index=0)
        fecha_pago_sel = col_abono3.date_input("Fecha de Pago:", value=None)
        
        if es_por_pagar:
            tipo_cobro_envio = "envio por pagar"
            monto_final = subtotal_carrito
        else:
            if modo_envio in ["Retiro en tienda", "Añadir a compra anterior", "Añadir a caja de suscripción"]:
                tipo_cobro_envio = "retiro"
                monto_final = subtotal_carrito
            else:
                tipo_cobro_envio = "envio pagado"
                monto_final = subtotal_carrito + valor_envio
        
        abono_default = 0.0
        mensaje_exito = ""
        if estado_venta_sel == "FINALIZADO" or estado_pago_sel == "PAGADO":
            abono_default = monto_final
            estado_pago_sel = "PAGADO"
            mensaje_exito = "💡 Venta FINALIZADA/PAGADA: El abono se iguala al monto total."
            
        val_abono = float(abono_default) if (abono_default is not None and not pd.isna(abono_default)) else 0.0
        abono_inicial = col_abono4.number_input("Abono Inicial ($):", min_value=0.0, step=1000.0, value=val_abono)
        
        if mensaje_exito:
            st.success(mensaje_exito)
            
        st.markdown(f"<div style='background-color:#E6F3E6; border:2px solid #4CAF50; padding:15px; border-radius:10px; text-align:center;'><p style='color:#2E7D32; margin:0;'>Subtotal Libros: ${subtotal_carrito:,.0f} | Envío: ${valor_envio:,.0f}</p><h2 style='color:#2E7D32; margin:0;'>MONTO FINAL: ${monto_final:,.0f}</h2><p style='color:#1B5E20; margin:0; font-weight:bold;'>Abono Registrado: ${abono_inicial:,.0f} | Deuda: ${(monto_final - abono_inicial):,.0f}</p></div>", unsafe_allow_html=True)
        st.write("")
        
        desactivar_boton = not c_nombre or len(st.session_state.carrito_caja) == 0 or bloquear_venta
        
        st.markdown("---")
        st.markdown("#### 🧾 Generar Comprobante Resumen (Opcional)")
        generar_comp = st.checkbox("🧾 Generar Vista Previa del Comprobante para descarga", value=False, key="chk_generar_comp_nueva")
        if generar_comp:
            if not c_nombre:
                st.info("💡 Completa el nombre del cliente para previsualizar el comprobante.")
            elif len(st.session_state.carrito_caja) == 0:
                st.info("💡 Agrega libros al carrito para previsualizar el comprobante.")
            else:
                with st.spinner("Generando comprobante..."):
                    img_bytes_preview = generar_comprobante(
                        carrito=st.session_state.carrito_caja,
                        cliente_nombre=c_nombre,
                        cliente_rut=c_rut,
                        cliente_email=c_correo,
                        cliente_telefono=c_telefono,
                        cliente_direccion=c_direccion,
                        fecha=fecha_venta_manual.strftime("%Y-%m-%d"),
                        metodo_envio=metodo_envio_final,
                        valor_envio=valor_envio,
                        metodo_pago=metodo_pago,
                        subtotal=subtotal_carrito,
                        monto_final=monto_final,
                        abono=abono_inicial,
                        deuda=monto_final - abono_inicial
                    )
                    st.image(io.BytesIO(img_bytes_preview), caption="Vista Previa de Comprobante", width=550)
                    st.download_button(
                        label="📥 Descargar Comprobante (JPG)",
                        data=img_bytes_preview,
                        file_name=f"comprobante_{limpiar_texto_para_busqueda(c_nombre).replace(' ', '_')}.jpg",
                        mime="image/jpeg",
                        use_container_width=True,
                        key="btn_dl_comprobante_nueva"
                    )
        
        if st.button("✅ CONFIRMAR VENTA TOTAL", type="primary", use_container_width=True, disabled=desactivar_boton):
            with st.spinner("Procesando Venta..."):
                final_cliente_id, error_cliente = gestionar_cliente(c_nombre, c_correo, c_telefono, c_rut, c_direccion, c_id)
                
                if error_cliente:
                    st.error(error_cliente)
                else:
                    v_id_fusion = None
                    if modo_envio == "Añadir a compra anterior" and 'v_id_asociada' in locals():
                        v_id_fusion = int(v_id_asociada)
                        
                    exito, err = procesar_venta_carrito(
                        st.session_state.carrito_caja, final_cliente_id, valor_envio, 
                        metodo_envio_final, metodo_pago, comentario_venta, fecha_venta_manual,
                        estado_venta_sel, estado_pago_sel, fecha_pago_sel, abono_inicial, 
                        tipo_cobro_envio, asignacion_id_target, v_id_fusion 
                    )
                    if exito: 
                        # 1. Registrar canje automático si usaba fidelidad
                        if st.session_state.get('chk_aplicar_cupon_fidelidad_auto', False) and final_cliente_id:
                            try:
                                conn = get_db_connection()
                                old_status = str(datos_c.get('status', 'CLIENTE REGULAR'))
                                if " | CANJE_CUPON:" in old_status:
                                    base_status = old_status.split(" | CANJE_CUPON:")[0].strip()
                                elif "CANJE_CUPON:" in old_status:
                                    base_status = old_status.split("CANJE_CUPON:")[0].strip().strip("| ")
                                else:
                                    base_status = old_status if old_status else "CLIENTE REGULAR"
                                    
                                hoy_str_canje = datetime.now().strftime("%Y-%m-%d")
                                nuevo_status = f"{base_status} | CANJE_CUPON: {hoy_str_canje}"
                                conn.table("clientes").update({"status": nuevo_status}).eq("cliente_id", int(final_cliente_id)).execute()
                            except Exception as ex_canje_auto:
                                log_error("vista_caja", "canje_cupon_auto_checkout", ex_canje_auto, "system")
                        
                        # 2. Registrar incremento de usos si usaba cupón del sistema
                        if st.session_state.aplicar_cupon_sistema_obj is not None:
                            try:
                                conn = get_db_connection()
                                c_obj = st.session_state.aplicar_cupon_sistema_obj
                                nuevos_usos = int(c_obj.get('usos_actuales', 0)) + 1
                                conn.table("cupones").update({"usos_actuales": nuevos_usos}).eq("cupon_id", int(c_obj['cupon_id'])).execute()
                            except Exception as ex_incremento:
                                log_error("vista_caja", "incrementar_uso_cupon_caja", ex_incremento, "system")
                        
                        if 'sel_cliente_caja' in st.session_state:
                            del st.session_state.sel_cliente_caja
                        if 'sel_libro_caja' in st.session_state:
                            del st.session_state.sel_libro_caja
                        st.session_state.clientes_limit_view = 200
                        st.session_state.aplicar_cupon_sistema_obj = None
                        
                        st.success("🎉 ¡Venta registrada con éxito!")
                        st.balloons()
                        time.sleep(2)
                        st.session_state.carrito_caja = []
                        st.rerun()
                    else: 
                        st.error(f"Error: {err}")
                    
    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        st.info("""
        💡 **¿Cómo se calculan las finanzas en este panel?**
        * **Ventas Totales (Monto Final):** Suma del precio cobrado por cada libro más el **Costo de Envío** (si aplica).
        * **Costos Totales (Costo Venta):** Suma del costo de adquisición registrado en catálogo para cada libro vendido.
        * **Utilidad Estimada:** Se obtiene restando `(Ventas Totales - Costo de Envío) - Costos Totales` (es decir, la utilidad real que te dejan los libros sin contar el despacho).
        """)
        
        df_ventas = df_ventas_global.copy()
        
        if df_ventas.empty: 
            st.info("Aún no hay ventas registradas.")
        else:
            fechas_invalidas = df_ventas['fecha_limpia'].isna()
            if fechas_invalidas.any():
                with st.expander(f"⚠️ Atención: {fechas_invalidas.sum()} ventas tienen fechas ilegibles"):
                    st.dataframe(df_ventas[fechas_invalidas][['venta_id', 'fecha_venta', 'cliente_nombre']], hide_index=True)
            with st.expander("🔍 Filtros del Historial"):
                df_fechas_validas = df_ventas.dropna(subset=['fecha_limpia'])
                options_mes = ["Ver Todo"]
                mapa_inverso_mes = {}
                if not df_fechas_validas.empty:
                    df_fechas_validas['mes_ano_str'] = df_fechas_validas['fecha_limpia'].dt.strftime('%Y-%m')
                    meses_unicos = sorted(df_fechas_validas['mes_ano_str'].unique(), reverse=True)
                    
                    month_map_es = {'01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril', '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto', '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'}
                    
                    for mes_str in meses_unicos:
                        ano, mes_num = mes_str.split('-')
                        nombre_amigable = f"{month_map_es.get(mes_num, '')} {ano}"
                        options_mes.append(nombre_amigable)
                        mapa_inverso_mes[nombre_amigable] = mes_str
                
                hoy = datetime.now()
                nombre_mes_actual = f"{month_map_es.get(hoy.strftime('%m'), '')} {hoy.year}"
                
                default_index = 0
                if nombre_mes_actual in options_mes:
                    default_index = options_mes.index(nombre_mes_actual)
                
                col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
                mes_seleccionado = col_f1.selectbox("Filtrar por Mes:", options=options_mes, index=default_index)
                cliente_filtro = col_f2.selectbox("Filtrar Cliente:", ["Todos"] + sorted(df_ventas['cliente_nombre'].unique().tolist()))
                estado_filtro = col_f3.selectbox("Filtrar Estado:", ["Todos"] + sorted(df_ventas['estado'].unique().tolist()))
                estado_pago_filtro = col_f4.selectbox("Filtrar Pago:", ["Todos", "PAGADO", "PENDIENTE"])
                
                if 'tipo_cobro_envio' in df_ventas.columns:
                    tipo_cobro_options = ["Todos"] + sorted(df_ventas['tipo_cobro_envio'].dropna().unique().tolist())
                else:
                    tipo_cobro_options = ["Todos", "retiro", "envio por pagar", "envio pagado"]
                tipo_cobro_filtro = col_f5.selectbox("Filtrar Cobro Envío:", options=tipo_cobro_options)
                
                st.markdown("---")
                solo_costo_cero = st.checkbox("⚠️ Mostrar rápido: Ventas sin costo asignado ($0)", value=False)
                
                st.markdown("---")
                columnas_hist_todas = ['venta_id', 'fecha_venta', 'fecha_pago', 'cliente_nombre', 'cliente_rut', 'cliente_email', 'cliente_telefono', 'libros_vendidos', 'monto_final', 'valor_envio', 'tipo_cobro_envio', 'abono', 'deuda', 'utilidad', 'costo_venta', 'estado', 'estado_pago', 'metodo_envio', 'comentario']
                columnas_por_defecto = ['venta_id', 'fecha_venta', 'cliente_nombre', 'libros_vendidos', 'monto_final', 'valor_envio', 'tipo_cobro_envio', 'abono', 'deuda', 'estado', 'estado_pago', 'fecha_pago']
                columnas_a_mostrar = st.multiselect("👀 Mostrar / Ocultar Columnas en Tabla", columnas_hist_todas, default=columnas_por_defecto)
                
            df_filtrado_general = df_ventas.copy()
            
            if mes_seleccionado != "Ver Todo":
                mes_str_a_buscar = mapa_inverso_mes.get(mes_seleccionado)
                if mes_str_a_buscar:
                    df_filtrado_fechas_validas = df_filtrado_general.dropna(subset=['fecha_limpia'])
                    df_filtrado_general = df_filtrado_fechas_validas[df_filtrado_fechas_validas['fecha_limpia'].dt.strftime('%Y-%m') == mes_str_a_buscar]
                
            if cliente_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['cliente_nombre'] == cliente_filtro]
            if estado_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['estado'] == estado_filtro]
            if estado_pago_filtro != "Todos": df_filtrado_general = df_filtrado_general[df_filtrado_general['estado_pago'] == estado_pago_filtro]
                
            st.markdown("#### 📊 Resumen del período filtrado")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("💰 Ventas Totales", f"${df_filtrado_general['monto_final'].sum():,.0f}")
            m2.metric("💳 Total Abonado", f"${df_filtrado_general['abono'].sum():,.0f}")
            m3.metric("📦 Costos Totales", f"${df_filtrado_general['costo_venta'].sum():,.0f}")
            m4.metric("📈 Utilidad Estimada", f"${df_filtrado_general['utilidad'].sum():,.0f}")
            st.markdown("---")
            
            df_mostrar = df_filtrado_general.copy()
            if solo_costo_cero: df_mostrar = df_mostrar[df_mostrar['costo_venta'] == 0]
            df_mostrar = df_mostrar[columnas_a_mostrar].copy()
            
            st.session_state.historial_original = df_mostrar.copy()
            
            config_cols_hist = {
                "monto_final": st.column_config.NumberColumn("Monto Final", format="$%.0f", disabled=True), 
                "valor_envio": st.column_config.NumberColumn("Valor Envío 🚚", format="$%.0f", step=500.0), 
                "tipo_cobro_envio": st.column_config.SelectboxColumn("Cobro Envío 💳", options=["retiro", "envio por pagar", "envio pagado"], required=True),
                "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                "deuda": st.column_config.NumberColumn("Deuda", format="$%.0f", disabled=True),
                "utilidad": st.column_config.NumberColumn("Utilidad", format="$%.0f", disabled=True),
                "costo_venta": st.column_config.NumberColumn("Costo Venta", format="$%.0f"),
                "estado": st.column_config.SelectboxColumn("Estado Venta", options=estados_posibles),
                "estado_pago": st.column_config.SelectboxColumn("Estado Pago", options=["PENDIENTE", "PAGADO"]),
                "fecha_pago": st.column_config.DateColumn("Fecha Pago", format="DD/MM/YYYY"),
                "metodo_envio": st.column_config.SelectboxColumn(
                    "Método de Envío", 
                    options=["Retiro en tienda", "Paket", "Bluexpress", "Envio por pagar", "Añadir a compra anterior", "Añadir a caja de suscripción"], 
                    required=True
                ),
                "cliente_nombre": st.column_config.TextColumn("Nombre Cliente"),
                "cliente_rut": st.column_config.TextColumn("RUT Cliente"),
                "cliente_email": st.column_config.TextColumn("Email Cliente"),
                "cliente_telefono": st.column_config.TextColumn("Teléfono Cliente")
            }
            
            limite_actual = st.session_state.caja_limit_view
            total_ventas_filtradas = len(df_mostrar)
            df_paginado = df_mostrar.head(limite_actual)
            
            if 'costo_venta' in df_paginado.columns:
                df_estilizado = df_paginado.style.apply(lambda s: ['background-color: #ffebee; color: #c62828; font-weight: bold;' if v == 0 else '' for v in s], subset=['costo_venta'])
            else: 
                df_estilizado = df_paginado
            disabled_cols = ['venta_id', 'fecha_venta', 'libros_vendidos', 'deuda', 'utilidad']
            disabled_cols_active = [c for c in disabled_cols if c in columnas_a_mostrar]
            
            st.caption(f"Mostrando las **{len(df_paginado)}** ventas más recientes de un total de **{total_ventas_filtradas}** encontradas.")
            
            df_editado = st.data_editor(df_estilizado, disabled=disabled_cols_active, use_container_width=True, hide_index=True, column_config=config_cols_hist)
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Historial", type="primary"):
                    num = actualizar_historial_caja(df_editado)
                    st.success(f"¡Se actualizaron {num} registros!")
                    time.sleep(1.5); st.rerun()
                    
            st.markdown("---")
            with st.expander("🚚 Re-rutar o Vincular Venta Existente a Suscripción/Courier", expanded=False):
                st.markdown("#### 🔄 Vincular o Cambiar Método de Envío de una Venta")
                
                df_target_ventas = df_filtrado_general.copy()
                if solo_costo_cero:
                    df_target_ventas = df_target_ventas[df_target_ventas['costo_venta'] == 0]
                
                lista_ventas_opciones = [""] + [
                    f"Venta #{v['venta_id']} - {v.get('cliente_nombre', 'Sin Nombre')} (Monto: ${v.get('monto_final', 0.0):,.0f})" 
                    for v in df_target_ventas.to_dict('records')
                ]
                venta_a_modificar = st.selectbox("1. Selecciona la venta a modificar:", options=lista_ventas_opciones, index=0)
                
                if venta_a_modificar:
                    v_id_tmp = int(venta_a_modificar.split("Venta #")[1].split(" - ")[0])
                    row_venta = df_target_ventas[df_target_ventas['venta_id'] == v_id_tmp].iloc[0]
                    
                    cliente_id_tmp = None
                    for col in ['cliente_id', 'cliente_cliente_id', 'cliente_id_clean']:
                        if col in row_venta and pd.notna(row_venta[col]) and str(row_venta[col]).strip() != '':
                            try:
                                cliente_id_tmp = int(float(row_venta[col]))
                                break
                            except ValueError:
                                continue
                    
                    st.write(f"👤 **Cliente:** {row_venta['cliente_nombre']}")
                    st.write(f"📦 **Método de Envío Actual:** `{row_venta.get('metodo_envio', 'No especificado')}`")
                    st.write(f"📚 **Libros vendidos:** `{row_venta['libros_vendidos']}`")
                    st.write(f"💰 **Subtotal Libros:** ${row_venta['monto_final'] - row_venta.get('valor_envio', 0.0):,.0f} | **Envío Actual:** ${row_venta.get('valor_envio', 0.0):,.0f}")
                    
                    st.markdown("---")
                    col_mod1, col_mod2 = st.columns(2)
                    
                    nuevo_metodo_sel = col_mod1.selectbox(
                        "2. Selecciona el nuevo Método de Envío:",
                        options=["Retiro en tienda", "Paket", "Bluexpress", "Envio por pagar", "Añadir a caja de suscripción"],
                        index=None,
                        placeholder="Elige un método..."
                    )
                    
                    bloquear_guardado = False
                    asig_id_target = None
                    valor_envio_nuevo = 0.0
                    
                    if nuevo_metodo_sel == "Añadir a caja de suscripción":
                        if cliente_id_tmp is not None:
                            conn = get_db_connection()
                            res_cajas = conn.table("asignaciones").select("asignacion_id, mes, estado_envio").eq("cliente_id", int(cliente_id_tmp)).execute()
                            cajas_abiertas = [c for c in res_cajas.data if c.get('estado_envio', '') not in ["ENVIADO", "RETIRADO", "ENTREGADO/RETIRADO", "ENTREGADO", "FINALIZADO"]]
                            
                            if cajas_abiertas:
                                opciones_cajas = [f"Suscripción {c['mes']} - {c.get('estado_envio','')} (ID: {c['asignacion_id']})" for c in cajas_abiertas]
                                caja_sel = col_mod2.selectbox("3. Selecciona la Caja de Suscripción abierta:", opciones_cajas)
                                if caja_sel:
                                    asig_id_target = int(caja_sel.split("(ID: ")[-1].strip(")"))
                                    st.success(f"✅ ¡Perfecto! Los libros se sumarán automáticamente como Extras a la cajita del mes.")
                            else:
                                col_mod2.warning("⚠️ El cliente no registra cajitas de suscripción abiertas actualmente para añadir.")
                                bloquear_guardado = True
                        else:
                            col_mod2.error("❌ Esta venta no registra un ID de cliente válido asociado.")
                            bloquear_guardado = True
                            
                    elif nuevo_metodo_sel and nuevo_metodo_sel not in ["Retiro en tienda", "Añadir a caja de suscripción"]:
                        valor_envio_nuevo = col_mod2.number_input("3. Establecer nuevo Costo de Envío ($):", min_value=0.0, step=500.0, value=float(row_venta.get('valor_envio', 0.0)))
                        
                    if nuevo_metodo_sel:
                        if st.button("💾 Guardar y Aplicar Cambios de Envío", type="primary", use_container_width=True, disabled=bloquear_guardado):
                            with st.spinner("Procesando re-rutado y actualizando base de datos..."):
                                ok, msg = cambiar_logistica_venta_existente(v_id_tmp, nuevo_metodo_sel, valor_envio_nuevo, asig_id_target)
                                if ok:
                                    st.success(msg)
                                    st.balloons()
                                    time.sleep(1.5)
                                    st.rerun()
                                else:
                                    st.error(msg)
                                    
            if total_ventas_filtradas > limite_actual:
                st.write("")
                col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
                with col_pag2:
                    if st.button(f"🔄 Cargar más ventas (+100) — Quedan {total_ventas_filtradas - limite_actual} por ver", use_container_width=True, key="btn_load_more_caja"):
                        st.session_state.caja_limit_view += 100
                        st.rerun()
                    
    with tab_cobranza:
        st.markdown("### 💸 Cuentas por Cobrar")
        if not df_ventas_global.empty:
            df_deudores = df_deudores_global.copy()
            if df_deudores.empty: st.success("🎉 ¡Felicidades! No hay deudas pendientes.")
            else:
                with st.expander("🔍 Filtros de Cobranza", expanded=True):
                    col_c1, col_c2 = st.columns(2)
                    fecha_min_c = df_deudores['fecha_limpia'].min().date()
                    fecha_max_c = df_deudores['fecha_limpia'].max().date()
                    rango_fechas_c = col_c1.date_input("Filtrar por Fecha de Venta:", value=(fecha_min_c, fecha_max_c), min_value=fecha_min_c, max_value=fecha_max_c, key="rango_cob")
                    clientes_cob = ["Todos"] + sorted(df_deudores['cliente_nombre'].unique().tolist())
                    cliente_filtro_c = col_c2.selectbox("Filtrar por Cliente:", clientes_cob, key="cliente_cob")
                if len(rango_fechas_c) == 2:
                    df_deudores = df_deudores[(df_deudores['fecha_limpia'].dt.date >= rango_fechas_c[0]) & (df_deudores['fecha_limpia'].dt.date <= rango_fechas_c[1])]
                if cliente_filtro_c != "Todos":
                    df_deudores = df_deudores[df_deudores['cliente_nombre'] == cliente_filtro_c]
                if df_deudores.empty: st.info("No hay deudas que coincidan con los filtros actuales.")
                else:
                    st.markdown(f"#### 💰 Total por Cobrar (Filtrado): **${df_deudores['deuda'].sum():,.0f}**")
                    df_deudores['Nivel Mora'] = df_deudores['dias_mora'].apply(lambda x: "🔴 Crítico (>14 días)" if x > 14 else ("🟡 Medio (7-14 días)" if x > 7 else "🟢 Normal"))
                    columnas_mostrar_cob = ['fecha_venta', 'cliente_nombre', 'monto_final', 'abono', 'deuda', 'Nivel Mora', 'estado', 'estado_pago']
                    st.dataframe(df_deudores[columnas_mostrar_cob], hide_index=True, use_container_width=True, 
                        column_config={
                            "monto_final": st.column_config.NumberColumn("Monto Venta", format="$%.0f"),
                            "abono": st.column_config.NumberColumn("Abono", format="$%.0f"),
                            "deuda": st.column_config.NumberColumn("Deuda Pendiente", format="$%.0f"),
                            "cliente_nombre": st.column_config.TextColumn("Nombre Cliente")
                        }
                    )
        else: st.info("No hay deudas registradas.")
        
    with tab_alertas:
        st.markdown("### 🚨 Control de Envíos en Olvido (>5 días)")
        df_alertas_temporal = df_ventas_global.copy()
        df_alertas_temporal['fecha_dt'] = pd.to_datetime(df_alertas_temporal['fecha_venta'], errors='coerce')
        hoy_datetime = datetime.now()
        df_alertas_temporal['dias_antiguedad'] = (hoy_datetime - df_alertas_temporal['fecha_dt']).dt.days
        
        df_olvidados = df_alertas_temporal[
            (df_alertas_temporal['dias_antiguedad'] > 5) & 
            (~df_alertas_temporal['estado'].isin(['FINALIZADO']))
        ].copy()
        
        if not df_olvidados.empty:
            col_c_b1, col_c_b2 = st.columns([1, 2.5])
            with col_c_b1:
                st.image("https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster.png", width=180)
            with col_c_b2:
                st.markdown(
                    """
                    <div style="background-color:#ffdde1; border:3px solid #ff4b4b; padding:20px; border-radius:10px; display:flex; flex-direction:column; justify-content:center; height:100%;">
                        <h2 style="color:#ff4b4b; margin:0; font-size:26px;">🐹💤 ¡BODEGA EN CRISIS!</h2>
                        <p style="color:#d00000; font-size:18px; font-weight:bold; margin:8px 0 0 0;">
                            ¡Ivonne, deja de dormir y ponte a trabajar!
                        </p>
                        <p style="color:#333; margin:4px 0 0 0; font-size:14px;">
                            Hay pedidos con más de 5 días de retraso esperando que los prepares. ¡A envolver paquetes! 📦📦
                        </p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
        else:
            col_c_b1, col_c_b2 = st.columns([1, 2.5])
            with col_c_b1:
                st.image("https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamsterfeliz.jpg", width=180)
            with col_c_b2:
                st.markdown(
                    """
                    <div style="background-color:#e8f5e9; border:3px solid #4caf50; padding:20px; border-radius:10px; display:flex; flex-direction:column; justify-content:center; height:100%;">
                        <h2 style="color:#2e7d32; margin:0; font-size:26px;">🐹✨ ¡BODEGA DESPEJADA!</h2>
                        <p style="color:#1b5e20; font-size:18px; font-weight:bold; margin:8px 0 0 0;">
                            Ivonne, tienes todo en orden, puedes dormir pero que no se te olvide trabajar tampoco.
                        </p>
                        <p style="color:#333; margin:4px 0 0 0; font-size:14px;">
                            No tienes ningún paquete demorado en bodega. ¡Excelente trabajo de organización! 🌟📦
                        </p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
        st.markdown("---")
        
        if df_ventas_global.empty:
            st.success("🎉 ¡Felicidades! Todo el catálogo está al día y armado.")
        else:
            df_alertas_temporal = df_ventas_global.copy()
            df_alertas_temporal['fecha_dt'] = pd.to_datetime(df_alertas_temporal['fecha_venta'], errors='coerce')
            hoy_datetime = datetime.now()
            df_alertas_temporal['dias_antiguedad'] = (hoy_datetime - df_alertas_temporal['fecha_dt']).dt.days
            
            df_olvidados = df_alertas_temporal[
                (df_alertas_temporal['dias_antiguedad'] > 5) & 
                (~df_alertas_temporal['estado'].isin(['PAQUETE LISTO', 'FINALIZADO']))
            ].copy()
            
            if df_olvidados.empty:
                st.success("🟢 ¡Increíble! No tienes ningún paquete pendiente de armado con más de 5 días de antigüedad. Todo está empaquetado o entregado.")
            else:
                st.error(f"⚠️ Alerta: Tienes **{len(df_olvidados)}** órdenes durmiendo en bodega que necesitan ser armadas de inmediato.")
                
                import urllib.parse
                conn = get_db_connection()
                
                for _, row in df_olvidados.iterrows():
                    v_id = row.get('venta_id')
                    c_nombre = row.get('cliente_nombre', 'Cliente')
                    c_telefono = str(row.get('cliente_telefono', '')).strip()
                    c_email = str(row.get('cliente_email', '')).strip()
                    libros_str = row.get('libros_vendidos', '')
                    dias = row.get('dias_antiguedad', 5)
                    monto = float(row.get('monto_final', 0))
                    estado_v = row.get('estado', 'PENDIENTE')
                    
                    with st.container(border=True):
                        col_card_info, col_card_btn = st.columns([2, 1])
                        
                        with col_card_info:
                            st.markdown(f"#### 📦 Venta #{v_id} - {c_nombre}")
                            st.markdown(f"💀 **¡Leva {dias} días sin prepararse!** *(Creado el {row.get('fecha_venta')})*")
                            st.markdown(f"📚 **Libros requeridos:** `{libros_str}`")
                            st.markdown(f"⚙️ **Estado de la Venta actual:** `{estado_v}`")
                            
                        with col_card_btn:
                            st.write("")
                            if st.button(f"✅ ¡YA LO ARMÉ! #{v_id}", type="primary", use_container_width=True, key=f"btn_armado_{v_id}"):
                                try:
                                    conn.table("registro_ventas").update({"estado": "FINALIZADO"}).eq("venta_id", v_id).execute()
                                    st.success(f"¡Orden #{v_id} empaquetada!")
                                    st.balloons()
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as err_bd:
                                    st.error(f"Error de base de datos: {err_bd}")
                            
                            dueña_tel = st.secrets.get("catalogo_publico", {}).get("whatsapp_numero", "56963531241")
                            dueña_tel_limpio = "".join(char for char in str(dueña_tel) if char.isdigit())
                                
                            msg_recordatorio = (
                                f"🚨 RECORDATORIO INTERNO ALBA LIBRERÍA 🚨\n\n"
                                f"Hola Ivonne, recuerda que tienes pendiente armar la orden #{v_id} para {c_nombre}.\n"
                                f"⏳ ¡Lleva {dias} días de retraso!\n"
                                f"📚 Libros a empacar: {libros_str}\n\n"
                                f"Por favor, prepáralo y luego márcalo como '¡YA LO ARMÉ!' en la app."
                            )
                            msg_encoded = urllib.parse.quote(msg_recordatorio)
                            wa_url = f"https://api.whatsapp.com/send?phone={dueña_tel_limpio}&text={msg_encoded}"
                            
                            st.markdown(
                                f'''
                                <div style="margin-top: 8px;">
                                    <a href="{wa_url}" target="_blank" style="text-decoration:none;">
                                        <button style="width:100%; background-color:#ff4b4b; color:white; border:none; padding:8px; border-radius:5px; cursor:pointer; font-weight:bold; font-size:12px;">
                                            🔥 Auto-Recordar por WhatsApp
                                        </button>
                                    </a>
                                </div>
                                ''',
                                unsafe_allow_html=True
                            )
    with tab_anular:
        st.markdown("### 🚫 Anular Venta y Restaurar Stock")
        df_ventas_anular = df_ventas_global.copy()
        if not df_ventas_anular.empty:
            df_ventas_anular['etiqueta_anular'] = df_ventas_anular.apply(lambda row: f"ID: {row.get('venta_id','')} | {row.get('fecha_venta','')} | {row.get('libros_vendidos','')} | ${row.get('monto_final',0):,.0f}", axis=1)
            venta_sel = st.selectbox("Selecciona la venta:", [""] + df_ventas_anular.sort_values('venta_id', ascending=False)['etiqueta_anular'].tolist())
            if venta_sel:
                venta_a_anular = df_ventas_anular[df_ventas_anular['etiqueta_anular'] == venta_sel].iloc[0]
                if st.button("🟥 CONFIRMAR ANULACIÓN", type="primary"):
                    exito, error = anular_venta(int(venta_a_anular['venta_id']), venta_a_anular['libros_vendidos'])
                    if exito: 
                        st.success("¡Venta anulada con éxito!")
                        time.sleep(1.5); st.rerun()
                    else: st.error(f"Error al anular: {error}")
                    
    with tab_comprobantes:
        st.markdown("### 🧾 Comprobantes de Ventas Abiertas")
        st.info("Genera y descarga el comprobante para ventas que aún no han sido finalizadas o que fueron recientemente actualizadas.")
        
        if df_ventas_global.empty:
            st.warning("No hay ventas registradas en el sistema.")
        else:
            df_abiertas = df_ventas_global[df_ventas_global['estado'] != 'FINALIZADO'].copy()
            
            if df_abiertas.empty:
                st.success("🎉 ¡Excelente! No hay ventas abiertas pendientes en este momento.")
            else:
                df_abiertas['etiqueta_abierta'] = df_abiertas.apply(
                    lambda row: f"Venta #{row.get('venta_id','')} | {row.get('cliente_nombre','')} | ${row.get('monto_final',0):,.0f} | Estado: {row.get('estado','')}", axis=1
                )
                
                venta_abierta_sel = st.selectbox(
                    "Selecciona una venta abierta:",
                    options=[""] + df_abiertas['etiqueta_abierta'].tolist(),
                    index=None,
                    placeholder="Elige una venta abierta...",
                    key="sel_venta_abierta_comprobante"
                )
                
                if venta_abierta_sel:
                    row_v = df_abiertas[df_abiertas['etiqueta_abierta'] == venta_abierta_sel].iloc[0]
                    v_id_sel = int(row_v['venta_id'])
                    
                    libros_vendidos_raw = row_v.get('libros_vendidos', '[]')
                    carrito_reconstruido = []
                    
                    if isinstance(libros_vendidos_raw, str) and libros_vendidos_raw.strip().startswith('['):
                        try:
                            items_json = json.loads(libros_vendidos_raw)
                            for item in items_json:
                                q = int(item.get('cantidad', 1))
                                p = float(item.get('precio', 0.0))
                                carrito_reconstruido.append({
                                    'cantidad': q,
                                    'titulo': item.get('titulo', 'N/A'),
                                    'precio_cobrado': p,
                                    'subtotal': q * p
                                })
                        except Exception:
                            carrito_reconstruido = [{'cantidad': 1, 'titulo': libros_vendidos_raw, 'precio_cobrado': float(row_v.get('monto_final', 0.0)), 'subtotal': float(row_v.get('monto_final', 0.0))}]
                    else:
                        items_str = str(libros_vendidos_raw).split(" | ")
                        for item_str in items_str:
                            partes = item_str.split(" x ", 1)
                            if len(partes) == 2:
                                try:
                                    q = int(partes[0].strip())
                                    titulo_l = partes[1].strip()
                                except ValueError:
                                    q = 1
                                    titulo_l = item_str
                            else:
                                q = 1
                                titulo_l = item_str
                                
                            sub_libros = float(row_v.get('subtotal_libros', 0.0))
                            carrito_reconstruido.append({
                                'cantidad': q,
                                'titulo': titulo_l,
                                'precio_cobrado': sub_libros / max(1, q) if len(items_str) == 1 else 0.0,
                                'subtotal': sub_libros if len(items_str) == 1 else 0.0
                            })
                    
                    c_nom_v = row_v.get('cliente_nombre', 'Cliente')
                    c_rut_v = row_v.get('cliente_rut', '')
                    c_em_v = row_v.get('cliente_email', '')
                    c_tel_v = row_v.get('cliente_telefono', '')
                    c_dir_v = row_v.get('cliente_direccion', '')
                    
                    col_info1, col_info2 = st.columns(2)
                    with col_info1:
                        st.markdown(f"👤 **Cliente:** {c_nom_v}")
                        st.markdown(f"🆔 **RUT:** {c_rut_v or 'No registrado'}")
                        st.markdown(f"📧 **Email:** {c_em_v or 'No registrado'}")
                        st.markdown(f"📞 **Teléfono:** {c_tel_v or 'No registrado'}")
                        st.markdown(f"📍 **Dirección:** {c_dir_v or 'No registrada'}")
                    with col_info2:
                        st.markdown(f"📅 **Fecha Venta:** {row_v.get('fecha_venta')}")
                        st.markdown(f"🚚 **Método Envío:** {row_v.get('metodo_envio')}")
                        st.markdown(f"💳 **Método Pago:** {row_v.get('comentario', '')}")
                        st.markdown(f"⚙️ **Estado Venta:** {row_v.get('estado')}")
                        
                    st.markdown("#### 🎨 Comprobante Generado")
                    with st.spinner("Creando ticket en base a plantilla..."):
                        img_bytes_abierta = generar_comprobante(
                            carrito=carrito_reconstruido,
                            cliente_nombre=c_nom_v,
                            cliente_rut=c_rut_v,
                            cliente_email=c_em_v,
                            cliente_telefono=c_tel_v,
                            cliente_direccion=c_dir_v,
                            fecha=str(row_v.get('fecha_venta'))[:10],
                            metodo_envio=row_v.get('metodo_envio'),
                            valor_envio=float(row_v.get('valor_envio', 0.0)),
                            metodo_pago=row_v.get('comentario', 'N/A'),
                            subtotal=float(row_v.get('subtotal_libros', 0.0)),
                            monto_final=float(row_v.get('monto_final', 0.0)),
                            abono=float(row_v.get('abono', 0.0)),
                            deuda=float(row_v.get('deuda', 0.0)),
                            venta_id=v_id_sel
                        )
                        
                        st.image(io.BytesIO(img_bytes_abierta), caption=f"Comprobante Venta #{v_id_sel}", width=550)
                        st.download_button(
                            label=f"📥 Descargar Comprobante Venta #{v_id_sel} (JPG)",
                            data=img_bytes_abierta,
                            file_name=f"comprobante_venta_{v_id_sel}_{limpiar_texto_para_busqueda(c_nom_v).replace(' ', '_')}.jpg",
                            mime="image/jpeg",
                            use_container_width=True,
                            key=f"dl_abierta_{v_id_sel}"
                        )
                        
    # =========================================================================
    # 🎟️ TAB 7: PANEL DE CUPONES Y FIDELIZACIÓN (CON GESTIÓN CRUD COMPLETA)
    # =========================================================================
    with tab_cupones:
        st.markdown("### 🎟️ Panel de Cupones y Fidelización Premium")
        
        # --- GUÍA DE USO INTERACTIVA ---
        with st.expander("📖 Manual de Uso Integrado: ¿Cómo funcionan mis cupones?", expanded=True):
            st.markdown("#### 1️⃣ Módulo de Cupones del Sistema (Cupones creados en Base de Datos)")
            st.info("""
            💡 **¿Cómo funciona el Límite de Usos?**
            * **Límite = 1 (De un solo uso absoluto):** Es un cupón de "primer canje". El primer cliente que lo utilice en caja lo consume y lo quema. El sistema registrará `Usado: 1/1` e invalidará el código inmediatamente para todo el mundo. *Ideal para: Compensaciones, regalos de cumpleaños o sorteos rápidos.*
            * **Límite = 1000 (Masivo público):** El cupón puede ser canjeado un total de 1000 veces en la tienda en total. Cualquier cliente puede usarlo, e incluso una misma clienta puede usarlo en varias ventas distintas, siempre y cuando no se supere el límite global de 1000 usos.
            * **Límite = N + Cliente Exclusivo:** Si creas un cupón con límite de usos (ej: 1 o 5) y seleccionas un cliente específico, **solo ese cliente podrá validarlo**. Nadie más tendrá acceso a ese descuento.
            """)
            
            st.markdown("#### 2️⃣ Módulo de Fidelización (Compras Acumuladas)")
            st.info("""
            ⏳ **¿Desde qué fecha se calculan los 365 días de acumulación?**
            * **La Ventana Flotante:** El plazo (ej: 365 días) se calcula **dinámicamente hacia atrás desde el día de hoy**. Es decir, si hoy es 25 de Agosto de 2026, el sistema sumará las compras realizadas desde el 25 de Agosto de 2025 hasta hoy. Las compras que tengan más de un año de antigüedad van "expirando" de la suma acumulada de forma automática todos los días.
            * **El Reinicio por Canje (Frontera de Tiempo):** En el momento en que confirmas el canje de una clienta, el sistema guarda la fecha actual en su perfil de Supabase (`CANJE_CUPON: 2026-08-25`). A partir de ese segundo, el motor de base de datos **ignora por completo todas las ventas anteriores a esa fecha**, reiniciando su acumulado a $0 para que pueda empezar a juntar compras para su próximo cupón desde mañana.
            """)
        
        if df_cupones.empty:
            st.warning("⚠️ No se han encontrado cupones registrados. Si es tu primera vez ejecutando este módulo, asegúrate de haber creado la tabla 'cupones' en Supabase.")
            with st.expander("📋 Ver SQL de Creación para Supabase", expanded=False):
                st.code("""
CREATE TABLE IF NOT EXISTS cupones (
    cupon_id SERIAL PRIMARY KEY,
    codigo TEXT UNIQUE NOT NULL,
    porcentaje_descuento INTEGER NOT NULL CHECK (porcentaje_descuento >= 0 AND porcentaje_descuento <= 100),
    fecha_inicio DATE,
    fecha_fin DATE,
    cliente_id_exclusivo INTEGER REFERENCES clientes(cliente_id) ON DELETE SET NULL,
    limite_usos INTEGER DEFAULT 1,
    usos_actuales INTEGER DEFAULT 0,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);
                """, language="sql")
                
        st.markdown("#### ➕ Crear Nuevo Cupón del Sistema")
        with st.container(border=True):
            col_nc1, col_nc2, col_nc3 = st.columns(3)
            nuevo_codigo = col_nc1.text_input("Código del Cupón (Ej: ALBA15):").upper().strip()
            nuevo_porcentaje = col_nc2.number_input("Porcentaje Descuento (%):", min_value=1, max_value=100, value=15, step=5)
            nuevo_limite_usos = col_nc3.number_input("Límite de usos totales (1 para un solo canje):", min_value=1, value=1, step=1)
            
            col_nc4, col_nc5, col_nc6 = st.columns(3)
            nuevo_fecha_inicio = col_nc4.date_input("Fecha Inicio (Vigencia):", value=None)
            nuevo_fecha_fin = col_nc5.date_input("Fecha Fin (Expiración):", value=None)
            
            opciones_cli_excl = ["Ninguno (Cupón Público)"] + sorted(df_clientes['nombre'].unique().tolist()) if not df_clientes.empty else ["Ninguno"]
            sel_cli_excl = col_nc6.selectbox(
                "Cupón exclusivo para un cliente:",
                options=opciones_cli_excl,
                index=0,
                placeholder="Selecciona si deseas vincularlo..."
            )
            
            btn_crear_disabled = not nuevo_codigo or nuevo_porcentaje <= 0
            if st.button("💾 Crear y Registrar Cupón en Supabase", type="primary", use_container_width=True, disabled=btn_crear_disabled):
                conn = get_db_connection()
                cli_excl_id = None
                if sel_cli_excl != "Ninguno (Cupón Público)" and not df_clientes.empty:
                    match_cli = df_clientes[df_clientes['nombre'] == sel_cli_excl]
                    if not match_cli.empty:
                        cli_excl_id = int(match_cli.iloc[0]['cliente_id'])
                        
                datos_cupon_insert = {
                    "codigo": nuevo_codigo,
                    "porcentaje_descuento": int(nuevo_porcentaje),
                    "fecha_inicio": nuevo_fecha_inicio.isoformat() if nuevo_fecha_inicio else None,
                    "fecha_fin": nuevo_fecha_fin.isoformat() if nuevo_fecha_fin else None,
                    "cliente_id_exclusivo": cli_excl_id,
                    "limite_usos": int(nuevo_limite_usos),
                    "usos_actuales": 0,
                    "activo": True
                }
                
                try:
                    conn.table("cupones").insert(datos_cupon_insert).execute()
                    st.success(f"🎉 ¡Cupón '{nuevo_codigo}' creado correctamente!")
                    st.cache_data.clear()
                    time.sleep(1.5)
                    st.rerun()
                except Exception as ex_insert_cup:
                    st.error(f"Error al registrar cupón en la base de datos: {ex_insert_cup}")

        if not df_cupones.empty:
            st.markdown("#### 📋 Listado y Estadísticas de Cupones Activos")
            
            df_cupones_viz = df_cupones.copy()
            if 'cliente_id_exclusivo' in df_cupones_viz.columns and not df_clientes.empty:
                df_cupones_viz = df_cupones_viz.merge(
                    df_clientes[['cliente_id', 'nombre']], 
                    left_on='cliente_id_exclusivo', 
                    right_on='cliente_id', 
                    how='left'
                ).rename(columns={'nombre': 'Exclusivo para'}).drop(columns=['cliente_id', 'cliente_id_exclusivo'], errors='ignore')
                df_cupones_viz['Exclusivo para'] = df_cupones_viz['Exclusivo para'].fillna('Público / Todos')
            else:
                df_cupones_viz['Exclusivo para'] = 'Público / Todos'
                
            st.dataframe(
                df_cupones_viz[['codigo', 'porcentaje_descuento', 'Exclusivo para', 'usos_actuales', 'limite_usos', 'fecha_inicio', 'fecha_fin', 'activo']],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "codigo": st.column_config.TextColumn("Código"),
                    "porcentaje_descuento": st.column_config.NumberColumn("Descuento", format="%d%%"),
                    "usos_actuales": st.column_config.NumberColumn("Usado"),
                    "limite_usos": st.column_config.NumberColumn("Límite"),
                    "activo": st.column_config.CheckboxColumn("Activo")
                }
            )
            
            st.markdown("##### ⚙️ Acciones Rápidas sobre Cupones")
            col_acc1, col_acc2 = st.columns(2)
            sel_cup_acc = col_acc1.selectbox("Selecciona un cupón para modificar:", options=[""] + df_cupones['codigo'].tolist(), index=0)
            
            if sel_cup_acc:
                row_cup_acc = df_cupones[df_cupones['codigo'] == sel_cup_acc].iloc[0]
                estado_actual_bool = bool(row_cup_acc.get('activo', True))
                label_actividad = "Desactivar Cupón 🟥" if estado_actual_bool else "Activar Cupón 🟩"
                
                if col_acc2.button(label_actividad, use_container_width=True):
                    try:
                        conn = get_db_connection()
                        conn.table("cupones").update({"activo": not estado_actual_bool}).eq("cupon_id", int(row_cup_acc['cupon_id'])).execute()
                        st.success(f"¡Estado del cupón '{sel_cup_acc}' cambiado con éxito!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e_cup_acc:
                        st.error(f"Error al cambiar estado del cupón: {e_cup_acc}")
                        
                if st.button("🗑️ Eliminar Cupón Permanentemente", type="primary", use_container_width=True):
                    try:
                        conn = get_db_connection()
                        conn.table("cupones").delete().eq("cupon_id", int(row_cup_acc['cupon_id'])).execute()
                        st.success(f"¡Cupón '{sel_cup_acc}' eliminado de forma permanente!")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e_cup_del:
                        st.error(f"Error al eliminar cupón: {e_cup_del}")

        st.markdown("---")
        st.markdown("#### 🏆 Fidelización: Compras Acumuladas por Clientes")
        with st.container(border=True):
            st.markdown("⚙️ **Configuración de Fidelidad (Descuento Automático)**")
            col_cfg1, col_cfg2 = st.columns(2)
            monto_min_cfg = col_cfg1.number_input(
                "Monto mínimo acumulado ($):", 
                min_value=0.0, 
                value=float(st.session_state.get('monto_minimo_cupon_cfg', 100000.0)), 
                step=10000.0,
                key="monto_minimo_cupon_cfg"
            )
            plazo_dias_cfg = col_cfg2.number_input(
                "Plazo de acumulación (días):", 
                min_value=1, 
                value=int(st.session_state.get('plazo_dias_cupon_cfg', 365)), 
                step=30,
                key="plazo_dias_cupon_cfg"
            )
            
        if df_clientes.empty:
            st.warning("No hay clientes registrados en el sistema.")
        else:
            with st.spinner("Analizando compras acumuladas..."):
                results_cupones = []
                
                if not df_ventas_global.empty:
                    ref_date_calc = df_ventas_global['fecha_limpia'].max()
                    if pd.isna(ref_date_calc):
                        ref_date_calc = pd.to_datetime("2026-08-27")
                else:
                    ref_date_calc = pd.to_datetime("2026-08-27")
                
                if hasattr(ref_date_calc, 'tz') and ref_date_calc.tz is not None:
                    ref_date_calc = ref_date_calc.tz_localize(None)
                    
                fecha_limite_calc = ref_date_calc - timedelta(days=int(plazo_dias_cfg))
                
                for _, cli in df_clientes.iterrows():
                    c_id_val = int(cli['cliente_id'])
                    status_str = str(cli.get('status', ''))
                    
                    fecha_canje_val = None
                    if "CANJE_CUPON:" in status_str:
                        try:
                            fecha_canje_str = status_str.split("CANJE_CUPON:")[1].strip()
                            fecha_canje_val = datetime.strptime(fecha_canje_str, "%Y-%m-%d")
                        except Exception:
                            pass
                            
                    total_acumulado = 0.0
                    if not df_ventas_global.empty and 'cliente_id' in df_ventas_global.columns:
                        df_cli_v = df_ventas_global[df_ventas_global['cliente_id'] == c_id_val].copy()
                        if not df_cli_v.empty:
                            df_cli_v['fecha_dt'] = pd.to_datetime(df_cli_v['fecha_venta'], errors='coerce')
                            df_cli_v = df_cli_v.dropna(subset=['fecha_dt'])
                            
                            def safe_to_naive_calc(val):
                                if pd.isna(val): return pd.NaT
                                ts = pd.to_datetime(val)
                                return ts.tz_localize(None) if ts.tz is not None else ts
                                
                            df_cli_v['fecha_dt'] = df_cli_v['fecha_dt'].apply(safe_to_naive_calc)
                            df_cli_v = df_cli_v[df_cli_v['fecha_dt'] >= fecha_limite_calc]
                            
                            if fecha_canje_val:
                                df_cli_v = df_cli_v[df_cli_v['fecha_dt'] > fecha_canje_val]
                                
                            df_completas_v = df_cli_v[
                                (df_cli_v['estado'] == 'FINALIZADO') | 
                                (df_cli_v['estado_pago'] == 'PAGADO')
                            ]
                            total_acumulado = df_completas_v['monto_final'].sum()
                            
                    clasifica_val = total_acumulado >= monto_min_cfg
                    results_cupones.append({
                        'cliente_id': c_id_val,
                        'nombre': cli['nombre'],
                        'email': cli.get('email', 'No registrado'),
                        'telefono': cli.get('telefono', 'No registrado'),
                        'status_original': status_str,
                        'fecha_ultimo_canje': fecha_canje_val.strftime("%d/%m/%Y") if fecha_canje_val else "Nunca",
                        'compras_acumuladas': total_acumulado,
                        'clasifica': clasifica_val
                    })
                    
                df_cupones_eval = pd.DataFrame(results_cupones)
                
            df_clasificados = df_cupones_eval[df_cupones_eval['clasifica'] == True].copy()
            
            st.markdown("#### 🏆 Apartado de Clientes que Clasifican para el Cupón de 10%")
            if df_clasificados.empty:
                st.success("🟢 Todas las cuentas al día. No hay clientas con cupones acumulados por canjear.")
            else:
                st.write(f"Se encontraron **{len(df_clasificados)}** clientas que superan el monto de **${monto_min_cfg:,.0f}** en compras en el período:")
                
                st.dataframe(
                    df_clasificados[['nombre', 'compras_acumuladas', 'fecha_ultimo_canje', 'email', 'telefono']],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "nombre": st.column_config.TextColumn("Nombre Cliente"),
                        "compras_acumuladas": st.column_config.NumberColumn("Compras Acumuladas", format="$%.0f"),
                        "fecha_ultimo_canje": st.column_config.TextColumn("Último Canje")
                    }
                )
                
                st.markdown("##### 🎁 Registrar Canje de Cupón de Fidelidad (Reinicio de Historial)")
                sel_cliente_canje = st.selectbox(
                    "Selecciona una clienta para registrar el canje:",
                    options=[""] + df_clasificados['nombre'].tolist(),
                    index=0,
                    placeholder="Elige una clienta..."
                )
                
                if sel_cliente_canje:
                    row_canje = df_clasificados[df_clasificados['nombre'] == sel_cliente_canje].iloc[0]
                    c_id_canje = int(row_canje['cliente_id'])
                    
                    st.write(f"⚠️ Al hacer clic en el botón de abajo, se guardará la fecha de hoy como último canje para **{sel_cliente_canje}**. Esto reiniciará la suma de sus compras acumuladas para futuros cupones.")
                    
                    if st.button("🎁 Confirmar Canje y Reiniciar Historial", type="primary", use_container_width=True):
                        try:
                            conn = get_db_connection()
                            old_status_val = str(row_canje['status_original'])
                            if " | CANJE_CUPON:" in old_status_val:
                                base_status_val = old_status_val.split(" | CANJE_CUPON:")[0].strip()
                            elif "CANJE_CUPON:" in old_status_val:
                                base_status_val = old_status_val.split("CANJE_CUPON:")[0].strip().strip("| ")
                            else:
                                base_status_val = old_status_val if old_status_val else "CLIENTE REGULAR"
                                
                            hoy_str_val = datetime.now().strftime("%Y-%m-%d")
                            nuevo_status_val = f"{base_status_val} | CANJE_CUPON: {hoy_str_val}"
                            
                            conn.table("clientes").update({"status": nuevo_status_val}).eq("cliente_id", c_id_canje).execute()
                            
                            st.success(f"🎉 Cupón registrado correctamente para {sel_cliente_canje}. Su historial ha sido reiniciado a partir de hoy.")
                            st.balloons()
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e_canje:
                            log_error("vista_caja", "canje_cupon_manual", e_canje, st.session_state.get('email_usuario', 'Desconocido'))
                            st.error(f"Error al registrar canje en Supabase: {e_canje}")
                            
            with st.expander("👥 Historial de Compras Acumuladas de todos los Clientes"):
                st.dataframe(
                    df_cupones_eval.sort_values(by='compras_acumuladas', ascending=False)[['nombre', 'compras_acumuladas', 'fecha_ultimo_canje', 'clasifica']],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "nombre": st.column_config.TextColumn("Nombre Cliente"),
                        "compras_acumuladas": st.column_config.NumberColumn("Compras Acumuladas", format="$%.0f"),
                        "fecha_ultimo_canje": st.column_config.TextColumn("Último Canje"),
                        "clasifica": st.column_config.CheckboxColumn("Clasifica para 10%")
                    }
                )

if __name__ == "__main__":
    mostrar_caja()