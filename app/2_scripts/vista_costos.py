import streamlit as st
import pandas as pd
from datetime import datetime
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

def unificar_formatos_fecha(serie_fechas):
    """
    Función de parseo de fechas robusta, capaz de interpretar múltiples 
    formatos (YYYY-MM-DD y DD-MM-YYYY).
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
        log_error("vista_costos", "unificar_formatos_fecha", f"Error inesperado al parsear fechas: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        return pd.to_datetime(serie_fechas, errors='coerce')

@st.cache_data(ttl=300)
def cargar_costos_no_ventas():
    """
    Carga todos los GASTOS desde Supabase.
    Bypassea el límite transaccional de 1000 registros utilizando paginación dinámica.
    """
    conn = get_db_connection()
    try:
        all_data = []
        chunk_size = 1000
        # Bucle seguro de rango amplio (hasta 100.000 costos)
        for bloque in range(100):
            start = bloque * chunk_size
            end = start + chunk_size - 1
            res = conn.table("costos_no_ventas")\
                .select("*")\
                .order("costo_id")\
                .range(start, end).execute()
            if res.data:
                all_data.extend(res.data)
                if len(res.data) < chunk_size:
                    break
            else:
                break
                
        df = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        if not df.empty:
            df['monto'] = pd.to_numeric(df['monto'], errors='coerce').fillna(0.0)
            # 🌟 CORRECCIÓN CRÍTICA: Convertir directamente la columna a datetime.date nativo de Python
            df['fecha_ocurrencia'] = unificar_formatos_fecha(df['fecha_ocurrencia']).dt.date
        return df
    except Exception as e:
        log_error("vista_costos", "cargar_costos_no_ventas", e, st.session_state.get('email_usuario', 'Desconocido'))
        st.error("Error crítico: No se pudo cargar el listado de costos no operacionales.")
        return pd.DataFrame(columns=['costo_id', 'fecha_ocurrencia', 'tipo_costo', 'monto', 'comentario', 'creado_por'])

def registrar_costo(fecha_ocurrencia, tipo_costo, monto, comentario):
    """Inserta un nuevo costo en Supabase."""
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    datos = {
        "fecha_ocurrencia": fecha_ocurrencia.strftime("%Y-%m-%d"),
        "tipo_costo": limpiar_texto_para_busqueda(tipo_costo).upper(),
        "monto": float(monto),
        "comentario": comentario.strip(),
        "creado_por": email_usuario
    }
    try:
        conn.table("costos_no_ventas").insert(datos).execute()
        return True, ""
    except Exception as e:
        log_error("vista_costos", "registrar_costo", e, email_usuario)
        return False, str(e)

def actualizar_historial_costos(df_editado):
    """Detecta cambios en el data_editor y actualiza los costos modificados."""
    df_original = st.session_state.get('historial_costos_original', pd.DataFrame())
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
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    
    for _, row in filas_cambiadas.iterrows():
        try:
            costo_id = int(row['costo_id'])
            datos_costo = {
                "fecha_ocurrencia": pd.to_datetime(row['fecha_ocurrencia']).strftime("%Y-%m-%d") if pd.notna(row['fecha_ocurrencia']) else None,
                "tipo_costo": limpiar_texto_para_busqueda(str(row['tipo_costo'])).upper(),
                "monto": float(row['monto']),
                "comentario": str(row['comentario']).strip()
            }
            conn.table("costos_no_ventas").update(datos_costo).eq("costo_id", costo_id).execute()
            updates += 1
        except Exception as e:
            log_error("vista_costos", "actualizar_historial_costos", f"Error en costo #{row.get('costo_id')}: {e}", email_usuario)
            st.warning(f"No se pudo guardar la fila del costo #{row.get('costo_id', '')}.")
            continue
    return updates

def eliminar_costo(costo_id):
    """Elimina permanentemente un costo en Supabase."""
    conn = get_db_connection()
    email_usuario = st.session_state.get('email_usuario', 'Desconocido')
    try:
        conn.table("costos_no_ventas").delete().eq("costo_id", costo_id).execute()
        return True, ""
    except Exception as e:
        log_error("vista_costos", "eliminar_costo", e, email_usuario)
        return False, str(e)

# ==========================================
# --- VISTA PRINCIPAL (COSTOS NO VENTAS) ---
# ==========================================
def mostrar_costos():
    if 'costos_limit_view' not in st.session_state:
        st.session_state.costos_limit_view = 50
        
    if 'historial_costos_original' not in st.session_state:
        st.session_state.historial_costos_original = pd.DataFrame()
        
    st.title("💸 GASTOS")
    
    df_costos = cargar_costos_no_ventas()
    
    # --- METRICAS DE RESUMEN ARRIBA ---
    st.markdown("#### 📊 Resumen del Período de Gastos")
    if not df_costos.empty:
        col1, col2, col3, col4 = st.columns(4)
        total_monto = df_costos['monto'].sum()
        promedio_monto = df_costos['monto'].mean()
        cant_costos = len(df_costos)
        tipo_mas_comun = df_costos['tipo_costo'].mode().iloc[0] if not df_costos['tipo_costo'].empty else "N/A"
        
        col1.metric("💰 Total Gastado", f"${total_monto:,.0f}")
        col2.metric("📈 Gasto Promedio", f"${promedio_monto:,.0f}")
        col3.metric("📋 Cantidad Registros", f"{cant_costos}")
        col4.metric("🏷️ Mayor Incidencia", tipo_mas_comun)
    else:
        st.info("No hay datos de costos no operacionales registrados.")
        
    st.markdown("---")
    
    tab_nuevo, tab_historial, tab_eliminar = st.tabs([
        "➕ Nuevo Costo", "📜 Historial y Edición", "🗑️ Eliminar Costo"
    ])
    
    # ================= TAB: REGISTRAR NUEVO COSTO =================
    with tab_nuevo:
        st.markdown("### 📝 Registrar Costo de Oficina / Administración")
        with st.form("form_nuevo_costo", clear_on_submit=True):
            col_fecha, col_tipo = st.columns(2)
            fecha_ocurrencia = col_fecha.date_input("Fecha de Ocurrencia del Costo:", value=datetime.now().date())
            
            categorias_sugeridas = ["CONTADORA", "PUBLICIDAD", "INSUMOS", "ALIMENTACIÓN", "PERSONAL", "OTROS"]
            tipo_seleccionado = col_tipo.selectbox(
                "Tipo de Costo (Seleccione una categoría):",
                options=categorias_sugeridas,
                index=None,
                placeholder="Selecciona una categoría...",
                key="sel_tipo_costo_nuevo"
            )
            
            tipo_personalizado = col_tipo.text_input("U otro tipo personalizado (Opcional):", placeholder="Ej: Servicios Básicos, Alquiler...")
            
            col_monto, col_comentario = st.columns([1, 2])
            monto_costo = col_monto.number_input("Monto ($):", min_value=0.0, step=1000.0, format="%f")
            comentario_costo = col_comentario.text_area("Comentario / Descripción:", placeholder="Detalle adicional del gasto...", max_chars=300)
            
            submit_btn = st.form_submit_button("💾 Guardar Costo", use_container_width=True)
            
            if submit_btn:
                tipo_final = tipo_personalizado.strip() if tipo_personalizado.strip() else (tipo_seleccionado if tipo_seleccionado else "")
                if not tipo_final:
                    st.error("❌ Debe especificar un Tipo de Costo.")
                elif monto_costo <= 0:
                    st.error("❌ El monto del costo debe ser mayor a $0.")
                else:
                    exito, err = registrar_costo(fecha_ocurrencia, tipo_final, monto_costo, comentario_costo)
                    if exito:
                        st.success("🎉 ¡Costo registrado exitosamente!")
                        st.cache_data.clear()
                        
                        # Patron UX: Auto-limpieza dinámica de estado de widget utilizando DEL
                        if "sel_tipo_costo_nuevo" in st.session_state:
                            del st.session_state["sel_tipo_costo_nuevo"]
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ Error al registrar costo: {err}")
                        
    # ================= TAB: HISTORIAL Y EDICIÓN =================
    with tab_historial:
        st.markdown("### 📜 Historial de GASTOS")
        if df_costos.empty:
            st.info("Aún no hay registros en el historial.")
        else:
            with st.expander("🔍 Filtros del Historial"):
                col_f1, col_f2 = st.columns(2)
                
                tipos_unicos = ["Todos"] + sorted(df_costos['tipo_costo'].unique().tolist())
                filtro_tipo = col_f1.selectbox("Filtrar por Categoría:", options=tipos_unicos, index=0)
                
                opciones_mes = ["Ver Todo"]
                mapa_inverso_mes = {}
                df_fechas_validas = df_costos.dropna(subset=['fecha_ocurrencia'])
                if not df_fechas_validas.empty:
                    df_fechas_validas['mes_ano_str'] = pd.to_datetime(df_fechas_validas['fecha_ocurrencia']).dt.strftime('%Y-%m')
                    meses_unicos = sorted(df_fechas_validas['mes_ano_str'].unique(), reverse=True)
                    
                    month_map_es = {
                        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
                        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
                        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
                    }
                    for mes_str in meses_unicos:
                        ano, mes_num = mes_str.split('-')
                        nombre_amigable = f"{month_map_es.get(mes_num, '')} {ano}"
                        opciones_mes.append(nombre_amigable)
                        mapa_inverso_mes[nombre_amigable] = mes_str
                        
                filtro_mes = col_f2.selectbox("Filtrar por Mes:", options=opciones_mes, index=0)
            
            # Procesar filtros
            df_filtrado = df_costos.copy()
            if filtro_tipo != "Todos":
                df_filtrado = df_filtrado[df_filtrado['tipo_costo'] == filtro_tipo]
            if filtro_mes != "Ver Todo":
                mes_str_a_buscar = mapa_inverso_mes.get(filtro_mes)
                if mes_str_a_buscar:
                    df_filtrado = df_filtrado[pd.to_datetime(df_filtrado['fecha_ocurrencia']).dt.strftime('%Y-%m') == mes_str_a_buscar]
                    
            st.markdown(f"#### Periodo Filtrado - Gasto Acumulado: **${df_filtrado['monto'].sum():,.0f}**")
            
            columnas_por_defecto = ['costo_id', 'fecha_ocurrencia', 'tipo_costo', 'monto', 'comentario', 'creado_por']
            df_mostrar = df_filtrado[columnas_por_defecto].copy()
            
            # Almacenar en session_state para auditoría de cambios
            st.session_state.historial_costos_original = df_mostrar.copy()
            
            config_cols = {
                "costo_id": st.column_config.NumberColumn("ID Costo", disabled=True),
                "fecha_ocurrencia": st.column_config.DateColumn("Fecha Ocurrencia", format="DD/MM/YYYY"),
                "tipo_costo": st.column_config.TextColumn("Tipo de Costo"),
                "monto": st.column_config.NumberColumn("Monto ($)", format="$%.0f"),
                "comentario": st.column_config.TextColumn("Comentario"),
                "creado_por": st.column_config.TextColumn("Registrado Por", disabled=True)
            }
            
            limite_actual = st.session_state.costos_limit_view
            df_paginado = df_mostrar.head(limite_actual)
            
            st.caption(f"Mostrando {len(df_paginado)} de {len(df_mostrar)} costos encontrados.")
            
            # 🌟 CORREGIDO: st.data_editor recibirá tipos datetime.date nativos en 'fecha_ocurrencia'
            df_editado = st.data_editor(
                df_paginado,
                use_container_width=True,
                hide_index=True,
                column_config=config_cols,
                key="editor_costos_no_ventas"
            )
            
            if not df_paginado.equals(df_editado):
                if st.button("💾 Guardar Cambios en Historial", type="primary", key="btn_save_costos"):
                    num = actualizar_historial_costos(df_editado)
                    if num > 0:
                        st.success(f"¡Se actualizaron {num} registros de costos exitosamente!")
                        st.cache_data.clear()
                        time.sleep(1.5)
                        st.rerun()
                        
            # Botón dinámico de paginación diferida
            if len(df_mostrar) > limite_actual:
                if st.button(f"🔄 Cargar más costos (+50)", use_container_width=True):
                    st.session_state.costos_limit_view += 50
                    st.rerun()
                    
    # ================= TAB: ELIMINAR REGISTRO =================
    with tab_eliminar:
        st.markdown("### 🗑️ Eliminar Registro de Costo")
        if df_costos.empty:
            st.info("No hay costos disponibles en bodega transaccional para eliminar.")
        else:
            df_costos_ordenados = df_costos.sort_values(by="costo_id", ascending=False)
            df_costos_ordenados['etiqueta'] = df_costos_ordenados.apply(
                lambda r: f"ID: {r['costo_id']} | Fecha: {r['fecha_ocurrencia']} | Tipo: {r['tipo_costo']} | Monto: ${r['monto']:,.0f}", axis=1
            )
            
            costo_seleccionado_etiqueta = st.selectbox(
                "Seleccione el costo que desea eliminar de manera permanente:",
                options=[""] + df_costos_ordenados['etiqueta'].tolist(),
                index=0,
                key="sel_costo_eliminar"
            )
            
            if costo_seleccionado_etiqueta:
                costo_sel = df_costos_ordenados[df_costos_ordenados['etiqueta'] == costo_seleccionado_etiqueta].iloc[0]
                costo_id_eliminar = int(costo_sel['costo_id'])
                
                st.warning(f"⚠️ ¿Está seguro de que desea eliminar el costo **ID {costo_id_eliminar}** por un monto de **${costo_sel['monto']:,.0f}**? Esta acción no se puede deshacer.")
                
                if st.button("🟥 CONFIRMAR ELIMINACIÓN PERMANENTE", type="primary", use_container_width=True):
                    exito, err = eliminar_costo(costo_id_eliminar)
                    if exito:
                        st.success(f"🎉 ¡El costo ID {costo_id_eliminar} fue removido exitosamente!")
                        st.cache_data.clear()
                        
                        # Patron UX: Limpieza de estado utilizando DEL
                        if "sel_costo_eliminar" in st.session_state:
                            del st.session_state["sel_costo_eliminar"]
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(f"❌ Error al eliminar el costo: {err}")