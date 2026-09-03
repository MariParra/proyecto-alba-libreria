import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import time
import io
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error
from functions_vista_caja import (
    cargar_libros_caja,
    cargar_clientes_caja,
    cargar_cupones_caja,
    unificar_formatos_fecha,
    check_elegibilidad_cliente_cupon,
    cargar_listas_desplegables_caja,
    check_exclusivity,
    cargar_historial_completo,
    evaluar_restricciones_libro,
    generar_comprobante,
    gestionar_cliente,
    procesar_venta_carrito,
    actualizar_historial_caja,
    cambiar_logistica_venta_existente,
    anular_venta

)

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
                            l_costo = st.number_input("Costo ($):", value=l_costo, step=100.0, key="costo_edit_caja_2")
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
            
            # Asegurarse de que 'costo' exista y sea numérico para evitar errores de tipo
            if 'costo' in df_carrito.columns:
                df_carrito['costo'] = pd.to_numeric(df_carrito['costo'], errors='coerce').fillna(0.0)
            else:
                df_carrito['costo'] = 0.0
                
            df_carrito_display = df_carrito[['Quitar', 'cantidad', 'titulo', 'costo', 'precio_cobrado', 'subtotal']].copy()
            df_carrito_estilizado = df_carrito_display.style.apply(
                lambda s: ['background-color: #ffebee; color: #c62828; font-weight: bold;' if (pd.isna(v) or v == 0 or v == 0.0) else '' for v in s],
                subset=['costo']
            )
            
            df_editado_carrito = st.data_editor(
                df_carrito_estilizado, 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    "Quitar": st.column_config.CheckboxColumn("Quitar ❌", default=False),
                    "costo": st.column_config.NumberColumn("Costo", format="$%.0f"),
                    "precio_cobrado": st.column_config.NumberColumn("Precio Cobrado", format="$%.0f"),
                    "subtotal": st.column_config.NumberColumn("Subtotal", format="$%.0f")
                }
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
        # --- MOTOR DE CUPONES CENTRALIZADO AL TOTAL DE LA COMPRA ---
        with st.expander("🎟️ Aplicar Cupón o Descuento de Fidelidad al Total", expanded=True):
            eligible_cupones = []
            if not df_cupones.empty:
                for _, cp in df_cupones.iterrows():
                    if not cp.get('activo', True):
                        continue
                    if int(cp.get('usos_actuales', 0)) >= int(cp.get('limite_usos', 1)):
                        continue
                        
                    hoy_dt = date.today()
                    fi = cp.get('fecha_inicio')
                    ff = cp.get('fecha_fin')
                    
                    # Validación de fecha de inicio ultra-segura contra NaT
                    if pd.notna(fi) and str(fi).strip() != "":
                        try:
                            fi_dt = pd.to_datetime(fi)
                            if pd.notna(fi_dt) and hoy_dt < fi_dt.date():
                                continue
                        except Exception:
                            pass
                            
                    # Validación de fecha de fin ultra-segura contra NaT
                    if pd.notna(ff) and str(ff).strip() != "":
                        try:
                            ff_dt = pd.to_datetime(ff)
                            if pd.notna(ff_dt) and hoy_dt > ff_dt.date():
                                continue
                        except Exception:
                            pass
                            
                    excl_raw = cp.get('cliente_id_exclusivo')
                    # Si es nulo, vacío, o '[]', es público para todos:
                    es_exclusivo = False
                    if pd.notna(excl_raw) and excl_raw is not None and str(excl_raw).strip() != "" and str(excl_raw).lower() not in ["none", "nan", "null", "[]"]:
                        es_exclusivo = True
                            
                    if es_exclusivo:
                        if c_id is None or not check_exclusivity(c_id, excl_raw):
                            continue
                            
                    eligible_cupones.append(cp.to_dict())
            
            # Construir opciones del selector
            coupon_options = ["Sin Cupón"]
            
            # Evaluar de forma no intrusiva si el cliente califica para fidelidad
            clasifica_fidelidad = False
            if c_id is not None:
                monto_min_cfg = st.session_state.get('monto_minimo_cupon_cfg', 100000.0)
                plazo_dias_cfg = st.session_state.get('plazo_dias_cupon_cfg', 365)
                clasifica_fidelidad, _, _ = check_elegibilidad_cliente_cupon(
                    c_id, df_clientes, df_ventas_global, monto_min_cfg, plazo_dias_cfg
                )
                
            if clasifica_fidelidad:
                coupon_options.append("🎟️ CUPÓN FIDELIDAD - 10% Descuento")
                
            for cp in eligible_cupones:
                coupon_options.append(f"🎫 {cp['codigo']} - {cp['porcentaje_descuento']}% Descuento")
                
            sel_cup_db = st.selectbox(
                "Selecciona un cupón disponible para esta venta:",
                options=coupon_options,
                index=0,
                key="sel_cup_db_venta"
            )
            
            st.session_state.aplicar_cupon_sistema_obj = None
            st.session_state.chk_aplicar_cupon_fidelidad_auto = False
            
            if sel_cup_db == "🎟️ CUPÓN FIDELIDAD - 10% Descuento":
                st.session_state.chk_aplicar_cupon_fidelidad_auto = True
            elif sel_cup_db != "Sin Cupón":
                codigo_sel = sel_cup_db.replace("🎫 ", "").split(" - ")[0].strip()
                for cp in eligible_cupones:
                    if cp['codigo'] == codigo_sel:
                        st.session_state.aplicar_cupon_sistema_obj = cp
                        break
                    
                    # =========================================================================
            # 📊 VISTA PREVIA INTERACTIVA DE DESCUENTOS (TABLA DE CONTROL DE PRECIOS)
            # =========================================================================
            pct_preview = 0
            is_fidelidad = st.session_state.get('chk_aplicar_cupon_fidelidad_auto', False)
            cupon_obj = st.session_state.get('aplicar_cupon_sistema_obj')
            
            if is_fidelidad:
                pct_preview = 10
            elif cupon_obj is not None:
                pct_preview = int(cupon_obj.get('porcentaje_descuento', 0))
                
            if pct_preview > 0 and len(st.session_state.carrito_caja) > 0:
                st.markdown("##### 📊 Desglose de Descuentos en Carrito")
                preview_rows = []
                for item in st.session_state.carrito_caja:
                    sub_original = float(item.get('subtotal', 0.0))
                    applies = True
                    
                    if cupon_obj is not None:
                        applies = evaluar_restricciones_libro(item, cupon_obj)
                        
                    sub_final = sub_original * (1 - (pct_preview / 100)) if applies else sub_original
                    descuento_monto = sub_original - sub_final
                    
                    status_badge = "✅ Aplica" if applies else "❌ No aplica"
                    
                    preview_rows.append({
                        "Libro": item['titulo'].upper(),
                        "Cantidad": item['cantidad'],
                        "Precio Normal": f"${sub_original:,.0f}",
                        "Descuento": f"-${descuento_monto:,.0f}" if applies else "$0",
                        "Estado": status_badge,
                        "Precio Final": f"${sub_final:,.0f}"
                    })
                
                df_preview = pd.DataFrame(preview_rows)
                st.dataframe(
                    df_preview,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Estado": st.column_config.TextColumn("Estado", width="small"),
                        "Precio Normal": st.column_config.TextColumn("Precio Normal"),
                        "Precio Final": st.column_config.TextColumn("Precio Final")
                    }
                )

        st.markdown("---")
        
        
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
        
                # =========================================================================
        # 💳 RE-CÁLCULO FINANCIERO TRANSACCIONAL SEGÚN RESTRICCIONES
        # =========================================================================
        porcentaje_descuento_aplicar = 0
        if st.session_state.get('chk_aplicar_cupon_fidelidad_auto', False):
            porcentaje_descuento_aplicar = 10
        elif st.session_state.get('aplicar_cupon_sistema_obj') is not None:
            porcentaje_descuento_aplicar = int(st.session_state.aplicar_cupon_sistema_obj.get('porcentaje_descuento', 0))
            
        subtotal_con_descuento = 0.0
        
        for item in st.session_state.carrito_caja:
            item_subtotal = float(item.get('subtotal', 0.0))
            if porcentaje_descuento_aplicar > 0:
                # Fidelidad del 10% aplica a todo el carrito sin restricciones
                if st.session_state.get('chk_aplicar_cupon_fidelidad_auto', False):
                    subtotal_con_descuento += item_subtotal * (1 - (porcentaje_descuento_aplicar / 100))
                # Cupones de sistema evalúan restricciones de catálogo
                elif st.session_state.get('aplicar_cupon_sistema_obj') is not None:
                    if evaluar_restricciones_libro(item, st.session_state.aplicar_cupon_sistema_obj):
                        subtotal_con_descuento += item_subtotal * (1 - (porcentaje_descuento_aplicar / 100))
                    else:
                        subtotal_con_descuento += item_subtotal
            else:
                subtotal_con_descuento += item_subtotal

        if es_por_pagar:
            tipo_cobro_envio = "envio por pagar"
            monto_final = subtotal_con_descuento
        else:
            if modo_envio in ["Retiro en tienda", "Añadir a compra anterior", "Añadir a caja de suscripción"]:
                tipo_cobro_envio = "retiro"
                monto_final = subtotal_con_descuento
            else:
                tipo_cobro_envio = "envio pagado"
                monto_final = subtotal_con_descuento + valor_envio
        
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
                        st.cache_data.clear()
                        time.sleep(2)
                        st.session_state.carrito_caja = []
                        st.rerun()
                    else: 
                        st.error(f"Error: {err}")
                    
    with tab_historial:
        st.markdown("### 📜 Historial de Ventas")
        
        with st.expander("💡 **¿Cómo se calculan las finanzas en este panel?**", expanded=False):
            st.info("""
            * **Ventas Totales (Monto Final):** Suma del precio cobrado por cada libro más el **Costo de Envío** (si aplica).
            * **Costos Totales (Costo Venta):** Suma del costo de adquisición registrado en catálogo para cada libro vendido.
            * **Utilidad Estimada:** Se obtiene restando `(Ventas Totales - Costo de Envío) - Costos Totales` (es decir, la utilidad real que te dejan los libros sin contar el despacho).
            """)
        
        df_ventas = df_ventas_global.copy()
        
        if df_ventas.empty: 
            st.info("Aún no hay ventas registradas.")
        else:
            # ---> INICIO DE EXTRACCIÓN DE SUGERENCIAS DESDE EL JSON CRUDO DE VENTAS <---
            titulos_sugeridos = set()
            col_target = 'libros_vendidos_raw' if 'libros_vendidos_raw' in df_ventas.columns else 'libros_vendidos'
            for val in df_ventas[col_target].dropna():
                val_str = str(val).strip()
                if val_str.startswith('['):
                    try:
                        items_json = json.loads(val_str)
                        for item in items_json:
                            if isinstance(item, dict) and 'titulo' in item:
                                t = str(item['titulo']).strip()
                                if t:
                                    titulos_sugeridos.add(t.upper())
                    except Exception:
                        pass
                else:
                    items_str = val_str.split(" | ")
                    for item_str in items_str:
                        partes = item_str.split(" x ", 1)
                        if len(partes) == 2:
                            t = partes[1].strip()
                        else:
                            t = item_str.strip()
                        if t:
                            titulos_sugeridos.add(t.upper())
            listado_titulos_sugeridos = sorted(list(titulos_sugeridos))
            
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
                
                
                col_search, col_cost = st.columns([3, 1])
                
                busqueda_titulo = col_search.selectbox(
                    "🔍 Buscar por Título de Libro en el Historial (Sugerencias):",
                    options=listado_titulos_sugeridos,
                    index=None,
                    placeholder="Escribe o selecciona un título de libro vendido...",
                    key="buscar_titulo_historial"
                )
                                
                if busqueda_titulo:
                    if col_search.button("🗑️ Limpiar búsqueda de título", key="btn_limpiar_busqueda_titulo", use_container_width=True):
                        if "buscar_titulo_historial" in st.session_state:
                            del st.session_state["buscar_titulo_historial"] # Destrucción limpia del estado
                        st.rerun() 
                        
                solo_costo_cero = col_cost.checkbox("⚠️ Ventas sin costo asignado ($0)", value=False)
                
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
            
            # Filtro por búsqueda de título (Lupa)
            if busqueda_titulo.strip():
                df_filtrado_general = df_filtrado_general[
                    df_filtrado_general['libros_vendidos'].str.contains(busqueda_titulo, case=False, na=False) |
                    df_filtrado_general['libros_vendidos_raw'].str.contains(busqueda_titulo, case=False, na=False)
                ]
            
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
                "monto_final": st.column_config.NumberColumn("Monto Final", format="$%.0f", disabled=False), 
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
                
                    if "buscar_titulo_historial" in st.session_state:
                        del st.session_state["buscar_titulo_historial"]  # Se destruye la clave para no persistir basura
                    st.rerun()     

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
            nuevo_limite_usos = col_nc3.number_input("Límite de usos totales:", min_value=1, value=1000, step=1)
            
            col_nc4, col_nc5, col_nc6 = st.columns(3)
            nuevo_fecha_inicio = col_nc4.date_input("Fecha Inicio (Vigencia):", value=None)
            nuevo_fecha_fin = col_nc5.date_input("Fecha Fin (Expiración):", value=None)
            
            opciones_cli = sorted(df_clientes['nombre'].unique().tolist()) if not df_clientes.empty else []
            sel_clientes_excl = col_nc6.multiselect(
                "Cupón exclusivo para (dejar vacío para público):",
                options=opciones_cli,
                placeholder="Selecciona una o más clientas..."
            )
            
            st.markdown("🎯 **Restricciones del Cupón (Ventas Aplicables)**")
            col_rest1, col_rest2, col_rest3 = st.columns(3)
            
            # 1. Obtener listas únicas del catálogo actual
            autores_disponibles, editoriales_disponibles = cargar_listas_desplegables_caja()
            
            sel_editoriales_rest = col_rest1.multiselect(
                "Restringir a Editoriales específicas (vacío = Todas):",
                options=editoriales_disponibles,
                placeholder="Elige editoriales..."
            )
            sel_autores_rest = col_rest2.multiselect(
                "Restringir a Autores específicos (vacío = Todos):",
                options=autores_disponibles,
                placeholder="Elige autores..."
            )
            sel_enc_rest = col_rest3.selectbox(
                "Tipo de Encuadernación permitida:",
                options=["Todos", "Solo Tapa Blanda", "Solo Tapa Dura", "Excluir Tapa Dura"],
                index=0
            )
            
            btn_crear_disabled = not nuevo_codigo or nuevo_porcentaje <= 0
            if st.button("💾 Crear y Registrar Cupón en Supabase", type="primary", use_container_width=True, disabled=btn_crear_disabled):
                conn = get_db_connection()
                cli_excl_ids = []
                if sel_clientes_excl and not df_clientes.empty:
                    for name in sel_clientes_excl:
                        match_cli = df_clientes[df_clientes['nombre'] == name]
                        if not match_cli.empty:
                            cli_excl_ids.append(int(match_cli.iloc[0]['cliente_id']))
                
                cliente_id_exclusivo_str = json.dumps(cli_excl_ids) if cli_excl_ids else None
                rest_editorial_str = json.dumps(sel_editoriales_rest) if sel_editoriales_rest else None
                rest_autor_str = json.dumps(sel_autores_rest) if sel_autores_rest else None
                        
                datos_cupon_insert = {
                    "codigo": nuevo_codigo,
                    "porcentaje_descuento": int(nuevo_porcentaje),
                    "fecha_inicio": nuevo_fecha_inicio.isoformat() if nuevo_fecha_inicio else None,
                    "fecha_fin": nuevo_fecha_fin.isoformat() if nuevo_fecha_fin else None,
                    "cliente_id_exclusivo": cliente_id_exclusivo_str,
                    "limite_usos": int(nuevo_limite_usos),
                    "usos_actuales": 0,
                    "activo": True,
                    "restriccion_editorial": rest_editorial_str,
                    "restriccion_autor": rest_autor_str,
                    "restriccion_encuadernacion": sel_enc_rest
                }
                
                try:
                    conn.table("cupones").insert(datos_cupon_insert).execute()
                    st.success(f"🎉 ¡Cupón '{nuevo_codigo}' creado correctamente!")
                    st.cache_data.clear()
                    time.sleep(1.5)
                    st.rerun()
                except Exception as ex_insert_cup:
                    st.error(f"Error al registrar cupón: {ex_insert_cup}")


            if not df_cupones.empty:
                st.markdown("#### 📋 Listado y Estadísticas de Cupones Activos")
                
                df_cupones_viz = df_cupones.copy()
                
                # Mapeo dinámico fila por fila para recolectar nombres de clientes exclusivos
                excl_names_list = []
                for _, cp in df_cupones_viz.iterrows():
                    excl_raw = cp.get('cliente_id_exclusivo')
                    names = []
                    if pd.notna(excl_raw) and excl_raw is not None and str(excl_raw).strip() != "" and str(excl_raw).lower() not in ["none", "nan", "null", "[]"]:
                        if not df_clientes.empty:
                            for _, cl in df_clientes.iterrows():
                                if check_exclusivity(cl['cliente_id'], excl_raw):
                                    names.append(cl['nombre'].upper())
                    
                    excl_names_list.append(", ".join(names) if names else "Público / Todos")
                
                df_cupones_viz['Exclusivo para'] = excl_names_list
                    
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

                
                st.markdown("##### ⚙️ Acciones Rápidas / Editar / Eliminar")
                sel_cup_acc = st.selectbox("Selecciona un cupón para gestionar:", options=[""] + df_cupones['codigo'].tolist(), index=0)
                
                if sel_cup_acc:
                    row_cup_acc = df_cupones[df_cupones['codigo'] == sel_cup_acc].iloc[0]
                    
                    # Recuperar nombres de clientes actualmente asociados
                    excl_raw = row_cup_acc.get('cliente_id_exclusivo')
                    current_names = []
                    if excl_raw and not df_clientes.empty:
                        for _, cl in df_clientes.iterrows():
                            if check_exclusivity(cl['cliente_id'], excl_raw):
                                current_names.append(cl['nombre'])
                    
                    with st.form("form_editar_cupon"):
                        col_ed1, col_ed2, col_ed3 = st.columns(3)
                        ed_porcentaje = col_ed1.number_input("Porcentaje Descuento (%):", min_value=1, max_value=100, value=int(row_cup_acc['porcentaje_descuento']))
                        ed_limite = col_ed2.number_input("Límite de Usos Totales:", min_value=1, value=int(row_cup_acc.get('limite_usos', 1)))
                        ed_activo = col_ed3.toggle("Cupón Activo", value=bool(row_cup_acc.get('activo', True)))
                        
                        col_ed4, col_ed5, col_ed6 = st.columns(3)
                        def safe_parse_date(d_val):
                            if pd.isna(d_val) or not d_val: return None
                            return pd.to_datetime(d_val).date()
                            
                        ed_fecha_inicio = col_ed4.date_input("Fecha Inicio:", value=safe_parse_date(row_cup_acc.get('fecha_inicio')))
                        ed_fecha_fin = col_ed5.date_input("Fecha Fin:", value=safe_parse_date(row_cup_acc.get('fecha_fin')))
                        
                        opciones_cli_ed = sorted(df_clientes['nombre'].unique().tolist()) if not df_clientes.empty else []
                        ed_clientes_excl = col_ed6.multiselect(
                            "Exclusivo para:",
                            options=opciones_cli_ed,
                            default=current_names
                        )
                        
                        col_btn_ed1, col_btn_ed2 = st.columns(2)
                        btn_guardar_ed = col_btn_ed1.form_submit_button("💾 Guardar Cambios", use_container_width=True)
                        btn_eliminar_ed = col_btn_ed2.form_submit_button("🗑️ Eliminar Cupón Permanentemente", use_container_width=True)
                        
                        if btn_guardar_ed:
                            conn = get_db_connection()
                            cli_excl_ids = []
                            if ed_clientes_excl and not df_clientes.empty:
                                for name in ed_clientes_excl:
                                    match_cli = df_clientes[df_clientes['nombre'] == name]
                                    if not match_cli.empty:
                                        cli_excl_ids.append(int(match_cli.iloc[0]['cliente_id']))
                                        
                            cliente_id_exclusivo_str = json.dumps(cli_excl_ids) if cli_excl_ids else None
                            
                            datos_update = {
                                "porcentaje_descuento": int(ed_porcentaje),
                                "limite_usos": int(ed_limite),
                                "activo": ed_activo,
                                "fecha_inicio": ed_fecha_inicio.isoformat() if ed_fecha_inicio else None,
                                "fecha_fin": ed_fecha_fin.isoformat() if ed_fecha_fin else None,
                                "cliente_id_exclusivo": cliente_id_exclusivo_str
                            }
                            
                            try:
                                conn.table("cupones").update(datos_update).eq("cupon_id", int(row_cup_acc['cupon_id'])).execute()
                                st.success(f"🎉 ¡Cupón '{sel_cup_acc}' editado con éxito!")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            except Exception as e_up:
                                st.error(f"Error al editar: {e_up}")
                                
                        if btn_eliminar_ed:
                            conn = get_db_connection()
                            try:
                                conn.table("cupones").delete().eq("cupon_id", int(row_cup_acc['cupon_id'])).execute()
                                st.success(f"🗑️ ¡Cupón '{sel_cup_acc}' eliminado de forma permanente!")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            except Exception as e_del:
                                st.error(f"Error al eliminar: {e_del}")

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
                                df_cli_v['fecha_dt'] = unificar_formatos_fecha(df_cli_v['fecha_venta'])
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