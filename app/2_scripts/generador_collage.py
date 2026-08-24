from PIL import Image, ImageDraw, ImageFont
import io
import requests
import os
import urllib.request
import re

def asegurar_fuentes():
    """Descarga las fuentes desde Google Fonts si no existen."""
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

def obtener_fuente(tamanio, bold=False):
    """
    Carga de forma dinámica y resiliente una fuente de alta calidad
    del sistema, de la caché local o un fallback del contenedor de Streamlit.
    """
    candidatas = [
        "assets/Montserrat-Bold.ttf" if bold else "assets/Montserrat-Regular.ttf",
        "/usr/share/fonts/GoogleSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "Arial.ttf"
    ]
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
    """
    Divide de forma inteligente el título de un libro en 2 líneas
    para evitar desbordamientos y colisiones en la retícula.
    """
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
    
    # Añadimos puntos suspensivos si quedaron palabras fuera
    words_joined = " ".join(palabras)
    joined_lines = " ".join(lineas)
    if len(words_joined) > len(joined_lines):
        if len(lineas) == 2:
            lineas[1] = lineas[1][:11] + ".."
        elif len(lineas) == 1:
            lineas[0] = lineas[0][:11] + ".."
            
    return lineas

def generar_collage_marketing(lista_libros_chunk, url_base_supabase, titulo_header="NOVEDADES"):
    """
    Genera una imagen 1080x1920 Premium con fondo de marca Alba Librería:
    Sombras 3D, tipografía Bold grande, paleta rosada y portadas maximizadas (hasta 12 libros).
    """
    asegurar_fuentes()
    
    try:
        W, H = (1080, 1920)
        
        # --- 🎨 PALETA AESTHETIC DE ROSADOS Y FRAMBUESAS PREMIUM ---
        BG_COLOR = (253, 232, 243)      # Fondo Fallback
        CARD_COLOR = (255, 255, 255)    # Tarjetas Blancas
        SHADOW_COLOR = (244, 204, 220)  # Sombra Rosa Pastel para efecto 3D
        PRIMARY_COLOR = (124, 12, 63)   # Títulos: Frambuesa / Vino Profundo (¡Cero Azul!)
        ACCENT_COLOR = (219, 39, 119)   # Precios de oferta: Fucsia / Rosa Fuerte
        MUTED_COLOR = (186, 150, 165)   # Precios original tachado: Rosa Muted
        BADGE_BG = (219, 39, 119)        # Etiqueta "Disponible": Fucsia vibrante
        BADGE_TEXT = (255, 255, 255)    # Texto etiqueta: Blanco
        
        # --- 🔠 FUENTES GEOMÉTRICAS GRANDES Y ATRACTIVAS ---
        font_header = obtener_fuente(45, bold=True) 
        font_titulo = obtener_fuente(20, bold=True)  # Ajustado a 20 para ser súper legible en 2 líneas
        font_precio = obtener_fuente(42, bold=True)
        font_tachado = obtener_fuente(28, bold=True)
        font_badge = obtener_fuente(18, bold=True) 

        # --- 2) CARGAR IMAGEN DE FONDO DE MARCA DESDE SUPABASE ---
        BG_URL = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/base.png"
        try:
            req = urllib.request.Request(BG_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response_bg:
                img = Image.open(io.BytesIO(response_bg.read())).convert('RGB')
            img = img.resize((W, H), Image.Resampling.LANCZOS)
        except Exception as e:
            img = Image.new('RGB', (W, H), color=BG_COLOR)
            
        draw = ImageDraw.Draw(img)

        # 1. TÍTULO PRINCIPAL EN UN RECTÁNGULO REDONDEADO CON SOMBRA (SIN 1/2 NI 1-2)
        titulo_limpio = re.sub(r"\s*\(\d+[\/\-]\d+\)", "", titulo_header).strip().upper()
        try:
            bbox_header = draw.textbbox((0, 0), titulo_limpio, font=font_header)
            text_w = bbox_header[2] - bbox_header[0]
            text_h = bbox_header[3] - bbox_header[1]
            
            pad_x, pad_y = 40, 20
            box_w = text_w + pad_x * 2
            box_h = text_h + pad_y * 2
            
            box_x1 = (W - box_w) / 2
            box_y1 = 60
            box_x2 = box_x1 + box_w
            box_y2 = box_y1 + box_h
            
            # Dibujar la sombra de la cabecera (offset 8px)
            draw.rounded_rectangle([box_x1 + 8, box_y1 + 8, box_x2 + 8, box_y2 + 8], radius=20, fill=SHADOW_COLOR)
            
            # Dibujar la tarjeta principal de la cabecera
            draw.rounded_rectangle([box_x1, box_y1, box_x2, box_y2], radius=20, fill=CARD_COLOR)
            
            # Dibujar el texto centrado
            draw.text((W/2, box_y1 + box_h/2), titulo_limpio, font=font_header, fill=PRIMARY_COLOR, anchor="mm")
        except Exception as e:
            pass

        # --- 📏 GEOMETRÍA AJUSTADA: RETÍCULA PERFECTA Y ALINEADA ---
        cols = 3
        x_margin = 35
        y_margin = 40
        start_y = 190
        
        # Tarjetas más altas y cómodas
        cell_w = int((W - x_margin * (cols + 1)) / cols)
        cell_h = 420 

        for i, libro in enumerate(lista_libros_chunk):
            if i >= 12: break 

            row_idx = i // cols
            col_idx = i % cols

            x_card = x_margin + col_idx * (cell_w + x_margin)
            y_card = start_y + row_idx * (cell_h + y_margin)

            # 2. DIBUJAR SOMBRA 3D DE LA TARJETA (Se dibuja 12px más abajo y a la derecha)
            try:
                draw.rounded_rectangle([x_card + 12, y_card + 12, x_card + cell_w + 12, y_card + cell_h + 12], radius=25, fill=SHADOW_COLOR)
                # DIBUJAR TARJETA BLANCA PRINCIPAL
                draw.rounded_rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], radius=25, fill=CARD_COLOR)
            except AttributeError:
                draw.rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], fill=CARD_COLOR)

            # 3. MAXIMIZAR LA PORTADA (Ocupa casi el 60% de la tarjeta con muy poco margen)
            img_height = 220 
            y_img = y_card + 20 # Sube la imagen para pegarla más al borde superior
            
            try:
                url_portada = f"{url_base_supabase}{libro['libro_id']}.jpg"
                response = requests.get(url_portada, stream=True, timeout=5)
                response.raise_for_status()
                portada_img = Image.open(response.raw).convert("RGBA")
                
                # Permite que la imagen sea mucho más ancha (solo 16px de padding total)
                portada_img.thumbnail((int(cell_w - 16), img_height)) 
                x_img = x_card + (cell_w - portada_img.width) / 2
                
                img.paste(portada_img, (int(x_img), int(y_img)), portada_img)
            except Exception:
                draw.rectangle([x_card + 20, y_img, x_card + cell_w - 20, y_img + img_height], fill=(245, 238, 241))

            # 4. ETIQUETA DE STOCK (Estilo "Cinta" vibrante)
            if int(libro.get('stock', 0)) > 0:
                texto_badge = " DISPONIBLE "
                try:
                    bbox_badge = draw.textbbox((0, 0), texto_badge, font=font_badge)
                    ancho_badge = bbox_badge[2] - bbox_badge[0]
                    alto_badge = 32
                    
                    x_badge = x_card + (cell_w - ancho_badge) / 2
                    y_badge_pos = y_card - 15 
                    
                    draw.rounded_rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], radius=15, fill=BADGE_BG)
                    draw.text((x_badge + ancho_badge/2, y_badge_pos + alto_badge/2), texto_badge, font=font_badge, fill=BADGE_TEXT, anchor="mm")
                except Exception:
                    pass

            # 5. TEXTOS GRANDES, LEGIBLES Y ALINEADOS EN RETÍCULA FIJA
            lineas_titulo = dividir_texto_en_lineas(libro['titulo'].upper(), max_chars=14)
            y_titulo_start = y_card + 285
            
            # Ajustamos levemente el inicio si hay dos líneas para evitar colisiones
            if len(lineas_titulo) == 2:
                y_titulo_start = y_card + 273
                
            for idx_linea, linea in enumerate(lineas_titulo):
                try:
                    draw.text((x_card + cell_w/2, y_titulo_start + idx_linea * 24), linea, font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            if precio_float < precio_orig_float:
                # Caso: Descuento Activo
                texto_orig = f"${precio_orig_float:,.0f}"
                y_orig_fijo = y_card + 342
                try:
                    draw.text((x_card + cell_w/2, y_orig_fijo), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                    bbox_orig = draw.textbbox((0, 0), texto_orig, font=font_tachado)
                    ancho_orig = bbox_orig[2] - bbox_orig[0]
                    draw.line((x_card + cell_w/2 - ancho_orig/2, y_orig_fijo - 8, x_card + cell_w/2 + ancho_orig/2, y_orig_fijo - 8), fill=MUTED_COLOR, width=3)
                except ValueError:
                    pass
                
                texto_final = f"${precio_float:,.0f}"
                y_final_fijo = y_card + 392
                try:
                    draw.text((x_card + cell_w/2, y_final_fijo), texto_final, font=font_precio, fill=ACCENT_COLOR, anchor="ms")
                except ValueError:
                    pass
            else:
                # Caso: Precio Normal
                texto_final = f"${precio_float:,.0f}"
                y_final_centrado = y_card + 372
                try:
                    draw.text((x_card + cell_w/2, y_final_centrado), texto_final, font=font_precio, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

        return img
        
    except Exception as e:
        print(f"Error en motor de collage: {e}")
        return None