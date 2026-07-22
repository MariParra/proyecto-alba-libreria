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
    
    frame_exportaciones = tk.LabelFrame(frame_top, text="Exportar Reportes", bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO, font=font_pequena_bold, width=150, height=70)
    frame_exportaciones.pack(side="right", padx=10, fill="y")
    tk.Button(frame_exportaciones, text="A Excel", command=comandos_ui.get('cmd_exportar_excel'), 
            bg="#03BB85", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", width=15, pady=2).pack(side="right", padx=5)    

    frame_acciones = tk.LabelFrame(frame_top, text="Operaciones de Base", bg=config.COLOR_FONDO_PRINCIPAL, fg=config.COLOR_TEXTO, font=font_pequena_bold)
    frame_acciones.pack(side="right", padx=10)
    tk.Button(frame_acciones, text="Sync Clientes", command=comandos_ui['cmd_sync_clientes'], bg=config.COLOR_BOTON_CRUD, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_acciones, text="Cargar Libros", command=comandos_ui['cmd_import_catalogo'], bg=config.COLOR_BOTON_CATALOGO, fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_acciones, text="Actualizar Stock/Precios", command=comandos_ui['cmd_actualizar_stock'], bg="#8E4F8B", fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    tk.Button(frame_acciones, text="Asignar Pendientes (Auto)", command=comandos_ui['cmd_asignar_aleatorio'], 
                bg="#FF007F", fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="left", padx=5, pady=2)
    notebook = ttk.Notebook(ventana) 
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # --- PESTAÑA 1: ASIGNACIONES Y CLIENTES ---
    frame_asignaciones = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(frame_asignaciones, text="Asignación de Libros")
    
    frame_controles_cli = tk.Frame(frame_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_controles_cli.pack(fill="x", padx=5, pady=5)
    tk.Label(frame_controles_cli, text="Meses:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_bold).pack(side="left")
    
    mb_meses = tk.Menubutton(frame_controles_cli, text="Seleccionar...", relief="raised", bg="white", width=15)
    mb_meses.pack(side="left", padx=5)
    
    menu_meses = tk.Menu(mb_meses, tearoff=0)
    mb_meses.config(menu=menu_meses)
    
    # Evitar que se cierre al hacer clic
    def mantener_menu_abierto(event):
        try:
            # Forzamos al Menubutton a volver a desplegar su menú inmediatamente
            mb_meses.focus_set()
            mb_meses.event_generate('<Button-1>')
        except:
            pass
        
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
    tk.Button(frame_controles_cli, text="Eliminar Asignación Seleccionada", command=comandos_ui['cmd_eliminar_asignacion'], 
            bg="#C0392B", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2"
            ).pack(side="right", padx=(20, 10))
    tk.Button(frame_controles_cli, text="Cerrar Mes", command=comandos_ui['cmd_cerrar_mes'], 
                bg="#933B5B", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2"
                ).pack(side="right", padx=(5, 10))
    # --- Frame para Opciones de la Pestaña de Asignaciones ---
    frame_opciones_asignaciones = tk.Frame(frame_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_opciones_asignaciones.pack(fill="x", padx=5, pady=(5, 5))

    # Sub-frame para los checkboxes de la izquierda
    frame_opc_izq = tk.Frame(frame_opciones_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_opc_izq.pack(side="left", anchor="w")
    
    tk.Label(frame_opc_izq, text="Mostrar info de contacto:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold, fg="#424242").pack(side="left")
    opcionales = [("RUT", "rut"), ("Email", "email"), ("Teléfono", "telefono"), ("Dirección", "direccion")]
    widgets['vars_opcionales'] = {}
    for texto, col_id in opcionales:
        var = tk.BooleanVar(value=False)
        widgets['vars_opcionales'][col_id] = var
        tk.Checkbutton(frame_opc_izq, text=texto, variable=var, bg=config.COLOR_FONDO_PRINCIPAL, 
                    command=comandos_ui['cmd_toggle_columnas'], cursor="hand2").pack(side="left", padx=5)

    # Sub-frame para la búsqueda a la derecha
    frame_opc_der = tk.Frame(frame_opciones_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_opc_der.pack(side="right", anchor="e")

    tk.Label(frame_opc_der, text="Buscar:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left", padx=(10, 5))
    widgets['entry_busqueda_asignaciones'] = ttk.Entry(frame_opc_der, width=30)
    widgets['entry_busqueda_asignaciones'].pack(side="left", padx=(0, 5))
                    
    frame_tabla_cli = tk.Frame(frame_asignaciones, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_tabla_cli.pack(fill="both", expand=True, padx=5, pady=5)
    scroll_x_cli = ttk.Scrollbar(frame_tabla_cli, orient="horizontal")
    scroll_y_cli = ttk.Scrollbar(frame_tabla_cli, orient="vertical")
    
    columnas_cli = ("asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "extras", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario", "rut", "email", "telefono", "direccion")
    tabla_cli = ttk.Treeview(frame_tabla_cli, columns=columnas_cli, show="headings", selectmode="browse", xscrollcommand=scroll_x_cli.set, yscrollcommand=scroll_y_cli.set)
    tabla_cli['displaycolumns'] = ("asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "extras", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario")
    scroll_x_cli.config(command=tabla_cli.xview)
    scroll_y_cli.config(command=tabla_cli.yview)
    
    for col in columnas_cli:
        tabla_cli.heading(col, text=..., command=lambda c=col: comandos_ui['cmd_ordenar_asignaciones'](c, False))
        titulo_col = col.replace("_", " ").title()
        if col == "tipo_envio": titulo_col = "Tipo De Envio"
        if col == "envio_pag": titulo_col = "Envio Pagado"
        if col == "ano": titulo_col = "Año"   
        tabla_cli.heading(col, text=titulo_col)
        ancho = 60 if col in ["ano", "mes", "pagado", "envio_pag"] else 120
        if col == "comentario": ancho = 150
        tabla_cli.column(col, width=ancho, minwidth=60)
        
    scroll_y_cli.pack(side="right", fill="y")
    scroll_x_cli.pack(side="bottom", fill="x")
    tabla_cli.pack(side="left", fill="both", expand=True)
    widgets['tabla_clientes'] = tabla_cli

    # --- PESTAÑA 2: GESTIÓN DE CLIENTES ---
    frame_gestion_clientes = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(frame_gestion_clientes, text="Gestión de Clientes")

    frame_tabla_gestion = tk.LabelFrame(frame_gestion_clientes, text="Listado de Clientes", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold, padx=10, pady=10)
    frame_tabla_gestion.pack(side="left", fill="both", expand=True, padx=15, pady=15)
    
    frame_busqueda_clientes = tk.Frame(frame_tabla_gestion, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_busqueda_clientes.pack(fill="x", pady=(0, 10))
    tk.Label(frame_busqueda_clientes, text="Buscar Cliente:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(side="left")
    widgets['entry_busqueda_clientes'] = ttk.Entry(frame_busqueda_clientes, width=30)
    widgets['entry_busqueda_clientes'].pack(side="left", padx=10)

    tk.Button(frame_busqueda_clientes, text="Importar Historiales", command=comandos_ui['cmd_importar_historicos'], 
            bg="#C63E4E", fg="white", font=font_pequena, relief="flat", cursor="hand2").pack(side="right", padx=10)
    
    scroll_y_clientes_gestion = ttk.Scrollbar(frame_tabla_gestion, orient="vertical")
    scroll_x_clientes_gestion = ttk.Scrollbar(frame_tabla_gestion, orient="horizontal")
    
    # NUEVAS COLUMNAS RUT Y DIRECCION
    columnas_gestion = ("cliente_id", "nombre", "email", "telefono", "rut", "direccion", "status")
    tabla_gestion_clientes = ttk.Treeview(frame_tabla_gestion, columns=columnas_gestion, show="headings", selectmode="browse", yscrollcommand=scroll_y_clientes_gestion.set, xscrollcommand=scroll_x_clientes_gestion.set)
    scroll_y_clientes_gestion.config(command=tabla_gestion_clientes.yview)
    scroll_x_clientes_gestion.config(command=tabla_gestion_clientes.xview)
    
    for col in columnas_gestion:
        # ORDENAR COLUMNAS GESTION CLIENTES
        tabla_gestion_clientes.heading(col, text=col.replace("_", " ").title(), command=lambda c=col: comandos_ui['cmd_ordenar_gestion'](c, False))
        ancho = 120
        if col == "cliente_id": ancho = 60
        elif col == "status": ancho = 80
        elif col == "email": ancho = 180
        elif col == "direccion": ancho = 180
        tabla_gestion_clientes.column(col, width=ancho, minwidth=60)

    scroll_y_clientes_gestion.pack(side="right", fill="y")
    scroll_x_clientes_gestion.pack(side="bottom", fill="x")
    tabla_gestion_clientes.pack(side="left", fill="both", expand=True)
    widgets['tabla_gestion_clientes'] = tabla_gestion_clientes

    frame_form_cliente = tk.LabelFrame(frame_gestion_clientes, text=" Editar Información del Cliente ", bg="#FFFFFF", font=font_bold, padx=20, pady=20)
    frame_form_cliente.pack(side="right", fill="y", padx=(0, 15), pady=15)
    
    widgets['lbl_status_cliente'] = tk.Label(frame_form_cliente, text="Seleccione un cliente para editar", font=font_italic_status, fg="#0277BD", bg="#FFFFFF")
    widgets['lbl_status_cliente'].grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))
    
    widgets['form_cliente_entries'] = {}
    campos_cliente_form = [("nombre", "Nombre:", "entry"), ("email", "Email:", "entry"), ("telefono", "Teléfono:", "entry"), 
                        ("direccion", "Dirección:", "entry"), ("rut", "RUT:", "entry"), ("instagram", "Instagram:", "entry"), ("status", "Status:", "combo")]

    for i, (col_id, label_text, tipo) in enumerate(campos_cliente_form, start=1):
        tk.Label(frame_form_cliente, text=label_text, bg="#FFFFFF", font=font_pequena_bold).grid(row=i, column=0, sticky="e", pady=8, padx=(0, 10))
        if tipo == "combo":
            entry = ttk.Combobox(frame_form_cliente, width=30, font=("Helvetica", 10), state="readonly", values=['ACTIVA', 'INACTIVA'])
        else:
            entry = tk.Entry(frame_form_cliente, width=32, relief="solid", bd=1, font=("Helvetica", 10))
        entry.grid(row=i, column=1, sticky="w", pady=8, ipady=4)
        widgets['form_cliente_entries'][col_id] = entry

    frame_botones_cliente = tk.Frame(frame_form_cliente, bg="#FFFFFF")
    frame_botones_cliente.grid(row=len(campos_cliente_form)+1, column=0, columnspan=2, sticky="ew", pady=(30, 0))
    tk.Button(frame_botones_cliente, text="Guardar Cambios", command=comandos_ui['cmd_guardar_cliente'], bg=config.COLOR_ROSA_FUERTE, fg="white", font=font_bold, relief="flat", cursor="hand2", pady=8).pack(fill="x", pady=5)
    tk.Button(frame_botones_cliente, text="Limpiar", command=comandos_ui['cmd_limpiar_form_cliente'], bg="#FDEEF1", fg=config.COLOR_TEXTO, font=font_pequena_bold, relief="flat", cursor="hand2", pady=6).pack(fill="x", pady=5)
    tk.Button(frame_botones_cliente, text="📖 Ver Historial de Lectura", command=comandos_ui['cmd_ver_historial'], 
            bg="#9A8DFF", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=6).pack(fill="x", pady=5)
    tk.Button(frame_botones_cliente, text="Eliminar Cliente", command=comandos_ui['cmd_eliminar_cliente'], bg="#D45B63", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=6).pack(fill="x", pady=(25, 5))


    # --- PESTAÑA 3: INVENTARIO DE LIBROS ---
    frame_libros = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(frame_libros, text="Inventario de Libros")
    
    # Formulario derecho (Administrar Libro)
    frame_form_libros = tk.LabelFrame(frame_libros, text=" Administrar Libro ", bg="#FFFFFF", font=font_bold, padx=20, pady=20)
    frame_form_libros.pack(side="right", fill="y", padx=(0, 15), pady=15)
    
    widgets['lbl_status_libro'] = tk.Label(frame_form_libros, text="Modo: Creando nuevo libro", font=font_italic_status, fg="#C2185B", bg="#FFFFFF")
    widgets['lbl_status_libro'].grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))
    widgets['form_libro_entries'] = {}
    
    campos_form = [("titulo", "Título", "entry"), ("autor", "Autor", "combo"), ("genero", "Género", "combo"), 
                    ("editorial", "Editorial", "combo"), ("encuadernacion", "Encuadernación", "combo"),
                    ("stock", "Stock", "entry"), ("precio_original", "Precio Original", "entry")]

    
    vcmd_int = (ventana.register(comandos_ui['cmd_validar_int']), '%P')
    vcmd_float = (ventana.register(comandos_ui['cmd_validar_float']), '%P')
    
    for i, (col_id, label_text, tipo) in enumerate(campos_form, start=1):
        tk.Label(frame_form_libros, text=f"{label_text}:", bg="#FFFFFF", font=font_pequena_bold).grid(row=i, column=0, sticky="e", pady=4, padx=(0, 10))
        
        if tipo == "combo":
            entry = ttk.Combobox(frame_form_libros, width=27, font=("Helvetica", 10))
            # --- LÓGICA AÑADIDA ---
            if col_id == "encuadernacion":
                entry['values'] = ['TAPA BLANDA', 'TAPA DURA', 'BOLSILLO']
                entry['state'] = 'readonly'
        else: # tipo == "entry"
            validation_cmd = None
            if col_id == "stock": validation_cmd = vcmd_int
            elif col_id == "precio_original": validation_cmd = vcmd_float
            entry = tk.Entry(frame_form_libros, width=28, relief="solid", bd=1, font=("Helvetica", 10), validate="key", validatecommand=validation_cmd)
        
        entry.grid(row=i, column=1, sticky="w", pady=4, ipady=2 if tipo == "entry" else 0)
        widgets['form_libro_entries'][col_id] = entry

        
        frame_botones = tk.Frame(frame_form_libros, bg="#FFFFFF")
        
    frame_botones.grid(row=len(campos_form)+1, column=0, columnspan=2, sticky="ew", pady=(15, 0))
    
    tk.Button(frame_botones, text="Guardar / Modificar", command=comandos_ui['cmd_guardar_libro'], bg=config.COLOR_ROSA_FUERTE, fg="white", font=font_bold, relief="flat", cursor="hand2", pady=4).pack(fill="x", pady=3)
    tk.Button(frame_botones, text="Limpiar Formulario", command=comandos_ui['cmd_limpiar_form_libro'], bg="#FDEEF1", fg=config.COLOR_TEXTO, font=font_pequena_bold, relief="flat", cursor="hand2", pady=4).pack(fill="x", pady=3)
    
    # --- SUB-FRAME PARA PONER LOS BOTONES DE DESCUENTO EN UNA SOLA FILA ---
    frame_descuentos = tk.Frame(frame_botones, bg="#FFFFFF")
    frame_descuentos.pack(fill="x", pady=(15, 3))
    
    tk.Button(frame_descuentos, text="Aplicar Descuento", command=comandos_ui['cmd_aplicar_descuento'], bg=config.COLOR_BOTON_CATALOGO, fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=4).pack(side="left", fill="x", expand=True, padx=(0, 2))
    tk.Button(frame_descuentos, text="Quitar Descuento", command=comandos_ui['cmd_quitar_descuentos'], bg="#757575", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=4).pack(side="right", fill="x", expand=True, padx=(2, 0))

    tk.Button(frame_botones, text="Eliminar Seleccionado", command=comandos_ui['cmd_eliminar_libro'], bg="#D45B63", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=4).pack(fill="x", pady=(10, 2))


    # --- Frame Izquierdo (Filtros y Tabla Inventario) ---
    frame_izquierdo = tk.Frame(frame_libros, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_izquierdo.pack(side="left", fill="both", expand=True, padx=15, pady=15)
    
    frame_busqueda_filtros = tk.LabelFrame(frame_izquierdo, text="Filtros de Inventario", bg=config.COLOR_FONDO_PRINCIPAL, font=("Helvetica", 9, "bold"), padx=10, pady=10)
    frame_busqueda_filtros.pack(fill="x", pady=(0, 10))

    # Fila 0: Búsqueda de texto y botones
    tk.Label(frame_busqueda_filtros, text="Buscar Título:", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).grid(row=0, column=0, padx=(0,5), sticky="w")
    widgets['entry_busqueda_libros'] = ttk.Entry(frame_busqueda_filtros, width=25)
    widgets['entry_busqueda_libros'].grid(row=0, column=1, padx=5, sticky="ew")
    tk.Button(frame_busqueda_filtros, text="Buscar", command=comandos_ui['cmd_aplicar_filtros'], bg="#1A73E8", fg="white", relief="flat", cursor="hand2", padx=10).grid(row=0, column=2, padx=5)
    tk.Button(frame_busqueda_filtros, text="Quitar Filtros", command=comandos_ui['cmd_limpiar_filtros'], bg="gray", fg="white", relief="flat", cursor="hand2", padx=10).grid(row=0, column=3, padx=5)

    # Fila 1: Filtros Combo
        # Fila 1: Filtros Múltiples (Listbox)
    frame_listas = tk.Frame(frame_busqueda_filtros, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_listas.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10,0))
    
    # Función auxiliar para crear las listas limpiamente
    def crear_lista_filtro(parent, texto):
        frame = tk.Frame(parent, bg=config.COLOR_FONDO_PRINCIPAL)
        tk.Label(frame, text=texto, bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold).pack(anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical")
        # selectmode="multiple" permite clics independientes. exportselection=False evita que se deseleccione al clicar otra lista.
        lista = tk.Listbox(frame, selectmode="multiple", exportselection=False, height=4, yscrollcommand=scroll.set, font=("Helvetica", 9))
        scroll.config(command=lista.yview)
        lista.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return frame, lista

    frame_autor, widgets['list_filtro_autor'] = crear_lista_filtro(frame_listas, "Autor(es):")
    frame_autor.pack(side="left", padx=(0, 5), fill="both", expand=True)
    
    frame_genero, widgets['list_filtro_genero'] = crear_lista_filtro(frame_listas, "Género(s):")
    frame_genero.pack(side="left", padx=5, fill="both", expand=True)
    
    frame_editorial, widgets['list_filtro_editorial'] = crear_lista_filtro(frame_listas, "Editorial(es):")
    frame_editorial.pack(side="left", padx=(5, 0), fill="both", expand=True)


    # Fila 2: Sliders de Stock (Min y Max)
    frame_sliders = tk.Frame(frame_busqueda_filtros, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_sliders.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10,0))
    widgets['lbl_filtro_stock_min'] = tk.Label(frame_sliders, text="Stock Min: 0", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold, width=12, anchor="w")
    widgets['lbl_filtro_stock_min'].pack(side="left")
    widgets['slider_stock_min'] = ttk.Scale(frame_sliders, from_=0, to=100, orient="horizontal")
    widgets['slider_stock_min'].pack(side="left", expand=True, fill="x", padx=(0,15))
    widgets['lbl_filtro_stock_max'] = tk.Label(frame_sliders, text="Stock Max: 0", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold, width=12, anchor="w")
    widgets['lbl_filtro_stock_max'].pack(side="left")
    widgets['slider_stock_max'] = ttk.Scale(frame_sliders, from_=0, to=100, orient="horizontal")
    widgets['slider_stock_max'].pack(side="left", expand=True, fill="x")

    frame_busqueda_filtros.grid_columnconfigure(1, weight=1)

    frame_tabla_libros = tk.Frame(frame_izquierdo, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_tabla_libros.pack(fill="both", expand=True)
    scroll_x_lib = ttk.Scrollbar(frame_tabla_libros, orient="horizontal")
    scroll_y_lib = ttk.Scrollbar(frame_tabla_libros, orient="vertical")
    
    columnas_lib = ("libro_id", "titulo", "autor", "genero", "editorial", "encuadernacion", "stock", "precio", "precio_original")
    tabla_lib = ttk.Treeview(frame_tabla_libros, columns=columnas_lib, show="headings", selectmode="browse", xscrollcommand=scroll_x_lib.set, yscrollcommand=scroll_y_lib.set)
    scroll_x_lib.config(command=tabla_lib.xview)
    scroll_y_lib.config(command=tabla_lib.yview)
    
    for col in columnas_lib:
        titulo_col = col.replace("_", " ").title()
        tabla_lib.heading(col, text=titulo_col, command=lambda c=col: comandos_ui['cmd_ordenar_libros'](c, False))
        ancho = 120
        if col in ["stock", "precio", "precio_original"]: ancho = 80
        elif col == "libro_id": ancho = 60
        tabla_lib.column(col, width=ancho, minwidth=60, stretch=(col == "titulo"))
        
    scroll_y_lib.pack(side="right", fill="y")
    scroll_x_lib.pack(side="bottom", fill="x")
    tabla_lib.pack(side="left", fill="both", expand=True)
    widgets['tabla_libros'] = tabla_lib
    
    widgets['lbl_stock_total'] = tk.Label(frame_izquierdo, text="Unidades Totales en Inventario: 0", font=font_bold, bg=config.COLOR_ROSA_BOTON_SEC, fg=config.COLOR_TEXTO, pady=10)
    widgets['lbl_stock_total'].pack(fill="x", pady=(10, 0))
    
        # --- PESTAÑA 4: REGISTRO DE VENTAS (PUNTO DE VENTA) ---
    tab_ventas = tk.Frame(notebook, bg=config.COLOR_FONDO_PRINCIPAL)
    notebook.add(tab_ventas, text="Caja / Ventas")

    # --- Columna Izquierda: Formulario de Nueva Venta (DISEÑO COMPACTO) ---
    frame_form_ventas = tk.Frame(tab_ventas, bg="white", width=400, relief="groove", borderwidth=1)
    frame_form_ventas.pack(side="left", fill="y", padx=10, pady=10)
    frame_form_ventas.pack_propagate(False)
    
    tk.Label(frame_form_ventas, text="Registrar Nueva Venta", font=("Helvetica", 14, "bold"), bg="white", fg="#4A148C").pack(pady=(10, 5))

    # =========================================================================
    # PANEL INFERIOR FIJO (Totales y Botón Guardar)
    # =========================================================================
    frame_bottom_v = tk.Frame(frame_form_ventas, bg="white")
    frame_bottom_v.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

    frame_totales = tk.Frame(frame_bottom_v, bg="#F1F8E9", relief="sunken", borderwidth=1)
    frame_totales.pack(fill="x", pady=(5, 10), ipady=5)
    tk.Label(frame_totales, text="Subtotal Libros:", font=font_pequena_bold, bg="#F1F8E9").grid(row=0, column=0, sticky="e", padx=5)
    widgets['lbl_v_subtotal'] = tk.Label(frame_totales, text="$ 0", font=font_pequena, bg="#F1F8E9")
    widgets['lbl_v_subtotal'].grid(row=0, column=1, sticky="w")
    tk.Label(frame_totales, text="Costo Envío:", font=font_pequena_bold, bg="#F1F8E9").grid(row=1, column=0, sticky="e", padx=5)
    widgets['lbl_v_costo_envio'] = tk.Label(frame_totales, text="$ 0", font=font_pequena, bg="#F1F8E9")
    widgets['lbl_v_costo_envio'].grid(row=1, column=1, sticky="w")
    tk.Label(frame_totales, text="TOTAL VENTA:", font=("Helvetica", 11, "bold"), bg="#F1F8E9").grid(row=2, column=0, sticky="e", padx=5, pady=(5,0))
    widgets['lbl_v_total_final'] = tk.Label(frame_totales, text="$ 0", font=("Helvetica", 11, "bold"), bg="#F1F8E9")
    widgets['lbl_v_total_final'].grid(row=2, column=1, sticky="w", pady=(5,0))
    frame_totales.grid_columnconfigure(1, weight=1)

    tk.Button(frame_bottom_v, text="💾 GUARDAR VENTA Y ACTUALIZAR STOCK", command=comandos_ui.get('cmd_v_guardar'), bg="#81BFB7", fg="white", font=font_pequena_bold, relief="flat", cursor="hand2", pady=8).pack(fill="x", pady=(0, 5))
    tk.Button(frame_bottom_v, text="Limpiar Formulario", command=comandos_ui.get('cmd_v_limpiar'), bg="#FDEEF1", fg="#212121", font=font_pequena, relief="flat", cursor="hand2").pack(fill="x", ipady=4)

    # =========================================================================
    # PANEL SUPERIOR (Campos Compactos, sin Canvas para evitar ocultamientos)
    # =========================================================================
    frame_inner_v = tk.Frame(frame_form_ventas, bg="white")
    frame_inner_v.pack(side="top", fill="both", expand=True, padx=15)

    from tkcalendar import DateEntry
    vcmd_float = (ventana.register(comandos_ui.get('cmd_validar_float', lambda: True)), '%P')

    # Fila 1: Fecha
    tk.Label(frame_inner_v, text="Fecha de Venta:", bg="white", font=font_pequena_bold).pack(anchor="w", pady=(2, 0))
    widgets['de_v_fecha'] = DateEntry(frame_inner_v, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
    widgets['de_v_fecha'].pack(anchor="w")

    # Fila 2: Cliente
    tk.Label(frame_inner_v, text="Cliente (Autocompletar o crear nuevo):", bg="white", font=font_pequena_bold).pack(anchor="w", pady=(5, 0))
    widgets['cmb_v_cliente'] = ttk.Combobox(frame_inner_v, font=font_pequena)
    widgets['cmb_v_cliente'].pack(fill="x", ipady=2)

    # Fila 3: Libro y Precio Especial (LADO A LADO para ahorrar espacio)
    frame_lp = tk.Frame(frame_inner_v, bg="white")
    frame_lp.pack(fill="x", pady=(8, 0))
    
    frame_l = tk.Frame(frame_lp, bg="white")
    frame_l.pack(side="left", fill="x", expand=True, padx=(0, 3))
    tk.Label(frame_l, text="Libro Vendido:", bg="white", font=font_pequena_bold).pack(anchor="w")
    widgets['cmb_v_libros'] = ttk.Combobox(frame_l, font=font_pequena)
    widgets['cmb_v_libros'].pack(fill="x", ipady=2)

    frame_p = tk.Frame(frame_lp, bg="white")
    frame_p.pack(side="right", fill="x", expand=True, padx=(3, 0))
    tk.Label(frame_p, text="Precio Espec. ($):", bg="white", font=font_pequena_bold).pack(anchor="w")
    widgets['entry_v_precio_custom'] = tk.Entry(frame_p, font=font_pequena, relief="flat", highlightbackground="#FDEEF1", highlightthickness=1, validate="key", validatecommand=vcmd_float)
    widgets['entry_v_precio_custom'].pack(fill="x", ipady=2)

    # Fila 4: Botones de Carrito
    frame_btn_libros = tk.Frame(frame_inner_v, bg="white")
    frame_btn_libros.pack(fill="x", pady=5)
    tk.Button(frame_btn_libros, text="➕ Añadir", command=comandos_ui.get('cmd_v_add_libro'), bg="#0288D1", fg="white", relief="flat", cursor="hand2").pack(side="left", expand=True, fill="x", padx=(0, 2))
    tk.Button(frame_btn_libros, text="❌ Quitar", command=comandos_ui.get('cmd_v_remove_libro'), bg="#D32F2F", fg="white", relief="flat", cursor="hand2").pack(side="right", expand=True, fill="x", padx=(2, 0))

    # Carrito
    widgets['list_v_libros'] = tk.Listbox(frame_inner_v, height=3, font=font_pequena, selectbackground="#81BFB7")
    widgets['list_v_libros'].pack(fill="x")

    # Fila 5: Envío y Costo (LADO A LADO para ahorrar espacio)
    frame_ec = tk.Frame(frame_inner_v, bg="white")
    frame_ec.pack(fill="x", pady=(5, 0))

    frame_e = tk.Frame(frame_ec, bg="white")
    frame_e.pack(side="left", fill="x", expand=True, padx=(0, 3))
    tk.Label(frame_e, text="Método Envío:", bg="white", font=font_pequena_bold).pack(anchor="w")
    widgets['cmb_v_envio'] = ttk.Combobox(frame_e, values=["RETIRO", "PAKET", "BLUEXPRESS", "STARKEN", "SIN INFORMACION"], state="readonly", font=font_pequena)
    widgets['cmb_v_envio'].pack(fill="x", ipady=2)
    widgets['cmb_v_envio'].set("SIN INFORMACION")

    frame_c = tk.Frame(frame_ec, bg="white")
    frame_c.pack(side="right", fill="x", expand=True, padx=(3, 0))
    tk.Label(frame_c, text="Costo Envío ($):", bg="white", font=font_pequena_bold).pack(anchor="w")
    widgets['entry_v_costo_envio'] = tk.Entry(frame_c, font=font_pequena, relief="flat", highlightbackground="#FDEEF1", highlightthickness=1, validate="key", validatecommand=vcmd_float)
    widgets['entry_v_costo_envio'].pack(fill="x", ipady=2)

    # Fila 6: Comentario (¡Libre para escribir texto!)
    tk.Label(frame_inner_v, text="Comentario:", bg="white", font=font_pequena_bold).pack(anchor="w", pady=(5, 0))
    widgets['entry_v_comentario'] = tk.Entry(frame_inner_v, font=font_pequena, relief="flat", highlightbackground="#FDEEF1", highlightthickness=1)
    widgets['entry_v_comentario'].pack(fill="x", ipady=3)
        
    # --- Columna Derecha: Historial de Ventas con Filtros ---
    frame_derecha_v = tk.Frame(tab_ventas, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_derecha_v.pack(side="left", fill="both", expand=True, padx=10, pady=10)
    # -- Panel de Filtros ---
    frame_filtros_v = tk.LabelFrame(frame_derecha_v, text="Filtrar Historial", bg=config.COLOR_FONDO_PRINCIPAL, font=font_pequena_bold, padx=10, pady=10)
    frame_filtros_v.pack(side="top", fill="x", pady=(0, 10))

    tk.Label(frame_filtros_v, text="Cliente:", bg=config.COLOR_FONDO_PRINCIPAL).grid(row=0, column=0)
    widgets['cmb_filtro_v_cliente'] = ttk.Combobox(frame_filtros_v, width=20)
    widgets['cmb_filtro_v_cliente'].grid(row=0, column=1, padx=5)

    tk.Label(frame_filtros_v, text="Desde:", bg=config.COLOR_FONDO_PRINCIPAL).grid(row=0, column=2, padx=(10, 0))
    widgets['de_filtro_v_desde'] = DateEntry(frame_filtros_v, width=10, date_pattern='yyyy-mm-dd')
    widgets['de_filtro_v_desde'].grid(row=0, column=3, padx=5)
    
    tk.Label(frame_filtros_v, text="Hasta:", bg=config.COLOR_FONDO_PRINCIPAL).grid(row=0, column=4)
    widgets['de_filtro_v_hasta'] = DateEntry(frame_filtros_v, width=10, date_pattern='yyyy-mm-dd')
    widgets['de_filtro_v_hasta'].grid(row=0, column=5, padx=5)

    frame_btn_filtros_v = tk.Frame(frame_filtros_v, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_btn_filtros_v.grid(row=0, column=6, padx=(10,0))
    tk.Button(frame_btn_filtros_v, text="Filtrar", command=comandos_ui.get('cmd_v_filtrar'), bg="#426567", fg="white", relief="flat").pack(side="left", padx=2)
    tk.Button(frame_btn_filtros_v, text="Limpiar", command=comandos_ui.get('cmd_v_limpiar_filtros'), bg="#757575", fg="white", relief="flat").pack(side="left", padx=2)

    frame_tabla_ventas = tk.Frame(frame_derecha_v, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_tabla_ventas.pack(side="top", fill="both", expand=True)
    
    columnas_ventas = ("id", "fecha", "cliente", "libros", "total", "envio", "comentario")
    widgets['tabla_ventas'] = ttk.Treeview(frame_tabla_ventas, columns=columnas_ventas, show="headings")
    
    frame_acciones_ventas = tk.Frame(frame_derecha_v, bg=config.COLOR_FONDO_PRINCIPAL)
    frame_acciones_ventas.pack(side="bottom", fill="x", pady=(10, 0))
    tk.Button(frame_acciones_ventas, text="🗑️ Eliminar Venta Seleccionada", 
            command=comandos_ui.get('cmd_v_eliminar_venta'), 
            bg="#D45B63", fg="white", font=font_pequena_bold, 
            relief="flat", cursor="hand2", padx=10, pady=4).pack(side="right")
    
    widgets['tabla_ventas'].heading("id", text="ID")
    widgets['tabla_ventas'].heading("fecha", text="Fecha")
    widgets['tabla_ventas'].heading("cliente", text="Cliente")
    widgets['tabla_ventas'].heading("libros", text="Libros Vendidos")
    widgets['tabla_ventas'].heading("total", text="Total ($)")
    widgets['tabla_ventas'].heading("envio", text="Envío")
    widgets['tabla_ventas'].heading("comentario", text="Comentario")

    widgets['tabla_ventas'].column("id", width=40, anchor="center")
    widgets['tabla_ventas'].column("fecha", width=90, anchor="center")
    widgets['tabla_ventas'].column("cliente", width=150)
    widgets['tabla_ventas'].column("libros", width=250)
    widgets['tabla_ventas'].column("total", width=80, anchor="e")
    widgets['tabla_ventas'].column("envio", width=100, anchor="center")
    widgets['tabla_ventas'].column("comentario", width=150)

    scroll_v = ttk.Scrollbar(frame_tabla_ventas, orient="vertical", command=widgets['tabla_ventas'].yview)
    widgets['tabla_ventas'].configure(yscrollcommand=scroll_v.set)
    scroll_v.pack(side="right", fill="y")
    widgets['tabla_ventas'].pack(side="left", fill="both", expand=True)

