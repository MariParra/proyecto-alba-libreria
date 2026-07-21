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

    tk.Button(win, text="Guardar", command=guardar_comentario, bg="#4CAF50", fg="white", font=("Helvetica", 10, "bold")).pack(pady=10)


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
    win.transient(root); win.grab_set(); win.configure(bg="#FFF8E1")
    
    tk.Label(win, text=f"Modificando asignación de:\n{cliente_nombre}", bg="#FFF8E1", font=("Helvetica", 11, "bold")).pack(pady=(10, 0))
    gustos_display = generos_str if generos_str and generos_str != "SIN INFORMACION" else "No especificados"
    tk.Label(win, text=f"Gustos de la clienta: {gustos_display}", bg="#FFF8E1", font=("Helvetica", 9, "italic"), fg="#555").pack(pady=(2, 5))
    
    lbl_alerta = tk.Label(win, text="¡Ojo! No hay libros en stock para sus gustos.", bg="#FFF8E1", font=("Helvetica", 9, "bold"), fg="red")
    if not libros_recomendados_stock and generos_preferidos:
        lbl_alerta.pack()

    # --- FRAME PARA LOS CHECKBOXES DE CONTROL ---
    frame_checks = tk.Frame(win, bg="#FFF8E1")
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

    chk_filtro_genero = tk.Checkbutton(frame_checks, text="Filtrar por Géneros", variable=usar_filtro_var, bg="#FFF8E1", command=actualizar_opciones_combobox, cursor="hand2")
    if not (libros_recomendados_stock or libros_recomendados_catalogo):
        chk_filtro_genero.config(state="disabled")
    chk_filtro_genero.pack(side="left", padx=10)

    chk_sin_stock = tk.Checkbutton(frame_checks, text="Incluir sin stock (Catálogo)", variable=incluir_sin_stock_var, bg="#FFF8E1", command=actualizar_opciones_combobox, cursor="hand2")
    chk_sin_stock.pack(side="left", padx=10)
    
    cb_libros.pack(pady=5, padx=15)
    actualizar_opciones_combobox()
    
    frame_botones = tk.Frame(win, bg="#FFF8E1")
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

    tk.Button(frame_botones, text="Guardar Cambios", command=guardar_y_cerrar, bg="#4CAF50", fg="white", font=("Helvetica", 10, "bold"), pady=6, width=15).pack(side="left", padx=(30, 10))
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
    win.geometry("550x400")
    win.transient(root)
    win.grab_set()
    win.configure(bg="#F3E5F5") # Fondo morado muy claro
    
    tk.Label(win, text=f"Biblioteca Personal de:\n{nombre_cliente}", bg="#F3E5F5", font=("Helvetica", 12, "bold")).pack(pady=(15, 10))
    
    frame_tabla = tk.Frame(win)
    frame_tabla.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    
    scroll_y = ttk.Scrollbar(frame_tabla, orient="vertical")
    # Tabla para mostrar el historial
    tabla_hist = ttk.Treeview(frame_tabla, columns=("titulo", "origen", "fecha"), show="headings", yscrollcommand=scroll_y.set)
    scroll_y.config(command=tabla_hist.yview)
    
    tabla_hist.heading("titulo", text="Título del Libro")
    tabla_hist.heading("origen", text="Origen / Método")
    tabla_hist.heading("fecha", text="Fecha (Mes/Año)")
    
    tabla_hist.column("titulo", width=250)
    tabla_hist.column("origen", width=120, anchor="center")
    tabla_hist.column("fecha", width=100, anchor="center")
    
    scroll_y.pack(side="right", fill="y")
    tabla_hist.pack(side="left", fill="both", expand=True)
    
    # Extraer y cruzar datos desde la Base de Datos
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        
        # Unimos el Histórico Importado con las Asignaciones hechas en la App
        query = """
            SELECT l.titulo, 'Importación (Librero Antiguo)' AS origen, 'N/A' AS fecha
            FROM librero_historico lh
            JOIN libros l ON lh.libro_id = l.libro_id
            WHERE lh.cliente_id = ?
            
            UNION
            
            SELECT l.titulo, 'Asignación App' AS origen, a.mes || '/' || a.ano AS fecha
            FROM asignaciones a
            JOIN libros l ON a.libro_suscripcion_id = l.libro_id
            WHERE a.cliente_id = ? AND a.libro_suscripcion_id IS NOT NULL
            
            ORDER BY titulo
        """
        cursor.execute(query, (cliente_id, cliente_id))
        registros = cursor.fetchall()
        conn.close()
        
        if not registros:
            tabla_hist.insert("", "end", values=("No hay libros registrados para esta clienta.", "", ""))
        else:
            for fila in registros:
                tabla_hist.insert("", "end", values=fila)
                
    except Exception as e:
        messagebox.showerror("Error BD", f"No se pudo cargar el historial: {e}", parent=win)
        win.destroy()
