import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
from supabase import create_client

# --- FUNCIÓN DE CARGA INTELIGENTE DE SECRETOS ---
def cargar_secretos_streamlit():
    secrets = {}
    secrets_path = Path(".streamlit/secrets.toml")
    if secrets_path.exists():
        try:
            import tomllib
            with open(secrets_path, "rb") as f:
                secrets = tomllib.load(f)
        except Exception:
            with open(secrets_path, "r", encoding="utf-8") as f:
                section = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        section = line[1:-1]
                    elif "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if section:
                            if "." in section:
                                s1, s2 = section.split(".", 1)
                                if s1 not in secrets: secrets[s1] = {}
                                if s2 not in secrets[s1]: secrets[s1][s2] = {}
                                secrets[s1][s2][k] = v
                            else:
                                if section not in secrets: secrets[section] = {}
                                secrets[section][k] = v
                        else:
                            secrets[k] = v
    return secrets

# --- FUNCIÓN DE PARSEO DE FECHAS ---
def unificar_formatos_fecha(serie_fechas):
    def parsear_valor(val):
        if pd.isna(val) or not str(val).strip() or str(val).strip().lower() in ['nan', 'nat']:
            return pd.NaT
        val_str = str(val).strip()
        try:
            if 't' in val_str.lower() or '+' in val_str:
                return pd.to_datetime(val_str).tz_localize(None)
            if len(val_str.split('-')[0]) == 4 or len(val_str.split('/')[0]) == 4:
                return pd.to_datetime(val_str, dayfirst=False, errors='coerce').tz_localize(None)
            else:
                return pd.to_datetime(val_str, dayfirst=True, errors='coerce').tz_localize(None)
        except Exception:
            try:
                return pd.to_datetime(val_str, errors='coerce').tz_localize(None)
            except Exception:
                return pd.NaT
    try:
        return serie_fechas.apply(parsear_valor)
    except Exception:
        return pd.to_datetime(serie_fechas, errors='coerce').dt.tz_localize(None)

# Cargar secretos
st_secrets = cargar_secretos_streamlit()

SUPABASE_URL = st_secrets.get("connections", {}).get("supabase", {}).get("url") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = st_secrets.get("connections", {}).get("supabase", {}).get("key") or os.environ.get("SUPABASE_KEY")

