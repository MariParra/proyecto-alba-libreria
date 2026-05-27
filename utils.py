import subprocess
import sys
import os
import pandas as pd

def requirements():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Librerías instaladas correctamente.")
    except Exception as e:
        print(f"Error al instalar requisitos: {e}")

def clean_text(text):
    return str(text).lower().strip()

def load_file(path):
    """Detecta si es excel o csv y lo carga."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        return pd.read_csv(path)
    elif ext in ['.xlsx', '.xls']:
        # sheet_name = 0 toma siempre la primera hoja
        return pd.read_excel(path, sheet_name = 0)
    return pd.DataFrame()