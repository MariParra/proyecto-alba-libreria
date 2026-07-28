import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto

def obtener_unicos(df, columna):
    """Devuelve una lista ordenada de valores únicos de una columna del DataFrame."""
    return sorted(df[columna].dropna().astype(str).unique())

@st.cache_data
def cargar_datos_completos():
    """
    Carga todos los datos de la tabla 'libros' desde Supabase
    y limpia de forma segura cualquier celda con valores nulos (NaN).
    """
    conn = get_db_connection()
    response = conn.table("libros").select("*").execute()
    
    if response.data:
        df = pd.DataFrame(response.data)
        columnas_texto = ['titulo', 'autor', 'editorial', 'genero', 'encuadernacion']
        for col in columnas_texto:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
                
        # Aseguramos que precio y stock también tengan valores numéricos válidos por si acaso
        if 'precio' in df.columns:
            df['precio'] = pd.to_numeric(df['precio'], errors='coerce').fillna(0.0)
        
        # ✅ Aseguramos que precio_original siempre tenga valor (si es nulo, usa el precio)
        if 'precio_original' in df.columns:
            df['precio_original'] = pd.to_numeric(df['precio_original'], errors='coerce')
            df['precio_original'] = df['precio_original'].fillna(df['precio'])
        else:
            df['precio_original'] = df['precio']

        if 'stock' in df.columns:
            df['stock'] = pd.to_numeric(df['stock'], errors='coerce').fillna(0).astype(int)
        if 'costo' in df.columns:
            df['costo'] = pd.to_numeric(df['costo'], errors='coerce').fillna(0.0)
        return df
        
    return pd.DataFrame()

def crear_nuevo_libro(titulo, autor, editorial, genero, encuadernacion, stock, precio, costo):
    conn = get_db_connection()
    datos = {
        "titulo": limpiar_texto(titulo), "autor": limpiar_texto(autor),
        "editorial": limpiar_texto(editorial), "genero": limpiar_texto(genero),
        "encuadernacion": limpiar_texto(encuadernacion), "stock": stock,
        "precio": precio, "precio_original": precio, "costo": costo
    }
    try:
        conn.table("libros").insert(datos).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

def actualizar_un_libro(libro_id, datos):
    conn = get_db_connection()
    try:
        conn.table("libros").update(datos).eq("libro_id", libro_id).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

def actualizar_libros_batch(df_editado):
    """Actualiza múltiples libros a la vez detectando los cambios (Optimizado para PC)."""
    df_original = st.session_state.get('inventario_original')
    if df_original is None: return 0
    
    df_original_comp = df_original.set_index('libro_id')
    df_editado_comp = df_editado.set_index('libro_id')
    diff_mask = df_original_comp.ne(df_editado_comp).any(axis=1)
    filas_cambiadas = df_editado_comp[diff_mask]
    
    if filas_cambiadas.empty: return 0
    
    conn = get_db_connection()
    updates_count = 0
    
    for libro_id, row in filas_cambiadas.iterrows():
        try:
            datos = {
                "autor": limpiar_texto(row['autor']),
                "editorial": limpiar_texto(row['editorial']),
                "genero": limpiar_texto(row['genero']),
                "encuadernacion": limpiar_texto(row['encuadernacion']),
                "stock": int(row['stock']),
                "precio": float(row['precio']),
                "costo": float(row.get('costo', 0))
            }
            conn.table("libros").update(datos).eq("libro_id", libro_id).execute()
            updates_count += 1
        except Exception:
            continue
            
    if updates_count > 0:
        cargar_datos_completos.clear()
        
    return updates_count

def eliminar_libro(libro_id):
    """Elimina un libro permanentemente de la tabla 'libros'."""
    conn = get_db_connection()
    try:
        conn.table("libros").delete().eq("libro_id", libro_id).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

def aplicar_descuento_masivo(lista_ids, porcentaje):
    """Aplica un descuento masivo calculando sobre el precio original."""
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
            # Si precio_original es None o 0, usamos el precio actual como base
            if precio_base is None or float(precio_base) == 0:
                precio_base = row.get("precio", 0.0)
                # Resguardamos el precio original en la BD
                conn.table("libros").update({"precio_original": precio_base}).eq("libro_id", row["libro_id"]).execute()

            precio_base = float(precio_base)
            nuevo_precio = round(precio_base * factor, 0)
            
            conn.table("libros").update({"precio": nuevo_precio}).eq("libro_id", row["libro_id"]).execute()
            actualizados += 1
            
        cargar_datos_completos.clear()
        return True, f"Se actualizó el precio de {actualizados} libros con un {porcentaje}% de descuento."
    except Exception as e:
        return False, str(e)


