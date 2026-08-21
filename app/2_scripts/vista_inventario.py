import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error
import time
from datetime import datetime, timedelta

def obtener_unicos(df, columna):
    """Devuelve una lista ordenada de valores únicos de una columna del DataFrame."""
    return sorted(df[columna].dropna().astype(str).unique())

@st.cache_data(ttl=300)
def cargar_datos_completos():
    """
    Carga todos los datos de la tabla 'libros' desde Supabase en bloques de 1.000,
    calculando el rango dinámicamente según la fecha de inicio, y calcula dinámicamente 
    si los libros tienen un descuento activo de forma segura.
    """
    conn = get_db_connection()
    
    try:
        # 1. Calculamos meses transcurridos desde Octubre 2025 hasta hoy
        fecha_inicio_proyecto = datetime(2025, 10, 1)
        hoy_dt = datetime.now()
        meses_transcurridos = (hoy_dt.year - fecha_inicio_proyecto.year) * 12 + (hoy_dt.month - fecha_inicio_proyecto.month) + 1
        
        # Límite dinámico (100 libros nuevos/mes, piso mínimo de 1.000)
        limite_dinamico_libros = max(1000, meses_transcurridos * 100)
        
        # 2. 🚀 Bucle acotado de paginación para traer todo el catálogo sin riesgo de truncado
        all_data = []
        chunk_size = 1000
        for bloque in range(3): # Soporta hasta 3.000 títulos en catálogo (Varios años de crecimiento)
            start = bloque * chunk_size
            end = start + chunk_size - 1
            response = conn.table("libros").select("*").order("libro_id", desc=True).range(start, end).execute()
            if response.data:
                all_data.extend(response.data)
                if len(response.data) < chunk_size:
                    break
            else:
                break
        
        if not all_data:
            return pd.DataFrame()
            
        # Creamos el DataFrame definitivo con el 100% de los libros descargados
        df = pd.DataFrame(all_data)
    
        # 🌟 CORRECCIÓN: Procesamos directamente el DataFrame unificado (Sin sobreescrituras destructivas)
        columnas_texto = ['titulo', 'autor', 'editorial', 'genero', 'encuadernacion']
        for col in columnas_texto:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
                
        if 'precio' in df.columns:
            df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0.0)
        
        if 'precio_original' in df.columns:
            df['precio_original'] = pd.to_numeric(df['precio_original'], errors='coerce')
            df['precio_original'] = df['precio_original'].fillna(df['precio'])
        else:
            df['precio_original'] = df['precio']

        if 'stock' in df.columns:
            df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0).astype(int)
        if 'costo' in df.columns:
            df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0.0)
        if 'apto_cajita' in df.columns:
            df['apto_cajita'] = df['apto_cajita'].fillna(True).astype(bool)
        if 'destacado' in df.columns:
            df['destacado'] = df['destacado'].fillna(False).astype(bool)
        else:
            df['destacado'] = False
            
        if 'visible_catalogo' in df.columns:
            df['visible_catalogo'] = df['visible_catalogo'].fillna(True).astype(bool)
        else:
            df['visible_catalogo'] = True
            
        # LÓGICA DE DESCUENTOS SEGURA Y POR FECHA
        hoy = pd.Timestamp(datetime.now().date())
        df['Dcto %'] = 0.0
        
        # Validamos si existen las columnas de fecha en Supabase y comparamos con el día de hoy
        if 'descuento_inicio' in df.columns and 'descuento_fin' in df.columns:
            df['f_ini_dt'] = pd.to_datetime(df['descuento_inicio'], errors='coerce') 
            df['f_fin_dt'] = pd.to_datetime(df['descuento_fin'], errors='coerce')
            
            mask_dcto = (
                (df['precio_original'] > df['precio']) & 
                (df['precio_original'] > 0) & 
                ((df['f_ini_dt'].isna()) | (df['f_ini_dt'] <= hoy)) & 
                ((df['f_fin_dt'].isna()) | (df['f_fin_dt'] >= hoy))
            )
        else:
            mask_dcto = (df['precio_original'] > df['precio']) & (df['precio_original'] > 0)
        
        calculo_dcto = (((df.loc[mask_dcto, 'precio_original'] - df.loc[mask_dcto, 'precio']) / df.loc[mask_dcto, 'precio_original']) * 100)
        df.loc[mask_dcto, 'Dcto %'] = calculo_dcto
        df['Dcto %'] = df['Dcto %'].fillna(0.0).round(0).astype(int)
        
        df['Oferta'] = df['Dcto %'].apply(lambda x: f"🔥 {x}% OFF" if x > 0 else "Estándar")
        
        return df
        
    except Exception as e:
        log_error("vista_inventario", "cargar_datos_completos", e, st.session_state.get('email_usuario', 'Desconocido'))
        return pd.DataFrame()


