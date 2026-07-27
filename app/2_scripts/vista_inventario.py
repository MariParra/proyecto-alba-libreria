import streamlit as st
import pandas as pd
from utilidades import get_db_connection, limpiar_texto

def obtener_unicos(df, columna):
    """Devuelve una lista ordenada de valores únicos de una columna del DataFrame."""
    return sorted(df[columna].dropna().astype(str).unique())

@st.cache_data(ttl=5)
def cargar_datos_completos():
    """Carga todos los datos de la tabla 'libros' desde Supabase."""
    conn = get_db_connection()
    response = conn.table("libros").select("*").execute()
    return pd.DataFrame(response.data)

def crear_nuevo_libro(titulo, autor, editorial, genero, encuadernacion, stock, precio):
    """Crea un nuevo libro en la tabla 'libros'."""
    conn = get_db_connection()
    datos = {
        "titulo": limpiar_texto(titulo),
        "autor": limpiar_texto(autor),
        "editorial": limpiar_texto(editorial),
        "genero": limpiar_texto(genero),
        "encuadernacion": limpiar_texto(encuadernacion),
        "stock": stock,
        "precio": precio,
        "precio_original": precio
    }
    try:
        conn.table("libros").insert(datos).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        return False, str(e)

def actualizar_un_libro(libro_id, datos):
    """Actualiza un solo libro mediante un formulario (Optimizado para móvil)."""
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
                "precio": float(row['precio'])
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
    if not lista_ids: return True, "No hay libros."
    conn = get_db_connection()
    factor = 1.0 - (porcentaje / 100.0)
    try:
        response = conn.table("libros").select("libro_id, precio_original").in_("libro_id", lista_ids).execute()
        for row in response.data:
            nuevo_precio = round(row["precio_original"] * factor, 0)
            conn.table("libros").update({"precio": nuevo_precio}).eq("libro_id", row["libro_id"]).execute()
        cargar_datos_completos.clear()
        return True, ""
    except Exception as e:
        return False, str(e)


