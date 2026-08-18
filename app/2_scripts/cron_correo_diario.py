import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path
import pandas as pd
from supabase import create_client

# --- FUNCIÓN DE CARGA INTELIGENTE DE SECRETOS (.toml) ---
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

    # ================= PARTE 1: CONSULTA DE ENVÍOS PENDIENTES =================
    res_ventas = supabase.table("registro_ventas").select("venta_id, fecha_venta, estado, libros_vendidos, cliente:clientes(nombre)").execute()
    df_ventas = pd.DataFrame(res_ventas.data) if res_ventas.data else pd.DataFrame()
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

    # ================= PARTE 2: CONSULTA DE NOTAS VENCIDAS DE LA PIZARRA =================
    res_notas = supabase.table("pizarra_recordatorios").select("*").eq("completada", False).execute()
    df_notas = pd.DataFrame(res_notas.data) if res_notas.data else pd.DataFrame()
    df_notas_vencidas = pd.DataFrame()

    if not df_notas.empty:
        df_notas['fecha_limite_dt'] = pd.to_datetime(df_notas['fecha_limite']).dt.date
        df_notas_vencidas = df_notas[df_notas['fecha_limite_dt'] < hoy.date()].copy()

    # Si no hay absolutamente nada pendiente, abortamos el envío para no molestar por gusto
    if df_criticas.empty and df_notas_vencidas.empty:
        print("🟢 Todo al día. No se requiere enviar reporte de alertas hoy.")
        return

    # ================= PARTE 3: CONSTRUCCIÓN DEL CORREO EN HTML CON HÁMSTERS DINÁMICOS =================
    total_retrasos = len(df_criticas) + len(df_notas_vencidas)
    
    # ================= MODALIDAD DUOLINGO: ESCALA DE DRAMA INTERNA =================
    # Selección de imagen y mensaje según el estado de los pendientes
    max_dias_retraso = 0
    if not df_criticas.empty:
        max_dias_retraso = max(max_dias_retraso, df_criticas['dias'].max())
    if not df_notas_vencidas.empty:
        # Calcular días de retraso de la pizarra
        df_notas_vencidas['dias_vencida'] = df_notas_vencidas['fecha_limite_dt'].apply(lambda x: (hoy.date() - x).days)
        max_dias_retraso = max(max_dias_retraso, df_notas_vencidas['dias_vencida'].max())

    if total_retrasos > 0:
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamster%20vigilando.jpg"
        header_color = "#d32f2f"
        border_style = "2px solid #ff4b4b"
        card_bg = "#ffebee"
        
        # Nivel de Drama Duolingo según el peor retraso
        if max_dias_retraso > 14:
            msg_titulo = "😭 ESTAS ALERTAS NO SIRVEN... NOS RENDIMOS 😭"
            msg_cuerpo = f"Hola Ivonne. Vemos que tienes tareas con {max_dias_retraso} días de retraso. Hemos decidido dejar de insistir... mentira, ¡PONTE A TRABAJAR YA! El hámster está llorando en un rincón de la bodega. 🐹💔"
        elif max_dias_retraso > 7:
            msg_titulo = "👁️ ¿HOLA? ¿HAY ALGUIEN AHÍ? TUS LIBROS TE EXTRAÑAN... 👁️"
            msg_cuerpo = f"¡Ivonne! Llevas {max_dias_retraso} días ignorando tus deberes. El hámster está preparando sus maletas para irse de Alba Librería. Por favor, completa tus pendientes hoy. 📦🐹"
        else:
            msg_titulo = "🚨 RECORDATORIO DIARIO DE PRODUCTIVIDAD 🚨"
            msg_cuerpo = "IVONNE, TIENES TAREAS PENDIENTES POR HACER, PONTE A TRABAJAR LUEGO PODRÁS DORMIR Y TOMAR. 🐹👁️"
    else:
        hamster_img_url = "https://mjwwljryowjehktgcmtm.supabase.co/storage/v1/object/public/grafica/hamstertrabajando.jpg"
        header_color = "#2e7d32"
        border_style = "2px solid #4caf50"
        card_bg = "#e8f5e9"
        msg_titulo = "🐹✨ ¡HAZAÑA COMPLETADA!"
        msg_cuerpo = "¡Pizarra y bodega limpias! Tienes todo en orden, puedes dormir pero que no se te olvide trabajar tampoco. ¡El hámster te da luz verde para descansar! 🍹🎉"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 650px; margin: 0 auto; border: {border_style}; border-radius: 8px; padding: 25px; background-color: #fafafa; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                
                <!-- Encabezado con imagen del hámster dinámica -->
                <div style="text-align: center; margin-bottom: 25px;">
                    <img src="{hamster_img_url}" width="150" style="border-radius: 8px; box-shadow: 1px 1px 5px rgba(0,0,0,0.15);" />
                    <h2 style="color: {header_color}; margin: 15px 0 0 0;">{msg_titulo}</h2>
                </div>
                
                <!-- Cuadro de humor personalizado -->
                <div style="background-color: {card_bg}; padding: 15px; border-radius: 6px; text-align: center; margin-bottom: 25px; border: 1px solid {header_color};">
                    <p style="color: {header_color}; font-size: 16px; font-weight: bold; margin: 0;">{msg_cuerpo}</p>
                </div>
    """

    # Bloque de Envíos Pendientes (si existen)
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

    # Bloque de Pizarra de Recordatorios Vencidos (si existen)
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

    html_content += """
                <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
                <p style="text-align: center; font-size: 13px; color: #666; font-style: italic;">
                    *Ivonne, ponte a trabajar duro hoy para que puedas dormir y tomar un copete en la noche con la pizarra limpia. El hámster te vigila.* 🐹👁️
                </p>
            </div>
        </body>
    </html>
    """

    # ================= PARTE 4: ENVÍO DEL CORREO =================
    msg = MIMEMultipart()
    msg['From'] = EMAIL_EMISOR
    msg['To'] = EMAIL_RECEPTOR
    
    # Asunto dinámico según el tipo de desastre
    total_retrasos = len(df_criticas) + len(df_notas_vencidas)
    msg['Subject'] = f"{msg_titulo} ({total_retrasos} pendientes) - {hoy.strftime('%d/%m/%Y')}"

    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_EMISOR, EMAIL_PASSWORD)
        server.sendmail(EMAIL_EMISOR, EMAIL_RECEPTOR, msg.as_string())
        server.quit()
        print(f"✅ ¡Éxito! Reporte consolidado de {total_retrasos} alertas enviado correctamente.")
    except Exception as e:
        print(f"❌ Error al enviar el correo por SMTP: {e}")

if __name__ == "__main__":
    generar_reporte_empaque()