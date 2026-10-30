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

PALABRAS_SEGURIDAD_RANDOM = [
    # Nombres de mascotas divertidos
    "HARRY", "TRUFA", "PETER", "CONO", "PRI", "GUAGUITO", "CACHORRA",
    
    # Divertidas y caóticas
    "APOCALIPSIS", "BOMBA", "TORNADO", "TURBO", "MAGIA", 
    "MUTACION", "CAOS", "MATRIZ", "VORTEX", "CHISPA", 
    "CATACLISMO", "FUSION", "ESTALLIDO", "RAYO", "COHETE",
    "SUPERNOVA", "AVALANCHA", "TERREMOTO", "MISIL", "REACTOR",
    
    # Objetos y conceptos cotidianos pero graciosos
    "PLATANO", "BURBUJA", "GALAXIA", "JARRON", "PINGUINO", 
    "BOTIQUIN", "PATITO", "KRAKEN", "CIBORG", "HAMBURGUESA",
    "ZOMBIE", "FANTASMA", "GALLETA", "NINJA", "PIRATA", 
    "ROBOT", "UNICORNIO", "FOGATA", "BANDIDO",
    
    # Literatura y librería con chispa
    "BIBLIOTECA", "IMPRENTA", "BESTSELLER", "MANUSCRITO", "ESTANTERIA", 
    "BOOKLOVER", "PROLOGO", "SINOPSIS", "EPILOGO", "TOMO", 
    "FOLIO", "RESEÑA", "TAPA", "LOMO", "EDICION", 
    "EJEMPLAR", "AUTOR", "PAGINAS", "CAPITULO", "TINTA",
    
    # Acciones y conceptos dinámicos
    "EJECUTAR", "RESTAURAR", "FORZAR", "SOPORTE", "INGRESAR", 
    "DESPACHO", "CATALOGO", "EDITORIAL", "ALBA", "LIBRERIA"
]

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

def normalizar_para_cruce(texto):
    clean = limpiar_texto_para_busqueda(texto)
    return re.sub(r'[^A-Z0-9\s]', '', clean).strip()

def autores_coinciden_flexible(autor_db, autor_import):
    key_db = set(normalizar_para_cruce(autor_db).split())
    key_import = set(normalizar_para_cruce(autor_import).split())
    
    interseccion = key_db.intersection(key_import)
    
    if len(interseccion) >= 2 or (len(key_db) > 0 and any(any(abs(len(a) - len(b)) <= 2 and (a[:4] == b[:4]) for b in key_import) for a in key_db)):
        return True
    return False

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
            
            titulo_key_saneado = normalizar_para_cruce(titulo_saneado)
            
            if not titulo_key_saneado:
                continue
                
            if editorial_tipo == "PLANETA":
                # 🚫 REGLA DE EXCLUSIÓN 1: Omitir formatos de Planeta restringidos del catálogo por completo
                formato_raw = row.get('FORMATO')
                f_upper_formato = limpiar_texto_para_busqueda(formato_raw)
                restringidos_formato = ["LOMO VISTO", "TODO CARTON", "PACK", "LIBRO DE BAN", "LIBRO DE TELA", "CALENDARIO"]
                if any(k in f_upper_formato for k in restringidos_formato):
                    continue  # Descartar libro por completo, nunca se sube a la BD
                    
                precio_lista = sanear_numero(row.get('PVP_ACT', 0.0))
                costo_base = (precio_lista - (precio_lista * (pct_descuento / 100.0))) * 1.19
                precio_venta = aproximar_cien_superior(costo_base + valor_fijo)
                tematica = limpiar_texto_para_busqueda(str(row.get('TEMÁTICA WEB', '')))
                genero_final = DICCIONARIO_PLANETA_GENEROS.get(tematica, None)
                
                # 🚫 REGLA DE EXCLUSIÓN 2: Omitir libros de No Ficción por completo del catálogo
                if genero_final == "NO FICCION":
                    continue  # Descartar libro por completo, nunca se sube a la BD
                    
                encuadernacion = normalizar_encuadernacion_planeta(formato_raw)
            else: # URANO
                precio_neto = sanear_numero(row.get('Precio Neto', 0.0))
                costo_base = (precio_neto - (precio_neto * (pct_descuento / 100.0))) * 1.19
                precio_venta = aproximar_cien_superior(costo_base + valor_fijo)
                genero_final = None
                encuadernacion = None
            
            # Búsqueda Inteligente de Doble Factor
            match_libro = None
            for b in db_libros:
                titulo_db_saneado = normalizar_para_cruce(b['titulo'])
                if titulo_db_saneado == titulo_key_saneado:
                    if autores_coinciden_flexible(b.get('autor', ''), autor_saneado):
                        match_libro = b
                        break
            
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
                        "ISBN": isbn_saneado if "ISBN" in campos_cambiados else match_libro.get('isbn'),
                        "Género": genero_final if "Género" in campos_cambiados else match_libro.get('genero'),
                        "Encuadernación": encuadernacion if "Encuadernación" in campos_cambiados else match_libro.get('encuadernacion'),
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
                    "Encuadernación": encuadernacion,
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
                "encuadernacion": item['Encuadernación'],
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
            
            if "ISBN" in item['Cambios a Aplicar'] and pd.notna(item.get('ISBN')): payload['isbn'] = item['ISBN']
            if "Autor" in item['Cambios a Aplicar'] and pd.notna(item.get('Autor')): payload['autor'] = item['Autor']
            if "Género" in item['Cambios a Aplicar'] and pd.notna(item.get('Género')): payload['genero'] = item['Género']
            if "Encuadernación" in item['Cambios a Aplicar'] and pd.notna(item.get('Encuadernación')): payload['encuadernacion'] = item['Encuadernación']
            payload['editorial'] = editorial_tipo
            
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

