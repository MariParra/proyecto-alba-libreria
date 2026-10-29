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
    return limpiar_texto_para_busqueda(autor_str)

def normalizar_titulo(titulo_raw):
    if pd.isna(titulo_raw): return ""
    titulo_str = str(titulo_raw).strip()
    titulo_str = re.sub(r'\s*\(CHI\)\s*$', '', titulo_str, flags=re.IGNORECASE)
    articles = [", EL", ", LA", ", LOS", ", LAS", ", UN", ", UNA", ", EN"]
    for art in articles:
        if titulo_str.upper().endswith(art):
            titulo_str = art[2:].strip() + " " + titulo_str[:-len(art)].strip()
            break
    return limpiar_texto_para_busqueda(titulo_str)

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

# --- SIMULADOR DE CAMBIOS (PREVIEW) ---
def simular_upsert_editorial(df_import, editorial_tipo, pct_descuento, valor_fijo, forzar_finanzas):
    db_libros = cargar_db_libros()
    map_db = {(limpiar_texto_para_busqueda(b['titulo']), limpiar_texto_para_busqueda(b.get('autor', ''))): b for b in db_libros}
    
    preview_creados = []
    preview_actualizados = []
    errores = []
    
    for idx, row in df_import.iterrows():
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
                continue
                
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
                # Libro existente -> Comparar diferencias de enriquecimiento
                campos_cambiados = []
                if not match_libro.get('isbn') and isbn_saneado: campos_cambiados.append("ISBN")
                if not match_libro.get('autor') and autor_saneado: campos_cambiados.append("Autor")
                if not match_libro.get('genero') and genero_final: campos_cambiados.append("Género")
                if not match_libro.get('encuadernacion') and encuadernacion: campos_cambiados.append("Encuadernación")
                if not match_libro.get('editorial'): campos_cambiados.append("Editorial")
                
                if forzar_finanzas:
                    campos_cambiados.extend(["Costo", "Precio"])
                
                if campos_cambiados:
                    preview_actualizados.append({
                        "ID": match_libro['libro_id'],
                        "Título": titulo_saneado,
                        "Autor": autor_saneado,
                        "Cambios a Aplicar": ", ".join(campos_cambiados),
                        "Nuevo Costo": f"${round(costo_base):,.0f}" if forzar_finanzas else "Sin cambios",
                        "Nuevo Precio": f"${precio_venta:,.0f}" if forzar_finanzas else "Sin cambios"
                    })
            else:
                # Libro Nuevo
                preview_creados.append({
                    "Título": titulo_saneado,
                    "Autor": autor_saneado,
                    "ISBN": isbn_saneado,
                    "Género": genero_final,
                    "Costo Calculado": f"${round(costo_base):,.0f}",
                    "Precio Venta": f"${precio_venta:,.0f}"
                })
        except Exception as e:
            errores.append(f"Fila {idx+2}: Error de simulación: {e}")
            
    return preview_creados, preview_actualizados, errores

