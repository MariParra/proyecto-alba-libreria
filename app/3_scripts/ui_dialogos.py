import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import datetime
import conexion

def abrir_dialogo_comentario(root, tabla, callback_refrescar):
    """Abre un diálogo para editar el campo de texto 'comentario'."""
    selected_iid = tabla.focus()
    if not selected_iid: return

    asignacion_id = tabla.set(selected_iid, "asignacion_id")
    valor_actual = tabla.set(selected_iid, "comentario")

    # Usamos un Toplevel personalizado para más control que simpledialog
    win = tk.Toplevel(root)
    win.title("Editar Comentario")
    win.geometry("400x300")
    win.transient(root)
    win.grab_set()
    win.configure(bg="#FCE4EC")

    tk.Label(win, text="Comentario:", bg="#FCE4EC", font=("Helvetica", 10, "bold")).pack(pady=(10, 5))
    
    text_frame = tk.Frame(win, bd=1, relief="sunken")
    text_frame.pack(padx=10, pady=5, fill="both", expand=True)
    
    text_widget = tk.Text(text_frame, wrap="word", height=10, width=40, font=("Helvetica", 10))
    text_widget.pack(fill="both", expand=True)
    text_widget.insert("1.0", valor_actual if valor_actual and valor_actual != 'SIN COMENTARIOS' else "")

    def guardar_comentario():
        nuevo_valor = text_widget.get("1.0", tk.END).strip()
        if not nuevo_valor:
            nuevo_valor = "SIN COMENTARIOS"

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE asignaciones SET comentario = ? WHERE asignacion_id = ?", (nuevo_valor, asignacion_id))
            conn.commit()
            conn.close()
            win.destroy()
            callback_refrescar()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo actualizar el comentario: {e}", parent=win)

    tk.Button(win, text="Guardar", command=guardar_comentario, bg="#81BFB7", fg="white", font=("Helvetica", 10, "bold")).pack(pady=10)


def manejar_edicion_celda(event, root, widgets, callback_refrescar):
    tabla = widgets['tabla_clientes']
    region = tabla.identify_region(event.x, event.y)
    if region != "cell": return

    col_display_id = tabla.identify_column(event.x)
    selected_col_name = tabla.column(col_display_id, 'id')
    selected_iid = tabla.focus()
    if not selected_iid: return

    asignacion_id = tabla.set(selected_iid, "asignacion_id")
    
    # --- LÓGICA DE DERIVACIÓN ---
    if selected_col_name == "fecha_asig":
        abrir_dialogo_fecha(root, tabla, callback_refrescar)
        return
    elif selected_col_name == "libro":
        abrir_dialogo_asignar_libro(root, tabla, callback_refrescar, lambda: refrescar_inventario_global(widgets))
        return
    # AÑADIDO: Manejo para la columna de comentario
    elif selected_col_name == "comentario":
        abrir_dialogo_comentario(root, tabla, callback_refrescar)
        return

    opciones_combo = None
    campo_bd = None
    
    estados = ["EN PREPARACION", "POR ENVIAR", "ENVIADO", "POR RETIRAR", "RETIRADO"]
    if selected_col_name == "estado":
        opciones_combo = estados
        campo_bd = "estado_envio"
    elif selected_col_name == "pagado":
        opciones_combo = ["Si", "No"]
        campo_bd = "pagado"
    elif selected_col_name == "envio_pag":
        opciones_combo = ["Si", "No"]
        campo_bd = "envio_pagado"
    elif selected_col_name == "tipo_envio":
        opciones_combo = ["BLUEXPRESS", "PAKET", "RETIRO", "STARKEN"]
        campo_bd = "metodo_entrega"

    if opciones_combo:
        x, y, w, h = tabla.bbox(selected_iid, col_display_id)
        valor_actual = tabla.set(selected_iid, selected_col_name)
        cb = ttk.Combobox(tabla, values=opciones_combo, state="readonly")
        cb.place(x=x, y=y, width=w, height=h)
        cb.set(valor_actual if valor_actual else opciones_combo[0])
        cb.focus()

        def guardar_cambio_combo(event=None):
            nuevo_valor = cb.get()
            valor_guardar = "TRUE" if nuevo_valor == "Si" else ("FALSE" if nuevo_valor == "No" else nuevo_valor)
            try:
                conn = conexion.conectar_db()
                cursor = conn.cursor()
                if campo_bd == "metodo_entrega":
                    cliente_id = tabla.set(selected_iid, "cliente_id")
                    cursor.execute("UPDATE suscripciones SET metodo_entrega = ? WHERE cliente_id = ?", (valor_guardar, cliente_id))
                else:
                    cursor.execute(f"UPDATE asignaciones SET {campo_bd} = ? WHERE asignacion_id = ?", (valor_guardar, asignacion_id))
                conn.commit()
                conn.close()
                cb.destroy()
                callback_refrescar()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar: {e}")
                cb.destroy()

        cb.bind("<FocusOut>", lambda e: cb.destroy())
        cb.bind("<Return>", guardar_cambio_combo)
        cb.bind("<<ComboboxSelected>>", guardar_cambio_combo)


