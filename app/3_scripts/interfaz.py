import tkinter as tk
from tkinter import ttk
from tkinter import font as tkFont
import datetime
import config

# -- WIDGET PERSONALIZADO PARA SELECCIÓN MÚLTIPLE --
class MultiSelectMenu(tk.Frame):
    def __init__(self, parent, label_text, options, initial_selection):
        super().__init__(parent, bg=config.COLOR_FONDO_PRINCIPAL)
        
        tk.Label(self, text=label_text, font=("Helvetica", 10, "bold"), bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO).pack(side="left", padx=(10, 2))
        
        self.button = tk.Button(self, text="Seleccionar ▾", font=("Helvetica", 10), bg="white", relief="solid", bd=1, command=self.show_menu)
        self.button.pack(side="left", padx=5)
        
        self.menu = tk.Toplevel(self)
        self.menu.wm_overrideredirect(True)
        self.menu.withdraw()

        self.vars = {}
        for option in options:
            var = tk.BooleanVar(value=(option in initial_selection))
            cb = tk.Checkbutton(self.menu, text=option, variable=var, font=("Helvetica", 10))
            cb.pack(anchor="w", padx=10, pady=2)
            self.vars[option] = var
            
        self.menu.bind("<FocusOut>", lambda e: self.menu.withdraw())

    def show_menu(self):
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height()
        self.menu.geometry(f"+{x}+{y}")
        self.menu.deiconify()
        self.menu.focus_set()

    def get_selection(self):
        return [option for option, var in self.vars.items() if var.get()]

