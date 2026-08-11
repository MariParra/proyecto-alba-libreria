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
    Genera una imagen 1080x1920 con un collage de los libros pasados (máximo 8).
    """
    # 1. Asegurarnos de que las fuentes existan
    asegurar_fuentes()
    
    try:
        W, H = (1080, 1920)
        BG_COLOR = (248, 249, 250)
        PRIMARY_COLOR = (33, 37, 41)
        ACCENT_COLOR = (220, 53, 69)
        MUTED_COLOR = (108, 117, 125)
        BADGE_COLOR = (40, 167, 69) 

        # Cargar las fuentes (ahora estamos seguros de que existen)
        try:
            font_titulo = ImageFont.truetype("assets/Montserrat-Bold.ttf", 40)
            font_precio = ImageFont.truetype("assets/Montserrat-Bold.ttf", 55)
            font_tachado = ImageFont.truetype("assets/Montserrat-Regular.ttf", 45)
            font_header = ImageFont.truetype("assets/Montserrat-Bold.ttf", 100)
            font_badge = ImageFont.truetype("assets/Montserrat-Bold.ttf", 25) 
        except IOError:
            font_titulo = font_precio = font_tachado = font_header = font_badge = ImageFont.load_default()

        img = Image.new('RGB', (W, H), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        # DIBUJAR TÍTULO DE LA HOJA
        titulo_seguro = (titulo_header[:20] + '..') if len(titulo_header) > 22 else titulo_header
        
        try:
            draw.text((W/2, 150), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR, anchor="ms")
        except ValueError:
            # Fallback seguro por si, por alguna extraña razón, falla la fuente
            draw.text((W/2 - 200, 100), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR)

        # --- LÓGICA DE LA CUADRÍCULA ---
        padding = 60
        num_libros = len(lista_libros_chunk)
        cols = 2
        rows = (num_libros + cols - 1) // cols 
        if rows == 0: rows = 1 

        cell_w = (W - padding * (cols + 1)) / cols
        cell_h = (H - 300 - padding * (rows + 1)) / rows 

        for i, libro in enumerate(lista_libros_chunk):
            if i >= 8: break 

            row_idx = i // cols
            col_idx = i % cols

            x0 = padding + col_idx * (cell_w + padding)
            y0 = 300 + padding + row_idx * (cell_h + padding)

            # Cargar Portada
            try:
                url_portada = f"{url_base_supabase}{libro['libro_id']}.jpg"
                response = requests.get(url_portada, stream=True, timeout=5)
                response.raise_for_status()
                portada_img = Image.open(response.raw).convert("RGBA")
                
                portada_img.thumbnail((int(cell_w), int(cell_h * 0.7))) 
                
                x_portada = x0 + (cell_w - portada_img.width) / 2
                y_portada = y0
                img.paste(portada_img, (int(x_portada), int(y_portada)), portada_img)
                y_texto = y_portada + portada_img.height + 30
            except Exception:
                y_texto = y0 + (cell_h * 0.7) + 30

            # Etiqueta de Stock (Mejorada para no dar errores)
            stock_actual = int(libro.get('stock', 0))
            if stock_actual > 0:
                texto_badge = " DISPONIBILIDAD INMEDIATA "
                bbox_badge = draw.[...](asc_slot://start-slot-1)textbbox((0, 0), texto_badge, font=font_badge)
                ancho_badge = bbox_badge - bbox_badge[0]
                
                alto_badge = 45
                x_badge = x0 + (cell_w - ancho_badge) / 2
                y_badge = y0 - 15 
                
                draw.rectangle([x_badge, y_badge, x_badge + ancho_badge, y_badge + alto_badge], fill=BADGE_COLOR)
                
                try:
                    draw.text((x_badge + ancho_badge/2, y_badge + alto_badge/2), texto_badge, font=font_badge, fill="white", anchor="mm")
                except ValueError:
                    draw.text((x_badge + 5, y_badge + 5), texto_badge, font=font_badge, fill="white")

            # Título del libro
            titulo_corto = (libro['titulo'][:25] + '...') if len(libro['titulo']) > 25 else libro['titulo']
            try:
                draw.text((x0 + cell_w/2, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
            except ValueError:
                draw.text((x0, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR)
            
            y_texto += 65

            # Precios
            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            if precio_float < precio_orig_float:
                texto_orig = f"${precio_orig_float:,.0f}"
                
                try:
                    draw.text((x0 + cell_w/2, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                except ValueError:
                    draw.text((x0, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR)
                
                bbox_orig = draw.[...](asc_slot://start-slot-3)textbbox((0, 0), texto_orig, font=font_tachado)
                ancho_orig = bbox_orig - bbox_orig[0]
                    
                draw.line((x0 + cell_w/2 - ancho_orig/2, y_texto - 20, x0 + cell_w/2 + ancho_orig/2, y_texto - 20), fill=MUTED_COLOR, width=4)
                y_texto += 55

            texto_oferta = f"${precio_float:,.0f}"
            try:
                draw.text((x0 + cell_w/2, y_texto), texto_oferta, font=font_precio, fill=ACCENT_COLOR, anchor="ms")
            except ValueError:
                draw.text((x0, y_texto), texto_oferta, font=font_precio, fill=ACCENT_COLOR)

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
        
    except Exception as e:
        print(f"Error crítico en el motor de collage: {e}")
        return None