def abrir_dialogo_asignar_libro(root, tabla, item_id, callback_asignaciones, callback_inventario):
    asignacion_id = tabla.set(item_id, "asignacion_id")
    cliente_nombre = tabla.set(item_id, "nombre")
    
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
        res = cursor.fetchone()
        current_libro_id = res[0] if res else None
        
        cursor.execute("SELECT s.generos_preferencia FROM asignaciones a JOIN suscripciones s ON a.cliente_id = s.cliente_id WHERE a.asignacion_id = ?", (asignacion_id,))
        res_gen = cursor.fetchone()
        generos_str = res_gen[0] if res_gen and res_gen[0] else ""
        generos_preferidos = [g.strip().upper() for g in generos_str.split(',') if g.strip()]
        
        cursor.execute("SELECT libro_id, titulo, stock, genero FROM libros ORDER BY titulo")
        todos_los_libros = cursor.fetchall()
        
        conn.close()
    except Exception as e:
        messagebox.showerror("Error", f"Error al acceder a BD: {e}")
        return
        
    libros_recomendados_stock = []
    libros_recomendados_catalogo = []
    libros_todos_stock = []
    libros_todos_catalogo = []
    
    for l_id, t, s, gen in todos_los_libros:
        texto_opcion = f"{t} (Stock: {s})"
        es_recomendado = any(pref in str(gen).strip().upper() or str(gen).strip().upper() in pref for pref in generos_preferidos)

        if es_recomendado:
            if s > 0: libros_recomendados_stock.append((texto_opcion, l_id))
            else: libros_recomendados_catalogo.append((texto_opcion, l_id))
        
        if s > 0: libros_todos_stock.append((texto_opcion, l_id))
        else: libros_todos_catalogo.append((texto_opcion, l_id))

    mapa_libros = {txt: l_id for txt, l_id in (libros_todos_stock + libros_todos_catalogo)}
    valor_actual_str = next((txt for txt, l_id in mapa_libros.items() if l_id == current_libro_id), "(Sin Asignar)")

    win = tk.Toplevel(root)
    win.title("Asignar / Quitar Libro")
    win.geometry("550x350")
    win.transient(root); win.grab_set(); win.configure(bg="#F7DAE7")
    
    tk.Label(win, text=f"Modificando asignación de:\n{cliente_nombre}", bg="#F7DAE7", font=("Helvetica", 11, "bold")).pack(pady=(10, 0))
    gustos_display = generos_str if generos_str and generos_str != "SIN INFORMACION" else "No especificados"
    tk.Label(win, text=f"Gustos de la clienta: {gustos_display}", bg="#F7DAE7", font=("Helvetica", 9, "italic"), fg="#555").pack(pady=(2, 5))
    
    lbl_alerta = tk.Label(win, text="¡Ojo! No hay libros en stock para sus gustos.", bg="#F7DAE7", font=("Helvetica", 9, "bold"), fg="red")
    if not libros_recomendados_stock and generos_preferidos:
        lbl_alerta.pack()

    # --- FRAME PARA LOS CHECKBOXES DE CONTROL ---
    frame_checks = tk.Frame(win, bg="#F7DAE7")
    frame_checks.pack(pady=5)
    
    usar_filtro_var = tk.BooleanVar(value=True if (libros_recomendados_stock or libros_recomendados_catalogo) else False)
    incluir_sin_stock_var = tk.BooleanVar(value=False) # Por defecto, no mostramos los de catálogo
    cb_libros = ttk.Combobox(win, state="readonly", width=70, font=("Helvetica", 10))
    
    def actualizar_opciones_combobox(*args):
        opciones_mostrar = ["(Sin Asignar)"]
        
        if usar_filtro_var.get(): # --- MODO FILTRADO POR GÉNERO ---
            if libros_recomendados_stock:
                opciones_mostrar.append("--- RECOMENDADOS EN STOCK ---")
                opciones_mostrar.extend([txt for txt, l_id in libros_recomendados_stock])
            if incluir_sin_stock_var.get() and libros_recomendados_catalogo:
                opciones_mostrar.append("--- RECOMENDADOS (CATÁLOGO / SIN STOCK) ---")
                opciones_mostrar.extend([txt for txt, l_id in libros_recomendados_catalogo])
        else: # --- MODO VER TODO EL INVENTARIO ---
            if libros_todos_stock:
                opciones_mostrar.append("--- TODO EL CATÁLOGO EN STOCK ---")
                opciones_mostrar.extend([txt for txt, l_id in libros_todos_stock])
            if incluir_sin_stock_var.get() and libros_todos_catalogo:
                opciones_mostrar.append("--- TODO EL CATÁLOGO (SIN STOCK) ---")
                opciones_mostrar.extend([txt for txt, l_id in libros_todos_catalogo])

        cb_libros.config(values=opciones_mostrar)
        if valor_actual_str in opciones_mostrar: cb_libros.set(valor_actual_str)
        else: cb_libros.set(opciones_mostrar[0])

    chk_filtro_genero = tk.Checkbutton(frame_checks, text="Filtrar por Géneros", variable=usar_filtro_var, bg="#F7DAE7", command=actualizar_opciones_combobox, cursor="hand2")
    if not (libros_recomendados_stock or libros_recomendados_catalogo):
        chk_filtro_genero.config(state="disabled")
    chk_filtro_genero.pack(side="left", padx=10)

    chk_sin_stock = tk.Checkbutton(frame_checks, text="Incluir sin stock (Catálogo)", variable=incluir_sin_stock_var, bg="#F7DAE7", command=actualizar_opciones_combobox, cursor="hand2")
    chk_sin_stock.pack(side="left", padx=10)
    
    cb_libros.pack(pady=5, padx=15)
    actualizar_opciones_combobox()
    
    frame_botones = tk.Frame(win, bg="#F7DAE7")
    frame_botones.pack(pady=15, fill="x", expand=True)
    def guardar_y_cerrar():
        seleccion_str = cb_libros.get()
        nuevo_libro_id = mapa_libros.get(seleccion_str, None)
        
        if nuevo_libro_id == current_libro_id:
            win.destroy()
            return
            
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            if current_libro_id:
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (current_libro_id,))
            if nuevo_libro_id:
                cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = ?", (nuevo_libro_id,))
                
            cursor.execute("UPDATE asignaciones SET libro_suscripcion_id = ? WHERE asignacion_id = ?", (nuevo_libro_id, asignacion_id))
            
            conn.commit()
            conn.close()
            win.destroy()
            callback_asignaciones()
            callback_inventario()
        except Exception as e:
            messagebox.showerror("Error BD", f"No se pudo guardar la asignación: {e}", parent=win)

    def quitar_y_cerrar():
        if not current_libro_id:
            messagebox.showinfo("Información", "Esta clienta ya se encuentra 'Sin Asignar'.", parent=win)
            return
            
        if messagebox.askyesno("Confirmar", f"¿Quitar el libro a {cliente_nombre}?\n\nEl libro volverá al stock.", parent=win):
            try:
                conn = conexion.conectar_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (current_libro_id,))
                cursor.execute("UPDATE asignaciones SET libro_suscripcion_id = NULL WHERE asignacion_id = ?", (asignacion_id,))
                conn.commit()
                conn.close()
                win.destroy()
                callback_asignaciones()
                callback_inventario()
                messagebox.showinfo("Éxito", "Libro desasignado y devuelto al inventario.", parent=root)
            except Exception as e:
                messagebox.showerror("Error BD", f"No se pudo quitar la asignación: {e}", parent=win)

    tk.Button(frame_botones, text="Guardar Cambios", command=guardar_y_cerrar, bg="#81BFB7", fg="white", font=("Helvetica", 10, "bold"), pady=6, width=15).pack(side="left", padx=(30, 10))
    tk.Button(frame_botones, text="Quitar Asignación", command=quitar_y_cerrar, bg="#D32F2F", fg="white", font=("Helvetica", 10, "bold"), pady=6, width=15).pack(side="right", padx=(10, 30))


