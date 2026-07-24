import os

# -- DEFINIR NOMBRE DE LA BASE DE DATOS --
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, "2_database", "libreria.db")

# -- ESTABLECER DIMENSIONES DE LA VENTANA PRINCIPAL --
VENTANA_ANCHO = 1280
VENTANA_ALTO = 700

# -- CONFIGURAR FUENTE PRINCIPAL --
FUENTE_PRINCIPAL = "Segoe UI"

# -- CONFIGURAR PALETA DE COLORES (ALTO CONTRASTE Y LEGIBILIDAD) --
COLOR_FONDO_PRINCIPAL = "#FCE4EC"  # Rosa muy pálido
COLOR_CONTENEDORES = "#FFFFFF"     # Blanco puro

# Texto oscuro para máximo contraste sobre fondos claros
COLOR_TEXTO = "#1E1E2F"            # Azul oscuro casi negro

# Tonos profundos para botones
COLOR_ROSA_FUERTE = "#C2185B"      # Magenta oscuro (Botones principales como ASIGNAR)
COLOR_ROSA_MEDIO = "#D81B60"       # Magenta vibrante (Botones secundarios activos)
COLOR_BOTON_CRUD = "#F00A5E"       # (Acciones de guardado/modificación)
COLOR_BOTON_CATALOGO = "#B80090"   # Morado oscuro (Importaciones masivas)

# Tonos suaves para selecciones
COLOR_ROSA_BOTON_SEC = "#F8BBD0"   # Rosa pastel (Selección en tablas y botones pasivos)
