import streamlit as st
import pandas as pd
import io
import re
import json
import time
from utilidades import get_db_connection, limpiar_texto_para_busqueda, log_error

# --- HOMOLOGACIÓN GÉNEROS PLANETA ---
DICCIONARIO_PLANETA_GENEROS = {
    "NOVELA ROMÁNTICA": "ROMANCE",
    "NOVELA CONTEMPORÁNEA": "FICCION GENERAL",
    "AUTOAYUDA": "AUTOAYUDA",
    "NOVELA LITERARIA": "FICCION GENERAL",
    "CIENCIA": "NO FICCION",
    "JUVENIL": None,
    "INFANTIL": None,
    "CIENCIAS HUMANAS Y SOCIALES": "NO FICCION",
    "RELIGIÓN": "NO FICCION",
    "NOVELA NEGRA": "THRILLER",
    "PSICOLOGÍA": "NO FICCION",
    "ACTUALIDAD": "NO FICCION",
    "ECONOMÍA": "NO FICCION",
    "HISTORIA": "NO FICCION",
    "OCIO Y ENTRETENIMIENTO": "NO FICCION",
    "ARTE": "NO FICCION",
    "FILOSOFÍA": "NO FICCION",
    "CÓMIC Y MANGA": None,
    "DICCIONARIOS Y REFERENCIA": "NO FICCION",
    "POESÍA": "POESIA",
    "NOVELA HISTÓRICA": "HISTORICO",
    "RELATOS": None,
    "ESTILO DE VIDA": "NO FICCION",
    "HUMOR": "NO FICCION",
    "TERROR": "TERROR",
    "FANTASÍA": "FANTASIA",
    "MANGA": None,
    "VIAJES": "NO FICCION",
    "CIENCIA FICCIÓN": "CIENCIA FICCION",
    "EMPRESA": "NO FICCION",
    "CALENDARIOS": "NO FICCION",
    "TEATRO": None,
    "SALUD": "NO FICCION",
    "PARA PADRES": "NO FICCION",
    "ESOTERISMO": None,
    "BEBÉS": "NO FICCION",
    "NOVELA ERÓTICA": "EROTICA",
    "AGENDAS": "NO FICCION",
    "COCINA": "NO FICCION"
}

