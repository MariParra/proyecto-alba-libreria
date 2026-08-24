from PIL import Image, ImageDraw, ImageFont
import io
import requests
import os
import urllib.request
import re

def asegurar_fuentes():
    """Descarga las fuentes base desde Google Fonts si no existen en el sistema."""
    if not os.path.exists("assets"):
        os.makedirs("assets")
    
    fuentes = {
        "Montserrat-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Bold.ttf",
        "Montserrat-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Regular.ttf"
    }
    
    for nombre, url in fuentes.items():
        ruta = os.path.join("assets", nombre)
        if not os.path.exists(ruta):
            try:
                print(f"Descargando fuente {nombre}...")
                urllib.request.urlretrieve(url, ruta)
            except Exception as e:
                pass

def asegurar_fuente_google(nombre_fuente):
    """
    Descarga dinámicamente cualquier fuente TrueType (.ttf) desde el repositorio
    oficial de Google Fonts en GitHub y la almacena en caché localmente.
    """
    if not os.path.exists("assets"):
        os.makedirs("assets")
        
    nombre_limpio = nombre_fuente.strip().replace(" ", "")
    ruta_font = os.path.join("assets", f"{nombre_limpio}.ttf")
    
    if os.path.exists(ruta_font):
        return ruta_font

    formatos_url = [
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_limpio}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_fuente.replace(' ', '')}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/apache/{nombre_limpio.lower()}/{nombre_limpio}-Regular.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{nombre_limpio.lower()}/{nombre_limpio}.ttf"
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

def hex_to_rgb(hex_str):
    """Convierte un string de color HEX (#RRGGBB) a una tupla RGB (R, G, B) de forma segura."""
    if not hex_str or not isinstance(hex_str, str):
        return (255, 255, 255)
    hex_str = hex_str.strip().lstrip('#')
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (255, 255, 255)

def obtener_fuente(nombre_fuente, tamanio, bold=False, italic=False):
    """
    Carga de forma dinámica y resiliente una fuente tipográfica premium con estilos aplicados.
    """
    nombre_limpio = nombre_fuente.strip()
    ruta_google = asegurar_fuente_google(nombre_limpio)
    
    candidatas = []
    if ruta_google:
        candidatas.append(ruta_google)
        
    candidatas.extend([
        "assets/Montserrat-Bold.ttf" if bold else "assets/Montserrat-Regular.ttf",
        "/usr/share/fonts/GoogleSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "Arial.ttf"
    ])
    
    for ruta in candidatas:
        try:
            if os.path.exists(ruta) or not ruta.endswith('.ttf'):
                return ImageFont.truetype(ruta, tamanio)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=tamanio)
    except:
        return ImageFont.load_default()

def dividir_texto_en_lineas(texto, max_chars=14):
    """Divide de forma inteligente el título de un libro en 2 líneas para evitar desbordamientos."""
    palabras = texto.split()
    lineas = []
    linea_actual = []
    longitud_actual = 0
    for palabra in palabras:
        if longitud_actual + len(palabra) + (1 if linea_actual else 0) <= max_chars:
            linea_actual.append(palabra)
            longitud_actual += len(palabra) + (1 if len(linea_actual) > 1 else 0)
        else:
            if linea_actual:
                lineas.append(" ".join(linea_actual))
            linea_actual = [palabra]
            longitud_actual = len(palabra)
            if len(lineas) >= 2:
                break
    if linea_actual and len(lineas) < 2:
        lineas.append(" ".join(linea_actual))
    
    words_joined = " ".join(palabras)
    joined_lines = " ".join(lineas)
    if len(words_joined) > len(joined_lines):
        if len(lineas) == 2:
            lineas = lineas[:11] + ".."
        elif len(lineas) == 1:
            lineas[0] = lineas[0][:11] + ".."
            
    return lineas