def construir_interfaz(ventana, app_logica):
    # -- CONFIGURAR VENTANA PRINCIPAL --
    ventana.title("Panel de Control Alba Librería")
    ventana.geometry(f"{config.VENTANA_ANCHO}x{config.VENTANA_ALTO}")
    ventana.configure(bg=config.COLOR_FONDO_PRINCIPAL)

    # -- CREAR OBJETOS DE FUENTE --
    font_normal = tkFont.Font(family="Helvetica", size=10)
    font_bold = tkFont.Font(family="Helvetica", size=10, weight="bold")
    font_italic = tkFont.Font(family="Helvetica", size=9, slant="italic")
    font_titulo_boton = tkFont.Font(family="Helvetica", size=11, weight="bold")
    font_pequena = tkFont.Font(family="Helvetica", size=9)
    font_pequena_bold = tkFont.Font(family="Helvetica", size=9, weight="bold")

    # -- CONFIGURAR ESTILOS --
    estilo = ttk.Style()
    estilo.theme_use("clam")
    estilo.configure("Treeview", background="#FFFFFF", foreground=config.COLOR_TEXTO, rowheight=25, fieldbackground="#FFFFFF", gridcolor="#FCE4EC", font=font_normal)
    estilo.map("Treeview", background=[("selected", config.COLOR_ROSA_BOTON_SEC)], foreground=[("selected", config.COLOR_TEXTO)])
    estilo.configure("Treeview.Heading", background="#FCE4EC", foreground=config.COLOR_TEXTO, font=font_bold)
    estilo.configure("TNotebook", background=config.COLOR_FONDO_PRINCIPAL, borderwidth=0)
    estilo.configure("TNotebook.Tab", background=config.COLOR_ROSA_BOTON_SEC, foreground=config.COLOR_TEXTO, font=font_bold, padding=[15, 5])
    estilo.map("TNotebook.Tab", background=[("selected", config.COLOR_CONTENEDORES)])

    # -- OBTENER FECHAS DINAMICAS --
    ahora = datetime.datetime.now()
    anio_actual = ahora.year
    anios_dinamicos = [str(y) for y in range(2025, anio_actual + 5)]
    meses_espanol = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    mes_actual_str = meses_espanol[ahora.month - 1]

    # -- BARRA SUPERIOR --
    frame_top = tk.Frame(ventana, bg=config.COLOR_FONDO_PRINCIPAL, padx=10, pady=10)
    frame_top.pack(fill="x")
    
    # -- MENÚ DE MESES --
    mes_menu = MultiSelectMenu(frame_top, "Mes(es):", meses_espanol, [mes_actual_str])
    mes_menu.pack(side="left")
    app_logica['menu_meses'] = mes_menu 

    # -- COMBOBOX DE AÑO --
    tk.Label(frame_top, text="Año:", font=font_bold, bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO).pack(side="left", padx=(12, 2))
    app_logica['combo_anio'] = ttk.Combobox(frame_top, values=anios_dinamicos, state="readonly", width=6, font=font_normal)
    app_logica['combo_anio'].set(str(anio_actual))
    app_logica['combo_anio'].pack(side="left", padx=5)
    
    tk.Button(frame_top, text="Sincronizar Periodo", command=app_logica['cmd_sincronizar_periodo'], bg=config.COLOR_ROSA_MEDIO, fg="white", font=font_bold, relief="flat", cursor="hand2").pack(side="left", padx=15)

    # -- PANEL DE IMPORTACIONES --
    frame_imp = tk.LabelFrame(frame_top, text="Importaciones Externas", bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO, font=font_pequena_bold)
    frame_imp.pack(side="right", padx=10)
    tk.Button(frame_imp, text="Sincronizar Clientes", command=app_logica['cmd_sync_clientes'], bg=config.COLOR_BOTON_CRUD, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_imp, text="Cargar Base Libros", command=app_logica['cmd_import_catalogo'], bg=config.COLOR_BOTON_CATALOGO, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)

    # -- CONTENEDOR DE PESTAÑAS --
    notebook = ttk.Notebook(ventana)
    notebook.pack(expand=True, fill="both", padx=10, pady=10)
    tab_despachos = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    tab_inventario = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(tab_despachos, text="Asignación Mensual Suscripción")
    notebook.add(tab_inventario, text="Catálogo e Inventario")

    # =========================================================
    # -- PESTAÑA 1: ASIGNACIÓN DE SUSCRIPCIÓN --
    # =========================================================
    frame_despach = tk.LabelFrame(tab_despachos, text="Asignación Mensual Suscripción", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_bold, padx=10, pady=10)
    frame_despach.pack(expand=True, fill="both", padx=10, pady=10)
    
    frame_controles = tk.Frame(frame_despach, bg=config.COLOR_CONTENEDORES)
    frame_controles.pack(fill="x", padx=5, pady=5)
    
    tk.Label(frame_controles, text="Buscar Cliente o Libro:", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_normal).pack(side="left")
    app_logica['txt_buscar'] = tk.Entry(frame_controles, highlightbackground=config.COLOR_ROSA_BOTON_SEC, relief="solid", bd=1, font=font_normal)
    app_logica['txt_buscar'].pack(side="left", expand=True, fill="x", padx=5)
    app_logica['txt_buscar'].bind("<KeyRelease>", app_logica['cmd_filtrar_teclado'])
    
    frame_opciones = tk.LabelFrame(frame_despach, text="Opciones de Vista", bg=config.COLOR_CONTENEDORES, font=font_pequena, padx=10)
    frame_opciones.pack(fill="x", padx=5, pady=(5,10))
    app_logica['vars_columnas'] = {}
    columnas_opcionales = {"email": "Email", "tel": "Teléfono", "dir": "Dirección"}
    for col_id, col_text in columnas_opcionales.items():
        var = tk.IntVar(value=0)
        chk = tk.Checkbutton(frame_opciones, text=col_text, variable=var, bg=config.COLOR_CONTENEDORES, font=font_pequena, command=app_logica['cmd_actualizar_columnas'])
        chk.pack(side="left", padx=10)
        app_logica['vars_columnas'][col_id] = var

    # -- TABLA DE CLIENTES (Eliminado "fecha_pago") --
    columnas_definidas = ("id", "nom", "email", "libro", "mes", "ano", "env", "fecha_asig", "tel", "dir", "lib_ext", "pagado", "env_pag", "est_env")
    app_logica['tabla_clientes'] = ttk.Treeview(frame_despach, columns=columnas_definidas, show="headings", height=15)
    
    cabeceras = [
        ("id", "ID"), ("nom", "Nombre Cliente"), ("email", "Email"), ("libro", "Libro Asignado"), 
        ("mes", "Mes"), ("ano", "Año"), ("env", "Tipo Envío"), ("fecha_asig", "Fecha Asignación"), 
        ("tel", "Teléfono"), ("dir", "Dirección"),
        ("lib_ext", "Libros Extras"), ("pagado", "Pagado"), ("env_pag", "Envío Pag."), ("est_env", "Est. Envío")
    ]
    for col_id, text in cabeceras:
        app_logica['tabla_clientes'].heading(col_id, text=text)
    
    app_logica['tabla_clientes']['displaycolumns'] = ('id', 'nom', 'libro', 'mes', 'ano', 'env', 'fecha_asig', 'lib_ext', 'pagado', 'env_pag', 'est_env')
    
    app_logica['tabla_clientes'].column("id", width=30, anchor="center")
    app_logica['tabla_clientes'].column("nom", width=120)
    app_logica['tabla_clientes'].column("email", width=150)
    app_logica['tabla_clientes'].column("libro", width=120)
    app_logica['tabla_clientes'].column("mes", width=70, anchor="center")
    app_logica['tabla_clientes'].column("ano", width=50, anchor="center")
    app_logica['tabla_clientes'].column("env", width=80, anchor="center")
    app_logica['tabla_clientes'].column("fecha_asig", width=110, anchor="center")
    app_logica['tabla_clientes'].column("lib_ext", width=80, anchor="center")
    app_logica['tabla_clientes'].column("pagado", width=60, anchor="center")
    app_logica['tabla_clientes'].column("env_pag", width=70, anchor="center")
    app_logica['tabla_clientes'].column("est_env", width=80, anchor="center")
    app_logica['tabla_clientes'].column("tel", width=80)
    app_logica['tabla_clientes'].column("dir", width=150)

    app_logica['tabla_clientes'].pack(expand=True, fill="both", padx=5, pady=5)
    tk.Button(frame_despach, text="ASIGNAR LIBRO SELECCIONADO", command=app_logica['cmd_asignar_libro'], bg=config.COLOR_ROSA_FUERTE, fg="white", font=font_titulo_boton, pady=8, relief="flat", cursor="hand2").pack(fill="x", padx=5, pady=10)

    # =========================================================
    # -- PESTAÑA 2: INVENTARIO Y CRUD --
    # =========================================================
    frame_inv = tk.LabelFrame(tab_inventario, text="Stock Libros", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_bold, padx=10, pady=10)
    frame_inv.pack(side="left", expand=True, fill="both", padx=10, pady=10)
    
    frame_busc_inv = tk.Frame(frame_inv, bg=config.COLOR_CONTENEDORES)
    frame_busc_inv.pack(fill="x", padx=5, pady=5)
    tk.Label(frame_busc_inv, text="Buscar Título/Autor:", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_normal).pack(side="left")
    app_logica['txt_buscar_inv'] = tk.Entry(frame_busc_inv, highlightbackground=config.COLOR_ROSA_BOTON_SEC, relief="solid", bd=1, font=font_normal)
    app_logica['txt_buscar_inv'].pack(side="left", expand=True, fill="x", padx=5)
    app_logica['txt_buscar_inv'].bind("<KeyRelease>", app_logica['cmd_filtrar_inv_teclado'])

    app_logica['tabla_inventario'] = ttk.Treeview(frame_inv, columns=("id", "tit", "aut", "gen", "edit", "stk", "pre"), show="headings", height=15)
    for col, text in [("id", "ID"), ("tit", "Título"), ("aut", "Autor"), ("gen", "Género"), ("edit", "Editorial"), ("stk", "Stock"), ("pre", "Precio")]:
        app_logica['tabla_inventario'].heading(col, text=text)
    app_logica['tabla_inventario'].column("id", width=40, anchor="center")
    app_logica['tabla_inventario'].column("stk", width=50, anchor="center")
    app_logica['tabla_inventario'].column("pre", width=70, anchor="center")
    app_logica['tabla_inventario'].pack(expand=True, fill="both", padx=5, pady=5)
    
    app_logica['lbl_stock_total'] = tk.Label(frame_inv, text="Unidades Totales en Inventario: 0", font=font_titulo_boton, bg=config.COLOR_ROSA_BOTON_SEC, fg=config.COLOR_TEXTO, pady=8)
    app_logica['lbl_stock_total'].pack(fill="x", padx=5, pady=5)

    app_logica['tabla_inventario'].tag_configure("agotado", background="#FFCDD2", foreground="#B71C1C")
    app_logica['tabla_inventario'].tag_configure("bajo", background="#FFF9C4", foreground="#F57F17")
    app_logica['tabla_inventario'].tag_configure("normal", background="#FFFFFF", foreground=config.COLOR_TEXTO)

    frame_form = tk.LabelFrame(tab_inventario, text="Administrar Libro Físico", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_bold, padx=10, pady=10)
    frame_form.pack(side="right", fill="y", padx=10, pady=10)
    
    app_logica['lbl_status_id'] = tk.Label(frame_form, text="Modo: Creando nuevo libro", font=font_italic, fg="#C2185B", bg=config.COLOR_CONTENEDORES)
    app_logica['lbl_status_id'].pack(anchor="w", pady=(0, 10))

    app_logica['entries'] = {}
    for campo, widget_type in [("Título", "entry"), ("Autor", "entry"), ("Género", "combo"), ("Editorial", "combo"), ("Stock", "entry"), ("Precio", "entry")]:
        tk.Label(frame_form, text=f"{campo}:", bg=config.COLOR_CONTENEDORES, font=font_pequena).pack(anchor="w")
        if widget_type == "entry":
            w = tk.Entry(frame_form, width=25, highlightbackground=config.COLOR_ROSA_BOTON_SEC, relief="solid", bd=1, font=font_pequena)
        else:
            w = ttk.Combobox(frame_form, width=22, font=font_pequena, state="normal")
        w.pack(pady=2)
        app_logica['entries'][campo.lower()] = w

    tk.Button(frame_form, text="Registrar Nuevo", command=app_logica['cmd_guardar_nuevo'], bg=config.COLOR_ROSA_MEDIO, fg="white", font=font_bold, relief="flat", cursor="hand2").pack(fill="x", pady=5)
    tk.Button(frame_form, text="Modificar Seleccionado", command=app_logica['cmd_modificar_sel'], bg=config.COLOR_BOTON_CRUD, fg="white", font=font_bold, relief="flat", cursor="hand2").pack(fill="x", pady=5)
    tk.Button(frame_form, text="Limpiar Formulario", command=app_logica['cmd_limpiar_form'], bg="#E0E0E0", fg=config.COLOR_TEXTO, font=font_normal, relief="flat", cursor="hand2").pack(fill="x", pady=10)
    tk.Button(frame_form, text="Eliminar Seleccionado", command=app_logica['cmd_eliminar_sel'], bg="#D32F2F", fg="white", font=font_bold, relief="flat", cursor="hand2").pack(fill="x", pady=(20, 5))
