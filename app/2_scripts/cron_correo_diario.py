import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path
import pandas as pd
from supabase import create_client

# --- FUNCIÓN DE CARGA INTELIGENTE DE SECRETOS DE STREAMLIT (.toml) ---
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

# --- FUNCIÓN DE PARSEO DE FECHAS A PRUEBA DE BALAS ---
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

# 1. Cargar secretos e inicializar variables
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
        print("❌ Error de configuración: No se encontraron las credenciales de Supabase.")
        return
    if not EMAIL_EMISOR or not EMAIL_RECEPTOR or not EMAIL_PASSWORD:
        print("❌ Error de configuración: Faltan las credenciales SMTP o las direcciones de correo.")
        return

    # Inicializar cliente de Supabase
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 2. Consultar pedidos pendientes
    res = supabase.table("registro_ventas").select("venta_id, fecha_venta, estado, libros_vendidos, cliente:clientes(nombre)").execute()
    if not res.data:
        print("No se encontraron registros de ventas.")
        return
        
    df = pd.DataFrame(res.data)
    
    # 🌟 CORRECCIÓN: Aplicamos el parseador unificado
    df['fecha_dt'] = unificar_formatos_fecha(df['fecha_venta'])
    hoy = datetime.now()
    
    df['dias'] = df['fecha_dt'].apply(
        lambda x: (hoy - x).days if pd.notna(x) else 0
    )
    
    # Filtrar pedidos con más de 5 días creados sin armar
    df_criticas = df[
        (df['dias'] > 5) & 
        (~df['estado'].isin(['PAQUETE LISTO', 'FINALIZADO']))
    ].copy()
    
    if df_criticas.empty:
        print("🟢 No hay pedidos retrasados en el limbo hoy.")
        return
        
    # Aplanar el nombre del cliente
    df_criticas['cliente_nombre'] = df_criticas['cliente'].apply(lambda x: x.get('nombre') if isinstance(x, dict) else 'Cliente')

    # 3. Construcción del cuerpo del correo en HTML (Diseño Profesional)
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ff4b4b; border-radius: 8px; padding: 20px; background-color: #fafafa;">
                <h2 style="color: #d32f2f; text-align: center; margin-top: 0;">🚨 ALBA BODEGA: Alerta de Pedidos por Armar 🚨</h2>
                <p>Hola Alba, te enviamos el reporte automático de bodega. Tienes <strong>{len(df_criticas)}</strong> pedidos pendientes de preparación que llevan más de 5 días en espera:</p>
                <hr style="border: 0; border-top: 1px solid #ccc; margin: 20px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #ffebee;">
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Venta ID</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Cliente</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Antigüedad</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Libros a Empacar</th>
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
                <p style="margin-top: 25px; text-align: center; font-size: 13px; color: #666;">
                    *Una vez armados, recuerda marcarlos como '¡YA LO ARMÉ!' en la aplicación para desactivar estas alertas.*
                </p>
            </div>
        </body>
    </html>
    """
    
    # 4. Enviar el correo electrónico vía SMTP de Gmail
    msg = MIMEMultipart()
    msg['From'] = EMAIL_EMISOR
    msg['To'] = EMAIL_RECEPTOR
    msg['Subject'] = f"🚨 ALBA BODEGA: {len(df_criticas)} Pedidos Pendientes de Armado - {hoy.strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_EMISOR, EMAIL_PASSWORD)
        server.sendmail(EMAIL_EMISOR, EMAIL_RECEPTOR, msg.as_string())
        server.quit()
        print(f"✅ ¡Éxito! Reporte enviado con {len(df_criticas)} pedidos pendientes detectados.")
    except Exception as e:
        print(f"❌ Error crítico al enviar correo por SMTP: {e}")

if __name__ == "__main__":
    generar_reporte_empaque()