def actualizar_destacados_batch(df_con_cambios):
    """
    Actualiza el estado 'destacado' de los libros en la base de datos.
    Recibe un DataFrame con las columnas 'libro_id' y 'destacado'.
    """
    conn = get_db_connection()
    updates_count = 0
    
    # Prepara los datos en el formato que Supabase espera para un 'upsert'
    # Esto es más eficiente que hacer un bucle de updates.
    datos_para_actualizar = df_con_cambios[['libro_id', 'destacado']].to_dict(orient='records')
    
    if not datos_para_actualizar:
        return 0

    try:
        # 'upsert' intentará actualizar. Si la fila no existe, la insertaría (aunque aquí siempre existirá)
        # on_conflict='libro_id' le dice que la columna 'libro_id' es la clave para encontrar el registro.
        conn.table("libros").upsert(datos_para_actualizar, on_conflict='libro_id').execute()
        updates_count = len(datos_para_actualizar)
        cargar_datos_completos.clear() # Limpiamos la caché para que se vean los cambios
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_inventario",
            funcion="actualizar_destacados_batch",
            error=f"Error masivo al actualizar destacados. Detalle: {e}",
            email_usuario=email_usuario
        )
        st.error(f"Ocurrió un error al guardar: {e}")
        return 0
        
    return updates_count

def crear_nuevo_libro(titulo, autor, editorial, genero, encuadernacion, stock, precio, costo):
    conn = get_db_connection()
    
    titulo_limpio = limpiar_texto_para_busqueda(titulo)
    autor_limpio = limpiar_texto_para_busqueda(autor)

    try:
        res = conn.table("libros").select("libro_id").eq("titulo", titulo_limpio).eq("autor", autor_limpio).execute()
        if res.data:
            return False, f"El libro '{titulo_limpio}' del autor '{autor_limpio}' ya existe en el catálogo."
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_inventario",
            funcion="crear_nuevo_libro (verificación duplicado)",
            error=f"Fallo al verificar duplicado para '{titulo_limpio}'. Detalle: {e}",
            email_usuario=email_usuario
        )
        return False, f"Error al verificar duplicados: {str(e)}"

    datos = {
        "titulo": titulo_limpio, "autor": autor_limpio,
        "editorial": limpiar_texto_para_busqueda(editorial), "genero": limpiar_texto_para_busqueda(genero),
        "encuadernacion": limpiar_texto_para_busqueda(encuadernacion), "stock": stock,
        "precio": precio, "precio_original": precio, "costo": costo
    }
    try:
        conn.table("libros").insert(datos).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        log_error(
            vista="vista_inventario",
            funcion="crear_nuevo_libro (inserción)",
            error=f"Fallo al insertar el libro '{titulo_limpio}'. Detalle: {e}",
            email_usuario=email_usuario
        )
        return False, f"Error al insertar en la base de datos: {str(e)}"