def mostrar_inventario():
    col_inv1, col_inv2 = st.columns([3, 1])
    with col_inv1:
        st.title("📦 Gestión de Inventario")
    with col_inv2:
        if st.button("🔄 Refrescar Datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

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
        
        if not df_inventario.empty:
            min_p, max_p = float(df_inventario['precio'].min()), float(df_inventario['precio'].max())
            if min_p == max_p: max_p += 1.0
            rango_precio = col_f5.slider("Rango de Precio ($):", min_value=min_p, max_value=max_p, value=(min_p, max_p))
            
            min_s, max_s = int(df_inventario['stock'].min()), int(df_inventario['stock'].max())
            if min_s == max_s: max_s += 1
            rango_stock = col_f6.slider("Rango de Stock:", min_value=min_s, max_value=max_s, value=(min_s, max_s))
        else:
            rango_precio = (0.0, 100000.0)
            rango_stock = (0, 1000)

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
    # --- SUBSECCIONES (PESTAÑAS) ---
    # =========================================================
    tab_catalogo, tab_editar, tab_crear, tab_desc, tab_eliminar = st.tabs([
        "📋 Catálogo", "✏️ Editar", "➕ Crear", "📉 Descuentos", "🗑️ Eliminar"
    ])

    # 0. PESTAÑA DE CATÁLOGO (Nueva Pestaña)
    with tab_catalogo:
        st.markdown(f"### 📋 Catálogo ({len(df_filtrado)} libros)")
        st.caption("💡 Tip: Toca el título de cualquier columna para ordenar los datos ↕️")
        
        columnas_fijas = ['libro_id', 'titulo', 'stock']
        
        # Excluimos las columnas fijas y otras que no son útiles para el usuario (como created_at, precio_original)
        columnas_opcionales_disponibles = [
            col for col in df_inventario.columns if col not in columnas_fijas + ['created_at', 'precio_original']
        ]
        
        # Creamos el selector de columnas
        columnas_extra_seleccionadas = st.multiselect(
            "Añadir/Quitar columnas de la tabla:",
            options=columnas_opcionales_disponibles,
            default=['autor', 'precio', 'editorial']  # Columnas que aparecerán por defecto
        )

        columnas_a_mostrar = columnas_fijas + columnas_extra_seleccionadas
        
        st.dataframe(
            df_filtrado[columnas_a_mostrar],
            hide_index=True, 
            use_container_width=True
        )

    # 1. PESTAÑA DE EDICIÓN (DUAL: MÓVIL Y PC)
    with tab_editar:
        st.markdown("#### ✏️ Modificar Libro")
        modo_edicion = st.radio("Elige la vista de edición:", ["📱 Vista Móvil (Formulario)", "💻 Vista PC (Tabla Editable)"], horizontal=True)
        st.write("") # Espaciador
        
        if modo_edicion == "📱 Vista Móvil (Formulario)":
            titulos_filtrados = [""] + df_filtrado['titulo'].tolist()
            titulo_a_editar = st.selectbox("Busca y selecciona un libro para editar:", titulos_filtrados, key="sel_editar")
            
            if titulo_a_editar:
                libro = df_filtrado[df_filtrado['titulo'] == titulo_a_editar].iloc[0]
                with st.form("form_editar"):
                    st.text_input("Título (No editable):", value=libro['titulo'], disabled=True)
                    
                    col1, col2 = st.columns(2)
                    nuevo_autor = col1.text_input("Autor:", value=libro['autor'])
                    nueva_editorial = col2.text_input("Editorial:", value=libro['editorial'])
                    
                    col3, col4 = st.columns(2)
                    nuevo_genero = col3.text_input("Género:", value=libro['genero'])
                    nueva_encuadernacion = col4.text_input("Encuadernación:", value=libro['encuadernacion'])
                    
                    col5, col6 = st.columns(2)
                    nuevo_stock = col5.number_input("Stock:", min_value=0, step=1, value=int(libro['stock']))
                    nuevo_precio = col6.number_input("Precio:", min_value=0.0, format="%.2f", value=float(libro['precio']))
                    
                    if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                        datos_actualizados = {
                            "autor": limpiar_texto(nuevo_autor),
                            "editorial": limpiar_texto(nueva_editorial),
                            "genero": limpiar_texto(nuevo_genero),
                            "encuadernacion": limpiar_texto(nueva_encuadernacion),
                            "stock": nuevo_stock,
                            "precio": nuevo_precio
                        }
                        exito, error = actualizar_un_libro(int(libro['libro_id']), datos_actualizados)
                        if exito:
                            st.success("¡Libro actualizado correctamente!")
                            st.rerun()
                        else:
                            st.error(f"Error: {error}")

        else: # VISTA PC (Tabla Editable)
            st.caption(f"Mostrando {len(df_filtrado)} libros. Haz doble clic en las celdas para modificar.")
            
            columnas_tabla_pc = ["libro_id", "titulo", "autor", "editorial", "genero", "encuadernacion", "stock", "precio"]
            df_mostrar = df_filtrado[columnas_tabla_pc]
            
            if 'inventario_original' not in st.session_state or not st.session_state.inventario_original.equals(df_mostrar):
                st.session_state.inventario_original = df_mostrar.copy()
                
            config_columnas = {
                "autor": st.column_config.SelectboxColumn("Autor", options=obtener_unicos(df_inventario, 'autor'), required=True),
                "editorial": st.column_config.SelectboxColumn("Editorial", options=obtener_unicos(df_inventario, 'editorial'), required=True),
                "genero": st.column_config.SelectboxColumn("Género", options=obtener_unicos(df_inventario, 'genero')),
                "encuadernacion": st.column_config.SelectboxColumn("Encuadernación", options=obtener_unicos(df_inventario, 'encuadernacion')),
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
            c1, c2 = st.columns(2)
            c1.number_input("Stock:", min_value=0, step=1, key="nuevo_stock")
            c2.number_input("Precio:", min_value=0.0, format="%.2f", key="nuevo_precio")
            
            if st.form_submit_button("➕ Añadir al Catálogo", type="primary", use_container_width=True):
                s = st.session_state
                autor_final = s.autor_nuevo if s.autor_nuevo else s.autor_existente
                editorial_final = s.editorial_nueva if s.editorial_nueva else s.editorial_existente
                genero_final = s.genero_nuevo if s.genero_nuevo else s.genero_existente
                enc_final = s.enc_nueva if s.enc_nueva else s.enc_existente
                
                if s.nuevo_titulo and autor_final and editorial_final:
                    success, error = crear_nuevo_libro(s.nuevo_titulo, autor_final, editorial_final, genero_final, enc_final, s.nuevo_stock, s.nuevo_precio)
                    if success:
                        st.success("¡Libro creado exitosamente!")
                        st.rerun()
                    else: 
                        st.error(f"Error: {error}")
                else: 
                    st.warning("Título, Autor y Editorial son obligatorios.")

    # 3. PESTAÑA DE DESCUENTOS
    with tab_desc:
        st.markdown("#### 📉 Aplicar Descuento Masivo")
        st.info(f"Vas a modificar el precio de **{len(df_filtrado)}** libros listados en tu búsqueda actual.")
        porcentaje = st.slider("Porcentaje de descuento (%):", 0, 100, 10, key="slider_descuento")
        st.caption("Nota: Aplicar un 0% restaura los libros a su Precio Original.")
        
        if st.button("🚀 Confirmar y Aplicar Descuento", type="primary", use_container_width=True):
            lista_ids = df_filtrado['libro_id'].tolist()
            success, error = aplicar_descuento_masivo(lista_ids, porcentaje)
            if success:
                st.success(f"¡Descuento del {porcentaje}% aplicado a {len(lista_ids)} libros!")
                st.rerun()
            else: 
                st.error(error)

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
