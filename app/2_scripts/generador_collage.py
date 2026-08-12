from PIL import Image, ImageDraw, ImageFont
import io
import requests
import os
import urllib.request

def asegurar_fuentes():
    """Descarga las fuentes necesarias desde Google Fonts si no existen."""
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
                print(f"Error al descargar la fuente {nombre}: {e}")

def generar_collage_marketing(lista_libros_chunk, url_base_supabase, titulo_header="NOVEDADES"):
    """
    Genera una imagen 1080x1920 con un diseño pastel, tarjetas redondeadas (hasta 12 libros, 3x4).
    """
    asegurar_fuentes()
    
    W, H = (1080, 1920)
    # --- PALETA DE COLORES PASTEL Y MODERNOS ---
    BG_COLOR = (253, 242, 248)      # Fondo rosa pastel
    CARD_COLOR = (255, 255, 255)    # Tarjetas blancas
    PRIMARY_COLOR = (74, 77, 126)   # Azul/Morado oscuro
    ACCENT_COLOR = (225, 29, 72)    # Rosa vibrante
    MUTED_COLOR = (156, 163, 175)   # Gris para tachado
    BADGE_BG = (167, 243, 208)      # Verde menta
    BADGE_TEXT = (6, 95, 70)        # Verde oscuro

    try:
        # --- FUENTES AJUSTADAS ---
        font_header = ImageFont.truetype("assets/Montserrat-Bold.ttf", 90)
        font_titulo = ImageFont.truetype("assets/Montserrat-Bold.ttf", 26)
        font_precio = ImageFont.truetype("assets/Montserrat-Bold.ttf", 45)
        font_tachado = ImageFont.truetype("assets/Montserrat-Regular.ttf", 32)
        font_badge = ImageFont.truetype("assets/Montserrat-Bold.ttf", 16) 
    except IOError:
        font_header = font_titulo = font_precio = font_tachado = font_badge = ImageFont.load_default()

    img = Image.new('RGB', (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 1. TÍTULO PRINCIPAL
    titulo_seguro = (titulo_header[:25] + '..') if len(titulo_header) > 25 else titulo_header
    draw.text((W/2, 110), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR, anchor="ms")

    # 2. GEOMETRÍA DE LA CUADRÍCULA 3x4
    cols = 3
    x_margin, y_margin, start_y = 35, 35, 200
    cell_w = int((W - x_margin * (cols + 1)) / cols)
    cell_h = 390

    for i, libro in enumerate(lista_libros_chunk):
        if i >= 12: break 
        row_idx, col_idx = i // cols, i % cols
        x_card = x_margin + col_idx * (cell_w + x_margin)
        y_card = start_y + row_idx * (cell_h + y_margin)

        # 3. DIBUJAR TARJETA BLANCA
        draw.rounded_rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], radius=20, fill=CARD_COLOR)

        # 4. CARGAR Y PEGAR PORTADA
        img_height = int(cell_h * 0.48)
        y_img = y_card + 35
        y_texto = y_img + img_height + 25
        try:
            libro_id_str = str(int(float(libro['libro_id'])))
            url_portada = f"{url_base_supabase}{libro_id_str}.jpg"
            response = requests.get(url_portada, stream=True, timeout=5)
            response.raise_for_status()
            portada_img = Image.open(response.raw).convert("RGBA")
            portada_img.thumbnail((int(cell_w - 30), img_height)) 
            x_img = x_card + (cell_w - portada_img.width) / 2
            img.paste(portada_img, (int(x_img), int(y_img)), portada_img)
        except Exception:
            draw.rectangle([x_card + 50, y_img, x_card + cell_w - 50, y_img + img_height], fill=(240,240,240))

        # 5. ETIQUETA DE STOCK
        if int(libro.get('stock', 0)) > 0:
            texto_badge = " DISPONIBLE "
            bbox_badge = draw.textbbox((0, 0), texto_badge, font=font_badge)
            ancho_badge = bbox_badge[2] - bbox_badge[0]
            alto_badge = 28
            x_badge = x_card + (cell_w - ancho_badge) / 2
            y_badge_pos = y_card - 12
            draw.rounded_rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], radius=10, fill=BADGE_BG)
            draw.text((x_badge + ancho_badge/2, y_badge_pos + alto_badge/2), texto_badge, font=font_badge, fill=BADGE_TEXT, anchor="mm")

        # 6. TEXTOS
        titulo_corto = (libro['titulo'][:22] + '..') if len(libro['titulo']) > 22 else libro['titulo']
        draw.text((x_card + cell_w/2, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
        y_texto += 50

        precio_float = float(libro['precio'])
        precio_orig_float = float(libro.get('precio_original', precio_float))

        if precio_float < precio_orig_float:
            texto_orig = f"${precio_orig_float:,.0f}"
            draw.text((x_card + cell_w/2, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
            bbox_orig = draw.textbbox((0, 0), texto_orig, font=font_tachado)
            ancho_orig = bbox_orig[2] - bbox_orig[0]
            draw.line((x_card + cell_w/2 - ancho_orig/2, y_texto, x_card + cell_w/2 + ancho_orig/2, y_texto), fill=MUTED_COLOR, width=3)
            y_texto += 45
        else:
            y_texto += 15

        texto_final = f"${precio_float:,.0f}"
        color_final = ACCENT_COLOR if precio_float < precio_orig_float else PRIMARY_COLOR
        draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=color_final, anchor="ms")

    return img