# main.py
import tkinter as tk
from controlador import AppControlador
import config

def iniciar_app():
    # 1. Instanciar la ventana principal
    root = tk.Tk()
    root.title("Alba Librería - Gestor Principal")
    
    # 2. Configuración de dimensiones y fondo
    root.geometry("1300x800")
    root.configure(bg=config.COLOR_FONDO_PRINCIPAL)

    # 3. Inicializar la aplicación a través del controlador
    app = AppControlador(root)

    # 4. Arrancar el bucle de eventos de Tkinter
    root.mainloop()

if __name__ == "__main__":
    iniciar_app()