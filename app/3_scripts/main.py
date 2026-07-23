import tkinter as tk
from tkinter import messagebox  # Importante para que funcione la ventanita de confirmación al salir
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

    # --- LÓGICA DE CIERRE DE VENTANA LÍMPIA ---
    def al_cerrar_ventana():
        """
        Esta función se ejecuta cuando el usuario cierra la ventana.
        """
        if messagebox.askokcancel("Salir", "¿Estás seguro de que quieres salir?"):
            # Ya no hacemos el respaldo local, solo cerramos la app.
            root.destroy()

    # 4. Interceptar el evento de cierre de la ventana
    root.protocol("WM_DELETE_WINDOW", al_cerrar_ventana)

    # 5. Arrancar el bucle de eventos de Tkinter
    root.mainloop()

if __name__ == "__main__":
    iniciar_app()