# --- PROCESADOR EFECTIVO EN SUPABASE ---
def ejecutar_upsert_editorial_seguro(lista_creados, lista_actualizados, editorial_tipo, pct_descuento, valor_fijo, forzar_finanzas):
    conn = get_db_connection()
    exitos_creados = 0
    exitos_actualizados = 0
    errores = []
    
    progreso = st.progress(0.0, text="Iniciando Escritura en Supabase...")
    total_crear = len(lista_creados)
    total_update = len(lista_actualizados)
    total_total = total_crear + total_update
    
    # 1. Crear Libros Nuevos
    for idx, item in enumerate(lista_creados):
        progreso.progress((idx + 1) / total_total, text=f"Creando nuevo libro {idx+1}/{total_crear}...")
        try:
            costo_float = float(item['Costo Calculado'].replace('$', '').replace('.', '').replace(',', ''))
            precio_float = float(item['Precio Venta'].replace('$', '').replace('.', '').replace(',', ''))
            
            payload_insert = {
                "titulo": item['Título'],
                "autor": item['Autor'],
                "editorial": editorial_tipo,
                "genero": item['Género'],
                "stock": 0,
                "precio": precio_float,
                "precio_original": precio_float,
                "costo": costo_float,
                "isbn": item['ISBN'],
                "visible_catalogo": True
            }
            conn.table("libros").insert(payload_insert).execute()
            exitos_creados += 1
        except Exception as e:
            errores.append(f"Fallo al insertar '{item['Título']}': {e}")
            
    # 2. Actualizar / Enriquecer Existentes
    for idx, item in enumerate(lista_actualizados):
        progreso.progress((total_crear + idx + 1) / total_total, text=f"Actualizando libro {idx+1}/{total_update}...")
        try:
            libro_id = int(item['ID'])
            payload = {}
            
            # Recuperar de las llaves que se simularon
            if "ISBN" in item['Cambios a Aplicar'] or "Costo" in item['Cambios a Aplicar']:
                # Hacemos una consulta rápida o mapeamos del objeto original
                pass
                
            # Para simplificar y resguardar, volvemos a evaluar el item
            # Pero dado que la simulación es idéntica, podemos mapear de vuelta de la DB
            # Para máxima seguridad, realizamos el update basado en campos rellenados:
            if "ISBN" in item['Cambios a Aplicar'] and pd.notna(item.get('ISBN')): payload['isbn'] = item['ISBN']
            if "Autor" in item['Cambios a Aplicar']: payload['autor'] = item['Autor']
            if "Editorial" in item['Cambios a Aplicar']: payload['editorial'] = editorial_tipo
            
            if forzar_finanzas:
                costo_float = float(item['Nuevo Costo'].replace('$', '').replace('.', '').replace(',', ''))
                precio_float = float(item['Nuevo Precio'].replace('$', '').replace('.', '').replace(',', ''))
                payload['costo'] = costo_float
                payload['precio'] = precio_float
                payload['precio_original'] = precio_float
                
            if payload:
                conn.table("libros").update(payload).eq("libro_id", libro_id).execute()
                exitos_actualizados += 1
        except Exception as e:
            errores.append(f"Fallo al actualizar '{item['Título']}' (ID: {item['ID']}): {e}")
            
    progreso.empty()
    st.cache_data.clear()
    return exitos_creados, exitos_actualizados, errores

