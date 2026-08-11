from PIL import Image, ImageDraw, ImageFont
import io
import requests

def generar_collage_marketing(lista_libros, url_base_supabase):
    """
    Genera una imagen 1080x1920 con un collage de hasta 8 libros.
    Incluye etiqueta de 'DISPONIBILIDAD INMEDIATA' si hay stock.
    """
    try:
        W, H = (1080, 1920)
        BG_COLOR = (248, 249, 250)
        PRIMARY_COLOR = (33, 37, 41)
        ACCENT_COLOR = (220, 53, 69)
        MUTED_COLOR = (108, 117, 125)
        BADGE_COLOR = (40, 167, 69) # Verde para disponibilidad

        try:
            font_titulo = ImageFont.truetype("assets/Montserrat-Bold.ttf", 40)
            font_precio = ImageFont.truetype("assets/Montserrat-Bold.ttf", 55)
            font_tachado = ImageFont.truetype("assets/Montserrat-Regular.ttf", 45)
            font_header = ImageFont.truetype("assets/Montserrat-Bold.ttf", 120)
            font_badge = ImageFont.truetype("assets/Montserrat-Bold.ttf", 25) # Fuente para la etiqueta
        except IOError:
            font_titulo = font_precio = font_tachado = font_header = font_badge = ImageFont.load_default()

        img = Image.new('RGB', (W, H), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        # DIBUJAR TÍTULO "NOVEDADES"
        draw.text((W/2, 150), "NOVEDADES", font=font_header, fill=PRIMARY_COLOR, anchor="ms")

        # --- LÓGICA DE LA CUADRÍCULA (GRID) ---
        padding = 60
        num_libros = len(lista_libros)
        cols = 2
        rows = (num_libros + cols - 1) // cols 

        # Calculamos el tamaño de cada celda
        cell_w = (W - padding * (cols + 1)) / cols
        cell_h = (H - 300 - padding * (rows + 1)) / rows 

        for i, libro in enumerate(lista_libros):
            if i >= 8: break 

            row_idx = i // cols
            col_idx = i % cols

            # Posición de la celda
            x0 = padding + col_idx * (cell_w + padding)
            y0 = 300 + padding + row_idx * (cell_h + padding)

            # Cargar y pegar la portada
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

            # --- ETIQUETA DE DISPONIBILIDAD (NUEVO) ---
            stock_actual = int(libro.get('stock', 0))
            if stock_actual > 0:
                texto_badge = " DISPONIBILIDAD INMEDIATA "
                
                # Calcular tamaño del texto de la etiqueta
                try:
                    ancho_badge = draw.textlength(texto_badge, font=font_badge)
                except AttributeError:
                    ancho_badge, _ = draw.textsize(texto_badge, font=font_badge)
                
                alto_badge = 45
                x_badge = x0 + (cell_w - ancho_badge) / 2
                y_badge = y0 - 15 # Lo colocamos sobresaliendo un poquito por encima de la portada
                
                # Dibujar rectángulo verde y texto blanco
                draw.rectangle([x_badge, y_badge, x_badge + ancho_badge, y_badge + alto_badge], fill=BADGE_COLOR)
                draw.text((x_badge + ancho_badge/2, y_badge + alto_badge/2), texto_badge, font=font_badge, fill="white", anchor="mm")
            # ----------------------------------------

            # Escribir título del libro
            titulo_corto = (libro['titulo'][:25] + '...') if len(libro['titulo']) > 25 else libro['titulo']
            draw.text((x0 + cell_w/2, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
            y_texto += 65

            # Escribir precios
            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            if precio_float < precio_orig_float:
                texto_orig = f"${precio_orig_float:,.0f}"
                draw.text((x0 + cell_w/2, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                
                try:
                    ancho_orig = draw.textlength(texto_orig, font=font_tachado)
                except AttributeError:
                    ancho_orig, _ = draw.textsize(texto_orig, font=font_tachado)
                    
                # Línea de tachado
                draw.line((x0 + cell_w/2 - ancho_orig/2, y_texto - 20, x0 + cell_w/2 + ancho_orig/2, y_texto - 20), fill=MUTED_COLOR, width=4)
                y_texto += 55

            draw.text((x0 + cell_w/2, y_texto), f"${precio_float:,.0f}", font=font_precio, fill=ACCENT_COLOR, anchor="ms")

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        return None