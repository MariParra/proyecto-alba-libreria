from PIL import Image, ImageDraw, ImageFont
import io
import requests
import os
import urllib.request

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

def generar_collage_marketing(lista_libros_chunk, url_base_supabase, titulo_header="NOVEDADES"):
    """
    Genera una imagen 1080x1920 Premium con fondo de marca Alba Librería:
    Sombras 3D, tipografía Bold grande, paleta rosada y portadas maximizadas (hasta 12 libros).
    """
    asegurar_fuentes()
    
    try:
        W, H = (1080, 1920)
        
        # --- 🎨 PALETA PINK AESTHETIC & PREMIUM ---
        BG_COLOR = (253, 232, 243)      # Fondo Fallback
        CARD_COLOR = (255, 255, 255)    # Tarjetas Blancas
        SHADOW_COLOR = (244, 204, 220)  # Sombra Rosa Oscuro para efecto 3D
        PRIMARY_COLOR = (49, 46, 129)   # Títulos: Azul Marino muy oscuro (casi negro)
        ACCENT_COLOR = (219, 39, 119)   # Precios y Botones: Fucsia / Rosa Fuerte
        MUTED_COLOR = (156, 163, 175)   # Precios tachados: Gris
        BADGE_BG = (225, 29, 72)        # Etiqueta "Disponible": Rojo/Rosa encendido
        BADGE_TEXT = (255, 255, 255)    # Texto etiqueta: Blanco
        
        # --- 🔠 FUENTES MUCHO MÁS GRANDES Y EN NEGRITA ---
        try:
            # Todo en Bold para mayor impacto visual
            font_header = ImageFont.truetype("assets/Montserrat-Bold.ttf", 100)
            font_titulo = ImageFont.truetype("assets/Montserrat-Bold.ttf", 32)
            font_precio = ImageFont.truetype("assets/Montserrat-Bold.ttf", 52)
            font_tachado = ImageFont.truetype("assets/Montserrat-Bold.ttf", 34)
            font_badge = ImageFont.truetype("assets/Montserrat-Bold.ttf", 18) 
        except IOError:
            font_header = font_titulo = font_precio = font_tachado = font_badge = ImageFont.load_default()

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

        # 1. TÍTULO PRINCIPAL (GIGANTE Y CENTRADO)
        titulo_seguro = (titulo_header[:20] + '..') if len(titulo_header) > 20 else titulo_header
        try:
            # Sombra del título para que resalte del fondo
            draw.text((W/2 + 5, 105), titulo_seguro.upper(), font=font_header, fill=SHADOW_COLOR, anchor="ms")
            draw.text((W/2, 100), titulo_seguro.upper(), font=font_header, fill=PRIMARY_COLOR, anchor="ms")
        except ValueError:
            pass

        # --- 📏 GEOMETRÍA AJUSTADA: MENOS MARGEN, MÁS PORTADA ---
        cols = 3
        x_margin = 35
        y_margin = 40
        start_y = 190
        
        # Tarjetas más anchas y altas
        cell_w = int((W - x_margin * (cols + 1)) / cols)
        cell_h = 400 

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
            img_height = int(cell_h * 0.58) 
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
                y_texto = y_img + portada_img.height + 35
            except Exception:
                draw.rectangle([x_card + 20, y_img, x_card + cell_w - 20, y_img + img_height], fill=(240,240,240))
                y_texto = y_img + img_height + 35

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

            # 5. TEXTOS EXTRA GRANDES Y NEGRITAS
            # Acortamos un poco el título a 18 caracteres para que quepa bien la fuente gigante
            titulo_corto = (libro['titulo'][:18] + '..') if len(libro['titulo']) > 18 else libro['titulo']
            try:
                draw.text((x_card + cell_w/2, y_texto), titulo_corto.upper(), font=font_titulo, fill=PRIMARY_COLOR, anchor="ms")
            except ValueError:
                pass
            
            y_texto += 55

            precio_float = float(libro['precio'])
            precio_orig_float = float(libro.get('precio_original', precio_float))

            if precio_float < precio_orig_float:
                texto_orig = f"${precio_orig_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_orig, font=font_tachado, fill=MUTED_COLOR, anchor="ms")
                    bbox_orig = draw.textbbox((0, 0), texto_orig, font=font_tachado)
                    ancho_orig = bbox_orig[2] - bbox_orig[0]
                    draw.line((x_card + cell_w/2 - ancho_orig/2, y_texto - 10, x_card + cell_w/2 + ancho_orig/2, y_texto - 10), fill=MUTED_COLOR, width=4)
                except ValueError:
                    pass
                
                y_texto += 55
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=ACCENT_COLOR, anchor="ms")
                except ValueError:
                    pass
            else:
                y_texto += 25
                texto_final = f"${precio_float:,.0f}"
                try:
                    draw.text((x_card + cell_w/2, y_texto), texto_final, font=font_precio, fill=PRIMARY_COLOR, anchor="ms")
                except ValueError:
                    pass

        return img
        
    except Exception as e:
        print(f"Error en motor de collage: {e}")
        return None