import tkinter as tk
from tkinter import ttk
from tkinter import font as tkFont
import config

def construir_interfaz(ventana, app_logica):
    # -- CONFIGURAR VENTANA PRINCIPAL --
    ventana.title("Panel de Control Alba Librería")
    ventana.geometry(f"{config.VENTANA_ANCHO}x{config.VENTANA_ALTO}")
    ventana.configure(bg=config.COLOR_FONDO_PRINCIPAL)

    # -- CREAR OBJETOS DE FUENTE (SIN ESPACIOS EN EL NOMBRE PARA EVITAR BUGS DE TCL) --
    font_normal = tkFont.Font(family="Helvetica", size=10)
    font_bold = tkFont.Font(family="Helvetica", size=10, weight="bold")
    font_italic = tkFont.Font(family="Helvetica", size=9, slant="italic")
    font_titulo_boton = tkFont.Font(family="Helvetica", size=11, weight="bold")
    font_pequena = tkFont.Font(family="Helvetica", size=9)
    font_pequena_bold = tkFont.Font(family="Helvetica", size=9, weight="bold")

    # -- CONFIGURAR ESTILOS PARA WIDGETS TTK --
    estilo = ttk.Style()
    estilo.theme_use("clam")
    estilo.configure("Treeview", background="#FFFFFF", foreground=config.COLOR_TEXTO, rowheight=25, fieldbackground="#FFFFFF", gridcolor="#FCE4EC", font=font_normal)
    estilo.map("Treeview", background=[("selected", config.COLOR_ROSA_BOTON_SEC)], foreground=[("selected", config.COLOR_TEXTO)])
    estilo.configure("Treeview.Heading", background="#FCE4EC", foreground=config.COLOR_TEXTO, font=font_bold)
    
    # -- ESTILIZAR LAS PESTAÑAS (NOTEBOOK) --
    estilo.configure("TNotebook", background=config.COLOR_FONDO_PRINCIPAL, borderwidth=0)
    estilo.configure("TNotebook.Tab", background=config.COLOR_ROSA_BOTON_SEC, foreground=config.COLOR_TEXTO, font=font_bold, padding=[15, 5])
    estilo.map("TNotebook.Tab", background=[("selected", config.COLOR_CONTENEDORES)])

    # -- CREAR BARRA SUPERIOR (SIEMPRE VISIBLE) --
    frame_top = tk.Frame(ventana, bg=config.COLOR_FONDO_PRINCIPAL, padx=10, pady=10)
    frame_top.pack(fill="x")
    tk.Label(frame_top, text="Mes:", font=font_bold, bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO).pack(side="left", padx=(10, 2))
    app_logica['combo_mes'] = ttk.Combobox(frame_top, values=["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], state="readonly", width=10, font=font_normal)
    app_logica['combo_mes'].set("Junio")
    app_logica['combo_mes'].pack(side="left", padx=5)
    tk.Label(frame_top, text="Año:", font=font_bold, bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO).pack(side="left", padx=(12, 2))
    app_logica['combo_anio'] = ttk.Combobox(frame_top, values=["2025", "2026", "2027", "2028"], state="readonly", width=6, font=font_normal)
    app_logica['combo_anio'].set("2026")
    app_logica['combo_anio'].pack(side="left", padx=5)
    tk.Button(frame_top, text="Sincronizar Periodo", command=app_logica['cmd_sincronizar_periodo'], bg=config.COLOR_ROSA_MEDIO, fg="white", font=font_bold, relief="flat", cursor="hand2").pack(side="left", padx=15)

    # -- CREAR SUBPANEL DE IMPORTACIONES (SIEMPRE VISIBLE) --
    frame_imp = tk.LabelFrame(frame_top, text="Importaciones Externas", bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO, font=font_pequena_bold)
    frame_imp.pack(side="right", padx=10)
    tk.Button(frame_imp, text="Sincronizar Clientes", command=app_logica['cmd_sync_clientes'], bg=config.COLOR_BOTON_CRUD, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_imp, text="Cargar Base Libros", command=app_logica['cmd_import_catalogo'], bg=config.COLOR_BOTON_CATALOGO, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)

    # -- CREAR CONTENEDOR DE PESTAÑAS (NOTEBOOK) --
    notebook = ttk.Notebook(ventana)
    notebook.pack(expand=True, fill="both", padx=10, pady=10)

    # -- CREAR FRAMES PARA CADA PESTAÑA --
    tab_despachos = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    tab_inventario = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)

    # -- AGREGAR PESTAÑAS AL NOTEBOOK --
    notebook.add(tab_despachos, text="Asignación Mensual Suscripción")
    notebook.add(tab_inventario, text="Catálogo e Inventario")

    # =========================================================
    # -- CONTENIDO DE LA PESTAÑA 1: ASIGNACIÓN DE SUSCRIPCIÓN --
    # =========================================================
    frame_despach = tk.LabelFrame(tab_despachos, text="Asignación Mensual Suscripción", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_bold, padx=10, pady=10)
    frame_despach.pack(expand=True, fill="both", padx=10, pady=10)
    
    frame_busc = tk.Frame(frame_despach, bg=config.COLOR_CONTENEDORES)
    frame_busc.pack(fill="x", padx=5, pady=5)
    tk.Label(frame_busc, text="Buscar:", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_normal).pack(side="left")
    app_logica['txt_buscar'] = tk.Entry(frame_busc, highlightbackground=config.COLOR_ROSA_BOTON_SEC, relief="solid", bd=1, font=font_normal)
    app_logica['txt_buscar'].pack(side="left", expand=True, fill="x", padx=5)
    app_logica['txt_buscar'].bind("<KeyRelease>", app_logica['cmd_filtrar_teclado'])
    
    # -- ACTUALIZAR COLUMNA A 'LIBRO ASIGNADO' --
    app_logica['tabla_clientes'] = ttk.Treeview(frame_despach, columns=("id", "nom", "em", "ent"), show="headings", height=15)
    for col, text in [("id", "ID"), ("nom", "Nombre Cliente"), ("em", "Email"), ("ent", "Libro Asignado")]:
        app_logica['tabla_clientes'].heading(col, text=text)
    app_logica['tabla_clientes'].column("id", width=40, anchor="center")
    app_logica['tabla_clientes'].pack(expand=True, fill="both", padx=5, pady=5)
    tk.Button(frame_despach, text="ASIGNAR LIBRO SELECCIONADO", command=app_logica['cmd_asignar_libro'], bg=config.COLOR_ROSA_FUERTE, fg="white", font=font_titulo_boton, pady=8, relief="flat", cursor="hand2").pack(fill="x", padx=5, pady=10)

    # =========================================================
    # -- CONTENIDO DE LA PESTAÑA 2: INVENTARIO Y CRUD --
    # =========================================================
    # -- PANEL DE INVENTARIO (IZQUIERDA) --
    frame_inv = tk.LabelFrame(tab_inventario, text="Stock Libros", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_bold, padx=10, pady=10)
    frame_inv.pack(side="left", expand=True, fill="both", padx=10, pady=10)
    
    frame_busc_inv = tk.Frame(frame_inv, bg=config.COLOR_CONTENEDORES)
    frame_busc_inv.pack(fill="x", padx=5, pady=5)
    tk.Label(frame_busc_inv, text="Buscar Título/Autor:", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_normal).pack(side="left")
    app_logica['txt_buscar_inv'] = tk.Entry(frame_busc_inv, highlightbackground=config.COLOR_ROSA_BOTON_SEC, relief="solid", bd=1, font=font_normal)
    app_logica['txt_buscar_inv'].pack(side="left", expand=True, fill="x", padx=5)
    app_logica['txt_buscar_inv'].bind("<KeyRelease>", app_logica['cmd_filtrar_inv_teclado'])

    # -- TABLA DE INVENTARIO --
    app_logica['tabla_inventario'] = ttk.Treeview(frame_inv, columns=("id", "tit", "aut", "gen", "edit", "stk", "pre"), show="headings", height=15)
    for col, text in [("id", "ID"), ("tit", "Título"), ("aut", "Autor"), ("gen", "Género"), ("edit", "Editorial"), ("stk", "Stock"), ("pre", "Precio")]:
        app_logica['tabla_inventario'].heading(col, text=text)
    app_logica['tabla_inventario'].column("id", width=40, anchor="center")
    app_logica['tabla_inventario'].column("stk", width=50, anchor="center")
    app_logica['tabla_inventario'].column("pre", width=70, anchor="center")
    app_logica['tabla_inventario'].pack(expand=True, fill="both", padx=5, pady=5)
    
    app_logica['lbl_stock_total'] = tk.Label(frame_inv, text="Unidades Totales en Inventario: 0", font=font_titulo_boton, bg=config.COLOR_ROSA_BOTON_SEC, fg=config.COLOR_TEXTO, pady=8)
    app_logica['lbl_stock_total'].pack(fill="x", padx=5, pady=5)

    # -- CONFIGURAR SEMAFORO DE COLORES PARA STOCK --
    app_logica['tabla_inventario'].tag_configure("agotado", background="#FFCDD2", foreground="#B71C1C")
    app_logica['tabla_inventario'].tag_configure("bajo", background="#FFF9C4", foreground="#F57F17")
    app_logica['tabla_inventario'].tag_configure("normal", background="#FFFFFF", foreground=config.COLOR_TEXTO)

    # -- PANEL DE FORMULARIO CRUD (DERECHA) --
    frame_form = tk.LabelFrame(tab_inventario, text="Administrar Libro Físico", bg=config.COLOR_CONTENEDORES, fg=config.COLOR_TEXTO, font=font_bold, padx=10, pady=10)
    frame_form.pack(side="right", fill="y", padx=10, pady=10)
    
    app_logica['lbl_status_id'] = tk.Label(frame_form, text="Modo: Creando nuevo libro", font=font_italic, fg="#C2185B", bg=config.COLOR_CONTENEDORES)
    app_logica['lbl_status_id'].pack(anchor="w", pady=(0, 10))

    # -- CREAR CAMPOS DE TEXTO Y COMBOBOXES PARA FORMULARIO --
    app_logica['entries'] = {}
    for campo, widget_type in [("Título", "entry"), ("Autor", "entry"), ("Género", "combo"), ("Editorial", "combo"), ("Stock", "entry"), ("Precio", "entry")]:
        tk.Label(frame_form, text=f"{campo}:", bg=config.COLOR_CONTENEDORES, font=font_pequena).pack(anchor="w")
        if widget_type == "entry":
            w = tk.Entry(frame_form, width=25, highlightbackground=config.COLOR_ROSA_BOTON_SEC, relief="solid", bd=1, font=font_pequena)
        else:
            w = ttk.Combobox(frame_form, width=22, font=font_pequena, state="normal")
        w.pack(pady=2)
        app_logica['entries'][campo.lower()] = w

    # -- CREAR BOTONES CRUD --
    tk.Button(frame_form, text="Registrar Nuevo", command=app_logica['cmd_guardar_nuevo'], bg=config.COLOR_ROSA_MEDIO, fg="white", font=font_bold, relief="flat", cursor="hand2").pack(fill="x", pady=5)
    tk.Button(frame_form, text="Modificar Seleccionado", command=app_logica['cmd_modificar_sel'], bg=config.COLOR_BOTON_CRUD, fg="white", font=font_bold, relief="flat", cursor="hand2").pack(fill="x", pady=5)
    tk.Button(frame_form, text="Limpiar Formulario", command=app_logica['cmd_limpiar_form'], bg="#E0E0E0", fg=config.COLOR_TEXTO, font=font_normal, relief="flat", cursor="hand2").pack(fill="x", pady=10)
    tk.Button(frame_form, text="Eliminar Seleccionado", command=app_logica['cmd_eliminar_sel'], bg="#D32F2F", fg="white", font=font_bold, relief="flat", cursor="hand2").pack(fill="x", pady=(20, 5))