def color_enriquecer_existentes(data):
    """
    Colorea en amarillo pastel suave las celdas que van a sufrir cambios
    según lo especificado en la columna 'Cambios a Aplicar'.
    """
    estilos = pd.DataFrame('', index=data.index, columns=data.columns)
    color_amarillo_pastel = 'background-color: #fff9c4; color: #5d4037; font-weight: bold;'
    
    for idx, row in data.iterrows():
        cambios = str(row.get('Cambios a Aplicar', '')).split(', ')
        for cambio in cambios:
            col_target = None
            if cambio == "ISBN": col_target = "ISBN"
            elif cambio == "Autor": col_target = "Autor"
            elif cambio == "Género": col_target = "Género"
            elif cambio == "Encuadernación": col_target = "Encuadernación"
            elif cambio == "Costo": col_target = "Nuevo Costo"
            elif cambio == "Precio": col_target = "Nuevo Precio"
            
            if col_target and col_target in data.columns:
                estilos.loc[idx, col_target] = color_amarillo_pastel
                
    return estilos

def normalizar_encuadernacion_planeta(formato_raw):
    if pd.isna(formato_raw):
        return None
    f_upper = limpiar_texto_para_busqueda(formato_raw)
    if not f_upper:
        return None
        
    if "RUSTICA" in f_upper or "RUSTICO" in f_upper:
        return "TAPA BLANDA"
    if "DURA" in f_upper or "CARTONE" in f_upper or "CARTON" in f_upper:
        return "TAPA DURA"
    if "BOLSILLO" in f_upper or "FLEXIBLE" in f_upper:
        return "BOLSILLO"
        
    return f_upper

def limpiar_cache_previsualizaciones():
    keys_to_delete = ['p_creados', 'p_actualizados', 'p_random_token', 'u_creados', 'u_actualizados', 'u_random_token']
    for k in keys_to_delete:
        if k in st.session_state:
            del st.session_state[k]

