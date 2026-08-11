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
    
    try:
        W, H = (1080, 1920)
        
        # --- 🎨 PALETA DE COLORES PASTEL Y MODERNOS ---
        BG_COLOR = (253, 242, 248)      # Fondo rosa pastel muy suave
        CARD_COLOR = (255, 255, 255)    # Tarjetas blancas
        PRIMARY_COLOR = (74, 77, 126)   # Texto principal (Azul/Morado oscuro elegante)
        ACCENT_COLOR = (225, 29, 72)    # Rosa vibrante para precios de oferta
        MUTED_COLOR = (156, 163, 175)   # Gris para el texto tachado
        BADGE_BG = (167, 243, 208)      # Verde menta pastel para la etiqueta
        BADGE_TEXT = (6, 95, 70)        # Texto verde oscuro para la etiqueta
        
        # --- 🔠 FUENTES AJUSTADAS PARA 3 COLUMNAS ---
        try:
            font_header = ImageFont.truetype("assets/Montserrat-Bold.ttf", 90)
            font_titulo = ImageFont.truetype("assets/Montserrat-Bold.ttf", 26)
            font_precio = ImageFont.truetype("assets/Montserrat-Bold.ttf", 45)
            font_tachado = ImageFont.truetype("assets/Montserrat-Regular.ttf", 32)
            font_badge = ImageFont.truetype("assets/Montserrat-Bold.ttf", 16) 
        except IOError:
            font_header = font_titulo = font_precio = font_tachado = font_badge = ImageFont.load_default()

        img = Image.new('RGB', (W, H), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        # 1. DIBUJAR TÍTULO PRINCIPAL (Centrado arriba)
        titulo_seguro = (titulo_header[:25] + '..') if len(titulo_header) > 25 else titulo_header
        try:
            draw.text((W/2, 110), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR, anchor="ms")
        except ValueError:
            draw.text((W/2 - 200, 50), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR)

        # --- 📏 GEOMETRÍA DE LA CUADRÍCULA 3x4 (12 LIBROS) ---
        cols = 3
        x_margin = 35
        y_margin = 35
        start_y = 200
        
        # Calculamos el tamaño exacto de cada tarjeta blanca
        cell_w = int((W - x_margin * (cols + 1)) / cols)
        cell_h = 390 # Altura ajustada para que quepan 4 filas

        for i, libro in enumerate(lista_libros_chunk):
            if i >= 12: break # Límite de 12 libros por hoja

            row_idx = i // cols
            col_idx = i % cols

            # Esquina superior izquierda de la tarjeta
            x_card = x_margin + col_idx * (cell_w + x_margin)
            y_card = start_y + row_idx * (cell_h + y_margin)

            # 2. DIBUJAR TARJETA BLANCA
            try:
                draw.rounded_rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], radius=20, fill=CARD_COLOR)
            except AttributeError:
                draw.rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], fill=CARD_COLOR)

            # 3. CARGAR Y PEGAR LA PORTADA
            img_height = int(cell_h * 0.48) # 48% de la tarjeta para la foto
            y_img = y_card + 35
            
            try:
                url_portada = f"{url_base_supabase}{libro['libro_id']}.jpg"
                response = requests.get(url_portada, stream=True, timeout=5)
                response.raise_for_status()
                portada_img = Image.open(response.raw).convert("RGBA")
                
                portada_img.thumbnail((int(cell_w - 30), img_height)) 
                x_img = x_card + (cell_w - portada_img.width) / 2
                
                img.paste(portada_img, (int(x_img), int(y_img)), portada_img)
                y_texto = y_img + portada_img.height + 25
            except Exception:
                # Cuadro gris de respaldo si no hay foto
                draw.rectangle([x_card + 50, y_img, x_card + cell_w - 50, y_img + img_height], fill=(240,240,240))
                y_texto = y_img + img_height + 25

            # 4. ETIQUETA DE STOCK (DISPONIBILIDAD)
            stock_actual = int(libro.get('stock', 0))
            if stock_actual > 0:
                texto_badge = " DISPONIBLE "
                
                bbox_badge = draw.textbbox((0, 0), texto_badge, font=font_badge)
                ancho_badge = bbox_badge - bbox_badge[0]
                alto_badge = 28
                
                x_badge = x_card + (cell_w - ancho_badge) / 2
                y_badge_pos = y_card - 12 # Sobresale por arriba de la tarjeta
                
                try:
                    draw.rounded_rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], radius=10, fill=BADGE_BG)
                except AttributeError:
                    draw.rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], fill=BADGE_BG)
                    
                try:
                    draw.text((x_badge + ancho_badge/2, y_badge_pos + alto_badge/2), texto_badge, font=font_badge, fill=BADGE_TEXT, anchor="mm")
                except ValueError:
                    draw.text((x_badge + 5, y_badge_pos + 5), texto_badge, font=font_badge, fill=BADGE_TEXT)

            # 5. TEXTOS (TÍTULO Y PRECIOS)
            titulo_corto = (libro['titulo'][:22] + '..') if len(libro['titulo']) > 22 else libro['titulo']
            try:
                draw.text((x_card + cell_w/2, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
            except ValueError:
                draw.text((x_card + 10, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR)
            
            y_texto += 50

            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            if precio_float < precio_orig_float:
                texto_orig = f"${precio_orig_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                    bbox_orig = draw.textbbox((0, 0), texto_orig, font=font_tachado)
                    ancho_orig = bbox_orig - bbox_orig[0]
                    draw.line((x_card + cell_w/2 - ancho_orig/2, y_texto - 10, x_card + cell_w/2 + ancho_orig/2, y_texto - 10), fill=MUTED_COLOR, width=3)
                except ValueError:
                    pass
                
                y_texto += 45
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=ACCENT_COLOR, anchor="ms")
                except ValueError:
                    pass
            else:
                y_texto += 15
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

        return img
        
    except Exception as e:
        print(f"Error crítico en el motor de collage: {e}")
        return None