EMAIL_EMISOR = st_secrets.get("email", {}).get("remitente") or os.environ.get("EMAIL_EMISOR")
EMAIL_RECEPTOR = st_secrets.get("email", {}).get("dest_admin") or os.environ.get("EMAIL_RECEPTOR")
EMAIL_PASSWORD = st_secrets.get("email", {}).get("password") or os.environ.get("EMAIL_PASSWORD")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def generar_reporte_empaque():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Faltan credenciales de Supabase.")
        return
    if not EMAIL_EMISOR or not EMAIL_RECEPTOR or not EMAIL_PASSWORD:
        print("❌ Error: Faltan credenciales de Correo.")
        return

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    hoy = datetime.now()
    hoy_str = hoy.strftime("%Y-%m-%d")
    dia_semana = hoy.weekday() # Monday is 0, Tuesday is 1, Wednesday is 2
    hora_actual = hoy.hour

    # ================= VALIDACIÓN DE DÍAS LABORALES =================
    if dia_semana in [5, 6]:  # Sábado (5) y Domingo (6)
        print("🟢 Fin de semana. Los reportes automáticos únicamente se envían de lunes a viernes.")
        return

    # ================= PARTE 1: CONSULTA DE ENVÍOS PENDIENTES (PAGINADO) =================
    all_data = []
    chunk_size = 1000
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_ventas = supabase.table("registro_ventas")\
            .select("venta_id, fecha_venta, estado, libros_vendidos, cliente:clientes(nombre)")\
            .order("venta_id")\
            .range(start, end).execute()
        if res_ventas.data:
            all_data.extend(res_ventas.data)
            if len(res_ventas.data) < chunk_size:
                break
        else:
            break
            
    df_ventas = pd.DataFrame(all_data) if all_data else pd.DataFrame()
    df_criticas = pd.DataFrame()
    
    if not df_ventas.empty:
        df_ventas['fecha_dt'] = unificar_formatos_fecha(df_ventas['fecha_venta'])
        df_ventas['dias'] = df_ventas['fecha_dt'].apply(lambda x: (hoy - x).days if pd.notna(x) else 0)
        df_criticas = df_ventas[
            (df_ventas['dias'] > 5) & 
            (~df_ventas['estado'].isin(['PAQUETE LISTO', 'FINALIZADO']))
        ].copy()
        if not df_criticas.empty:
            df_criticas['cliente_nombre'] = df_criticas['cliente'].apply(lambda x: x.get('nombre') if isinstance(x, dict) else 'Cliente')

    # ================= PARTE 2: CONSULTA DE NOTAS DE LA PIZARRA (PAGINADO) =================
    all_notes = []
    for bloque in range(100):
        start = bloque * chunk_size
        end = start + chunk_size - 1
        res_notes = supabase.table("pizarra_recordatorios")\
            .select("*")\
            .eq("completada", False)\
            .order("nota_id")\
            .range(start, end).execute()
        if res_notes.data:
            all_notes.extend(res_notes.data)
            if len(res_notes.data) < chunk_size:
                break
        else:
            break
            
    df_notes = pd.DataFrame(all_notes) if all_notes else pd.DataFrame()
    df_notas_vencidas = pd.DataFrame()
    df_notas_pendientes = pd.DataFrame()

    if not df_notes.empty:
        df_notes['fecha_limite_dt'] = pd.to_datetime(df_notes['fecha_limite']).dt.date
        # 1. Separar vencidas
        df_notas_vencidas = df_notes[df_notes['fecha_limite_dt'] < hoy.date()].copy()
        # 2. Separar pendientes en plazo (hoy o fecha futura)
        df_notas_pendientes = df_notes[df_notes['fecha_limite_dt'] >= hoy.date()].copy()
        # Ordenar pendientes por fecha para ver las que expiran más pronto arriba
        if not df_notas_pendientes.empty:
            df_notas_pendientes = df_notas_pendientes.sort_values(by='fecha_limite_dt')

    # --- VALIDACIÓN DE FACTURAS VENCIDAS (HÁMSTER FURIOSO OVERRIDE!) ---
    facturas_vencidas_activas = []
    if not df_notes.empty:
        facturas_vencidas_activas = df_notes[
            (df_notes['titulo'] == "HACER FACTURAS DE LA SEMANA") & 
            (df_notes['fecha_limite_dt'] < hoy.date())
        ].copy()

    # ================= PARTE 3: MODALIDAD DUOLINGO: ESCALA DE DRAMA INTERNA =================
    if not facturas_vencidas_activas.empty:
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/angry%20hamster.jpg"
        header_color = "#d32f2f"
        border_style = "3px solid #d32f2f"
        card_bg = "#ffebee"
        msg_titulo = "🔥 ¡HÁMSTER FURIOSO: FACTURAS VENCIDAS! 🔥"
        msg_cuerpo = f"¡Ivonne, esto ya es el colmo! Tienes {len(facturas_vencidas_activas)} tarea(s) vieja(s) de facturas pendientes de completar en la pizarra. ¡El hámster está extremadamente enojado y listo para morder! 🐹💢 ¡Ponte a facturar de inmediato!"

    elif df_criticas.empty and df_notas_vencidas.empty and dia_semana not in [1, 2]:
        # ¡HÁMSTER ZEN / FELIZ!
        cant_pendientes = len(df_notas_pendientes) if not df_notas_pendientes.empty else 0
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster%20peace.jpg"
        header_color = "#2e7d32"
        border_style = "2px solid #2e7d32"
        card_bg = "#e8f5e9"
        msg_titulo = "✨ ¡HÁMSTER FELIZ: BODEGA EN PAZ ZEN! ✨"
        
        if cant_pendientes > 0:
            msg_cuerpo = f"¡Increíble Ivonne! No tienes paquetes demorados ni post-its vencidos en la pizarra. Solo te quedan {cant_pendientes} tarea(s) en plazo para los próximos días (las verás detalladas abajo). El hámster está en su modo zen más pacífico, orgulloso de tu productividad. 🐹🌸 ¡Disfruta el día con tranquilidad!"
        else:
            msg_cuerpo = "¡Increíble Ivonne! No tienes paquetes demorados, post-its vencidos ni tareas pendientes en la pizarra. ¡Todo está 100% al día! El hámster está en un estado de iluminación absoluta. 🐹✨ ¡Disfruta tu día libre de pendientes!"

    elif dia_semana == 1: # Martes
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster%20peace.jpg"
        header_color = "#0288d1"
        border_style = "2px solid #0288d1"
        card_bg = "#e1f5fe"
        msg_titulo = "🕊️ ¡MAÑANA ES DÍA DE FACTURAS! (PAZ ANTES DE LA TORMENTA)"
        msg_cuerpo = "Ivonne, recuerda que hoy es Martes... ¡Mañana se viene el día de facturas! Mantén la paz mental hoy y prepárate para mañana. 🐹✌️"

    elif dia_semana == 2: # Miércoles
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster%20mirando.jpg"
        header_color = "#ef6c00"
        border_style = "2px solid #ef6c00"
        card_bg = "#fff3e0"
        
        if hora_actual <= 14: # Mediodía
            msg_titulo = "👀 ¡MIÉRCOLES DE FACTURAS (MEDIODÍA)! 👀"
            msg_cuerpo = "Ivonne, ya es mediodía de miércoles. ¿Cómo van esas facturas semanales? El hámster te está observando fijamente... 🐹🔍"
        else: # Tarde (17:00 en adelante)
            msg_titulo = "🚨 ¡MIÉRCOLES DE FACTURAS (ÚLTIMO AVISO DE LA TARDE)! 🚨"
            msg_cuerpo = "¡Ivonne! Son las 5 de la tarde de miércoles. Termina de clavar las facturas de la semana en la pizarra antes de que acabe el día laboral. 🐹📦"

    else:
        max_dias_retraso = df_criticas['dias'].max() if not df_criticas.empty else 0
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster%20vigilando.jpg"
        header_color = "#d32f2f"
        border_style = "2px solid #ff4b4b"
        card_bg = "#ffebee"
        
        if max_dias_retraso > 14:
            msg_titulo = "😭 ESTAS ALERTAS NO SIRVEN... NOS RENDIMOS 😭"
            msg_cuerpo = f"Hola Ivonne. Vemos que tienes tareas con {max_dias_retraso} días de retraso. ¡El hámster está llorando en un rincón de la bodega! 🐹💔"
        else:
            msg_titulo = "🚨 RECORDATORIO DIARIO DE PRODUCTIVIDAD 🚨"
            msg_cuerpo = "IVONNE, TIENES TAREAS PENDIENTES POR HACER, PONTE A TRABAJAR LUEGO PODRÁS DORMIR Y TOMAR. 🐹👁️"

    # --- PIE DE PÁGINA DINÁMICO ---
    footer_text = "*Ivonne, ponte a trabajar duro hoy para que puedas dormir y tomar un copete en la noche con la pizarra limpia. El hámster te vigila.* 🐹👁️"
    if df_criticas.empty and df_notas_vencidas.empty and dia_semana not in [1, 2]:
        footer_text = "*¡Salud, Ivonne! Hoy te ganaste ese copete con la frente en alto y la pizarra impecable. El hámster aprueba esto.* 🐹🥂✨"

    # ================= CONSTRUCCIÓN DEL HTML =================
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 650px; margin: 0 auto; border: {border_style}; border-radius: 8px; padding: 25px; background-color: #fafafa; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                
                <!-- Encabezado con imagen del hámster dinámica -->
                <div style="text-align: center; margin-bottom: 25px;">
                    <img src="{hamster_img_url}" width="160" style="border-radius: 8px; box-shadow: 1px 1px 5px rgba(0,0,0,0.15);" />
                    <h2 style="color: {header_color}; margin: 15px 0 0 0;">{msg_titulo}</h2>
                </div>
                
                <!-- Cuadro de humor personalizado -->
                <div style="background-color: {card_bg}; padding: 15px; border-radius: 6px; text-align: center; margin-bottom: 25px; border: 1px solid {header_color};">
                    <p style="color: {header_color}; font-size: 16px; font-weight: bold; margin: 0;">{msg_cuerpo}</p>
                </div>
    """

    # --- SECCIÓN 1.1: POST-ITS VENCIDOS (URGENTES / COLOR NARANJA) ---
    if not df_notas_vencidas.empty:
        html_content += f"""
                <h3 style="color: #e65100; border-bottom: 2px solid #ffe0b2; padding-bottom: 5px;">📌 Post-its Vencidos en la Pizarra</h3>
                <p>Tienes <strong>{len(df_notas_vencidas)}</strong> tareas anotadas cuya fecha límite ya venció:</p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <thead>
                        <tr style="background-color: #fff3e0;">
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Tarea / Recordatorio</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Detalle Adicional</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Fecha Límite</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        for _, row in df_notas_vencidas.iterrows():
            html_content += f"""
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; color: #e65100;">📌 {row['titulo']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{row['contenido']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; color: #d32f2f;">{row['fecha_limite_dt'].strftime('%d/%m/%Y')}</td>
                        </tr>
            """
        html_content += """
                    </tbody>
                </table>
        """

    # --- SECCIÓN 1.2: POST-ITS PENDIENTES (EN PLAZO / COLOR AZUL) ---
    if not df_notas_pendientes.empty:
        html_content += f"""
                <h3 style="color: #1565c0; border-bottom: 2px solid #bbdefb; padding-bottom: 5px;">📅 Post-its Pendientes (En Plazo)</h3>
                <p>Tienes <strong>{len(df_notas_pendientes)}</strong> tareas activas por hacer con vencimiento hoy o a futuro:</p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <thead>
                        <tr style="background-color: #e3f2fd;">
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Tarea / Recordatorio</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Detalle Adicional</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Fecha Límite</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        for _, row in df_notas_pendientes.iterrows():
            vence_hoy = row['fecha_limite_dt'] == hoy.date()
            color_fecha = "#2e7d32" if vence_hoy else "#333"
            peso_fecha = "bold" if vence_hoy else "normal"
            label_hoy = " (¡Vence Hoy!)" if vence_hoy else ""
            
            html_content += f"""
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; color: #1565c0;">📌 {row['titulo']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{row['contenido']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd; font-weight: {peso_fecha}; color: {color_fecha};">
                                {row['fecha_limite_dt'].strftime('%d/%m/%Y')}{label_hoy}
                            </td>
                        </tr>
            """
        html_content += """
                    </tbody>
                </table>
        """

    # --- SECCIÓN 2: ARMADO DE PAQUETES DEMORADOS ---
    if not df_criticas.empty:
        html_content += f"""
                <h3 style="color: #c62828; border-bottom: 2px solid #ffcdd2; padding-bottom: 5px;">📦 Armado de Paquetes Demorados (>5 días)</h3>
                <p>Hay <strong>{len(df_criticas)}</strong> órdenes pendientes que no has empaquetado:</p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <thead>
                        <tr style="background-color: #ffebee;">
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">ID</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Cliente</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Antigüedad</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Detalle de Libros</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        for _, row in df_criticas.iterrows():
            html_content += f"""
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">#{row['venta_id']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{row['cliente_nombre']}</td>
                            <td style="padding: 10px; border: 1px solid #ddd; color: #d32f2f; font-weight: bold;">{row['dias']} días</td>
                            <td style="padding: 10px; border: 1px solid #ddd; font-style: italic;">{row['libros_vendidos']}</td>
                        </tr>
            """
        html_content += """
                    </tbody>
                </table>
        """

    html_content += f"""
                <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
                <p style="text-align: center; font-size: 13px; color: #666; font-style: italic;">
                    {footer_text}
                </p>
            </div>
        </body>
    </html>
    """

    # ================= PARTE 4: ENVÍO DEL CORREO =================
    msg = MIMEMultipart()
    msg['From'] = EMAIL_EMISOR
    msg['To'] = EMAIL_RECEPTOR
    
    retrasos = len(df_criticas) + len(df_notas_vencidas)
    pendientes_en_plazo = len(df_notas_pendientes)
    total_alertas = retrasos + pendientes_en_plazo
    
    msg['Subject'] = f"{msg_titulo} ({retrasos} críticos / {total_alertas} total) - {hoy.strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_EMISOR, EMAIL_PASSWORD)
        server.sendmail(EMAIL_EMISOR, EMAIL_RECEPTOR, msg.as_string())
        server.quit()
        print(f"✅ ¡Éxito! Reporte consolidado de {total_alertas} alertas enviado correctamente.")
    except Exception as e:
        print(f"❌ Error al enviar el correo por SMTP: {e}")

if __name__ == "__main__":
    generar_reporte_empaque()