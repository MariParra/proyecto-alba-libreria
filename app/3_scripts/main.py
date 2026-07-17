import tkinter as tk
from controlador import AppControlador
import config
from conexion import realizar_respaldo_automatico # <-- 1. IMPORTAR LA FUNCIÓN

def iniciar_app():
    # --- RESPALDO AL ABRIR LA APLICACIÓN ---
    realizar_respaldo_automatico(etiqueta="OPEN")

    # 1. Instanciar la ventana principal
    root = tk.Tk()
    root.title("Alba Librería - Gestor Principal")
    
    # 2. Configuración de dimensiones y fondo
    root.geometry("1300x800")
    root.configure(bg=config.COLOR_FONDO_PRINCIPAL)

    # 3. Inicializar la aplicación a través del controlador
    app = AppControlador(root)

    # --- LÓGICA DE RESPALDO AL CERRAR ---
    def al_cerrar_ventana():
        """
        Esta función se ejecuta cuando el usuario cierra la ventana.
        Primero crea el respaldo y luego cierra la aplicación.
        """
        if tk.messagebox.askokcancel("Salir", "¿Estás seguro de que quieres salir?"):
            realizar_respaldo_automatico(etiqueta="CLOSE")
            root.destroy()

    # 4. Interceptar el evento de cierre de la ventana
    root.protocol("WM_DELETE_WINDOW", al_cerrar_ventana)

    # 5. Arrancar el bucle de eventos de Tkinter
    root.mainloop()

if __name__ == "__main__":
    iniciar_app()