def mostrar_carga_editoriales():
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
        
        up_planeta = st.file_uploader("Sube el catálogo de Planeta (.xlsx):", type=["xlsx"], key="up_planeta")
        if up_planeta:
            df_p = pd.read_excel(up_planeta, engine="openpyxl")
            
            if st.button("🔍 Previsualizar Simulación de Cambios (Planeta)", type="secondary", use_container_width=True):
                with st.spinner("Simulando cambios y analizando duplicados..."):
                    creados_p, actualizados_p, errores_p = simular_upsert_editorial(df_p, "PLANETA", pct_p, val_p, force_p)
                    st.session_state['p_creados'] = creados_p
                    st.session_state['p_actualizados'] = actualizados_p
                    st.session_state['p_errores'] = errores_p
                    
            if 'p_creados' in st.session_state:
                st.markdown("### 🔍 Previsualización de Cambios Simulados")
                c1, c2 = st.columns(2)
                c1.metric("Libros Nuevos por Crear", len(st.session_state['p_creados']))
                c2.metric("Libros Existentes por Enriquecer", len(st.session_state['p_actualizados']))
                
                with st.expander("📚 Ver Detalle de Libros Nuevos por Crear", expanded=True):
                    st.dataframe(pd.DataFrame(st.session_state['p_creados']), use_container_width=True, hide_index=True) if st.session_state['p_creados'] else st.info("No hay libros nuevos para crear.")
                    
                with st.expander("🔧 Ver Detalle de Libros Existentes por Enriquecer", expanded=True):
                    st.dataframe(pd.DataFrame(st.session_state['p_actualizados']), use_container_width=True, hide_index=True) if st.session_state['p_actualizados'] else st.info("No hay libros existentes por enriquecer.")
                
                # --- SISTEMA DE CONFIRMACIÓN DE SEGURIDAD ---
                st.markdown("---")
                st.markdown("#### 🔒 Confirmación de Seguridad Obligatoria")
                palabra_seguridad = st.text_input("Escribe la palabra **PROCEDER** en mayúsculas para confirmar los cambios:", key="confirm_p")
                
                if st.button("🚨 EJECUTAR CARGA MASIVA EN VIVO (PLANETA)", type="primary", use_container_width=True, disabled=(palabra_seguridad != "PROCEDER")):
                    exitos_c, exitos_u, errores_v = ejecutar_upsert_editorial_seguro(
                        st.session_state['p_creados'], 
                        st.session_state['p_actualizados'], 
                        "PLANETA", pct_p, val_p, force_p
                    )
                    st.success(f"🎉 Carga masiva completada: Se crearon {exitos_c} libros y se enriquecieron {exitos_u} exitosamente.")
                    st.balloons()
                    del st.session_state['p_creados']
                    del st.session_state['p_actualizados']
                    time.sleep(2)
                    st.rerun()

    # ================= PESTAÑA: URANO =================
    with tab_urano:
        st.subheader("Carga Masiva - Urano World")
        col_u1, col_u2 = st.columns(2)
        pct_u = col_u1.number_input("Descuento Comercial de Urano (%):", min_value=0.0, max_value=100.0, value=35.0, step=1.0, key="pct_u")
        val_u = col_u2.number_input("Valor Fijo de Utilidad ($):", min_value=0, value=5000, step=500, key="val_u")
        
        force_u = st.toggle("🚨 Forzar actualización de Costo y Precio de Venta en libros existentes", value=False, key="force_u")
        
        up_urano = st.file_uploader("Sube el catálogo de Urano (.xlsx):", type=["xlsx"], key="up_urano")
        if up_urano:
            df_u = pd.read_excel(up_urano, engine="openpyxl")
            
            if st.button("🔍 Previsualizar Simulación de Cambios (Urano)", type="secondary", use_container_width=True):
                with st.spinner("Simulando cambios y analizando duplicados..."):
                    creados_u, actualizados_u, errores_u = simular_upsert_editorial(df_u, "URANO", pct_u, val_u, force_u)
                    st.session_state['u_creados'] = creados_u
                    st.session_state['u_actualizados'] = actualizados_u
                    st.session_state['u_errores'] = errores_u
                    
            if 'u_creados' in st.session_state:
                st.markdown("### 🔍 Previsualización de Cambios Simulados")
                c1, c2 = st.columns(2)
                c1.metric("Libros Nuevos por Crear", len(st.session_state['u_creados']))
                c2.metric("Libros Existentes por Enriquecer", len(st.session_state['u_actualizados']))
                
                with st.expander("📚 Ver Detalle de Libros Nuevos por Crear", expanded=True):
                    st.dataframe(pd.DataFrame(st.session_state['u_creados']), use_container_width=True, hide_index=True) if st.session_state['u_creados'] else st.info("No hay libros nuevos para crear.")
                    
                with st.expander("🔧 Ver Detalle de Libros Existentes por Enriquecer", expanded=True):
                    st.dataframe(pd.DataFrame(st.session_state['u_actualizados']), use_container_width=True, hide_index=True) if st.session_state['u_actualizados'] else st.info("No hay libros existentes por enriquecer.")
                
                # --- SISTEMA DE CONFIRMACIÓN DE SEGURIDAD ---
                st.markdown("---")
                st.markdown("#### 🔒 Confirmación de Seguridad Obligatoria")
                palabra_seguridad_u = st.text_input("Escribe la palabra **PROCEDER** en mayúsculas para confirmar los cambios:", key="confirm_u")
                
                if st.button("🚨 EJECUTAR CARGA MASIVA EN VIVO (URANO)", type="primary", use_container_width=True, disabled=(palabra_seguridad_u != "PROCEDER")):
                    exitos_c, exitos_u, errores_v = ejecutar_upsert_editorial_seguro(
                        st.session_state['u_creados'], 
                        st.session_state['u_actualizados'], 
                        "URANO", pct_u, val_u, force_u
                    )
                    st.success(f"🎉 Carga masiva completada: Se crearon {exitos_c} libros y se enriquecieron {exitos_u} exitosamente.")
                    st.balloons()
                    del st.session_state['u_creados']
                    del st.session_state['u_actualizados']
                    time.sleep(2)
                    st.rerun()

if __name__ == "__main__":
    mostrar_carga_editoriales()