def actualizar_un_libro(libro_id, datos):
    conn = get_db_connection()
    try:
        conn.table("libros").update(datos).eq("libro_id", libro_id).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        error_detalle = (
            f"Fallo al actualizar el libro ID {libro_id}. "
            f"Datos intentados: {str(datos)}. Detalle: {e}"
        )
        
        log_error(
            vista="vista_inventario",
            funcion="actualizar_un_libro",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

def actualizar_libros_batch(df_original, df_editado):
    if df_original.empty or df_editado.empty: return 0
    
    if 'libro_id' not in df_original.columns or 'libro_id' not in df_editado.columns:
        return 0
        
    df_original_comp = df_original.set_index('libro_id')
    df_editado_comp = df_editado.set_index('libro_id')
    
    cols_comunes = df_original_comp.columns.intersection(df_editado_comp.columns)
    diff_mask = df_original_comp[cols_comunes].ne(df_editado_comp[cols_comunes]).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates_count = 0
    
    for libro_id, row in filas_cambiadas.iterrows():
        try:
            datos = {}
            if 'autor' in row: datos['autor'] = limpiar_texto_para_busqueda(str(row['autor']))
            if 'editorial' in row: datos['editorial'] = limpiar_texto_para_busqueda(str(row['editorial']))
            if 'genero' in row: datos['genero'] = limpiar_texto_para_busqueda(str(row['genero']))
            if 'encuadernacion' in row: datos['encuadernacion'] = limpiar_texto_para_busqueda(str(row['encuadernacion']))
            if 'stock' in row: datos['stock'] = int(row['stock'])
            if 'costo' in row: datos['costo'] = float(row.get('costo', 0))
            if 'titulo' in row: datos['titulo'] = limpiar_texto_para_busqueda(str(row['titulo']))
            if 'apto_cajita' in row: datos['apto_cajita'] = bool(row['apto_cajita'])
            if 'destacado' in row: datos['destacado'] = bool(row['destacado'])
            if 'visible_catalogo' in row: datos['visible_catalogo'] = bool(row['visible_catalogo'])
            
            # 🔴 LÓGICA DE RECALCULO DE PRECIOS AUTOMÁTICA
            # Si cambiaron el precio_original, recalculamos el precio de oferta (si lo tenía)
            if 'precio_original' in row and pd.notna(row['precio_original']):
                nuevo_precio_orig = float(row['precio_original'])
                datos['precio_original'] = nuevo_precio_orig
                
                # Rescatamos el porcentaje de descuento actual desde el df original
                porcentaje_dcto_actual = float(df_original_comp.loc[libro_id].get('Dcto %', 0))
                
                if porcentaje_dcto_actual > 0:
                    # Aplica el mismo % de descuento sobre el nuevo precio original
                    factor = 1.0 - (porcentaje_dcto_actual / 100.0)
                    datos['precio'] = round(nuevo_precio_orig * factor, 0)
                else:
                    # Si no tenía descuento, igualamos ambos
                    datos['precio'] = nuevo_precio_orig
            
            # Si el usuario modificó manualmente la columna "precio" en lugar de "precio_original"
            # (sobreescribe la regla anterior para darte libertad absoluta)
            if 'precio' in row and pd.notna(row['precio']):
                if 'precio' not in datos or datos['precio'] != float(row['precio']):
                    datos['precio'] = float(row['precio'])
                
            if datos:
                conn.table("libros").update(datos).eq("libro_id", libro_id).execute()
                updates_count += 1
        except Exception as e:
            
            email_usuario = st.session_state.get('email_usuario', 'Desconocido')
            log_error(
                vista="vista_inventario",
                funcion="actualizar_libros_batch",
                error=f"Error actualizando libro {libro_id}. Detalle: {e}",
                email_usuario=email_usuario
            )
            
            print(f"Error actualizando libro {libro_id}: {e}")
            continue
            
    if updates_count > 0:
        cargar_datos_completos.clear()
        
    return updates_count

def eliminar_libro(libro_id):
    conn = get_db_connection()
    try:
        conn.table("libros").delete().eq("libro_id", libro_id).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        error_detalle = (
            f"Fallo al intentar ELIMINAR el libro ID {libro_id}. Detalle: {e}"
        )
        
        log_error(
            vista="vista_inventario",
            funcion="eliminar_libro",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

def aplicar_descuento_masivo(lista_ids, porcentaje, fecha_inicio=None, fecha_fin=None):
    if not lista_ids: return False, "No hay libros seleccionados para aplicar descuento."
    conn = get_db_connection()
    factor = 1.0 - (porcentaje / 100.0)
    try:
        response = conn.table("libros").select("libro_id, precio, precio_original").in_("libro_id", lista_ids).execute()
        if not response.data:
            return False, "No se encontraron los registros en la base de datos."

        actualizados = 0
        for row in response.data:
            precio_base = row.get("precio_original")
            if precio_base is None or float(precio_base) == 0:
                precio_base = row.get("precio", 0.0)
                conn.table("libros").update({"precio_original": precio_base}).eq("libro_id", row["libro_id"]).execute()

            precio_base = float(precio_base)
            nuevo_precio = round(precio_base * factor, 0)
            
            datos_update = {"precio": nuevo_precio}
            if fecha_inicio:
                datos_update["descuento_inicio"] = fecha_inicio.strftime("%Y-%m-%d")
            if fecha_fin:
                datos_update["descuento_fin"] = fecha_fin.strftime("%Y-%m-%d")
            
            conn.table("libros").update(datos_update).eq("libro_id", row["libro_id"]).execute()
            actualizados += 1
            
        cargar_datos_completos.clear()
        return True, f"Se actualizó el precio de {actualizados} libros con un {porcentaje}% de descuento."
    except Exception as e:
        email_usuario = st.session_state.get('email_usuario', 'Desconocido')
        
        error_detalle = (
            f"Fallo en descuento masivo del {porcentaje}%. "
            f"Error en el bucle de actualización. Detalle: {e}"
        )
        
        log_error(
            vista="vista_inventario",
            funcion="aplicar_descuento_masivo",
            error=error_detalle,
            email_usuario=email_usuario
        )
        return False, str(e)

def actualizar_visibilidad_batch(df_con_cambios):
    """
    Actualiza la visibilidad en catálogo ('visible_catalogo') de los libros en masa.
    """
    conn = get_db_connection()
    datos_para_actualizar = df_con_cambios[['libro_id', 'visible_catalogo']].to_dict(orient='records')
    if not datos_para_actualizar: return 0
    try:
        conn.table("libros").upsert(datos_para_actualizar, on_conflict='libro_id').execute()
        cargar_datos_completos.clear()
        return len(datos_para_actualizar)
    except Exception as e:
        log_error("vista_inventario", "actualizar_visibilidad_batch", f"Error: {e}", st.session_state.get('email_usuario', 'Desconocido'))
        st.error(f"Error al guardar visibilidad: {e}")
        return 0

def mostrar_inventario():
    if 'inventario_limit_view' not in st.session_state:
        st.session_state.inventario_limit_view = 100

    col_inv1, col_inv2 = st.columns([3, 1])
    with col_inv1:
        st.title("📦 Gestión de Inventario")
    with col_inv2:
        if st.button("🔄 Refrescar Datos", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.toast("✅ ¡Datos actualizados! La aplicación ha sido refrescada.", icon="🔄")
            time.sleep(1) 
            st.rerun()
            
    df_inventario = cargar_datos_completos()
    
    with st.expander("🔍 Buscador y Filtros", expanded=False):
        busqueda_titulo = st.text_input("Buscar por Título:", placeholder="Ej: El Señor de los Anillos")
        
        col_f1, col_f2 = st.columns(2)
        autores_seleccionados = col_f1.multiselect("Autor(es):", obtener_unicos(df_inventario, 'autor'))
        editoriales_seleccionadas = col_f2.multiselect("Editorial(es):", obtener_unicos(df_inventario, 'editorial'))
        
        col_f3, col_f4 = st.columns(2)
        generos_seleccionados = col_f3.multiselect("Género(s):", obtener_unicos(df_inventario, 'genero'))
        encuadernaciones_seleccionadas = col_f4.multiselect("Encuadernación:", obtener_unicos(df_inventario, 'encuadernacion'))

        st.markdown("---")
        st.markdown("**Filtros Numéricos**")
        col_f5, col_f6 = st.columns(2)
        
        min_p = float(df_inventario['precio'].min()) if not df_inventario.empty else 0.0
        max_p = float(df_inventario['precio'].max()) if not df_inventario.empty else 1.0
        if min_p >= max_p: 
            max_p = min_p + 1.0
        rango_precio = col_f5.slider("Rango de Precio ($):", min_value=min_p, max_value=max_p, value=(min_p, max_p))

        min_s_db = int(df_inventario['stock'].min()) if not df_inventario.empty else 0
        min_s_slider = max(0, min_s_db)
        
        max_s = int(df_inventario['stock'].max()) if not df_inventario.empty else 1
        if min_s_slider >= max_s: 
            max_s = min_s_slider + 1
        rango_stock = col_f6.slider("Rango de Stock:", min_value=min_s_slider, max_value=max_s, value=(min_s_slider, max_s))

        st.markdown("---")
        col_chk1, col_chk2 = st.columns(2)
        solo_descuentos = col_chk1.checkbox("🏷️ Mostrar solo libros con descuento activo", value=False)
        solo_con_stock = col_chk2.checkbox("📦 Mostrar solo libros con stock (> 0)", value=False)
        solo_aptos_cajita = st.checkbox("🎁 Mostrar solo libros aptos para cajitas", value=False)

    df_filtrado = df_inventario.copy()

    # Búsqueda por título con normalización
    if busqueda_titulo: 
        busqueda_limpia = limpiar_texto_para_busqueda(busqueda_titulo)
        df_filtrado = df_filtrado[
            df_filtrado['titulo'].apply(limpiar_texto_para_busqueda).str.contains(busqueda_limpia, case=False, na=False)
        ]

    if autores_seleccionados: 
        df_filtrado = df_filtrado[df_filtrado['autor'].isin(autores_seleccionados)]
    if editoriales_seleccionadas: 
        df_filtrado = df_filtrado[df_filtrado['editorial'].isin(editoriales_seleccionadas)]
    if generos_seleccionados: 
        df_filtrado = df_filtrado[df_filtrado['genero'].isin(generos_seleccionados)]
    if encuadernaciones_seleccionadas: 
        df_filtrado = df_filtrado[df_filtrado['encuadernacion'].isin(encuadernaciones_seleccionadas)]
    
    # Aplicación de rangos con índices explícitos [0] y [1]
    if not df_filtrado.empty:
        df_filtrado = df_filtrado[df_filtrado['precio'].between(rango_precio[0], rango_precio[1])]
        df_filtrado = df_filtrado[df_filtrado['stock'].between(rango_stock[0], rango_stock[1])]
        
    if solo_descuentos and not df_filtrado.empty:
        df_filtrado = df_filtrado[df_filtrado['Dcto %'] > 0]
    if solo_con_stock and not df_filtrado.empty:
        df_filtrado = df_filtrado[df_filtrado['stock'] > 0]
        
    if solo_aptos_cajita and not df_filtrado.empty:
        if 'apto_cajita' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['apto_cajita'] == True]

    # Contadores de Inventario dinámicos en la cabecera
    st.markdown("### 📊 Métricas del Stock")
    
    st.info("""
    ℹ️ **¿Cómo se calculan los indicadores de este panel?**
    * **Libros Distintos:** Cantidad de títulos únicos registrados bajo la selección y filtros activos actuales.
    * **Unidades en Stock:** Suma total de ejemplares físicos disponibles en el inventario para todos los libros listados.
    * **Valor de Venta Estimado:** Representa el ingreso total potencial de los ejemplares físicos si se liquidaran hoy al público, calculado bajo la fórmula:
    $$\\text{Valor de Venta Estimado} = \\sum (\\text{Stock de cada libro} \\times \\text{Precio de venta actual})$$
    *(Nota: Si un libro tiene una oferta vigente por rango de fechas, este cálculo asume automáticamente su precio rebajado).*
    """)
    
    m1, m2, m3 = st.columns(3)
    total_titulos_filtrados = len(df_filtrado)
    total_stock_filtrado = df_filtrado['stock'].sum() if 'stock' in df_filtrado.columns else 0
    valor_inventario_filtrado = (df_filtrado['stock'] * df_filtrado['precio']).sum() if ('stock' in df_filtrado.columns and 'precio' in df_filtrado.columns) else 0
    
    m1.metric("Libros Distintos", f"{total_titulos_filtrados:,}")
    m2.metric("Unidades en Stock", f"{total_stock_filtrado:,} uds.")
    m3.metric("Valor del Inventario (P. Venta)", f"${valor_inventario_filtrado:,.0f}")
    st.markdown("---")
    
    # Tabs de navegación
    tab_catalogo, tab_editar, tab_crear, tab_desc, tab_eliminar = st.tabs([
        "📋 Catálogo", "✏️ Editar", "➕ Crear", "📉 Descuentos", "🗑️ Eliminar"
    ])


    with tab_catalogo:
        st.markdown(f"### 📋 Catálogo ({len(df_filtrado)} libros)")
        st.caption("💡 Tip: Toca el título de cualquier columna para ordenar los datos ↕️")
        
        columnas_fijas = ['libro_id', 'titulo', 'stock']
        columnas_opcionales_disponibles = [col for col in df_inventario.columns if col not in columnas_fijas + ['created_at', 'Dcto %']]
        
        columnas_por_defecto = ['autor', 'precio', 'precio_original', 'Oferta']
        favoritos_disponibles = [c for c in columnas_por_defecto if c in columnas_opcionales_disponibles] # <-- FILTRO DE SEGURIDAD
        
        columnas_extra_seleccionadas = st.multiselect(
            "Añadir/Quitar columnas de la tabla:", 
            options=columnas_opcionales_disponibles, 
            default=favoritos_disponibles # <-- Ahora este parámetro es 100% inmune
        )
        
        columnas_a_mostrar = columnas_fijas + columnas_extra_seleccionadas
        
        def estilizar_catalogo(data):
            # Creamos un DataFrame vacío para almacenar los estilos CSS
            estilos = pd.DataFrame('', index=data.index, columns=data.columns)

            con_stock = df_filtrado.loc[data.index, 'stock'] > 0

            for col in data.columns:
                estilos.loc[con_stock, col] = 'background-color: #d7edd2; color: #75956f; font-weight: bold'
            return estilos

            
        df_mostrar_tabla = df_filtrado[columnas_a_mostrar]
        
        # Paginación visual en catálogo (Cortar el DataFrame para renderizar solo los más recientes)
        limite_actual = st.session_state.inventario_limit_view
        total_libros_filtrados = len(df_mostrar_tabla)
        
        df_paginado = df_mostrar_tabla.head(limite_actual)
        
        if 'Oferta' in df_paginado.columns:
            df_estilizado = df_paginado.style.apply(estilizar_catalogo, axis=None)
        else:
            df_estilizado = df_paginado

        config_cols_catalogo = {
            "precio": st.column_config.NumberColumn("Precio", format="$%.0f"),
            "precio_original": st.column_config.NumberColumn("Precio Original", format="$%.0f"),
            "costo": st.column_config.NumberColumn("Costo", format="$%.0f")
        }
        
        st.caption(f"Mostrando los **{len(df_paginado)}** libros más recientes de un total de **{total_libros_filtrados}** encontrados.")
        st.dataframe(df_estilizado, hide_index=True, use_container_width=True, column_config=config_cols_catalogo)

        # Botón dinámico para expandir la tabla de 100 en 100
        if total_libros_filtrados > limite_actual:
            col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
            with col_pag2:
                if st.button(f"🔄 Cargar más libros (+100) — Quedan {total_libros_filtrados - limite_actual} por ver", use_container_width=True, key="btn_load_more_inv"):
                    st.session_state.inventario_limit_view += 100
                    st.rerun()
        else:
            # Si se aplicaron filtros y el total es menor al límite, restablecemos el paginador
            st.session_state.inventario_limit_view = 100
    with tab_editar:
        st.markdown("#### ✏️ Modificar Libro")
        modo_edicion = st.radio("Elige la vista de edición:", ["📱 Vista Móvil (Formulario)", "💻 Vista PC (Tabla Editable)"], horizontal=True)
        st.write("")
        
        if modo_edicion == "📱 Vista Móvil (Formulario)":
            
            # 1. Creamos un diccionario que une el ID único con el Título {15: "El Principito"}
            dict_libros = dict(zip(df_filtrado['libro_id'], df_filtrado['titulo']))
            
            # 2. Creamos la lista de opciones usando los IDs (agregando None al principio para que quede vacío por defecto)
            opciones_ids = [None] + list(dict_libros.keys())
            
            # 3. El selectbox usa los IDs, pero MUESTRA los títulos gracias a format_func
            libro_id_a_editar = st.selectbox(
                "Busca y selecciona un libro para editar:", 
                options=opciones_ids,
                format_func=lambda x: "" if x is None else dict_libros[x],
                key="sel_editar_id"
            )
            
            if libro_id_a_editar:
                filas_encontradas = df_filtrado[df_filtrado['libro_id'] == libro_id_a_editar]
                
                if filas_encontradas.empty:
                    st.warning("⚠️ El libro seleccionado ya no está disponible en los filtros actuales. Por favor, refresca la página.")
                else:
                    libro = filas_encontradas.iloc[0]
                    with st.container(border=True):
                        nuevo_titulo = st.text_input("Título:", value=libro['titulo'])
                        
                        # Cargamos opciones y añadimos la opción de crear
                        opciones_autor = ["➕ Escribir nuevo..."] + obtener_unicos(df_inventario, 'autor')
                        opciones_editorial = ["➕ Escribir nueva..."] + obtener_unicos(df_inventario, 'editorial')
                        opciones_genero = ["➕ Escribir nuevo..."] + obtener_unicos(df_inventario, 'genero')
                        opciones_enc = ["➕ Escribir nueva..."] + obtener_unicos(df_inventario, 'encuadernacion')
                        
                        col1, col2 = st.columns(2)
                        
                        # --- AUTOR ---
                        idx_autor = opciones_autor.index(libro['autor']) if libro['autor'] in opciones_autor else 0
                        sel_autor = col1.selectbox("Autor:", opciones_autor, index=idx_autor)
                        if sel_autor == "➕ Escribir nuevo...":
                            nuevo_autor = col1.text_input("Ingresa el nuevo autor:", placeholder="Ej: J.K. Rowling")
                        else:
                            nuevo_autor = sel_autor
                            
                        # --- EDITORIAL ---
                        idx_editorial = opciones_editorial.index(libro['editorial']) if libro['editorial'] in opciones_editorial else 0
                        sel_editorial = col2.selectbox("Editorial:", opciones_editorial, index=idx_editorial)
                        if sel_editorial == "➕ Escribir nueva...":
                            nueva_editorial = col2.text_input("Ingresa la nueva editorial:", placeholder="Ej: Planeta")
                        else:
                            nueva_editorial = sel_editorial
                            
                        col3, col4 = st.columns(2)
                        
                        # --- GÉNERO ---
                        idx_genero = opciones_genero.index(libro['genero']) if libro['genero'] in opciones_genero else 0
                        sel_genero = col3.selectbox("Género:", opciones_genero, index=idx_genero)
                        if sel_genero == "➕ Escribir nuevo...":
                            nuevo_genero = col3.text_input("Ingresa el nuevo género:", placeholder="Ej: Ficción")
                        else:
                            nuevo_genero = sel_genero
                            
                        # --- ENCUADERNACIÓN ---
                        idx_enc = opciones_enc.index(libro['encuadernacion']) if libro['encuadernacion'] in opciones_enc else 0
                        sel_enc = col4.selectbox("Encuadernación:", opciones_enc, index=idx_enc)
                        if sel_enc == "➕ Escribir nueva...":
                            nueva_encuadernacion = col4.text_input("Ingresa la nueva encuadernación:")
                        else:
                            nueva_encuadernacion = sel_enc
                            
                        # --- STOCK Y PRECIOS ---
                        col5, col6, col7 = st.columns(3)
                        nuevo_stock = col5.number_input("Stock:", min_value=0, step=1, value=int(libro['stock']))
                        nuevo_costo = col6.number_input("Costo ($):", min_value=0.0, format="%.0f", value=float(libro.get('costo', 0)))
                        nuevo_precio_original = col7.number_input("Precio Orig. ($):", min_value=0.0, format="%.0f", value=float(libro['precio_original']))
                        
                        st.markdown("📅 **Vigencia del Descuento (Individual)**")
                        col_ed_f1, col_ed_f2 = st.columns(2)
                        f_ini_val = pd.to_datetime(libro.get('descuento_inicio')).date() if pd.notna(libro.get('descuento_inicio')) else datetime.now().date()
                        f_fin_val = pd.to_datetime(libro.get('descuento_fin')).date() if pd.notna(libro.get('descuento_fin')) else datetime.now().date() + timedelta(days=30)
                        nuevo_f_ini = col_ed_f1.date_input("Fecha Inicio:", value=f_ini_val, key="edit_f_ini")
                        nuevo_f_fin = col_ed_f2.date_input("Fecha Fin:", value=f_fin_val, key="edit_f_fin")

                        
                        check_col1, check_col2, check_col3 = st.columns(3)
                        nuevo_apto_cajita = check_col1.checkbox("🎁 Apto Cajitas", value=bool(libro.get('apto_cajita', True)))
                        nuevo_destacado = check_col2.checkbox("⭐ Destacado", value=bool(libro.get('destacado', False)))
                        nuevo_visible = check_col3.checkbox("👁️ Visible en Web", value=bool(libro.get('visible_catalogo', True)))

                        st.write("")
                        
                        if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
                            if not nuevo_autor or not nueva_editorial or not nuevo_titulo:
                                st.error("⚠️ El Título, Autor y Editorial no pueden estar vacíos.")
                            else:
                                datos_actualizados = {
                                        "titulo": limpiar_texto_para_busqueda(nuevo_titulo),
                                        "autor": limpiar_texto_para_busqueda(nuevo_autor), 
                                        "editorial": limpiar_texto_para_busqueda(nueva_editorial), 
                                        "genero": limpiar_texto_para_busqueda(nuevo_genero), 
                                        "encuadernacion": limpiar_texto_para_busqueda(nueva_encuadernacion), 
                                        "stock": nuevo_stock, 
                                        "costo": nuevo_costo, 
                                        "precio_original": nuevo_precio_original,
                                        "descuento_inicio": nuevo_f_ini.strftime("%Y-%m-%d"),
                                        "descuento_fin": nuevo_f_fin.strftime("%Y-%m-%d"),
                                        "apto_cajita": nuevo_apto_cajita,
                                        "destacado": nuevo_destacado,
                                        "visible_catalogo": nuevo_visible
                                    }
                                
                                pct_dcto = float(libro.get('Dcto %', 0))
                                if pct_dcto > 0:
                                    datos_actualizados['precio'] = round(nuevo_precio_original * (1.0 - (pct_dcto / 100.0)), 0)
                                else:
                                    datos_actualizados['precio'] = nuevo_precio_original
                                    
                                exito, error = actualizar_un_libro(int(libro['libro_id']), datos_actualizados)
                                if exito:
                                    st.success("¡Libro actualizado correctamente!")
                                    st.snow()
                                    time.sleep(1.5)
                                    st.rerun()
                                else:
                                    st.error(f"Error: {error}")
        else:
            st.caption(f"Mostrando {len(df_filtrado)} libros. Haz doble clic en las celdas para modificar (estilo Excel).")
            
            columnas_tabla_pc_todas = [
                "libro_id", "titulo", "autor", "editorial", "genero", "encuadernacion", 
                "stock", "costo", "precio", "precio_original", 
                "apto_cajita", "destacado", "visible_catalogo"
            ]
            columnas_base = ["libro_id", "titulo"]
            columnas_opcionales = [c for c in columnas_tabla_pc_todas if c in df_filtrado.columns and c not in columnas_base]
            columnas_a_mostrar = st.multiselect(
                    "👀 Mostrar / Ocultar Columnas en Tabla", 
                    columnas_opcionales, 
                    default=["autor", "stock", "precio", "apto_cajita", "destacado", "visible_catalogo"]
                )
            
            columnas_finales = columnas_base + columnas_a_mostrar
            
            df_mostrar = df_filtrado[columnas_finales].copy().reset_index(drop=True)
            
            st.session_state.df_original_para_editar = df_mostrar
            
            autores_unicos = obtener_unicos(df_inventario, 'autor')
            editoriales_unicas = obtener_unicos(df_inventario, 'editorial')
            generos_unicos = obtener_unicos(df_inventario, 'genero')
            encuadernaciones_unicas = obtener_unicos(df_inventario, 'encuadernacion')
            
            config_columnas = {
                "autor": st.column_config.SelectboxColumn("Autor", options=autores_unicos, required=True),
                "editorial": st.column_config.SelectboxColumn("Editorial", options=editoriales_unicas, required=True),
                "genero": st.column_config.SelectboxColumn("Género", options=generos_unicos),
                "encuadernacion": st.column_config.SelectboxColumn("Encuadernación", options=encuadernaciones_unicas),
                "stock": st.column_config.NumberColumn("Stock", step=1),
                "costo": st.column_config.NumberColumn("Costo ($)", format="%.0f"),
                "precio": st.column_config.NumberColumn("Precio ($)", format="%.0f"),
                "precio_original": st.column_config.NumberColumn("Precio Original ($)", format="%.0f"),
                "apto_cajita": st.column_config.CheckboxColumn("¿Apto Cajita? 🎁", default=True),
                "destacado": st.column_config.CheckboxColumn("¿Destacado? 💫", default=False),
                "visible_catalogo": st.column_config.CheckboxColumn("¿Visible en Web? 👁️", default=False)
            }
            
            disabled_finales = [c for c in ["libro_id"] if c in df_mostrar.columns]
            
            df_editado = st.data_editor(
                df_mostrar, use_container_width=True, hide_index=True, 
                disabled=disabled_finales, column_config=config_columnas
            )
            
            hay_cambios = not df_mostrar.equals(df_editado)
            
            if st.button("💾 Guardar Cambios en Tabla", type="primary", use_container_width=True, disabled=not hay_cambios):
                with st.spinner("Actualizando datos..."):
                    # Mandamos al procesador tanto df_filtrado original (para que lea el Dcto %) como el editado
                    num_actualizados = actualizar_libros_batch(df_filtrado, df_editado)
                    st.success(f"¡Se actualizaron {num_actualizados} libros!")
                    st.snow()
                    time.sleep(1.5)
                    st.rerun()

    with tab_crear:
        with st.form("form_nuevo_libro", clear_on_submit=False):
            val_titulo = st.text_input("Título:", key="n_tit")
            opciones_autor = [""] + obtener_unicos(df_inventario, 'autor')
            val_autor_ex = st.selectbox("Autor (Existente):", options=opciones_autor, key="n_aut_ex")
            val_autor_nu = st.text_input("O escribe un nuevo Autor:", key="n_aut_nu")
            opciones_editorial = [""] + obtener_unicos(df_inventario, 'editorial')
            val_edit_ex = st.selectbox("Editorial (Existente):", options=opciones_editorial, key="n_edi_ex")
            val_edit_nu = st.text_input("O escribe una nueva Editorial:", key="n_edi_nu")
            opciones_genero = [""] + obtener_unicos(df_inventario, 'genero')
            val_gen_ex = st.selectbox("Género (Existente):", options=opciones_genero, key="n_gen_ex")
            val_gen_nu = st.text_input("O escribe un nuevo Género:", key="n_gen_nu")
            opciones_enc = [""] + obtener_unicos(df_inventario, 'encuadernacion')
            val_enc_ex = st.selectbox("Encuadernación (Existente):", options=opciones_enc, key="n_enc_ex")
            val_enc_nu = st.text_input("O escribe una nueva Encuadernación:", key="n_enc_nu")
            c1, c2, c3 = st.columns(3)
            val_stock = c1.number_input("Stock:", min_value=0, step=1, key="n_sto")
            val_costo = c2.number_input("Costo ($):", min_value=0.0, format="%.0f", key="n_cos")
            val_precio = c3.number_input("Precio ($):", min_value=0.0, format="%.0f", key="n_pre")
            st.write("")
            col_btn1, col_btn2 = st.columns(2)
            btn_guardar = col_btn1.form_submit_button("➕ Añadir al Catálogo", type="primary", use_container_width=True)
            btn_limpiar = col_btn2.form_submit_button("🧹 Limpiar Formulario", type="secondary", use_container_width=True)
            claves_formulario = ["n_tit", "n_aut_ex", "n_aut_nu", "n_edi_ex", "n_edi_nu", "n_gen_ex", "n_gen_nu", "n_enc_ex", "n_enc_nu", "n_sto", "n_cos", "n_pre"]
            if btn_limpiar:
                for key in claves_formulario:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
            if btn_guardar:
                autor_final = val_autor_nu if val_autor_nu else val_autor_ex
                editorial_final = val_edit_nu if val_edit_nu else val_edit_ex
                genero_final = val_gen_nu if val_gen_nu else val_gen_ex
                enc_final = val_enc_nu if val_enc_nu else val_enc_ex
                if val_titulo and autor_final and editorial_final:
                    success, error = crear_nuevo_libro(val_titulo, autor_final, editorial_final, genero_final, enc_final, val_stock, val_precio, val_costo)
                    if success:
                        st.success("🎉 ¡Libro creado exitosamente!"); st.snow()
                        for key in claves_formulario:
                            if key in st.session_state: del st.session_state[key]
                        time.sleep(1.5); st.rerun()
                    else: st.error(f"❌ {error}")
                else: st.warning("⚠️ Título, Autor y Editorial son obligatorios.")

    with tab_desc:
        st.markdown("#### 📉 Aplicar Descuento Masivo")
        st.info(f"Vas a modificar el precio de **{len(df_filtrado)}** libros listados en tu búsqueda actual.")
        porcentaje = st.slider("Porcentaje de descuento (%):", 0, 100, 10, key="slider_descuento")
        st.caption("Nota: Aplicar un 0% restaura los libros a su Precio Original.")
        
        st.markdown("📅 **Vigencia del Descuento Masivo**")
        col_desc_f1, col_desc_f2 = st.columns(2)
        fecha_inicio = col_desc_f1.date_input("Fecha de Inicio:", value=datetime.now().date(), key="f_ini_desc")
        fecha_fin = col_desc_f2.date_input("Fecha de Término:", value=datetime.now().date() + timedelta(days=30), key="f_fin_desc")
        
        if st.button("🚀 Confirmar y Aplicar Descuento", type="primary", use_container_width=True):
            if fecha_inicio > fecha_fin:
                st.error("Error: La fecha de inicio no puede ser posterior a la fecha de término.")
            elif df_filtrado.empty:
                st.warning("No hay libros visibles o filtrados para aplicar el descuento.")
            else:
                lista_ids = df_filtrado['libro_id'].tolist()
                with st.spinner("Aplicando descuento..."):
                    success, mensaje = aplicar_descuento_masivo(lista_ids, porcentaje, fecha_inicio, fecha_fin)
                if success:
                    st.success(mensaje); st.snow()
                    time.sleep(2); st.rerun()
                else: st.error(f"Error al aplicar descuento: {mensaje}")

    with tab_eliminar:
        st.markdown("#### 🗑️ Borrar del Catálogo")
        st.warning("⚠️ Atención: Esta acción no se puede deshacer.")
        titulos_filtrados = [""] + df_filtrado['titulo'].tolist()
        titulo_a_eliminar = st.selectbox("Selecciona un libro de la lista filtrada:", titulos_filtrados)
        if titulo_a_eliminar:
            libro_id = int(df_filtrado[df_filtrado['titulo'] == titulo_a_eliminar].iloc[0]['libro_id'])
            if st.button(f"Eliminar '{titulo_a_eliminar}' permanentemente", type="primary", use_container_width=True):
                success, error = eliminar_libro(libro_id)
                if success: 
                    st.success("El libro fue eliminado de la base de datos.")
                    time.sleep(1.5); st.rerun()
                else: st.error(f"Error: {error}")

if __name__ == "__main__":
    mostrar_inventario()
