import tkinter as tk
from tkinter import ttk
import config

def construir_interfaz(ventana, widgets, comandos_ui):
    font_bold = ("Helvetica", 11, "bold")
    font_pequena = ("Helvetica", 9)
    font_pequena_bold = ("Helvetica", 9, "bold")
    font_italic_status = ("Helvetica", 9, "italic")

    estilo = ttk.Style()
    estilo.theme_use('clam')
    estilo.configure("TNotebook", background=config.COLOR_FONDO_PRINCIPAL, borderwidth=0)
    estilo.configure("TNotebook.Tab", background=config.COLOR_ROSA_BOTON_SEC, foreground=config.COLOR_TEXTO, font=("Helvetica", 10, "bold"), padding=[20, 8], borderwidth=0)
    estilo.map("TNotebook.Tab", background=[("selected", config.COLOR_CONTENEDORES)], expand=[("selected", [1, 1, 1, 1])])
    
    estilo.configure("Treeview.Heading", background="#FCE4EC", foreground="black", font=("Helvetica", 10, "bold"))
    estilo.map("Treeview.Heading", background=[("active", "#F8BBD0")])
    estilo.configure("Treeview", font=("Helvetica", 9), rowheight=25)
    estilo.map("Treeview", background=[("selected", config.COLOR_ROSA_BOTON_SEC)], foreground=[("selected", "black")])

    frame_top = tk.Frame(ventana, bg=config.COLOR_FONDO_PRINCIPAL, padx=10, pady=10)
    frame_top.pack(fill="x")
    
    frame_exportaciones = tk.LabelFrame(frame_top, text="Exportar Reportes", bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO, font=font_pequena_bold)
    frame_exportaciones.pack(side="right", padx=10)
    tk.Button(frame_exportaciones, text="A Excel", command=comandos_ui['cmd_exportar_excel'], bg="#1D6F42", fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_exportaciones, text="A GSheets", command=comandos_ui['cmd_exportar_gsheets'], bg="#0F9D58", fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    
    frame_acciones = tk.LabelFrame(frame_top, text="Operaciones de Base", bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO, font=font_pequena_bold)
    frame_acciones.pack(side="right", padx=10)
    tk.Button(frame_acciones, text="Sync Clientes", command=comandos_ui['cmd_sync_clientes'], bg=config.COLOR_BOTON_CRUD, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_acciones, text="Cargar Libros", command=comandos_ui['cmd_import_catalogo'], bg=config.COLOR_BOTON_CATALOGO, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)

    notebook = ttk.Notebook(ventana) 
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # --- PESTAÑA 1: ASIGNACIONES Y CLIENTES ---
    frame_asignaciones = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(frame_asignaciones, text="Asignaciones y Clientes")

    frame_controles_cli = tk.Frame(frame_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_controles_cli.pack(fill="x", padx=5, pady=5)

    tk.Label(frame_controles_cli, text="Meses:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_bold).pack(side="left")
    mb_meses = tk.Menubutton(frame_controles_cli, text="Seleccionar...", relief="raised", bg="white", width=15)
    mb_meses.pack(side="left", padx=5)
    menu_meses = tk.Menu(mb_meses, tearoff=0)
    mb_meses.config(menu=menu_meses)
    meses_lista = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    widgets['meses_vars'] = {}
    widgets['mb_meses'] = mb_meses
    for mes in meses_lista:
        var = tk.BooleanVar(value=False)
        widgets['meses_vars'][mes] = var
        menu_meses.add_checkbutton(label=mes, variable=var, command=comandos_ui['cmd_sincronizar_periodo'])
        
    tk.Label(frame_controles_cli, text="Año:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_bold).pack(side="left", padx=(10, 0))
    widgets['cmb_ano'] = ttk.Combobox(frame_controles_cli, values=[str(y) for y in range(2023, 2031)], width=6, state="readonly")
    widgets['cmb_ano'].pack(side="left", padx=5)

    tk.Label(frame_controles_cli, text="Filtros ->", bg=config.COLOR_FONDO_PRINCIPAL, font=font_bold).pack(side="left", padx=(30, 5))
    
    tk.Label(frame_controles_cli, text="Libro:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left")
    widgets['cmb_filtro_libro'] = ttk.Combobox(frame_controles_cli, values=["Todos", "Asignados", "Sin Asignar"], width=10, state="readonly")
    widgets['cmb_filtro_libro'].pack(side="left", padx=5)
    widgets['cmb_filtro_libro'].set("Todos")

    tk.Label(frame_controles_cli, text="Estado:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left", padx=(10,0))
    estados = ["TODOS", "EN PREPARACION", "POR ENVIAR", "ENVIADO", "POR RETIRAR", "RETIRADO"]
    widgets['cmb_filtro_estado'] = ttk.Combobox(frame_controles_cli, values=estados, width=15, state="readonly")
    widgets['cmb_filtro_estado'].pack(side="left", padx=5)
    widgets['cmb_filtro_estado'].set("TODOS")

    tk.Label(frame_controles_cli, text="Pagado:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left", padx=(10,0))
    widgets['cmb_filtro_pagado'] = ttk.Combobox(frame_controles_cli, values=["Todos", "Si", "No"], width=6, state="readonly")
    widgets['cmb_filtro_pagado'].pack(side="left", padx=5)
    widgets['cmb_filtro_pagado'].set("Todos")

    tk.Label(frame_controles_cli, text="Envío:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left", padx=(10,0))
    widgets['cmb_filtro_envio'] = ttk.Combobox(frame_controles_cli, values=["Todos", "Si", "No", "N/A"], width=6, state="readonly")
    widgets['cmb_filtro_envio'].pack(side="left", padx=5)
    widgets['cmb_filtro_envio'].set("Todos")

    frame_columnas_opc = tk.Frame(frame_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_columnas_opc.pack(fill="x", padx=5, pady=(0, 5))
    tk.Label(frame_columnas_opc, text="Mostrar info de contacto:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold, fg="#424242").pack(side="left")
    
    opcionales = [("RUT", "rut"), ("Email", "email"), ("Teléfono", "telefono"), ("Dirección", "direccion")]
    widgets['vars_opcionales'] = {}
    for texto, col_id in opcionales:
        var = tk.BooleanVar(value=False)
        widgets['vars_opcionales'][col_id] = var
        tk.Checkbutton(frame_columnas_opc, text=texto, variable=var, bg=config.COLOR_FONDO_PRINCIPAL, 
                       command=comandos_ui['cmd_toggle_columnas'], cursor="hand2").pack(side="left", padx=10)

    frame_tabla_cli = tk.Frame(frame_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_tabla_cli.pack(fill="both", expand=True, padx=5, pady=5)
    scroll_x_cli = ttk.Scrollbar(frame_tabla_cli, orient="horizontal")
    scroll_y_cli = ttk.Scrollbar(frame_tabla_cli, orient="vertical")
    
    # AÑADIDO: 'comentario' a la lista de columnas
    columnas_cli = ("asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario", "rut", "email", "telefono", "direccion")
    tabla_cli = ttk.Treeview(frame_tabla_cli, columns=columnas_cli, show="headings", selectmode="browse", xscrollcommand=scroll_x_cli.set, yscrollcommand=scroll_y_cli.set)
    
    # AÑADIDO: 'comentario' a las columnas visibles por defecto
    tabla_cli['displaycolumns'] = ("asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario")
    
    scroll_x_cli.config(command=tabla_cli.xview)
    scroll_y_cli.config(command=tabla_cli.yview)
    for col in columnas_cli:
        titulo_col = col.replace("_", " ").title()
        if col == "tipo_envio": titulo_col = "Tipo De Envio"
        if col == "envio_pag": titulo_col = "Envio Pagado"
            
        tabla_cli.heading(col, text=titulo_col)
        ancho = 60 if col in ["ano", "mes", "pagado", "envio_pag"] else 120
        if col == "comentario": ancho = 150 # Ancho para el comentario
        tabla_cli.column(col, width=ancho, minwidth=60)
        
    scroll_y_cli.pack(side="right", fill="y")
    scroll_x_cli.pack(side="bottom", fill="x")
    tabla_cli.pack(side="left", fill="both", expand=True)
    widgets['tabla_clientes'] = tabla_cli

    # --- PESTAÑA 2: INVENTARIO DE LIBROS ---
    frame_libros = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(frame_libros, text="Inventario de Libros")
    
    frame_form_libros = tk.LabelFrame(frame_libros, text=" Administrar Libro ", bg="#FFFFFF", font=font_bold, padx=20, pady=20)
    frame_form_libros.pack(side="right", fill="y", padx=(0, 15), pady=15)
    
    widgets['lbl_status_libro'] = tk.Label(frame_form_libros, text="Modo: Creando nuevo libro", font=font_italic_status, fg="#C2185B", bg="#FFFFFF")
    widgets['lbl_status_libro'].grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))
    widgets['form_libro_entries'] = {}
    
    # AÑADIDO: 'encuadernacion' al formulario
    campos_form = [("titulo", "Título", "entry"), ("autor", "Autor", "combo"), ("genero", "Género", "combo"), 
                   ("editorial", "Editorial", "combo"), ("encuadernacion", "Encuadernación", "combo_enc"),
                   ("stock", "Stock", "entry"), ("precio", "Precio", "entry")]
    
    vcmd_int = (ventana.register(comandos_ui['cmd_validar_int']), '%P')
    vcmd_float = (ventana.register(comandos_ui['cmd_validar_float']), '%P')
    
    for i, (col_id, label_text, tipo) in enumerate(campos_form, start=1):
        tk.Label(frame_form_libros, text=f"{label_text}:", bg="#FFFFFF", font=font_pequena_bold).grid(row=i, column=0, sticky="e", pady=8, padx=(0, 10))
        
        if tipo == "combo":
            entry = ttk.Combobox(frame_form_libros, width=27, font=("Helvetica", 10))
        # AÑADIDO: Lógica para el combobox de encuadernación
        elif tipo == "combo_enc":
            entry = ttk.Combobox(frame_form_libros, width=27, font=("Helvetica", 10), state="readonly",
                                 values=['TAPA BLANDA', 'TAPA DURA', 'BOLSILLO'])
        else:
            validation_cmd = None
            if col_id == "stock": validation_cmd = vcmd_int
            elif col_id == "precio": validation_cmd = vcmd_float
            entry = tk.Entry(frame_form_libros, width=28, relief="solid", bd=1, font=("Helvetica", 10), validate="key", validatecommand=validation_cmd)
            
        entry.grid(row=i, column=1, sticky="w", pady=8, ipady=4 if tipo == "entry" else 0)
        widgets['form_libro_entries'][col_id] = entry
        
    frame_botones = tk.Frame(frame_form_libros, bg="#FFFFFF")
    frame_botones.grid(row=len(campos_form)+1, column=0, columnspan=2, sticky="ew", pady=(30, 0))
    tk.Button(frame_botones, text="Guardar / Modificar", command=comandos_ui['cmd_guardar_libro'], bg=config.COLOR_ROSA_FUERTE, fg="white", font=font_bold, relief="flat", cursor="hand2", pady=8).pack(fill="x", pady=5)
    tk.Button(frame_botones, text="Limpiar Formulario", command=comandos_ui['cmd_limpiar_form_libro'], bg="#E0E0E0", fg=config.COLOR_TEXTO, font=font_pequena_bold, relief="flat", cursor="hand2", pady=6).pack(fill="x", pady=5)
    tk.Button(frame_botones, text="Eliminar Seleccionado", command=comandos_ui['cmd_eliminar_libro'], bg="#D32F2F", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=6).pack(fill="x", pady=(25, 5))

    frame_izquierdo = tk.Frame(frame_libros, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_izquierdo.pack(side="left", fill="both", expand=True, padx=15, pady=15)
    frame_busqueda = tk.Frame(frame_izquierdo, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_busqueda.pack(fill="x", pady=(0, 10))
    tk.Label(frame_busqueda, text="Buscar Libro (Título o Autor):", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left")
    widgets['entry_busqueda_libros'] = ttk.Entry(frame_busqueda, width=30)
    widgets['entry_busqueda_libros'].pack(side="left", padx=10)
    tk.Button(frame_busqueda, text="Buscar", command=comandos_ui['cmd_buscar_libro'], bg=config.COLOR_BOTON_CATALOGO, fg="white", relief="flat", cursor="hand2", padx=10).pack(side="left", padx=5)
    tk.Button(frame_busqueda, text="Quitar Filtro", command=comandos_ui['cmd_quitar_filtro'], bg="gray", fg="white", relief="flat", cursor="hand2", padx=10).pack(side="left", padx=5)
    
    frame_tabla_libros = tk.Frame(frame_izquierdo, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_tabla_libros.pack(fill="both", expand=True)
    scroll_x_lib = ttk.Scrollbar(frame_tabla_libros, orient="horizontal")
    scroll_y_lib = ttk.Scrollbar(frame_tabla_libros, orient="vertical")
    
    # AÑADIDO: 'encuadernacion' a las columnas de la tabla de libros
    columnas_lib = ("libro_id", "titulo", "autor", "genero", "editorial", "encuadernacion", "stock", "precio")
    tabla_lib = ttk.Treeview(frame_tabla_libros, columns=columnas_lib, show="headings", selectmode="browse", xscrollcommand=scroll_x_lib.set, yscrollcommand=scroll_y_lib.set)
    scroll_x_lib.config(command=tabla_lib.xview)
    scroll_y_lib.config(command=tabla_lib.yview)
    for col in columnas_lib:
        tabla_lib.heading(col, text=col.replace("_", " ").title())
        ancho = 120
        if col == "stock" or col == "precio":
            ancho = 80
        elif col == "libro_id":
            ancho = 60
        tabla_lib.column(col, width=ancho, minwidth=60, stretch=(col == "titulo"))
        
    scroll_y_lib.pack(side="right", fill="y")
    scroll_x_lib.pack(side="bottom", fill="x")
    tabla_lib.pack(side="left", fill="both", expand=True)
    widgets['tabla_libros'] = tabla_lib
    widgets['lbl_stock_total'] = tk.Label(frame_izquierdo, text="Unidades Totales en Inventario: 0", font=font_bold, bg=config.COLOR_ROSA_BOTON_SEC, fg=config.COLOR_TEXTO, pady=10)
    widgets['lbl_stock_total'].pack(fill="x", pady=(10, 0))