import streamlit as st
import pandas as pd
import time
from datetime import datetime
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error
from functions_vista_asignaciones import (
    cargar_clientes_suscritos,
    cargar_catalogo_completo_libros,
    cargar_libros_aptitud,
    auto_descartar_tapa_dura,
    cargar_libros_filtrados_para_cliente,
    cargar_asignaciones_mes,
    verificar_mes_cerrado,
    cambiar_estado_mes,
    comenzar_mes,
    asignar_libro_principal,
    generar_propuesta_azar,
    confirmar_propuesta_azar,
    guardar_ajustes_logistica,
    quitar_un_libro,
    eliminar_asignacion,
    actualizar_asignaciones_batch,
    mapear_sino,
    actualizar_asignaciones_masivo,
    cargar_historial_cambios,
    registrar_cambio_masivo,
    cargar_historico_asignaciones_completo
)

# --- INTERFAZ PRINCIPAL ---
def mostrar_asignaciones():
    st.title("📦 Gestión de Suscripciones")
    
    # Inicialización del límite del pagador del historial (comienza mostrando 200)
    if 'hist_limit_view' not in st.session_state:
        st.session_state.hist_limit_view = 200
    
    # Mapeo de meses de trabajo
    meses_dict = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
    
    opciones_menu = [
        "📋 Gestión (Tabla Editable)", 
        "📖 Asignar Libro Principal", 
        "📜 Historial suscripciones",
        "🚚 Gestionar Envío y Ajuste Manual", 
        "🚀 Generar / Actualizar Mes", 
        "🗑️ Eliminar/Quitar Libros", 
        "🧹 Desasignar Libros del Mes",
        "🔒 Cierre de Mes"
    ]
    
    opcion_menu = st.selectbox("👉 SELECCIONA LA ACCIÓN QUE DESEAS REALIZAR:", opciones_menu)
    st.markdown("---")
    
    # =========================================================================
    # 🌟 PASO 1: CARGA DE DATOS DINÁMICA SEGÚN LA PESTAÑA SELECCIONADA
    # =========================================================================
    if opcion_menu == "📜 Historial suscripciones":
        # En el Historial no se usa mes de trabajo activo, inicializamos valores neutros
        ano_sel = datetime.now().year
        mes_num = datetime.now().month
        df_mes = pd.DataFrame()
        mes_esta_cerrado = False
        
    else:
        # En las demás pestañas, renderizamos de forma limpia el selector del Mes de Trabajo activo
        with st.container(border=True):
            st.markdown("### 📅 Mes de Trabajo")
            c1, c2 = st.columns(2)
            mes_sel = c1.selectbox("Mes:", list(meses_dict.values()), index=datetime.now().month - 1)
            ano_sel = c2.number_input("Año:", min_value=2020, max_value=2050, value=datetime.now().year, step=1)
            mes_num = list(meses_dict.keys())[list(meses_dict.values()).index(mes_sel)]
        
    df_mes = cargar_asignaciones_mes(ano_sel, mes_num)
    mes_esta_cerrado = verificar_mes_cerrado(ano_sel, mes_num)
    
    # Procesamos y normalizamos los datos del mes actual
    if not df_mes.empty:
        df_mes['pagado'] = df_mes['pagado'].apply(mapear_sino)
        
        # 1. Normalizar y rellenar tipo_cobro_envio en caso de nulos
        if 'tipo_cobro_envio' not in df_mes.columns:
            df_mes['tipo_cobro_envio'] = ""
        df_mes['tipo_cobro_envio'] = df_mes['tipo_cobro_envio'].fillna("").astype(str).str.upper().str.strip()
                
        # 2. Regla auto-curativa en memoria: Si es POR PAGAR o RETIRO, envio_pagado es NO APLICA
        mask_no_aplica = df_mes['tipo_cobro_envio'].isin(["POR PAGAR", "RETIRO EN TIENDA"])
        df_mes.loc[mask_no_aplica, 'envio_pagado'] = "NO APLICA"
        
        # Para los despachos tradicionales pagados, normalizar pago a SI/NO
        df_mes.loc[~mask_no_aplica, 'envio_pagado'] = df_mes.loc[~mask_no_aplica, 'envio_pagado'].apply(mapear_sino)
        
        df_mes['estado_envio'] = df_mes['estado_envio'].apply(lambda x: str(x).upper())
        df_mes['extras'] = df_mes['extras'].fillna("").astype(str)
        
        df_mes['comentario'] = df_mes['comentario'].apply(lambda x: "" if pd.isna(x) or str(x).upper() == "NONE" else str(x))
        
        df_mes['valor_envio'] = pd.to_numeric(df_mes.get('valor_envio', 0), errors='coerce').fillna(0.0)
        df_mes['valor_extras'] = pd.to_numeric(df_mes.get('valor_extras', 0), errors='coerce').fillna(0.0)
        df_mes['monto_total'] = pd.to_numeric(df_mes.get('monto_total', 0), errors='coerce').fillna(0.0)
        
        # =========================================================================
        # 🌟 PASO 2: RENDERIZADO EXCLUSIVO DE MÉTRICAS LOGÍSTICAS DE CABECERA
        # =========================================================================
        # Solo se muestran las métricas de cajas si estamos en las pestañas operativas del mes actual
        if opcion_menu in ["📋 Gestión (Tabla Editable)", "📖 Asignar Libro Principal"] and not df_mes.empty:
            cajas_pagadas = len(df_mes[df_mes['pagado'] == 'SI'])
            cajas_pendientes = len(df_mes[df_mes['estado_envio'].isin(['PENDIENTE PREPARACION', 'EN PREPARACION'])])
            cajas_listas = len(df_mes[df_mes['estado_envio'].isin(['POR ENVIAR', 'POR RETIRAR'])])
            
            c_res1, c_res2, c_res3, c_res4 = st.columns(4)
            c_res1.metric("📦 Total Cajas", len(df_mes))
            c_res2.metric("💳 Pagadas", f"{cajas_pagadas} / {len(df_mes)}")
            c_res3.metric("⏳ Por Preparar", cajas_pendientes)
            c_res4.metric("✅ Listas para Enviar", cajas_listas)
            st.markdown("---")
            
        # =========================================================================
        # 🌟 PASO 3: RENDERIZADO EXCLUSIVO DEL MENSAJE DE MES BLOQUEADO
        # =========================================================================
        # La alerta roja de bloqueo solo aparece si el mes está cerrado y estamos en las pestañas operativas
        if mes_esta_cerrado and opcion_menu in ["📋 Gestión (Tabla Editable)", "📖 Asignar Libro Principal"]:
            st.error(f"🔒 **MES CERRADO:** {mes_sel.upper()} {ano_sel} está bloqueado. Los cambios están deshabilitados.", icon="🔒")

    # ==========================================================
    # 1. TABLA EDITABLE (VERSIÓN FINAL COMPLETA)
    # ==========================================================
    if opcion_menu == "📋 Gestión (Tabla Editable)":
        if not mes_esta_cerrado:
            with st.expander("💡 GUÍA RÁPIDA: Gestión de Preferencias Mensuales", expanded=False):
                st.info(
                    "1. **¿Qué es?** Aquí puedes registrar el género que una clienta pidió **específicamente para este mes** (ej: 'Terror').\n\n"
                    "2. **¿Cómo funciona?** Escribe el o los géneros en la columna `Preferencia Mensual`. Si dejas la celda vacía, el sistema usará las preferencias de siempre de la clienta.\n\n"
                    "3. **Prioridad:** Lo que escribas aquí **siempre tendrá prioridad** sobre los gustos históricos de la clienta al momento de asignar libros.\n\n"
                    "4. **Guardado:** Haz doble clic en una celda para editar y luego presiona `💾 Guardar Cambios Manuales` al final de la tabla."
                )
            
            st.markdown("---")
            
            with st.expander("📖 Ver Historial de Últimos Cambios Masivos", expanded=False):
                # Llamamos a la función que busca los datos en Supabase
                df_historial = cargar_historial_cambios()
                
                if df_historial.empty:
                    st.caption("Aún no se han registrado ediciones en bloque.")
                else:
                    st.caption("Mostrando los últimos 5 cambios realizados con la herramienta de edición masiva.")
                    for _, row in df_historial.iterrows():
                        with st.container(border=True):
                            # Intentamos formatear la fecha a hora de Chile
                            try:
                                fecha_utc = pd.to_datetime(row['fecha_cambio']).tz_convert('America/Santiago')
                                fecha_str = fecha_utc.strftime('%d-%m-%Y a las %H:%M:%S hrs')
                            except:
                                fecha_str = str(row['fecha_cambio'])[:19] # Fallback si no hay pytz
                            st.markdown(f"**Fecha:** {fecha_str} | **Usuario:** `{row['email_usuario']}`")
                            st.markdown(
                                f"Se cambió la columna **`{row['columna_afectada']}`** al nuevo valor **`{row['valor_nuevo']}`** "
                                f"para **{row['total_filas_afectadas']} clientes** en el mes **{row['mes_afectado']}/{row['ano_afectado']}**."
                            )
                            
                            # Tratamos de leer el JSON con los clientes afectados y sus valores antiguos
                            try:
                                import json
                                clientes = json.loads(row['clientes_afectados'])
                                nombres_clientes = [f"{c['nombre']} *(Antes: {c.get('valor_antiguo', 'N/A')})*" for c in clientes]
                                st.code("- " + "\n- ".join(nombres_clientes), language=None)
                            except Exception as e:
                                st.caption(f"No se pudo cargar el detalle de las clientas. Error: {e}")
            
            if df_mes.empty: 
                st.warning("No hay registros para este mes.")
            else:
                with st.expander("🔽 Filtros de Búsqueda y Visibilidad de Columnas", expanded=False):
                    # 🔴 Fila 1: Tres columnas perfectamente equilibradas
                    col_fa1, col_fa2, col_fa3 = st.columns(3)
                    
                    with col_fa1:
                        # Selección Múltiple con Autocompletado para Clientes
                        opciones_nombre = sorted(df_mes['nombre'].dropna().unique())
                        filtro_nombres_sel = st.multiselect("🔍 Seleccionar Cliente(s):", options=opciones_nombre, placeholder="Escribe o selecciona clientes...")
                        
                    with col_fa2:
                        # Selección Múltiple con Autocompletado para Libros
                        opciones_libro = sorted(df_mes['titulo_libro'].dropna().unique())
                        filtro_libros_sel = st.multiselect("📖 Seleccionar Libro(s):", options=opciones_libro, placeholder="Escribe o selecciona libros...")
                        
                    with col_fa3:
                        fechas_pago_unicas = sorted([d for d in df_mes['fecha_pago'].dropna().unique()], reverse=True)
                        filtro_fecha_pago = st.selectbox("📅 Fecha de Pago:", ["Todas"] + fechas_pago_unicas)
                    
                    st.markdown("---")
                    # 🔴 Fila 2: Filtros de estados y envío
                    col_fa4, col_fa5, col_fa5_2, col_fa6, col_fa7 = st.columns(5)
                    with col_fa4:
                        filtro_estado = st.selectbox("📦 Estado Envío:", ["Todos"] + df_mes['estado_envio'].unique().tolist())
                    with col_fa5:
                        filtro_pagado = st.selectbox("💳 Estado de Pago:", ["Todos"] + df_mes['pagado'].unique().tolist())
                    with col_fa5_2:
                        filtro_tipo_cobro_envio = st.selectbox("🚚 Cobro Envío:", ["Todos"] + df_mes['tipo_cobro_envio'].unique().tolist())
                    with col_fa6:
                        filtro_libro = st.selectbox("📚 Asignación Libro:", ["Todos", "Sin Libro", "Con Libro"])
                    with col_fa7:
                        # Filtro de Método de Envío (Multiselección)
                        opciones_envio = [str(x) for x in df_mes['metodo_entrega'].dropna().unique().tolist() if str(x).strip()]
                        filtro_metodo_envio = st.multiselect("🚚 Método Envío:", options=opciones_envio, default=[])
                    
                    st.markdown("---")
                    
                    # 🔴 Fila 3: Visibilidad de Columnas
                    columnas_opcionales = [
                        'pagado', 'envio_pagado', 'tipo_cobro_envio', 'nombre', 'titulo_libro', 'estado_envio', 
                        'costo_caja', 'valor_envio', 'valor_extras', 'monto_total', 'extras', 'comentario', 'metodo_entrega',
                        'preferencia_mensual' 
                    ]
                    
                    columnas_visibles = st.multiselect(
                        "👁️ Ocultar/Mostrar Columnas en la Tabla:", 
                        options=columnas_opcionales, 
                        default=['pagado', 'envio_pagado', 'tipo_cobro_envio', 'nombre', 'titulo_libro', 'estado_envio', 'preferencia_mensual'],
                        help="Quita las columnas que no necesites ver para tener una vista más limpia."
                    )

                # =========================================================================
                # 🌟 NUEVA UBICACIÓN: HERRAMIENTA DE ASIGNACIÓN DE PREFERENCIAS (DEBAJO DE LOS FILTROS)
                # =========================================================================
                if not mes_esta_cerrado:
                    with st.expander("✨ Asignar Preferencia Mensual a un Cliente", expanded=False):
                        # 1. Cargamos todos los libros (incluso sin stock) para conocer el universo total de géneros
                        df_libros_completo = cargar_catalogo_completo_libros(incluir_sin_stock=True)
                        
                        set_generos = set()
                        if not df_libros_completo.empty and 'genero' in df_libros_completo.columns:
                            generos_raw = df_libros_completo['genero'].dropna().unique()
                            
                            # 2. Desempaquetamos y limpiamos los géneros de los libros
                            for g_str in generos_raw:
                                if isinstance(g_str, str) and g_str.strip():
                                    # Dividimos por coma por si algún libro tiene más de un género
                                    generos_individuales = [g.strip().upper() for g in g_str.split(',') if g.strip()]
                                    set_generos.update(generos_individuales)
                        
                        # 3. Lista final limpia y ordenada
                        generos_disponibles = sorted(list(set_generos))
                        # --------------------------------------------------------------
                        
                        clientes_disponibles = dict(zip(df_mes['nombre'], df_mes['asignacion_id']))
                        col_a1, col_a2 = st.columns(2)
                        
                        cliente_sel = col_a1.selectbox(
                            "1. Selecciona un Cliente:",
                            options=list(clientes_disponibles.keys()),
                            index=None,
                            placeholder="👤 Busca o selecciona un cliente...",
                            key="cliente_pref_sel"
                        )
                        
                        if cliente_sel:
                            asignacion_id_sel = clientes_disponibles[cliente_sel]
                            
                            # Buscamos las preferencias actuales de ese cliente
                            preferencia_actual_str = df_mes.loc[df_mes['asignacion_id'] == asignacion_id_sel, 'preferencia_mensual'].values[0]
                            
                            # Normalizamos a mayúsculas y filtramos solo los géneros que existen en el catálogo actual para evitar StreamlitAPIException
                            preferencias_actuales = []
                            if preferencia_actual_str and isinstance(preferencia_actual_str, str):
                                preferencias_actuales = [
                                    g.strip().upper() 
                                    for g in preferencia_actual_str.split(',') 
                                    if g.strip().upper() in generos_disponibles
                                ]
                            
                            generos_sel = col_a2.multiselect(
                                "2. Selecciona hasta 3 géneros:",
                                options=generos_disponibles,
                                default=preferencias_actuales,
                                max_selections=3,
                                key="generos_pref_sel"
                            )
                            
                            if st.button("💾 Guardar Preferencia para este Cliente", type="primary", key="btn_guardar_pref"):
                                # Unimos los géneros seleccionados en un solo string
                                preferencia_final_str = ", ".join(generos_sel).upper()
                                
                                try:
                                    conn = get_db_connection()
                                    conn.table("asignaciones").update(
                                        {"preferencia_mensual": preferencia_final_str}
                                    ).eq("asignacion_id", asignacion_id_sel).execute()
                                    
                                    st.success(f"¡Preferencia '{preferencia_final_str}' guardada para {cliente_sel}!")
                                    
                                    # Limpieza dinámica del estado para forzar renderizado limpio sin widgets "pegados"
                                    if 'cliente_pref_sel' in st.session_state: 
                                        del st.session_state.cliente_pref_sel
                                    if 'generos_pref_sel' in st.session_state: 
                                        del st.session_state.generos_pref_sel
                                    
                                    time.sleep(1.5)
                                    st.rerun() # Refrescamos para que la tabla principal muestre el cambio
                                except Exception as e:
                                    st.error(f"No se pudo guardar la preferencia. Error: {e}")
                    st.markdown("---")

                # --- 2. APLICACIÓN DE FILTROS INTELIGENTES ---
                df_filtrado = df_mes.copy()
                
                # Buscador de Nombres (usa la lista del multiselect 'filtro_nombres_sel')
                if filtro_nombres_sel:
                    df_filtrado = df_filtrado[df_filtrado['nombre'].isin(filtro_nombres_sel)]
                        
                # Buscador de Títulos (usa la lista del multiselect 'filtro_libros_sel')
                if filtro_libros_sel:
                    df_filtrado = df_filtrado[df_filtrado['titulo_libro'].isin(filtro_libros_sel)]
                    
                # (El resto de tus filtros de fecha, estado, etc. se mantienen igual)
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
                if filtro_tipo_cobro_envio != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['tipo_cobro_envio'] == filtro_tipo_cobro_envio]   
                if filtro_metodo_envio:
                    df_filtrado = df_filtrado[df_filtrado['metodo_entrega'].isin(filtro_metodo_envio)]
                
                # --- 3. PREPARACIÓN DE COLUMNAS ---
                columnas_visibles_ordenadas = [col for col in columnas_opcionales if col in columnas_visibles]
                columnas_mostrar = ['asignacion_id'] + columnas_visibles_ordenadas
                
                columnas_seguras = [col for col in columnas_mostrar if col in df_filtrado.columns]
                df_mostrar = df_filtrado[columnas_seguras].copy()
                
                # --- 4. MODO EDICIÓN EN BLOQUE ---
                if 'edit_mode' not in st.session_state:
                    st.session_state.edit_mode = False
                if st.button("✏️ Activar/Desactivar Edición en Bloque", use_container_width=True, type="primary", help="Selecciona varias filas y aplica un cambio a todas a la vez."):
                    st.session_state.edit_mode = not st.session_state.edit_mode
                    if not st.session_state.edit_mode and 'propuesta_cambio' in st.session_state:
                        del st.session_state.propuesta_cambio
                    st.rerun()
                
                if st.session_state.edit_mode:
                    with st.expander("🆘 Edición Masiva Ayuda 🆘", expanded=False):
                        st.info(
                            "💡 **GUÍA RÁPIDA: ¿Cómo usar la Edición en Bloque?**\n"
                            "1. ✅ **Selecciona a los clientes:** Marca la casilla en la primera columna de la tabla (`Seleccionar`) para cada cliente que quieras modificar.\n"
                            "2. ✍️ **Elige el cambio:** Ve al formulario de abajo y escoge la **columna** que quieres cambiar y el **nuevo valor** que le aplicarás a todos.\n"
                            "3. 🔍 **Previsualiza:** Presiona el botón `Previsualizar Cambios`. El sistema te mostrará un resumen de lo que estás a punto de hacer.\n"
                            "4. 🛡️ **Confirma con seguridad:** En el cuadro de previsualización, escribe la palabra `CONFIRMAR CAMBIOS` y presiona `Confirmar y Ejecutar` para aplicar los cambios de forma masiva."
                        )
                        
                    df_mostrar.insert(0, "Seleccionar", False)
                
                # --- 5. GUARDADO DE ESTADO ORIGINAL ---
                if 'asignaciones_original' not in st.session_state or not st.session_state.asignaciones_original.equals(df_mostrar):
                    st.session_state.asignaciones_original = df_mostrar.copy()
                
                # --- 6. CONFIGURACIÓN Y DIBUJO DE LA TABLA ---
                st.caption("Doble clic en las celdas para modificar manualmente. Los totales se recalcularán al guardar.")
                
                config_cols = {
                    "asignacion_id": None,
                    "estado_envio": st.column_config.SelectboxColumn("Estado", options=["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO", "LIBRO ASIGNADO"], required=True),
                    "pagado": st.column_config.SelectboxColumn("Pagado", options=["SI", "NO", "ABONO"], required=True),
                    "envio_pagado": st.column_config.SelectboxColumn("Envío Pagado 💳", options=["SI", "NO", "NO APLICA"], required=True),
                    "tipo_cobro_envio": st.column_config.SelectboxColumn("Tipo de Cobro Envío 🚚", options=["", "PAGADO", "POR PAGAR", "RETIRO EN TIENDA"], required=False),
                    "costo_caja": st.column_config.NumberColumn("Costo Caja Fijo ($)", format="$%.0f"),
                    "valor_envio": st.column_config.NumberColumn("Valor Envío ($)", format="$%.0f"),
                    "valor_extras": st.column_config.NumberColumn("Valor Extras ($)", format="$%.0f"),
                    "monto_total": st.column_config.NumberColumn("Monto Total a Cobrar ($)", format="$%.0f"),
                    "comentario": st.column_config.TextColumn("Comentario", max_chars=300),
                    "preferencia_mensual": st.column_config.TextColumn(
                        "Preferencia Mensual", 
                        help="Este campo se edita en el formulario de arriba.",
                        disabled=True
                    )
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
                
                # --- 7. PREVISUALIZACIÓN Y CONFIRMACIÓN ---
                if 'propuesta_cambio' in st.session_state:
                    propuesta = st.session_state.propuesta_cambio
                    st.markdown("---")
                    with st.container(border=True):
                        st.error("🚨 **¡ESTÁS A UN PASO DE APLICAR CAMBIOS MASIVOS!** 🚨")
                        st.write(f"Vas a escribir **'{propuesta['valor']}'** en la columna **'{propuesta['columna']}'** para **{len(propuesta['ids_afectados'])}** clientes:")
                        
                        nombres_preview = "- " + "\n- ".join(propuesta['nombres_afectados'][:10])
                        st.code(nombres_preview, language=None)
                        if len(propuesta['nombres_afectados']) > 10:
                            st.caption(f"...y {len(propuesta['nombres_afectados']) - 10} más.")
                        
                        st.warning("⚠️ **Por favor, revisa la lista de arriba muy bien.**")
                        st.info("""
                            🤷‍♀️ **Aviso del Departamento de TI:** Te hemos entregado un gran poder, y un gran poder conlleva una gran responsabilidad. \n 
                            Si omites revisar, cambias todo al valor equivocado y dejas la escoba en la base de datos... *TI se lava las manos*. \n
                            ¡Úsalo con sabiduría! 🪄✨ Porque al **CONFIRMAR CAMBIOS** aceptas los términos y condiciones 🙂‍↕️.
                        """)                    
                        st.markdown("---")
                        
                        with st.form("form_confirmacion_final"):
                            confirmacion_texto = st.text_input("Si estás seguro de no arruinarlo, escribe **CONFIRMAR CAMBIOS** en mayúsculas:")
                            submit_final = st.form_submit_button("✅ Confirmar y Ejecutar", type="primary", use_container_width=True)
                            if submit_final and confirmacion_texto == "CONFIRMAR CAMBIOS":
                                with st.spinner("Aplicando cambios y registrando en el historial..."):
                                    exito, error_msg = actualizar_asignaciones_masivo(propuesta['ids_afectados'], propuesta['columna'], propuesta['valor'])
                                    if exito:
                                        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
                                        registrar_cambio_masivo(
                                            email=email_usuario,
                                            columna=propuesta['columna'],
                                            valor=propuesta['valor'],
                                            ids_afectados=propuesta['ids_afectados'],
                                            nombres_afectados=propuesta['nombres_afectados'],
                                            valores_antiguos=propuesta['valores_antiguos'], 
                                            mes=mes_num,
                                            ano=ano_sel
                                        )
                                        st.success("¡Cambios aplicados y registrados con éxito!")
                                        del st.session_state.propuesta_cambio
                                        if 'asignaciones_original' in st.session_state:
                                            del st.session_state.asignaciones_original
                                        st.session_state.edit_mode = False
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Error al aplicar los cambios: {error_msg}")
                        
                        if st.button("❌ Arrepentirse y Cancelar", use_container_width=True):
                            del st.session_state.propuesta_cambio
                            st.rerun()
                
                # --- 8. HERRAMIENTAS DE EDICIÓN MASIVA ---
                else:
                    if st.session_state.edit_mode:
                        st.markdown("---")
                        col_limite, col_contador = st.columns([1, 2])
                        limite_filas = col_limite.selectbox("🛑 Límite de filas a editar a la vez:", options=[5, 10, 15, 20, 25, 30], index=0)
                        filas_seleccionadas = df_editado[df_editado["Seleccionar"] == True]
                        cantidad_sel = len(filas_seleccionadas)
                        excede_limite = len(filas_seleccionadas) > limite_filas
                        
                        with col_contador:
                            st.write("") # Pequeño espacio para alinear con el cuadro de la izquierda
                            st.write("")
                            if cantidad_sel == 0:
                                st.info("👉 No has marcado ninguna fila todavía.")
                            elif excede_limite:
                                st.error(f"⚠️ Has marcado **{cantidad_sel}** filas. ¡Superaste el límite permitido de {limite_filas}!")
                            else:
                                st.success(f"✅ Llevas **{cantidad_sel}** filas seleccionadas listas para modificar.")
                        
                        st.markdown("##### ⚙️ Aplicar Cambios en Lote")
                        st.warning("⚠️ **ACCIÓN DELICADA:** Revisa bien las filas seleccionadas antes de proceder.")
                        
                        def forzar_rerun():
                            pass 
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            columnas_modificables = ["estado_envio", "pagado", "envio_pagado", "tipo_cobro_envio", "valor_envio", "comentario"]
                            columna_a_cambiar = st.selectbox("1. Columna a modificar:", columnas_modificables, key="col_a_cambiar", on_change=forzar_rerun)
                        
                        with col2:
                            opciones_desplegables = {
                                "estado_envio": ["PENDIENTE PREPARACION", "EN PREPARACION", "POR ENVIAR", "POR RETIRAR", "ENVIADO", "RETIRADO", "LIBRO ASIGNADO"],
                                "pagado": ["SI", "NO", "ABONO"],
                                "envio_pagado": ["SI", "NO", "NO APLICA"],
                                "tipo_cobro_envio": ["", "PAGADO", "POR PAGAR", "RETIRO EN TIENDA"]
                            }
                            if columna_a_cambiar in opciones_desplegables:
                                nuevo_valor = st.selectbox("2. Nuevo valor:", options=opciones_desplegables[columna_a_cambiar])
                            elif columna_a_cambiar == "valor_envio":
                                nuevo_valor = st.number_input("2. Nuevo valor ($):", min_value=0.0, step=1000.0, format="%.0f")
                            else:
                                nuevo_valor = st.text_input("2. Nuevo valor:", value="")
                                
                        if st.button("🔍 Previsualizar Cambios", disabled=(filas_seleccionadas.empty or excede_limite), type="primary"):
                            nombres_lista = filas_seleccionadas['nombre'].tolist() if 'nombre' in filas_seleccionadas.columns else [f"ID {x}" for x in filas_seleccionadas['asignacion_id'].tolist()]
                            valores_antiguos = filas_seleccionadas[columna_a_cambiar].tolist()
                            
                            st.session_state.propuesta_cambio = {
                                "columna": columna_a_cambiar, 
                                "valor": nuevo_valor,
                                "ids_afectados": filas_seleccionadas['asignacion_id'].tolist(),
                                "nombres_afectados": nombres_lista, 
                                "valores_antiguos": valores_antiguos
                            }
                            st.rerun()
                    
                    # --- 9. GUARDADO MANUAL ---
                    else:
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
                                        
    # ==========================================================
    # 2. ASIGNAR SOLO LIBRO PRINCIPAL
    # ==========================================================
    elif opcion_menu == "📖 Asignar Libro Principal":
        if mes_esta_cerrado: 
            st.warning("Mes cerrado.")
        else:
            with st.expander("⚙️ Gestionar Aptitud de Libros para Cajitas (Exclusiones)", expanded=False):
                with st.expander("📖 ¿Cómo funciona esta sección? (Ver Guía Rápida)", expanded=False):
                    st.info(
                        "💡 **GUÍA RÁPIDA: ¿Cómo funciona esta sección?**\n\n"
                        "1. **¿Qué significa Apto?** Los libros con el check (✅) entrarán en la asignación de cajitas. Los desmarcados (⬜) serán excluidos.\n"
                        "2. **El botón mágico (🪄):** Si tienes muchos libros 'TAPA DURA', presiónalo y el sistema los excluirá automáticamente por ti con un solo clic.\n"
                        "3. **Edición manual:** Si hay un libro específico (ej. uno muy pesado o caro) que quieres excluir, simplemente desmarca su casilla en la tabla de abajo.\n"
                        "4. **Guardar:** Una vez que edites la tabla, aparecerá el botón azul `💾 Guardar Cambios de Aptitud`. Presiónalo para confirmar."
                    )
                st.write("")
                
                if st.button("🪄 Auto-excluir libros Tapa Dura", help="Marca como 'No Apto' a todos los libros con encuadernación TAPA DURA", key="btn_auto_excluir_tapa_dura"):
                    with st.spinner("Actualizando catálogo..."):
                        modificados = auto_descartar_tapa_dura()
                        if modificados > 0:
                            st.success(f"¡Listo! Se excluyeron {modificados} libros Tapa Dura.")
                        elif modificados == 0:
                            st.info("Todos los libros Tapa Dura ya estaban excluidos.")
                        else:
                            st.error("Hubo un error al actualizar la base de datos.")
                        
                        cargar_libros_aptitud.clear()
                        cargar_catalogo_completo_libros.clear()
                        st.session_state.clear_apt_cache = True
                        time.sleep(1.5)
                        st.rerun()
                
                df_aptitud_base = cargar_libros_aptitud()
                
                if not df_aptitud_base.empty:
                    df_aptitud_base['apto_cajita'] = df_aptitud_base['apto_cajita'].fillna(True).astype(bool)
                    
                    # Inicializamos la copia de trabajo en session_state para persistir ediciones entre búsquedas
                    if 'df_aptitud_working' not in st.session_state or st.session_state.get('clear_apt_cache', False):
                        st.session_state.df_aptitud_working = df_aptitud_base.copy()
                        st.session_state.clear_apt_cache = False
                        
                    # Botones de desmarcar / marcar todos
                    col_lote1, col_lote2 = st.columns(2)
                    if col_lote1.button("⬜ Desmarcar Todos (Ninguno Apto)", use_container_width=True, key="btn_desmarcar_todos_apt"):
                        st.session_state.df_aptitud_working['apto_cajita'] = False
                        st.rerun()
                    if col_lote2.button("✅ Marcar Todos como Aptos (Excluyendo Tapa Dura)", use_container_width=True, key="btn_marcar_todos_apt"):
                        df_work = st.session_state.df_aptitud_working
                        df_work['apto_cajita'] = df_work['encuadernacion'].fillna("").astype(str).str.upper().str.strip() != "TAPA DURA"
                        st.rerun()
                        
                    # Lupa para buscar libros particulares
                    lupa_libro = st.text_input("🔍 Lupa: Buscar libro por título o autor (Aptitud):", placeholder="Escribe el nombre o autor del libro...", key="lupa_aptitud")
                    
                    # Filtrado dinámico en memoria
                    df_mostrar_apt = st.session_state.df_aptitud_working.copy()
                    if lupa_libro:
                        filtro_lupa = (
                            df_mostrar_apt['titulo'].str.contains(lupa_libro, case=False, na=False) |
                            df_mostrar_apt.get('autor', pd.Series(dtype=str)).str.contains(lupa_libro, case=False, na=False)
                        )
                        df_mostrar_apt = df_mostrar_apt[filtro_lupa]
                        
                    total_libros_stock = len(st.session_state.df_aptitud_working)
                    aptos = st.session_state.df_aptitud_working['apto_cajita'].sum()
                    no_aptos = total_libros_stock - aptos
                    
                    st.markdown("##### Resumen de Estado Actual")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("📚 Total con Stock", total_libros_stock)
                    col_m2.metric("✅ Aptos para Cajita", aptos)
                    col_m3.metric("❌ No Aptos", no_aptos)
                    st.markdown("---")
                    
                    # Dibujamos el data_editor con los datos filtrados por la lupa
                    df_editado_apt_filtered = st.data_editor(
                        df_mostrar_apt,
                        column_config={
                            "libro_id": None,
                            "titulo": st.column_config.TextColumn("Título", disabled=True, width="large"),
                            "encuadernacion": st.column_config.TextColumn("Encuadernación", disabled=True),
                            "stock": st.column_config.NumberColumn("Stock", disabled=True),
                            "apto_cajita": st.column_config.CheckboxColumn("¿Apto Cajita? ✅", default=True)
                        },
                        hide_index=True, use_container_width=True, key="editor_aptitud_libros"
                    )
                    
                    # Guardamos de vuelta los checks modificados al DataFrame maestro de session_state
                    if not df_mostrar_apt.equals(df_editado_apt_filtered):
                        st.session_state.df_aptitud_working.set_index('libro_id', inplace=True)
                        df_editado_apt_filtered_set = df_editado_apt_filtered.set_index('libro_id')
                        st.session_state.df_aptitud_working.update(df_editado_apt_filtered_set)
                        st.session_state.df_aptitud_working.reset_index(inplace=True)
                        st.rerun()
                        
                    # Botón para guardar los cambios de aptitud modificados en la Base de Datos
                    if not df_aptitud_base.equals(st.session_state.df_aptitud_working):
                        if st.button("💾 Guardar Cambios de Aptitud", type="primary", use_container_width=True, key="btn_guardar_apt_db"):
                            with st.spinner("Guardando en la base de datos..."):
                                conn = get_db_connection()
                                diff = st.session_state.df_aptitud_working.merge(df_aptitud_base, on='libro_id', suffixes=('_nuevo', '_viejo'))
                                cambios = diff[diff['apto_cajita_nuevo'] != diff['apto_cajita_viejo']]
                                
                                for _, row in cambios.iterrows():
                                    conn.table("libros").update({"apto_cajita": row['apto_cajita_nuevo']}).eq("libro_id", row['libro_id']).execute()
                                
                                if not cambios.empty:
                                    st.success(f"Se actualizaron {len(cambios)} libros con éxito.")
                                    st.session_state.clear_apt_cache = True
                                    cargar_libros_aptitud.clear()
                                    cargar_catalogo_completo_libros.clear()
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.info("No se detectaron cambios para guardar.")
                else:
                    st.warning("No hay libros con stock en el inventario.")
            
            st.markdown("---")
            if df_mes.empty: 
                st.info("No hay suscripciones en el mes.")
            else:
                df_pendientes = df_mes[df_mes['titulo_libro'] == "⏳ PENDIENTE DE ASIGNAR"]

                ## --- ASIGNACIÓN MASIVA Y AUTOMÁTICA ---
                with st.container(border=True):
                    st.markdown("### 🎲 Asignación al Azar (Masiva y Segura)")
                    st.caption("Analiza stock y gustos en vivo. Solo asigna libros si existe coincidencia perfecta.")
                    
                    df_filtrado_final = df_pendientes.copy()
                    
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
                    
                    
                    # --- BOTÓN DE GENERACIÓN DE PROPUESTA PRINCIPAL ---
                    if st.button("🔍 Generar Propuesta (Previsualización)", type="primary", use_container_width=True, key="btn_generar_propuesta_azar"):
                        if not df_filtrado_final.empty:
                            with st.spinner("Analizando inventario y gustos..."):
                                prop, sin_asig = generar_propuesta_azar(df_filtrado_final)
                                st.session_state.propuesta_azar = prop
                                st.session_state.sin_asignar_azar = sin_asig
                        else: 
                            st.warning("No hay clientes pendientes  que cumplan las condiciones de fecha si están activas).")

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
                        df_pendientes['metodo_entrega_limpio'] = df_pendientes['metodo_entrega'].apply(limpiar_texto_para_busqueda)
                        metodos_disponibles = sorted(df_pendientes['metodo_entrega_limpio'].dropna().unique())
                        metodos_disponibles = [m for m in metodos_disponibles if m]
                        
                        contenedor_selector = st.container()
                        contenedor_filtro = st.container()
                        contenedor_resto = st.container()
                        
                        # 1. LÓGICA DEL FILTRO (Se mostrará abajo gracias al contenedor_filtro)
                        with contenedor_filtro:
                            with st.expander("🔍 Filtrar lista por método de envío (Opcional)", expanded=False):
                                metodo_seleccionado = st.multiselect(
                                    "Selecciona uno o más métodos:",
                                    options=metodos_disponibles,
                                    label_visibility="collapsed"
                                )
                                
                        # Aplicamos el filtro a los datos
                        df_clientes_a_mostrar = df_pendientes.copy()
                        if metodo_seleccionado:
                            df_clientes_a_mostrar = df_clientes_a_mostrar[df_clientes_a_mostrar['metodo_entrega_limpio'].isin(metodo_seleccionado)]
                            
                        # 2. SELECTOR DE CLIENTE (Se mostrará arriba gracias al contenedor_selector)
                        with contenedor_selector:
                            if df_clientes_a_mostrar.empty:
                                st.warning("No hay clientes pendientes que coincidan con ese método de envío.")
                                cliente_nom = None
                            else:
                                dict_clientes = dict(zip(df_clientes_a_mostrar['nombre'], df_clientes_a_mostrar['cliente_id']))
                                
                                # --- SELECTOR VACÍO POR DEFECTO ---
                                cliente_nom = st.selectbox(
                                    "👤 Seleccionar Cliente Pendiente:", 
                                    options=list(dict_clientes.keys()),
                                    index=None,
                                    placeholder="Busca o selecciona a una clienta..."
                                )
                            
                            if cliente_nom:
                                with contenedor_resto:
                                    cliente_id = dict_clientes[cliente_nom]
                                    filas_cliente = df_clientes_a_mostrar[df_clientes_a_mostrar['cliente_id'] == cliente_id]
                                    
                                    if filas_cliente.empty:
                                        st.warning("⚠️ No se pudieron cargar los datos de este cliente. Por favor, refresca la página.")
                                    else:
                                        asig_row = filas_cliente.iloc[0]
                                        
                                        preferencia_del_mes = asig_row.get('preferencia_mensual')
                                        tiene_pref_mensual = pd.notna(preferencia_del_mes) and str(preferencia_del_mes).strip() != ""
                                        
                                        st.write("---") # Separador visual
                                        col_chk1, col_chk2 = st.columns(2)
                                        ver_sin_stock = col_chk1.checkbox("📦 Mostrar también libros sin stock", value=False, key=f"chk_stock_{cliente_id}")
                                        
                                        usar_historica_forzada = False
                                        if tiene_pref_mensual:
                                            usar_historica_forzada = col_chk1.checkbox("📜 Usar preferencias de siempre", value=False, help="Ignora la preferencia del mes y usa las preferencias de siempre de la clienta.", key=f"chk_hist_{cliente_id}")
                                        
                                        ignorar_preferencias = col_chk2.checkbox("📚 Ignorar todas las preferencias", value=False, disabled=usar_historica_forzada, key=f"chk_ignorar_{cliente_id}")
                                        st.write("---")
                                        
                                        df_libros_disponibles, gustos_cliente = cargar_libros_filtrados_para_cliente(
                                            cliente_id, asig_row, incluir_sin_stock=ver_sin_stock, usar_historica=usar_historica_forzada
                                        )
                                        
                                        if ignorar_preferencias:
                                            st.info("Mostrando todos los libros disponibles (preferencias ignoradas).")
                                        elif gustos_cliente:
                                            st.info(f"❤️ Géneros preferidos del cliente: **{', '.join(gustos_cliente)}**")
                                        else:
                                            st.caption("ℹ️ El cliente no registra géneros de preferencia específicos.")
                                            
                                        if df_libros_disponibles.empty:
                                            st.warning("No hay libros disponibles en el catálogo que el cliente no posea ya.")
                                        else:
                                            df_libros_a_mostrar = df_libros_disponibles.copy()
                                            
                                            if gustos_cliente and not ignorar_preferencias:
                                                df_libros_a_mostrar['genero_limpio'] = df_libros_a_mostrar['genero'].apply(lambda x: limpiar_texto_para_busqueda(str(x)).upper())
                                                
                                                def es_sugerido(row):
                                                    return not set(gustos_cliente).isdisjoint(set(row['genero_limpio'].split()))
                                                df_libros_a_mostrar['es_sugerido'] = df_libros_a_mostrar.apply(es_sugerido, axis=1)
                                                
                                                df_libros_a_mostrar = df_libros_a_mostrar[df_libros_a_mostrar['es_sugerido']]
                                                
                                                if df_libros_a_mostrar.empty:
                                                    st.warning("⚠️ No hay libros en stock que coincidan con sus gustos. Marca 'Ignorar todas las preferencias' para ver el resto del catálogo.")
                                            else:
                                                df_libros_a_mostrar['es_sugerido'] = False 
                                            
                                            if not df_libros_a_mostrar.empty:
                                                df_libros_a_mostrar = df_libros_a_mostrar.sort_values(by=['es_sugerido', 'stock', 'titulo'], ascending=[False, False, True])
                                                
                                                df_libros_a_mostrar['label_opcion'] = df_libros_a_mostrar.apply(
                                                    lambda row: f"⭐ {row['titulo']} (Género: {row['genero']} | Stock: {row['stock']})" if row['es_sugerido'] else f"  {row['titulo']} (Género: {row['genero']} | Stock: {row['stock']})",
                                                    axis=1
                                                )
                                                
                                                dict_libros = dict(zip(df_libros_a_mostrar['label_opcion'], df_libros_a_mostrar['libro_id']))
                                                
                                                libro_sel_label = st.selectbox(
                                                    "Seleccionar Libro para Asignar:", 
                                                    options=list(dict_libros.keys()),
                                                    index=None,
                                                    placeholder="Busca o selecciona un libro..."
                                                )
                                                
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
                                                            if 'cliente_manual_asig' in st.session_state: del st.session_state.cliente_manual_asig
                                                            if 'libro_manual_asig' in st.session_state: del st.session_state.libro_manual_asig
                                                            st.success(f"¡Libro '{libro_info['titulo']}' asignado a {cliente_nom} con éxito!")
                                                            time.sleep(1.5)
                                                            st.rerun()
                                                        else:
                                                            st.error(f"Error al asignar: {err}")

    # ==========================================================
    # 3. HISTORIAL SUSCRIPCIONES (MÉTRICAS REACTIVAS CON COSTO Y UTILIDAD)
    # ==========================================================
    elif opcion_menu == "📜 Historial suscripciones":
        st.markdown("### 📜 Historial de Suscripciones y Envíos")
        
        # Nota explicativa de cálculos del historial
        st.info("""
        💡 **¿Cómo se calculan las finanzas en este panel de Historial?**
        * **Recaudación Bruta:** Suma de los montos de suscripción (`valor_suscripcion`) cobrados para todas las cajas listadas (excluyendo envíos y extras).
        * **Costos de Producción:** Suma acumulada del costo de armado físico (`costo_caja`) para las cajas del período (estimado en **$10,000** por defecto por caja).
        * **Utilidad Estimada:** Se obtiene restando `Recaudación Bruta - Costos de Producción` (representa tu ganancia neta real basada puramente en el margen de membresía de libros).
        """)
        
        df_historico_raw = cargar_historico_asignaciones_completo()
        
        if df_historico_raw.empty:
            st.info("Aún no registras asignaciones históricas en el sistema.")
        else:
            df_hist_asig = df_historico_raw.copy()
            df_hist_asig['pagado'] = df_hist_asig['pagado'].apply(mapear_sino)
            df_hist_asig['estado_envio'] = df_hist_asig['estado_envio'].apply(lambda x: str(x).upper())
            df_hist_asig['monto_total'] = pd.to_numeric(df_hist_asig['monto_total'], errors='coerce').fillna(0.0)
            
            # 🌟 CORRECCIÓN 1: Coaccionar la columna 'mes' de forma segura a tipo entero para evitar fallos de strings ("1")
            df_hist_asig['mes_int'] = pd.to_numeric(df_hist_asig['mes'], errors='coerce').fillna(0).astype(int)
            
            # 🌟 CORRECCIÓN 2: Mapeamos con el diccionario sobre la nueva columna entera corregida
            df_hist_asig['mes_nombre'] = df_hist_asig['mes_int'].map(meses_dict).fillna("Desconocido")
            
            with st.expander("🔍 Filtros de Búsqueda del Historial", expanded=True):
                col_h1, col_h2, col_h3, col_h4 = st.columns(4)
                
                # Filtro por Año
                anios_disponibles = ["Ver Todos"] + sorted(list(set(df_hist_asig['ano'].dropna().astype(int).tolist())), reverse=True)
                sel_anio_h = col_h1.selectbox("Filtrar por Año:", options=anios_disponibles, key="hist_filter_year")
                
                # 🌟 CORRECCIÓN 3: Poblar el dropdown de meses dinámicamente y de forma cronológica (Ene-Dic)
                meses_numericos_presentes = sorted([m for m in df_hist_asig['mes_int'].unique() if m in meses_dict])
                meses_disponibles = ["Ver Todos"] + [meses_dict[m] for m in meses_numericos_presentes]
                
                sel_mes_h = col_h2.selectbox("Filtrar por Mes:", options=meses_disponibles, key="hist_filter_month")
                sel_pago_h = col_h3.selectbox("Filtrar por Pago:", ["Todos", "SI", "NO", "ABONO"], key="hist_filter_pago")
                
                opciones_clientes_h = sorted(df_hist_asig['nombre'].dropna().unique().tolist())
                sel_clientes_h = col_h4.multiselect("Buscar Cliente(s):", options=opciones_clientes_h, placeholder="", key="hist_filter_clients")

            df_filtrado_h = df_hist_asig.copy()
            if sel_anio_h != "Ver Todos": df_filtrado_h = df_filtrado_h[df_filtrado_h['ano'] == int(sel_anio_h)]
            if sel_mes_h != "Ver Todos": df_filtrado_h = df_filtrado_h[df_filtrado_h['mes_nombre'] == sel_mes_h]
            if sel_pago_h != "Todos": df_filtrado_h = df_filtrado_h[df_filtrado_h['pagado'] == sel_pago_h]
            if sel_clientes_h: df_filtrado_h = df_filtrado_h[df_filtrado_h['nombre'].isin(sel_clientes_h)]

            # --- 📊 KPI'S REACTIVAS FINANCIERAS CORREGIDAS (MARGEN PURO DE MEMBRESÍA) ---
            total_cajas_h = len(df_filtrado_h)
            
            # Filtramos una copia en memoria solo con las transacciones pagadas para el balance real
            df_pagadas_h = df_filtrado_h[df_filtrado_h['pagado'] == 'SI'].copy()
            cajas_pagadas_h = len(df_pagadas_h)
            
            # Convertimos valores a numéricos de forma segura en ambos dataframes
            df_pagadas_h['valor_suscripcion'] = pd.to_numeric(df_pagadas_h['valor_suscripcion'], errors='coerce').fillna(18500.0)
            df_pagadas_h['costo_caja'] = pd.to_numeric(df_pagadas_h['costo_caja'], errors='coerce').fillna(10000.0)
            
            # 🌟 RECAUDACIÓN BRUTA REAL: Suma pura de los cobros de membresía ($17.000 / $18.500)
            monto_total_recaudado_h = df_pagadas_h['valor_suscripcion'].sum()
            
            # Costo de Producción Real = Sumatoria de costos de armado de cajas que ya se pagaron
            costo_total_cajas_h = df_pagadas_h['costo_caja'].sum()
            
            # 🌟 UTILIDAD REAL: Recaudación de Membresías - Costos de Caja (Descontando envíos y extras por completo)
            df_pagadas_h['utilidad_real'] = df_pagadas_h['valor_suscripcion'] - df_pagadas_h['costo_caja']
            utilidad_total_h = df_pagadas_h['utilidad_real'].sum()

            st.markdown("#### 📊 Balance Financiero del Período Filtrado")
            c_h1, c_h2, c_h3, c_h4 = st.columns(4)
            c_h1.metric("💰 Recaudación Bruta", f"${monto_total_recaudado_h:,.0f}")
            c_h2.metric("📦 Costos de Producción", f"${costo_total_cajas_h:,.0f}", help="Costo total de armado físico acumulado para las cajas de este período.")
            
            if utilidad_total_h >= 0:
                c_h3.metric("📈 Utilidad Estimada", f"${utilidad_total_h:,.0f}", help="Utilidad calculada excluyendo los costos de despacho.")
            else:
                c_h3.metric("📉 Pérdida Estimada", f"${utilidad_total_h:,.0f}")
            c_h4.metric("💳 Cajas Pagadas", f"{cajas_pagadas_h} / {total_cajas_h}")
            st.markdown("---")

            # --- TABLA DE DATOS DEL HISTORIAL GENERAL CON PAGINACIÓN ---
            limite_actual = st.session_state.hist_limit_view
            total_filas_filtradas = len(df_filtrado_h)
            
            # Cortamos el DataFrame para mostrar únicamente las filas más recientes según el límite
            df_paginado = df_filtrado_h.head(limite_actual)
            
            st.caption(f"Mostrando los **{len(df_paginado)}** registros más recientes de un total de **{total_filas_filtradas}** encontrados para los filtros activos.")
            
            st.dataframe(
                df_paginado[['asignacion_id', 'nombre', 'ano', 'mes_nombre', 'estado_envio', 'pagado', 'monto_total', 'comentario']],
                use_container_width=True, hide_index=True,
                column_config={
                    "asignacion_id": "ID", "nombre": "Cliente", "ano": "Año", "mes_nombre": "Mes de Trabajo",
                    "estado_envio": "Estado Despacho", "pagado": "Estado Pago",
                    "monto_total": st.column_config.NumberColumn("Monto Cobrado", format="$%.0f"), "comentario": "Comentarios"
                }
            )
            
            # Renderizar el botón de paginación diferida solo si quedan filas por mostrar
            if total_filas_filtradas > limite_actual:
                col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
                with col_pag2:
                    if st.button(f"🔄 Cargar más registros (+100) — Quedan {total_filas_filtradas - limite_actual} por ver", use_container_width=True):
                        st.session_state.hist_limit_view += 100
                        st.rerun()
            else:
                # Si aplicó filtros y se muestran menos de las filas límite, restablecemos el paginador al valor por defecto
                st.session_state.hist_limit_view = 100

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
                    cliente_mod_sel = st.selectbox(
                        "1. Seleccionar Cliente:", 
                        options=lista_clientes,
                        index=None,
                        placeholder="🚚 Selecciona un cliente...",
                        key="cliente_logistica_sel"
                    )
                    
                    if cliente_mod_sel:
                        id_asig_tmp = int(cliente_mod_sel.split(" - ")[0].replace("ID:", ""))
                        row_caja = df_mes[df_mes['asignacion_id'] == id_asig_tmp].iloc[0]
                        
                        st.markdown("#### 🚚 Despacho y Envío")
                        tipo_cobro_envio_manual = st.number_input("Establecer Costo de Envío para esta caja ($):", min_value=0.0, step=500.0, value=float(row_caja.get('valor_envio', 0.0)))
                        
                        st.markdown("#### 📝 Ajuste Manual de Extras (Escape Hatch)")
                        st.warning("⚠️ Modifica estas casillas SOLAMENTE si necesitas corregir un error (ej: si anulaste una venta en caja y necesitas borrar el nombre del libro de esta lista).")
                        nuevo_extra_txt = st.text_input("Texto libre de Extras:", value=row_caja.get('extras', ''))
                        nuevo_valor_ext = st.number_input("Monto total acumulado por Extras ($):", min_value=0.0, step=500.0, value=float(row_caja.get('valor_extras', 0.0)))
                        
                        st.markdown("---")
                        if st.button("✅ Guardar Cambios en Logística", type="primary"):
                            ex, err = guardar_ajustes_logistica(id_asig_tmp, row_caja['cliente_id'], tipo_cobro_envio_manual, nuevo_extra_txt, nuevo_valor_ext)
                            if ex: 
                                if 'cliente_logistica_sel' in st.session_state: del st.session_state.cliente_logistica_sel
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
                
                # --- NUEVA LÓGICA: DETECTAR INACTIVOS CON CAJA ---
                df_inactivos_mes = pd.DataFrame()
                if not df_mes.empty:
                    conn = get_db_connection()
                    ids_mes = df_mes['cliente_id'].dropna().unique().tolist()
                    if ids_mes:
                        # Extraemos el estado actual de los clientes que tienen caja este mes
                        res_status = conn.table("clientes").select("cliente_id, status").in_("cliente_id", [int(x) for x in ids_mes]).execute()
                        if res_status.data:
                            df_status = pd.DataFrame(res_status.data)
                            df_mes_con_status = pd.merge(df_mes, df_status, on='cliente_id', how='left')
                            # Filtramos a las que ya NO son "ACTIVA"
                            df_inactivos_mes = df_mes_con_status[df_mes_con_status['status'] != 'ACTIVA']
                    clientes_en_mes = df_mes['cliente_id'].nunique()
                    # Clientes activos que aún no tienen caja
                    ids_activos = df_suscritos_activos['cliente_id'].tolist()
                    clientes_faltantes = len(set(ids_activos) - set(ids_mes))
                else:
                    clientes_en_mes = 0
                    clientes_faltantes = total_clientes_activos
                
                col1, col2, col3 = st.columns(3)
                col1.metric("👥 Total Clientes Activos", total_clientes_activos)
                col2.metric("📦 Cajas Creadas en el Mes", clientes_en_mes)
                col3.metric("⏳ Cajas Pendientes por Crear", max(0, clientes_faltantes), help="Clientes activos que aún no tienen una caja para este mes.")
                st.markdown("---")
                
                # --- NUEVA SECCIÓN: ALERTA Y ELIMINACIÓN DE INACTIVOS ---
                if not df_inactivos_mes.empty:
                    st.error(f"🚨 **¡ATENCIÓN!** Hay **{len(df_inactivos_mes)} cliente(s)** con caja asignada en este mes que actualmente NO ESTÁN ACTIVAS (Ej: Pausadas, Inactivas).")
                    
                    df_mostrar_inact = df_inactivos_mes[['asignacion_id', 'nombre', 'status', 'titulo_libro', 'libro_suscripcion_id', 'cliente_id', 'extras']].copy()
                    
                    # Destacamos si tienen libro asignado
                    df_mostrar_inact['Alerta Libro'] = df_mostrar_inact['titulo_libro'].apply(
                        lambda x: "⚠️ DEVOLVERÁ STOCK" if x != "⏳ PENDIENTE DE ASIGNAR" else "Caja vacía (Seguro borrar)"
                    )
                    st.dataframe(
                        df_mostrar_inact[['nombre', 'status', 'titulo_libro', 'Alerta Libro']],
                        column_config={
                            "nombre": "Cliente",
                            "status": "Estado Actual",
                            "titulo_libro": "Libro Asignado",
                            "Alerta Libro": "Aviso Stock"
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    if st.button("🗑️ Eliminar Cajas de estos Clientes Inactivos", type="primary"):
                        with st.spinner("Eliminando registros y devolviendo stock al inventario..."):
                            exitos = 0
                            errores = []
                            for _, row in df_mostrar_inact.iterrows():
                                ex, err = eliminar_asignacion(
                                    asignacion_id=int(row['asignacion_id']), 
                                    libro_id=row['libro_suscripcion_id'], 
                                    cliente_id=int(row['cliente_id']), 
                                    ano=ano_sel, 
                                    mes=mes_num, 
                                    texto_extras=row.get('extras', '')
                                )
                                if ex: exitos += 1
                                else: errores.append(f"Error con {row['nombre']}: {err}")
                            
                            if exitos > 0:
                                st.success(f"✅ Se eliminaron {exitos} cajas inútiles correctamente. ¡Stock restaurado!")
                            if errores:
                                for e in errores: st.error(e)
                            
                            time.sleep(2)
                            st.rerun()
                    st.markdown("---")
                
                # --- SECCIÓN ORIGINAL DE CREACIÓN ---
                st.info(
                    "💡 **¿Cómo usar esta herramienta?**\n\n"
                    "1. **A principio de mes:** Crea las cajas en blanco para todas tus clientas en estado 'ACTIVA'.\n\n"
                    "2. **A mitad de mes:** Si se inscriben nuevas clientas, presiona este botón nuevamente para agregarlas.\n\n"
                    "🛡️ **Tranquilidad:** El sistema es inteligente y **solo agregará a las clientas faltantes** con un costo fijo de caja base de $10.000."
                )
                
                if st.button("🚀 Crear Registros Faltantes del Mes", type="primary", use_container_width=True):
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