def mostrar_carga_editoriales():
    # --- EXPLICACIÓN COLAPSABLE (UX GUIDELINE) ---
    with st.expander("📖 Manual y Guía de Ingesta Inteligente de Editoriales (Fórmulas y Columnas)", expanded=False):
        st.markdown("""
        ### ⚙️ ¿Cómo funciona este módulo?
        Este procesador lee el catálogo de las distribuidoras y realiza un **Upsert cruzado** inteligente contra tu base de datos de Supabase, resolviendo automáticamente las diferencias de escritura tradicionales sin corromper tu información.
        
        #### 🧠 Inteligencia de Homologación:
        * **Reordenamiento de Autores:** Convierte automáticamente formatos invertidos como `POSTON, ASHLEY` $\\rightarrow$ `ASHLEY POSTON`.
        * **Limpieza de Títulos:** Sanea artículos finales como `VERANO QUE NUNCA FUE, EL` $\\rightarrow$ `EL VERANO QUE NUNCA FUE`. También remueve sufijos comerciales chilenos de forma transparente como `(CHI)`.
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
            **📋 Columnas relevantes para PLANETA:**
            * `TITULO`
            * `AUTOR`
            * `EAN` (ISBN)
            * `FORMATO` (Encuadernación)
            * `TEMÁTICA WEB` (Género)
            * `PVP_ACT` (Precio de lista)
            """)
        with col_m2:
            st.markdown("""
            **📋 Columnas relevantes para URANO:**
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
        
        force_p = st.toggle("🚨 Forzar actualización de Costo y Precio de Venta en libros existentes", value=False, key="force_p", on_change=limpiar_cache_previsualizaciones)
        
        up_planeta = st.file_uploader("Sube el catálogo de Planeta (.xlsx):", type=["xlsx"], key="up_planeta")
        if up_planeta:
            df_p = pd.read_excel(up_planeta, engine="openpyxl")
            
            if st.button("🔍 Previsualizar Simulación de Cambios (Planeta)", type="secondary", use_container_width=True):
                with st.spinner("Simulando cambios y analizando duplicados..."):
                    creados_p, actualizados_p, errores_p = simular_upsert_editorial(df_p, "PLANETA", pct_p, val_p, force_p)
                    st.session_state['p_creados'] = creados_p
                    st.session_state['p_actualizados'] = actualizados_p
                    st.session_state['p_errores'] = errores_p
                    import random
                    st.session_state['p_random_token'] = random.choice(PALABRAS_SEGURIDAD_RANDOM)
                    
            if 'p_creados' in st.session_state:
                st.markdown("### 🔍 Previsualización de Cambios Simulados")
                c1, c2 = st.columns(2)
                c1.metric("Libros Nuevos por Crear", len(st.session_state['p_creados']))
                c2.metric("Libros Existentes por Enriquecer", len(st.session_state['p_actualizados']))
                
                with st.expander("📚 Ver Detalle de Libros Nuevos por Crear", expanded=True):
                    st.dataframe(pd.DataFrame(st.session_state['p_creados']), use_container_width=True, hide_index=True) if st.session_state['p_creados'] else st.info("No hay libros nuevos para crear.")
                    
                with st.expander("🔧 Ver Detalle de Libros Existentes por Enriquecer", expanded=True):
                    if st.session_state['p_actualizados']:
                        df_act_styled = pd.DataFrame(st.session_state['p_actualizados'])
                        st.dataframe(df_act_styled.style.apply(color_enriquecer_existentes, axis=None), use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay libros existentes por enriquecer.")
                
                # --- SISTEMA DE CONFIRMACIÓN DE SEGURIDAD ---
                st.markdown("---")
                st.markdown("#### 🔒 Confirmación de Seguridad Obligatoria")
                token_esperado_p = st.session_state.get('p_random_token', 'CONFIRMAR')
                
                palabra_seguridad = st.text_input(
                    f"Para confirmar, digite exactamente la palabra **{token_esperado_p}** en mayúsculas:", 
                    key="confirm_p",
                    placeholder=f"Escribe {token_esperado_p} aquí..."
                )
                
                if st.button("🚨 EJECUTAR CARGA MASIVA EN VIVO (PLANETA)", type="primary", use_container_width=True, disabled=(palabra_seguridad != token_esperado_p)):
                    exitos_c, exitos_u, errores_v = ejecutar_upsert_editorial_seguro(
                        st.session_state['p_creados'], 
                        st.session_state['p_actualizados'], 
                        "PLANETA", pct_p, val_p, force_p
                    )
                    st.success(f"🎉 Carga masiva completada: Se crearon {exitos_c} libros y se enriquecieron {exitos_u} exitosamente.")
                    st.balloons()
                    del st.session_state['p_creados']
                    del st.session_state['p_actualizados']
                    if 'p_random_token' in st.session_state: del st.session_state['p_random_token']
                    time.sleep(2)
                    st.rerun()

    # ================= PESTAÑA: URANO =================
    with tab_urano:
        st.subheader("Carga Masiva - Urano World")
        col_u1, col_u2 = st.columns(2)
        pct_u = col_u1.number_input("Descuento Comercial de Urano (%):", min_value=0.0, max_value=100.0, value=35.0, step=1.0, key="pct_u")
        val_u = col_u2.number_input("Valor Fijo de Utilidad ($):", min_value=0, value=5000, step=500, key="val_u")
        
        force_u = st.toggle("🚨 Forzar actualización de Costo y Precio de Venta en libros existentes", value=False, key="force_u", on_change=limpiar_cache_previsualizaciones)
        
        up_urano = st.file_uploader("Sube el catálogo de Urano (.xlsx):", type=["xlsx"], key="up_urano")
        if up_urano:
            df_u = pd.read_excel(up_urano, engine="openpyxl")
            
            if st.button("🔍 Previsualizar Simulación de Cambios (Urano)", type="secondary", use_container_width=True):
                with st.spinner("Simulando cambios y analizando duplicados..."):
                    creados_u, actualizados_u, errores_u = simular_upsert_editorial(df_u, "URANO", pct_u, val_u, force_u)
                    st.session_state['u_creados'] = creados_u
                    st.session_state['u_actualizados'] = actualizados_u
                    st.session_state['u_errores'] = errores_u
                    import random
                    st.session_state['u_random_token'] = random.choice(PALABRAS_SEGURIDAD_RANDOM)
                    
            if 'u_creados' in st.session_state:
                st.markdown("### 🔍 Previsualización de Cambios Simulados")
                c1, c2 = st.columns(2)
                c1.metric("Libros Nuevos por Crear", len(st.session_state['u_creados']))
                c2.metric("Libros Existentes por Enriquecer", len(st.session_state['u_actualizados']))
                
                with st.expander("📚 Ver Detalle de Libros Nuevos por Crear", expanded=True):
                    st.dataframe(pd.DataFrame(st.session_state['u_creados']), use_container_width=True, hide_index=True) if st.session_state['u_creados'] else st.info("No hay libros nuevos para crear.")
                    
                with st.expander("🔧 Ver Detalle de Libros Existentes por Enriquecer", expanded=True):
                    if st.session_state['u_actualizados']:
                        df_act_styled_u = pd.DataFrame(st.session_state['u_actualizados'])
                        st.dataframe(df_act_styled_u.style.apply(color_enriquecer_existentes, axis=None), use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay libros existentes por enriquecer.")
                
                # --- SISTEMA DE CONFIRMACIÓN DE SEGURIDAD ---
                st.markdown("---")
                st.markdown("#### 🔒 Confirmación de Seguridad Obligatoria")
                token_esperado_u = st.session_state.get('u_random_token', 'CONFIRMAR')
                
                palabra_seguridad_u = st.text_input(
                    f"Para confirmar, digite exactamente la palabra \*\*{token_esperado_u}\*\* en mayúsculas:", 
                    key="confirm_u",
                    placeholder=f"Escribe {token_esperado_u} aquí..."
                )
                
                if st.button("🚨 EJECUTAR CARGA MASIVA EN VIVO (URANO)", type="primary", use_container_width=True, disabled=(palabra_seguridad_u != token_esperado_u)):
                    exitos_c, exitos_u, errores_v = ejecutar_upsert_editorial_seguro(
                        st.session_state['u_creados'], 
                        st.session_state['u_actualizados'], 
                        "URANO", pct_u, val_u, force_u
                    )
                    st.success(f"🎉 Carga masiva completada: Se crearon {exitos_c} libros y se enriquecieron {exitos_u} exitosamente.")
                    st.balloons()
                    del st.session_state['u_creados']
                    del st.session_state['u_actualizados']
                    if 'u_random_token' in st.session_state: del st.session_state['u_random_token']
                    time.sleep(2)
                    st.rerun()

if __name__ == "__main__":
    mostrar_carga_editoriales()