def generar_collage_marketing(lista_libros_chunk, url_base_supabase, titulo_header="NOVEDADES", config_diseno=None):
    """
    Genera un collage de marketing 1080x1920 con retícula dinámica simétrica y adaptativa.
    Centra automáticamente los elementos si la última fila queda con espacios sobrantes.
    """
    if config_diseno is None:
        config_diseno = {
            "font_family_header": "Montserrat",
            "font_family_books": "Montserrat",
            "bold_header": True,
            "italic_header": False,
            "tamanio_header": 45,
            "tamanio_libros": 20,
            "color_bg": "#FDE8F3",
            "color_card": "#FFFFFF",
            "color_shadow": "#F4CCD4",
            "color_primary": "#7C0C3F",
            "color_accent": "#DB2777",
            "color_muted": "#BA96A5",
            "color_badge_bg": "#DB2777",
            "color_badge_text": "#FFFFFF",
            "color_header_rect_bg": "#FFFFFF",
            "color_header_rect_border": "#7C0C3F",
            "header_rect_border_width": 2,
            "header_rect_radius": 20,
            "header_pad_x": 40,
            "header_pad_y": 20
        }

    try:
        W, H = (1080, 1920)
        
        # --- 🎨 PALETA AESTHETIC DE ROSADOS Y FRAMBUESAS PREMIUM ---
        BG_COLOR = hex_to_rgb(config_diseno.get("color_bg", "#FDE8F3"))
        CARD_COLOR = hex_to_rgb(config_diseno.get("color_card", "#FFFFFF"))
        SHADOW_COLOR = hex_to_rgb(config_diseno.get("color_shadow", "#F4CCD4"))
        PRIMARY_COLOR = hex_to_rgb(config_diseno.get("color_primary", "#7C0C3F"))
        ACCENT_COLOR = hex_to_rgb(config_diseno.get("color_accent", "#DB2777"))
        MUTED_COLOR = hex_to_rgb(config_diseno.get("color_muted", "#BA96A5"))
        BADGE_BG = hex_to_rgb(config_diseno.get("color_badge_bg", "#DB2777"))
        BADGE_TEXT = hex_to_rgb(config_diseno.get("color_badge_text", "#FFFFFF"))
        HEADER_RECT_BG = hex_to_rgb(config_diseno.get("color_header_rect_bg", "#FFFFFF"))
        HEADER_RECT_BORDER = hex_to_rgb(config_diseno.get("color_header_rect_border", "#7C0C3F"))
        HEADER_RECT_BORDER_W = int(config_diseno.get("header_rect_border_width", 2))
        HEADER_RECT_RADIUS = int(config_diseno.get("header_rect_radius", 20))
        HEADER_PAD_X = int(config_diseno.get("header_pad_x", 40))
        HEADER_PAD_Y = int(config_diseno.get("header_pad_y", 20))
        
        font_header = obtener_fuente(
            config_diseno.get("font_family_header", "Montserrat"), 
            int(config_diseno.get("tamanio_header", 45)),
            bold=config_diseno.get("bold_header", True),
            italic=config_diseno.get("italic_header", False)
        )
        font_titulo = obtener_fuente(
            config_diseno.get("font_family_books", "Montserrat"), 
            int(config_diseno.get("tamanio_libros", 20)),
            bold=True
        )
        font_precio = obtener_fuente(config_diseno.get("font_family_books", "Montserrat"), 42, bold=True)
        font_tachado = obtener_fuente(config_diseno.get("font_family_books", "Montserrat"), 28, bold=True)
        font_badge = obtener_fuente(config_diseno.get("font_family_books", "Montserrat"), 18, bold=True)

        # Cargar imagen de fondo oficial desde Supabase
        BG_URL = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/base.png"
        try:
            req = urllib.request.Request(BG_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as response_bg:
                img = Image.open(io.BytesIO(response_bg.read())).convert('RGB')
            img = img.resize((W, H), Image.Resampling.LANCZOS)
        except Exception:
            img = Image.new('RGB', (W, H), color=BG_COLOR)
            
        draw = ImageDraw.Draw(img)

        # 1. Título de género con tamaño y bordes adaptables
        titulo_limpio = re.sub(r"\s*\(\d+[\/\-]\d+\)", "", titulo_header).strip().upper()
        try:
            bbox_header = draw.textbbox((0, 0), titulo_limpio, font=font_header)
            text_w = bbox_header - bbox_header[0]
            text_h = bbox_header - bbox_header
            
            box_w = text_w + HEADER_PAD_X * 2
            box_h = text_h + HEADER_PAD_Y * 2
            
            box_x1 = (W - box_w) / 2
            box_y1 = 60
            box_x2 = box_x1 + box_w
            box_y2 = box_y1 + box_h
            
            # Sombra y Rectángulo Principal
            draw.rounded_rectangle([box_x1 + 8, box_y1 + 8, box_x2 + 8, box_y2 + 8], radius=HEADER_RECT_RADIUS, fill=SHADOW_COLOR)
            draw.rounded_rectangle([box_x1, box_y1, box_x2, box_y2], radius=HEADER_RECT_RADIUS, fill=HEADER_RECT_BG)
            
            if HEADER_RECT_BORDER_W > 0:
                draw.rounded_rectangle(
                    [box_x1, box_y1, box_x2, box_y2], 
                    radius=HEADER_RECT_RADIUS, 
                    outline=HEADER_RECT_BORDER, 
                    width=HEADER_RECT_BORDER_W
                )
            
            draw.text((W/2, box_y1 + box_h/2), titulo_limpio, font=font_header, fill=PRIMARY_COLOR, anchor="mm")
        except Exception:
            pass

        # --- 📐 RETÍCULA ADAPTATIVA INTELIGENTE ---
        n_libros = len(lista_libros_chunk)
        
        if n_libros == 1:
            cols = 1
            start_y = 520
            cell_w = 600
            cell_h = 750
            x_margin = (W - cell_w) / 2
            y_margin = 0
            img_height = 420
        elif n_libros <= 4:
            cols = 2
            start_y = 400
            cell_w = 420
            cell_h = 560
            x_margin = (W - cell_w * 2) / 3
            y_margin = 60
            img_height = 320
        elif n_libros <= 8:
            cols = 2
            start_y = 230
            cell_w = 420
            cell_h = 360
            x_margin = (W - cell_w * 2) / 3
            y_margin = 40
            img_height = 170
        else:
            cols = 3
            start_y = 190
            cell_w = 313
            cell_h = 420
            x_margin = 35
            y_margin = 40
            img_height = 220

        # Dibujo secuencial de tarjetas
        for i, libro in enumerate(lista_libros_chunk):
            if i >= 12: 
                break 

            row_idx = i // cols
            col_idx = i % cols

            # =========================================================================
            # 🌟 MEJORA UX CLAVE: CENTRADO DE FILA SI SOBRA ESPACIO (Última Fila)
            # =========================================================================
            # Calculamos cuántos elementos habrá en la fila actual
            elementos_en_esta_fila = min(cols, n_libros - row_idx * cols)
            
            # Ancho total ocupado por las tarjetas y sus respectivos márgenes en esta fila
            ancho_ocupado_fila = elementos_en_esta_fila * cell_w + (elementos_en_esta_fila - 1) * x_margin
            
            # Margen inicial centrado para esta fila
            x_inicio_centrado = (W - ancho_ocupado_fila) / 2
            
            # Coordenada X final corregida y centrada
            x_card = x_inicio_centrado + col_idx * (cell_w + x_margin)
            y_card = start_y + row_idx * (cell_h + y_margin)
            # =========================================================================

            try:
                draw.rounded_rectangle([x_card + 12, y_card + 12, x_card + cell_w + 12, y_card + cell_h + 12], radius=25, fill=SHADOW_COLOR)
                draw.rounded_rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], radius=25, fill=CARD_COLOR)
            except AttributeError:
                draw.rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], fill=CARD_COLOR)

            y_img = y_card + 20
            try:
                url_portada = f"{url_base_supabase}{libro['libro_id']}.jpg"
                response = requests.get(url_portada, stream=True, timeout=5)
                response.raise_for_status()
                portada_img = Image.open(response.raw).convert("RGBA")
                
                portada_img.thumbnail((int(cell_w - 24), img_height)) 
                x_img = x_card + (cell_w - portada_img.width) / 2
                
                img.paste(portada_img, (int(x_img), int(y_img)), portada_img)
            except Exception:
                draw.rectangle([x_card + 24, y_img, x_card + cell_w - 24, y_img + img_height], fill=(245, 238, 241))

            if int(libro.get('stock', 0)) > 0:
                texto_badge = " DISPONIBLE "
                try:
                    bbox_badge = draw.textbbox((0, 0), texto_badge, font=font_badge)
                    ancho_badge = bbox_badge - bbox_badge[0]
                    alto_badge = 32
                    
                    x_badge = x_card + (cell_w - ancho_badge) / 2
                    y_badge_pos = y_card - 15 
                    
                    draw.rounded_rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], radius=15, fill=BADGE_BG)
                    draw.text((x_badge + ancho_badge/2, y_badge_pos + alto_badge/2), texto_badge, font=font_badge, fill=BADGE_TEXT, anchor="mm")
                except Exception:
                    pass

            max_c = 18 if n_libros > 4 else 26
            lineas_titulo = dividir_texto_en_lineas(libro['titulo'].upper(), max_chars=max_c)
            
            y_titulo_start = y_card + (cell_h * 0.68)
            if len(lineas_titulo) == 2:
                y_titulo_start -= 12
                
            for idx_linea, linea in enumerate(lineas_titulo):
                try:
                    draw.text((x_card + cell_w/2, y_titulo_start + idx_linea * 24), linea, font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            y_precios = y_card + (cell_h * 0.82)
            if precio_float < precio_orig_float:
                texto_orig = f"${precio_orig_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_precios), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                    bbox_orig = draw.textbbox((0, 0), texto_orig, font=font_tachado)
                    ancho_orig = bbox_orig - bbox_orig[0]
                    draw.line((x_card + cell_w/2 - ancho_orig/2, y_precios - 8, x_card + cell_w/2 + ancho_orig/2, y_precios - 8), fill=MUTED_COLOR, width=3)
                except ValueError:
                    pass
                
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_precios + 45), texto_final, font=font_precio, fill=ACCENT_COLOR, anchor="ms")
                except ValueError:
                    pass
            else:
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_precios + 25), texto_final, font=font_precio, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

        return img
        
    except Exception as e:
        print(f"Error en motor de collage: {e}")
        return None