def abrir_dialogo_fecha(root, tabla, callback_refrescar):
    selected_iid = tabla.focus()
    if not selected_iid: return
    
    asignacion_id = tabla.set(selected_iid, "asignacion_id")
    valor_actual = tabla.set(selected_iid, "fecha_asig")
    win = tk.Toplevel(root)
    win.title("Editar Fecha")
    win.geometry("350x150")
    win.transient(root)
    win.grab_set()
    win.configure(bg="#FCE4EC")
    tk.Label(win, text="Editar fecha (YYYY-MM-DD HH:MM:SS)", bg="#FCE4EC", font=("Helvetica", 10, "bold")).pack(pady=(10, 2))
    entry_fecha = tk.Entry(win, width=30, font=("Helvetica", 10))
    entry_fecha.pack(pady=5, padx=20)
    entry_fecha.insert(0, valor_actual if valor_actual else "")
    
    def guardar_fecha():
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE asignaciones SET fecha_asignacion = ? WHERE asignacion_id = ?", (entry_fecha.get().strip(), asignacion_id))
            conn.commit()
            conn.close()
            win.destroy()
            callback_refrescar()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=win)
            
    def usar_timestamp_actual():
        entry_fecha.delete(0, tk.END)
        entry_fecha.insert(0, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        guardar_fecha()
        
    frame_botones = tk.Frame(win, bg="#FCE4EC")
    frame_botones.pack(pady=10)
    tk.Button(frame_botones, text="Guardar", command=guardar_fecha).pack(side="left", padx=10)
    tk.Button(frame_botones, text="Usar Fecha Actual", command=usar_timestamp_actual).pack(side="left", padx=10)
    
def refrescar_inventario_global(widgets):
    pass

def abrir_dialogo_ver_historial(root, tabla_gestion_clientes):
    seleccion = tabla_gestion_clientes.selection()
    if not seleccion:
        messagebox.showwarning("Sin Selección", "Por favor, seleccione una clienta de la lista primero.")
        return
        
    cliente_id = tabla_gestion_clientes.set(seleccion[0], "cliente_id")
    nombre_cliente = tabla_gestion_clientes.set(seleccion[0], "nombre")
    
    win = tk.Toplevel(root)
    win.title(f"Librero Histórico - {nombre_cliente}")
    # --- VENTANA MÁS ANCHA PARA QUE QUEPA EL AUTOR ---
    win.geometry("700x450") 
    win.transient(root)
    win.grab_set()
    win.configure(bg="#F3E5F5") 
    
    tk.Label(win, text=f"Biblioteca Personal de:\n{nombre_cliente}", bg="#F3E5F5", font=("Helvetica", 12, "bold")).pack(pady=(15, 10))
    
    frame_filtros = tk.Frame(win, bg="#F3E5F5")
    frame_filtros.pack(fill="x", padx=20, pady=(0, 10))
    
    tk.Label(frame_filtros, text="Filtrar por origen:", bg="#F3E5F5", font=("Helvetica", 9, "bold")).pack(side="left")
    cmb_filtro_origen = ttk.Combobox(frame_filtros, state="readonly", values=["Todos", "Importados (Librero Antiguo)", "Asignados (App)"], width=25)
    cmb_filtro_origen.set("Todos")
    cmb_filtro_origen.pack(side="left", padx=10)
    
    frame_tabla = tk.Frame(win)
    frame_tabla.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    
    scroll_y = ttk.Scrollbar(frame_tabla, orient="vertical")
    # --- SE AÑADE LA COLUMNA "autor" ---
    tabla_hist = ttk.Treeview(frame_tabla, columns=("titulo", "autor", "origen", "fecha"), show="headings", yscrollcommand=scroll_y.set)
    scroll_y.config(command=tabla_hist.yview)
    
    def ordenar_columna_historial(tv, col, reverse):
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        try: l.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError: l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)
        tv.heading(col, command=lambda _col=col: ordenar_columna_historial(tv, _col, not reverse))

    tabla_hist.heading("titulo", text="Título del Libro", command=lambda: ordenar_columna_historial(tabla_hist, "titulo", False))
    # --- ENCABEZADO Y ORDENAMIENTO PARA EL AUTOR ---
    tabla_hist.heading("autor", text="Autor", command=lambda: ordenar_columna_historial(tabla_hist, "autor", False))
    tabla_hist.heading("origen", text="Origen / Método", command=lambda: ordenar_columna_historial(tabla_hist, "origen", False))
    tabla_hist.heading("fecha", text="Fecha (Mes/Año)", command=lambda: ordenar_columna_historial(tabla_hist, "fecha", False))
    
    tabla_hist.column("titulo", width=220)
    tabla_hist.column("autor", width=150) # Ancho para el autor
    tabla_hist.column("origen", width=120, anchor="center")
    tabla_hist.column("fecha", width=100, anchor="center")
    
    scroll_y.pack(side="right", fill="y")
    tabla_hist.pack(side="left", fill="both", expand=True)
    
    registros_completos = [] 
    
    def actualizar_vista(*args):
        for item in tabla_hist.get_children():
            tabla_hist.delete(item)
            
        filtro = cmb_filtro_origen.get()
        
        for fila in registros_completos:
            origen_db = fila[2] 
            mostrar = False
            
            if filtro == "Todos":
                mostrar = True
            elif filtro == "Importados (Librero Antiguo)" and "Importación" in origen_db:
                mostrar = True
            elif filtro == "Asignados (App)" and "Asignación App" in origen_db:
                mostrar = True
                
            if mostrar:
                fila_formateada = list(fila)
                if fila_formateada[1] and fila_formateada[1] != 'None':
                    fila_formateada[1] = str(fila_formateada[1]).upper()
                else:
                    fila_formateada[1] = "DESCONOCIDO"
                
                tabla_hist.insert("", "end", values=tuple(fila_formateada))

    cmb_filtro_origen.bind("<<ComboboxSelected>>", actualizar_vista)
    
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        
        # --- CONSULTA SQL ANTI-DUPLICADOS ---
        query = """
            SELECT 
                l.titulo, 
                -- Si autor_historico NO es nulo o vacío, úsalo. Si no, usa el autor de la tabla libros.
                COALESCE(NULLIF(h.autor_historico, ''), l.autor) AS autor_final,
                'Asignación App' AS origen, 
                a.mes || '/' || a.ano AS fecha
            FROM asignaciones a
            JOIN libros l ON a.libro_suscripcion_id = l.libro_id
            LEFT JOIN librero_historico h ON a.cliente_id = h.cliente_id AND a.libro_suscripcion_id = h.libro_id
            WHERE a.cliente_id = ? AND a.libro_suscripcion_id IS NOT NULL

            UNION

            SELECT 
                l.titulo, 
                COALESCE(NULLIF(lh.autor_historico, ''), l.autor) AS autor_final,
                'Importación (Librero Antiguo)' AS origen, 
                '--' AS fecha
            FROM librero_historico lh
            JOIN libros l ON lh.libro_id = l.libro_id
            WHERE lh.cliente_id = ? AND lh.libro_id NOT IN (
                SELECT a2.libro_suscripcion_id FROM asignaciones a2 WHERE a2.cliente_id = ? AND a2.libro_suscripcion_id IS NOT NULL
            )
            
            ORDER BY titulo;
        """
        cursor.execute(query, (cliente_id, cliente_id, cliente_id))

        registros_completos = cursor.fetchall() 
        conn.close()
        
        if not registros_completos:
            tabla_hist.insert("", "end", values=("No hay libros registrados para esta clienta.", "", "", ""))
            cmb_filtro_origen.config(state="disabled") 
        else:
            actualizar_vista() 
            
    except Exception as e:
        messagebox.showerror("Error BD", f"No se pudo cargar el historial: {e}", parent=win)
        win.destroy()
        