# --- PARSERS INTELIGENTES ---
def sanear_numero(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip()
    val_str = re.sub(r'[^\d.,-]', '', val_str)
    if not val_str: return 0.0
    if ',' in val_str and '.' in val_str:
        if val_str.find('.') < val_str.find(','):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        parts = val_str.split(',')
        if len(parts[-1]) == 3:
            val_str = val_str.replace(',', '')
        else:
            val_str = val_str.replace(',', '.')
    elif '.' in val_str:
        parts = val_str.split('.')
        if len(parts[-1]) == 3:
            val_str = val_str.replace('.', '')
    try:
        return float(val_str)
    except:
        return 0.0

def normalizar_autor(autor_raw):
    if pd.isna(autor_raw): return ""
    autor_str = str(autor_raw).strip()
    if autor_str.startswith("-"):
        autor_str = autor_str[1:].strip()
    if "," in autor_str:
        parts = autor_str.split(",")
        if len(parts) == 2:
            autor_str = f"{parts[1].strip()} {parts[0].strip()}"
    return limpiar_texto_para_busqueda(autor_str)  # <--- SANEADO UNIFICADO SIN TILDES Y EN MAYÚSCULAS

def normalizar_titulo(titulo_raw):
    if pd.isna(titulo_raw): return ""
    titulo_str = str(titulo_raw).strip()
    articles = [", EL", ", LA", ", LOS", ", LAS", ", UN", ", UNA", ", EN"]
    for art in articles:
        if titulo_str.upper().endswith(art):
            titulo_str = art[2:].strip() + " " + titulo_str[:-len(art)].strip()
            break
    return limpiar_texto_para_busqueda(titulo_str)  # <--- SANEADO UNIFICADO SIN TILDES Y EN MAYÚSCULAS

def aproximar_cien_superior(valor):
    import math
    return int(math.ceil(valor / 100.0)) * 100

# --- CARGA DEL INVENTARIO DE BASE ---
def cargar_db_libros():
    conn = get_db_connection()
    all_books = []
    chunk_size = 1000
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res = conn.table("libros").select("libro_id, titulo, autor, editorial, genero, encuadernacion, stock, precio, costo, isbn").order("libro_id").range(start, end).execute()
        if res.data:
            all_books.extend(res.data)
            if len(res.data) < chunk_size: break
        else:
            break
    return all_books

# --- GESTOR DE UPSERT ---
def ejecutar_upsert_editorial(df_import, editorial_tipo, pct_descuento, valor_fijo, forzar_finanzas):
    conn = get_db_connection()
    db_libros = cargar_db_libros()
    
    # Llave de emparejamiento limpia y homogeneizada: (titulo_key, autor_key) -> libro_db_dict
    map_db = {(limpiar_texto_para_busqueda(b['titulo']), limpiar_texto_para_busqueda(b.get('autor', ''))): b for b in db_libros}
    
    exitos_creados = 0
    exitos_actualizados = 0
    errores = []
    
    progreso = st.progress(0.0, text="Iniciando Upsert...")
    total_filas = len(df_import)
    
    for idx, row in df_import.iterrows():
        progreso.progress((idx + 1) / total_filas, text=f"Procesando fila {idx+1}/{total_filas}...")
        
        try:
            titulo_original = row.get('TITULO') if editorial_tipo == "PLANETA" else row.get('Titulo')
            autor_original = row.get('AUTOR') if editorial_tipo == "PLANETA" else row.get('Autores')
            isbn_original = str(row.get('EAN')).split('.')[0] if editorial_tipo == "PLANETA" else str(row.get('EAN13')).split('.')[0]
            
            titulo_saneado = normalizar_titulo(titulo_original)
            autor_saneado = normalizar_autor(autor_original)
            isbn_saneado = isbn_original.strip() if pd.notna(isbn_original) else None
            
            titulo_key = limpiar_texto_para_busqueda(titulo_saneado)
            autor_key = limpiar_texto_para_busqueda(autor_saneado)
            
            if not titulo_key:
                errores.append(f"Fila {idx+2}: Título vacío. Omitido.")
                continue
                
            # Cálculo financiero
            if editorial_tipo == "PLANETA":
                precio_lista = sanear_numero(row.get('PVP_ACT', 0.0))
                costo_base = (precio_lista - (precio_lista * (pct_descuento / 100.0))) * 1.19
                precio_venta = aproximar_cien_superior(costo_base + valor_fijo)
                
                tematica = limpiar_texto_para_busqueda(str(row.get('TEMÁTICA WEB', '')))
                genero_final = DICCIONARIO_PLANETA_GENEROS.get(tematica, None)
                encuadernacion = limpiar_texto_para_busqueda(str(row.get('FORMATO', '')))
            else: # URANO
                precio_neto = sanear_numero(row.get('Precio Neto', 0.0))
                costo_base = (precio_neto - (precio_neto * (pct_descuento / 100.0))) * 1.19
                precio_venta = aproximar_cien_superior(costo_base + valor_fijo)
                
                genero_final = None
                encuadernacion = None
            
            match_libro = map_db.get((titulo_key, autor_key))
            
            if match_libro:
                # El libro ya existe -> Modo UPDATE / RELLENO inteligente
                libro_id = match_libro['libro_id']
                payload = {}
                
                # Saneamiento de campos que están vacíos en tu Base de Datos
                if not match_libro.get('isbn') and isbn_saneado:
                    payload['isbn'] = isbn_saneado
                if not match_libro.get('autor') and autor_saneado:
                    payload['autor'] = autor_saneado
                if not match_libro.get('genero') and genero_final:
                    payload['genero'] = genero_final
                if not match_libro.get('encuadernacion') and encuadernacion:
                    payload['encuadernacion'] = encuadernacion
                if not match_libro.get('editorial'):
                    payload['editorial'] = editorial_tipo
                
                # Modificaciones financieras (Solo si se activó el Toggle explícito)
                if forzar_finanzas:
                    payload['costo'] = costo_base
                    payload['precio'] = precio_venta
                    payload['precio_original'] = precio_venta
                
                if payload:
                    conn.table("libros").update(payload).eq("libro_id", libro_id).execute()
                    exitos_actualizados += 1
            else:
                # El libro no existe -> Modo CREATE
                payload_insert = {
                    "titulo": titulo_saneado,
                    "autor": autor_saneado,
                    "editorial": editorial_tipo,
                    "genero": genero_final,
                    "encuadernacion": encuadernacion,
                    "stock": 0,
                    "precio": precio_venta,
                    "precio_original": precio_venta,
                    "costo": costo_base,
                    "isbn": isbn_saneado,
                    "visible_catalogo": True
                }
                conn.table("libros").insert(payload_insert).execute()
                exitos_creados += 1
                
        except Exception as e:
            errores.append(f"Fila {idx+2}: Error al procesar '{titulo_original}'. Detalle: {e}")
            
    progreso.empty()
    st.cache_data.clear()
    return exitos_creados, exitos_actualizados, errores

def mostrar_carga_editoriales():
    # --- EXPLICACIÓN COLAPSABLE (UX GUIDELINE) ---
    with st.expander("📖 Manual y Guía de Ingesta Inteligente de Editoriales (Fórmulas y Columnas)", expanded=False):
        st.markdown("""
        ### ⚙️ ¿Cómo funciona este módulo?
        Este procesador lee el catálogo de las distribuidoras y realiza un **Upsert cruzado** inteligente contra tu base de datos de Supabase, resolviendo automáticamente las diferencias de escritura tradicionales sin corromper tu información.
        
        #### 🧠 Inteligencia de Homologación:
        * **Reordenamiento de Autores:** Convierte automáticamente formatos invertidos como `POSTON, ASHLEY` $\\rightarrow$ `ASHLEY POSTON`.
        * **Limpieza de Títulos:** Sanea artículos finales como `VERANO QUE NUNCA FUE, EL` $\\rightarrow$ `EL VERANO QUE NUNCA FUE`.
        * **Homologación de Géneros (Planeta):** Mapea la columna *Temática Web* de Planeta con los géneros de tu tienda de forma nativa.
        
        #### 📊 Fórmulas de Costos y Ventas:
        * **Urano:** 
          $$\\text{Costo} = (\\text{Precio Neto} - (\\text{Precio Neto} \\times \\text{Descuento})) \\times 1.19$$
        * **Planeta:** 
          $$\\text{Costo} = (\\text{PVP Sugerido} - (\\text{PVP Sugerido} \\times \\text{Descuento})) \\times 1.19$$
        * **Precio de Venta (Ambas):** 
          $$\\text{Precio Venta} = \\text{Costo} + \\text{Valor Fijo} \\rightarrow \\text{Aproximado al 100 Superior (ej: } 24410 \\rightarrow 24500)$$
        """)
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown("""
            **📋 Formato Esperado para PLANETA:**
            * `TITULO`
            * `AUTOR`
            * `EAN` (ISBN)
            * `FORMATO` (Encuadernación)
            * `TEMÁTICA WEB` (Género)
            * `PVP_ACT` (Precio de lista)
            """)
        with col_m2:
            st.markdown("""
            **📋 Formato Esperado para URANO:**
            * `Titulo`
            * `Autores`
            * `EAN13`
            * `Precio Neto`
            """)

    tab_planeta, tab_urano = st.tabs(["🌎 Grupo Planeta", "🌌 Urano World"])
    
    # ================= PESTAÑA: PLANETA =================
    with tab_planeta:
        st.subheader("Carga Masiva - Grupo Planeta")
        col_p1, col_p2 = st.columns(2)
        pct_p = col_p1.number_input("Descuento Comercial de Planeta (%):", min_value=0.0, max_value=100.0, value=40.0, step=1.0, key="pct_p")
        val_p = col_p2.number_input("Valor Fijo de Utilidad ($):", min_value=0, value=5000, step=500, key="val_p")
        
        force_p = st.toggle("🚨 Forzar actualización de Costo y Precio de Venta en libros existentes", value=False, key="force_p")
        if not force_p:
            st.info("🔒 Modo Relleno Activo: Solo se inyectarán ISBNs y campos vacíos. Costos y precios existentes no serán alterados.")
        else:
            st.warning("⚠️ Forzar Finanzas Activo: Se recalcularán y sobreescribirán costos y precios de venta de tus libros existentes.")
            
        up_planeta = st.file_uploader("Sube el catálogo de Planeta (.xlsx):", type=["xlsx"], key="up_planeta")
        if up_planeta:
            df_p = pd.read_excel(up_planeta, engine="openpyxl")
            if st.button("🚀 Ejecutar Ingesta Planeta", type="primary", use_container_width=True, key="btn_p"):
                creados, actualizados, errores = ejecutar_upsert_editorial(df_p, "PLANETA", pct_p, val_p, force_p)
                
                st.markdown("### 📊 Resultado de la Operación")
                c1, c2, c3 = st.columns(3)
                c1.metric("Libros Creados ✨", creados)
                c2.metric("Libros Enriquecidos 🔧", actualizados)
                c3.metric("Fallas de Fila ❌", len(errores))
                
                if creados > 0 or actualizados > 0:
                    st.success("¡Ingesta de catálogo de Planeta completada exitosamente!")
                    st.balloons()
                if errores:
                    with st.expander("Ver lista de advertencias"):
                        for err in errores: st.write(err)

    # ================= PESTAÑA: URANO =================
    with tab_urano:
        st.subheader("Carga Masiva - Urano World")
        col_u1, col_u2 = st.columns(2)
        pct_u = col_u1.number_input("Descuento Comercial de Urano (%):", min_value=0.0, max_value=100.0, value=35.0, step=1.0, key="pct_u")
        val_u = col_u2.number_input("Valor Fijo de Utilidad ($):", min_value=0, value=5000, step=500, key="val_u")
        
        force_u = st.toggle("🚨 Forzar actualización de Costo y Precio de Venta en libros existentes", value=False, key="force_u")
        if not force_u:
            st.info("🔒 Modo Relleno Activo: Solo se inyectarán ISBNs y campos vacíos. Costos y precios existentes no serán alterados.")
        else:
            st.warning("⚠️ Forzar Finanzas Activo: Se recalcularán y sobreescribirán costos y precios de venta de tus libros existentes.")
            
        up_urano = st.file_uploader("Sube el catálogo de Urano (.xlsx):", type=["xlsx"], key="up_urano")
        if up_urano:
            df_u = pd.read_excel(up_urano, engine="openpyxl")
            if st.button("🚀 Ejecutar Ingesta Urano", type="primary", use_container_width=True, key="btn_u"):
                creados, actualizados, errores = ejecutar_upsert_editorial(df_u, "URANO", pct_u, val_u, force_u)
                
                st.markdown("### 📊 Resultado de la Operación")
                c1, c2, c3 = st.columns(3)
                c1.metric("Libros Creados ✨", creados)
                c2.metric("Libros Enriquecidos 🔧", actualizados)
                c3.metric("Fallas de Fila ❌", len(errores))
                
                if creados > 0 or actualizados > 0:
                    st.success("¡Ingesta de catálogo de Urano completada exitosamente!")
                    st.balloons()
                if errores:
                    with st.expander("Ver lista de advertencias"):
                        for err in errores: st.write(err)

if __name__ == "__main__":
    mostrar_carga_editoriales()