def mostrar_inventario():
    col_inv1, col_inv2 = st.columns([3, 1])
    with col_inv1:
        st.title("📦 Gestión de Inventario")
    with col_inv2:
        if st.button("🔄 Refrescar Datos", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.toast("✅ ¡Datos actualizados! La aplicación ha sido refrescada.", icon="🔄")
            import time
            time.sleep(1) 
            st.rerun()
            
    df_inventario = cargar_datos_completos()
    
    # --- FILTROS GLOBALES ---
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
        
        min_p, max_p = float(df_inventario['precio'].min()) if not df_inventario.empty else 0.0, float(df_inventario['precio'].max()) if not df_inventario.empty else 1.0
        if min_p >= max_p: max_p = min_p + 1.0
        rango_precio = col_f5.slider("Rango de Precio ($):", min_value=min_p, max_value=max_p, value=(min_p, max_p))

        min_s_db = int(df_inventario['stock'].min()) if not df_inventario.empty else 0
        min_s_slider = max(0, min_s_db)
        
        max_s = int(df_inventario['stock'].max()) if not df_inventario.empty else 1
        if min_s_slider >= max_s: max_s = min_s_slider + 1

        valor_inicial_slider = (min_s_slider, max_s)

        rango_stock = col_f6.slider(
            "Rango de Stock:", 
            min_value=min_s_slider, 
            max_value=max_s, 
            value=valor_inicial_slider
        )

    # Aplicamos todos los filtros
    df_filtrado = df_inventario.copy()
    if busqueda_titulo: df_filtrado = df_filtrado[df_filtrado['titulo'].str.contains(limpiar_texto(busqueda_titulo), case=False, na=False)]
    if autores_seleccionados: df_filtrado = df_filtrado[df_filtrado['autor'].isin(autores_seleccionados)]
    if editoriales_seleccionadas: df_filtrado = df_filtrado[df_filtrado['editorial'].isin(editoriales_seleccionadas)]
    if generos_seleccionados: df_filtrado = df_filtrado[df_filtrado['genero'].isin(generos_seleccionados)]
    if encuadernaciones_seleccionadas: df_filtrado = df_filtrado[df_filtrado['encuadernacion'].isin(encuadernaciones_seleccionadas)]
    
    if not df_filtrado.empty:
        df_filtrado = df_filtrado[df_filtrado['precio'].between(rango_precio[0], rango_precio[1])]
        df_filtrado = df_filtrado[df_filtrado['stock'].between(rango_stock[0], rango_stock[1])]

    # =========================================================
    # --- PESTAÑAS ---
    # =========================================================
    tab_catalogo, tab_editar, tab_crear, tab_desc, tab_eliminar = st.tabs([
        "📋 Catálogo", "✏️ Editar", "➕ Crear", "📉 Descuentos", "🗑️ Eliminar"
    ])

    # 0. PESTAÑA DE CATÁLOGO
    with tab_catalogo:
        st.markdown(f"### 📋 Catálogo ({len(df_filtrado)} libros)")
        st.caption("💡 Tip: Toca el título de cualquier columna para ordenar los datos ↕️")
        
        columnas_fijas = ['libro_id', 'titulo', 'stock']
        columnas_opcionales_disponibles = [
            col for col in df_inventario.columns if col not in columnas_fijas + ['created_at']
        ]
        
        columnas_extra_seleccionadas = st.multiselect(
            "Añadir/Quitar columnas de la tabla:",
            options=columnas_opcionales_disponibles,
            default=['autor', 'precio', 'editorial']
        )

        columnas_a_mostrar = columnas_fijas + columnas_extra_seleccionadas
        
        st.dataframe(
            df_filtrado[columnas_a_mostrar],
            hide_index=True, 
            use_container_width=True
        )

    # 1. PESTAÑA DE EDICIÓN
    with tab_editar:
        st.markdown("#### ✏️ Modificar Libro")
        modo_edicion = st.radio("Elige la vista de edición:", ["📱 Vista Móvil (Formulario)", "💻 Vista PC (Tabla Editable)"], horizontal=True)
        st.write("")
        
        if modo_edicion == "📱 Vista Móvil (Formulario)":
            titulos_filtrados = [""] + df_filtrado['titulo'].tolist()
            titulo_a_editar = st.selectbox("Busca y selecciona un libro para editar:", titulos_filtrados, key="sel_editar")
            
            if titulo_a_editar:
                libro = df_filtrado[df_filtrado['titulo'] == titulo_a_editar].iloc[0]
                with st.form("form_editar_movil"):
                    st.text_input("Título (No editable):", value=libro['titulo'], disabled=True)
                    
                    opciones_autor = obtener_unicos(df_inventario, 'autor')
                    opciones_editorial = obtener_unicos(df_inventario, 'editorial')
                    opciones_genero = obtener_unicos(df_inventario, 'genero')
                    opciones_enc = obtener_unicos(df_inventario, 'encuadernacion')

                    col1, col2 = st.columns(2)
                    try: idx_autor = opciones_autor.index(libro['autor'])
                    except ValueError: idx_autor = 0
                    nuevo_autor = col1.selectbox("Autor:", opciones_autor, index=idx_autor)

                    try: idx_editorial = opciones_editorial.index(libro['editorial'])
                    except ValueError: idx_editorial = 0
                    nueva_editorial = col2.selectbox("Editorial:", opciones_editorial, index=idx_editorial)
                    
                    col3, col4 = st.columns(2)
                    try: idx_genero = opciones_genero.index(libro['genero'])
                    except ValueError: idx_genero = 0
                    nuevo_genero = col3.selectbox("Género:", opciones_genero, index=idx_genero)

                    try: idx_enc = opciones_enc.index(libro['encuadernacion'])
                    except ValueError: idx_enc = 0
                    nueva_encuadernacion = col4.selectbox("Encuadernación:", opciones_enc, index=idx_enc)
                    
                    col5, col6, col7 = st.columns(3)
                    nuevo_stock = col5.number_input("Stock:", min_value=0, step=1, value=int(libro['stock']))
                    nuevo_costo = col6.number_input("Costo ($):", min_value=0.0, format="%.0f", value=float(libro.get('costo', 0)))
                    nuevo_precio = col7.number_input("Precio:", min_value=0.0, format="%.2f", value=float(libro['precio']))
                    
                    if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                        datos_actualizados = {
                            "autor": nuevo_autor,
                            "editorial": nueva_editorial,
                            "genero": nuevo_genero,
                            "encuadernacion": nueva_encuadernacion,
                            "stock": nuevo_stock,
                            "costo": nuevo_costo,
                            "precio": nuevo_precio
                        }
                        exito, error = actualizar_un_libro(int(libro['libro_id']), datos_actualizados)
                        if exito:
                            st.success("¡Libro actualizado correctamente!")
                            st.rerun()
                        else:
                            st.error(f"Error: {error}")

        else: # VISTA PC
            st.caption(f"Mostrando {len(df_filtrado)} libros. Haz doble clic en las celdas para modificar.")
            
            columnas_tabla_pc = ["libro_id", "titulo", "autor", "editorial", "genero", "encuadernacion", "stock", "costo", "precio"]
            df_mostrar = df_filtrado[columnas_tabla_pc]
            
            if 'inventario_original' not in st.session_state or not st.session_state.inventario_original.equals(df_mostrar):
                st.session_state.inventario_original = df_mostrar.copy()
                
            config_columnas = {
                "autor": st.column_config.SelectboxColumn("Autor", options=obtener_unicos(df_inventario, 'autor'), required=True),
                "editorial": st.column_config.SelectboxColumn("Editorial", options=obtener_unicos(df_inventario, 'editorial'), required=True),
                "genero": st.column_config.SelectboxColumn("Género", options=obtener_unicos(df_inventario, 'genero')),
                "encuadernacion": st.column_config.SelectboxColumn("Encuadernación", options=obtener_unicos(df_inventario, 'encuadernacion')),
                "costo": st.column_config.NumberColumn("Costo ($)", format="$%.0f")
            }
            
            df_editado = st.data_editor(
                df_mostrar, use_container_width=True, hide_index=True,
                disabled=["libro_id", "titulo"], key="editor_inventario",
                column_config=config_columnas
            )
            
            if not df_mostrar.equals(df_editado):
                if st.button("💾 Guardar Cambios en Tabla", type="primary", use_container_width=True):
                    with st.spinner("Actualizando datos..."):
                        num_actualizados = actualizar_libros_batch(df_editado)
                        st.success(f"¡Se actualizaron {num_actualizados} libros!")
                        st.rerun()

    # 2. PESTAÑA DE CREACIÓN
    with tab_crear:
        st.markdown("#### ➕ Ingresar Nuevo Libro")
        with st.form("form_nuevo_libro", clear_on_submit=True):
            st.text_input("Título:", key="nuevo_titulo")
            opciones_autor = [""] + obtener_unicos(df_inventario, 'autor')
            st.selectbox("Autor (Existente):", options=opciones_autor, key="autor_existente")
            st.text_input("O escribe un nuevo Autor:", key="autor_nuevo")
            opciones_editorial = [""] + obtener_unicos(df_inventario, 'editorial')
            st.selectbox("Editorial (Existente):", options=opciones_editorial, key="editorial_existente")
            st.text_input("O escribe una nueva Editorial:", key="editorial_nueva")
            opciones_genero = [""] + obtener_unicos(df_inventario, 'genero')
            st.selectbox("Género (Existente):", options=opciones_genero, key="genero_existente")
            st.text_input("O escribe un nuevo Género:", key="genero_nuevo")
            opciones_enc = [""] + obtener_unicos(df_inventario, 'encuadernacion')
            st.selectbox("Encuadernación (Existente):", options=opciones_enc, key="enc_existente")
            st.text_input("O escribe una nueva Encuadernación:", key="enc_nueva")
            c1, c2, c3 = st.columns(3)
            c1.number_input("Stock:", min_value=0, step=1, key="nuevo_stock")
            c2.number_input("Costo ($):", min_value=0.0, format="%.0f", key="nuevo_costo")
            c3.number_input("Precio:", min_value=0.0, format="%.2f", key="nuevo_precio")
            
            if st.form_submit_button("➕ Añadir al Catálogo", type="primary", use_container_width=True):
                s = st.session_state
                autor_final = s.autor_nuevo if s.autor_nuevo else s.autor_existente
                editorial_final = s.editorial_nueva if s.editorial_nueva else s.editorial_existente
                genero_final = s.genero_nuevo if s.genero_nuevo else s.genero_existente
                enc_final = s.enc_nueva if s.enc_nueva else s.enc_existente
                
                if s.nuevo_titulo and autor_final and editorial_final:
                    success, error = crear_nuevo_libro(
                        s.nuevo_titulo, autor_final, editorial_final, genero_final, 
                        enc_final, s.nuevo_stock, s.nuevo_precio, s.nuevo_costo
                    )
                    if success:
                        st.success("¡Libro creado exitosamente!")
                        st.rerun()
                    else: 
                        st.error(f"Error: {error}")
                else: 
                    st.warning("Título, Autor y Editorial son obligatorios.")

    # 3. PESTAÑA DE DESCUENTOS (Corregida)
    with tab_desc:
        st.markdown("#### 📉 Aplicar Descuento Masivo")
        st.info(f"Vas a modificar el precio de **{len(df_filtrado)}** libros listados en tu búsqueda actual.")
        porcentaje = st.slider("Porcentaje de descuento (%):", 0, 100, 10, key="slider_descuento")
        st.caption("Nota: Aplicar un 0% restaura los libros a su Precio Original.")
        
        if st.button("🚀 Confirmar y Aplicar Descuento", type="primary", use_container_width=True):
            if df_filtrado.empty:
                st.warning("No hay libros visibles o filtrados para aplicar el descuento.")
            else:
                lista_ids = df_filtrado['libro_id'].tolist()
                with st.spinner("Aplicando descuento en la base de datos..."):
                    success, mensaje = aplicar_descuento_masivo(lista_ids, porcentaje)
                if success:
                    st.success(mensaje)
                    import time
                    time.sleep(1)
                    st.rerun()
                else: 
                    st.error(f"Error al aplicar descuento: {mensaje}")

    # 4. PESTAÑA DE ELIMINACIÓN
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
                    st.rerun()
                else: 
                    st.error(f"Error: {error}")
