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
    Genera una imagen 1080x1920 con un diseño pastel, tarjetas redondeadas y fuentes grandes.
    """
    asegurar_fuentes()
    
    try:
        W, H = (1080, 1920)
        
        # --- 🎨 NUEVA PALETA DE COLORES PASTEL Y MODERNOS ---
        BG_COLOR = (253, 242, 248)      # Fondo rosa pastel muy suave
        CARD_COLOR = (255, 255, 255)    # Tarjetas blancas
        PRIMARY_COLOR = (74, 77, 126)   # Texto principal (Azul/Morado oscuro elegante)
        ACCENT_COLOR = (225, 29, 72)    # Rosa vibrante para precios de oferta
        MUTED_COLOR = (156, 163, 175)   # Gris para el texto tachado
        BADGE_BG = (167, 243, 208)      # Verde menta pastel para la etiqueta
        BADGE_TEXT = (6, 95, 70)        # Texto verde oscuro para la etiqueta
        
        # --- 🔠 NUEVAS FUENTES MÁS GRANDES ---
        try:
            font_header = ImageFont.truetype("assets/Montserrat-Bold.ttf", 110)
            font_titulo = ImageFont.truetype("assets/Montserrat-Bold.ttf", 45)
            font_precio = ImageFont.truetype("assets/Montserrat-Bold.ttf", 65)
            font_tachado = ImageFont.truetype("assets/Montserrat-Regular.ttf", 45)
            font_badge = ImageFont.truetype("assets/Montserrat-Bold.ttf", 22) 
        except IOError:
            font_header = font_titulo = font_precio = font_tachado = font_badge = ImageFont.load_default()

        img = Image.new('RGB', (W, H), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        # 1. DIBUJAR TÍTULO PRINCIPAL
        titulo_seguro = (titulo_header[:20] + '..') if len(titulo_header) > 22 else titulo_header
        try:
            draw.text((W/2, 120), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR, anchor="ms")
        except ValueError:
            draw.text((100, 50), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR)

        # --- 📏 GEOMETRÍA DE LA CUADRÍCULA CON TARJETAS BLANCAS ---
        cols = 2
        x_margin = 50
        y_margin = 40
        start_y = 230
        
        # Calculamos el tamaño de cada "Tarjeta" blanca
        cell_w = (W - x_margin * (cols + 1)) / cols  
        cell_h = 370 # Altura fija para mantener proporciones estéticas

        for i, libro in enumerate(lista_libros_chunk):
            if i >= 8: break 

            row_idx = i // cols
            col_idx = i % cols

            # Esquina superior izquierda de cada tarjeta
            x_card = x_margin + col_idx * (cell_w + x_margin)
            y_card = start_y + row_idx * (cell_h + y_margin)

            # 2. DIBUJAR TARJETA BLANCA (Fondo de cada libro)
            try:
                draw.rounded_rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], radius=25, fill=CARD_COLOR)
            except AttributeError:
                # Fallback por si la versión de Pillow es muy antigua
                draw.rectangle([x_card, y_card, x_card + cell_w, y_card + cell_h], fill=CARD_COLOR)

            # 3. CARGAR Y PEGAR LA PORTADA DENTRO DE LA TARJETA
            img_height = int(cell_h * 0.50) # 50% de la tarjeta para la foto
            y_img = y_card + 35
            
            try:
                url_portada = f"{url_base_supabase}{libro['libro_id']}.jpg"
                response = requests.get(url_portada, stream=True, timeout=5)
                response.raise_for_status()
                portada_img = Image.open(response.raw).convert("RGBA")
                
                portada_img.thumbnail((int(cell_w - 40), img_height)) 
                x_img = x_card + (cell_w - portada_img.width) / 2
                
                img.paste(portada_img, (int(x_img), int(y_img)), portada_img)
                y_texto = y_img + portada_img.height + 30
            except Exception:
                # Dejamos un cuadro gris suave si no hay foto
                draw.rectangle([x_card + 120, y_img, x_card + cell_w - 120, y_img + img_height], fill=(240,240,240))
                y_texto = y_img + img_height + 30

            # 4. ETIQUETA DE STOCK (BADGE MENTA PASTEL)
            stock_actual = int(libro.get('stock', 0))
            if stock_actual > 0:
                texto_badge = " DISPONIBILIDAD INMEDIATA "
                bbox_badge = draw.textbbox((0, 0), texto_badge, font=font_badge)
                ancho_badge = bbox_badge - bbox_badge[0]
                alto_badge = 38
                
                x_badge = x_card + (cell_w - ancho_badge) / 2
                y_badge_pos = y_card - 15 # Sobresale como un "pin" por encima de la tarjeta blanca
                
                try:
                    draw.rounded_rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], radius=12, fill=BADGE_BG)
                except AttributeError:
                    draw.rectangle([x_badge, y_badge_pos, x_badge + ancho_badge, y_badge_pos + alto_badge], fill=BADGE_BG)
                    
                try:
                    draw.text((x_badge + ancho_badge/2, y_badge_pos + alto_badge/2 - 2), texto_badge, font=font_badge, fill=BADGE_TEXT, anchor="mm")
                except ValueError:
                    draw.text((x_badge + 5, y_badge_pos + 5), texto_badge, font=font_badge, fill=BADGE_TEXT)

            # 5. TEXTOS (TÍTULOS Y PRECIOS GRANDES)
            titulo_corto = (libro['titulo'][:22] + '...') if len(libro['titulo']) > 22 else libro['titulo']
            try:
                draw.text((x_card + cell_w/2, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
            except ValueError:
                draw.text((x_card + 20, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR)
            
            y_texto += 55

            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            if precio_float < precio_orig_float:
                # Muestra el precio tachado y la oferta abajo
                texto_orig = f"${precio_orig_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                    bbox_orig = draw.textbbox((0, 0), texto_orig, font=font_tachado)
                    ancho_orig = bbox_orig - bbox_orig[0]
                    draw.line((x_card + cell_w/2 - ancho_orig/2, y_texto - 15, x_card + cell_w/2 + ancho_orig/2, y_texto - 15), fill=MUTED_COLOR, width=4)
                except ValueError:
                    pass
                
                y_texto += 55
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=ACCENT_COLOR, anchor="ms")
                except ValueError:
                    pass
            else:
                # Si no hay descuento, centra el precio normal más abajo
                y_texto += 20
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

        # Devolver el objeto PIL
        return img
        
    except Exception as e:
        print(f"Error crítico en el motor de collage: {e}")
        return None