def abrir_dialogo_extras(root, tabla, item_id, callback_asignaciones):
    asignacion_id = tabla.set(item_id, "asignacion_id")
    cliente_nombre = tabla.set(item_id, "nombre")
    extras_actuales_str = tabla.set(item_id, "extras")
    
    if not extras_actuales_str or extras_actuales_str == "None":
        extras_actuales_str = ""
    lista_extras = [e.strip() for e in extras_actuales_str.split(",") if e.strip()]
    
    # --- 1. CARGAR INVENTARIO ACTUAL ---
    titulos_inventario = []
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT UPPER(titulo) FROM libros ORDER BY titulo")
        titulos_inventario = [row[0] for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        messagebox.showerror("Error BD", f"No se pudo cargar el catálogo: {e}")

    win = tk.Toplevel(root)
    win.title(f"Gestionar Extras - {cliente_nombre}")
    win.geometry("450x380")
    win.transient(root)
    win.grab_set()
    win.configure(bg="#F7DAE7")
    
    tk.Label(win, text=f"Libros Extras para:\n{cliente_nombre}", bg="#F7DAE7", font=("Helvetica", 11, "bold")).pack(pady=(10, 5))
    
    frame_lista = tk.Frame(win, bg="#F7DAE7")
    frame_lista.pack(fill="both", expand=True, padx=20, pady=5)
    
    listbox = tk.Listbox(frame_lista, font=("Helvetica", 10), selectbackground="#81BFB7")
    listbox.pack(side="left", fill="both", expand=True)
    
    for ex in lista_extras:
        listbox.insert("end", ex)
        
    frame_controles = tk.Frame(win, bg="#F7DAE7")
    frame_controles.pack(fill="x", padx=20, pady=5)
    
    cb_nuevo = ttk.Combobox(frame_controles, values=titulos_inventario, width=32, font=("Helvetica", 10))
    cb_nuevo.pack(side="left", padx=(0, 5))
    
    def autocompletar(event):
        tecla = event.keysym
        if tecla in ('Up', 'Down', 'Left', 'Right', 'Return'): return
        texto_tecleado = cb_nuevo.get().upper()
        if texto_tecleado == "": cb_nuevo.config(values=titulos_inventario)
        else:
            datos_filtrados = [item for item in titulos_inventario if texto_tecleado in item]
            cb_nuevo.config(values=datos_filtrados)
            
    cb_nuevo.bind('<KeyRelease>', autocompletar)
    
    # --- NUEVO: FUNCIÓN DE AUTOGUARDADO EN SEGUNDO PLANO ---
    def auto_guardar_bd():
        nuevos_extras = [listbox.get(i) for i in range(listbox.size())]
        extras_str = ", ".join(nuevos_extras)
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE asignaciones SET extras = ? WHERE asignacion_id = ?", (extras_str, asignacion_id))
            conn.commit()
            conn.close()
            callback_asignaciones() # Refresca la tabla de atrás sin que te des cuenta
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar: {e}", parent=win)

    def agregar_extra():
        nuevo = cb_nuevo.get().strip().upper()
        if not nuevo: return
        
        if nuevo not in titulos_inventario:
            if messagebox.askyesno("Nuevo Libro", f"El libro '{nuevo}' NO existe en tu inventario.\n\n¿Deseas crearlo ahora en tu catálogo (con stock 0)?"):
                try:
                    conn = conexion.conectar_db()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original)
                        VALUES (?, 'SIN INFORMACION', 'SIN INFORMACION', 'SIN INFORMACION', 'TAPA BLANDA', 0, 0.0, 0.0)
                    """, (nuevo,))
                    conn.commit()
                    conn.close()
                    titulos_inventario.append(nuevo)
                    titulos_inventario.sort()
                    messagebox.showinfo("Éxito", "Libro creado y añadido al catálogo.", parent=win)
                except Exception as e:
                    messagebox.showerror("Error BD", f"No se pudo crear el libro: {e}", parent=win)
                    return
            else:
                pass
                
        listbox.insert("end", nuevo)
        cb_nuevo.set("")
        cb_nuevo.config(values=titulos_inventario)
        auto_guardar_bd() # <--- SE GUARDA SOLITO AL AÑADIR
            
    def quitar_extra():
        seleccion = listbox.curselection()
        if seleccion:
            listbox.delete(seleccion[0])
            auto_guardar_bd() # <--- SE GUARDA SOLITO AL QUITAR
            
    tk.Button(frame_controles, text="Añadir", command=agregar_extra, bg="#0288D1", fg="white", cursor="hand2").pack(side="left", padx=5)
    tk.Button(frame_controles, text="Quitar", command=quitar_extra, bg="#D32F2F", fg="white", cursor="hand2").pack(side="right")
    
    # --- EL BOTÓN DE ABAJO AHORA SOLO CIERRA LA VENTANA ---
    tk.Button(win, text="Cerrar Ventana", command=win.destroy, bg="#757575", fg="white", font=("Helvetica", 10, "bold"), pady=5).pack(fill="x", padx=20, pady=(10, 20))