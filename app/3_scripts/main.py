# aplicativo/main.py

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import sqlite3
import os
import conexion
import interfaz

# -- DEFINIR DICCIONARIO CENTRAL --
app = {}

# -- TRADUCTOR DE MESES --
MAPEO_MESES = {
    "Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04", "Mayo": "05", 
    "Junio": "06", "Julio": "07", "Agosto": "08", "Septiembre": "09", 
    "Octubre": "10", "Noviembre": "11", "Diciembre": "12"
}
INVERSO_MESES = {v: k for k, v in MAPEO_MESES.items()}

def iniciar_sincronizacion_periodo():
    meses_ui = app['menu_meses'].get_selection()
    
    meses_bd = [MAPEO_MESES.get(m) for m in meses_ui if m in MAPEO_MESES]
    anio_var = app['combo_anio'].get()
    app['txt_buscar'].delete(0, tk.END)
    
    if not meses_bd:
        messagebox.showwarning("Advertencia", "Debe seleccionar al menos un mes.")
        return

    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()

        for mes in meses_bd:
            cursor.execute("""
                INSERT OR IGNORE INTO asignaciones (cliente_id, mes, ano)
                SELECT c.cliente_id, ?, ? FROM clientes c
                WHERE c.status = 'ACTIVA' AND c.cliente_id NOT IN (
                    SELECT a.cliente_id FROM asignaciones a WHERE a.mes = ? AND a.ano = ?
                )
            """, (mes, anio_var, mes, anio_var))
        conn.commit()

        placeholders = ','.join(['?'] * len(meses_bd))
        
        query = f"""
            SELECT 
                a.asignacion_id, c.nombre, c.email, COALESCE(l.titulo, 'PENDIENTE'),
                a.mes, a.ano, s.fecha_pago, s.metodo_entrega, a.fecha_asignacion,
                c.telefono, c.direccion,
                a.libros_extras, a.pagado, a.envio_pagado, a.estado_envio
            FROM asignaciones a
            JOIN clientes c ON a.cliente_id = c.cliente_id
            JOIN suscripciones s ON c.cliente_id = s.cliente_id
            LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
            WHERE a.mes IN ({placeholders}) AND a.ano = ?
        """
        parametros = tuple(meses_bd) + (anio_var,)
        
        cursor.execute(query, parametros)
        
        filas_crudas = cursor.fetchall()
        filas_formateadas = []
        for fila in filas_crudas:
            lista_fila = list(fila)
            lista_fila[4] = INVERSO_MESES.get(lista_fila[4], lista_fila[4]) 
            lista_fila[12] = "SI" if str(lista_fila[12]).strip().upper() == "TRUE" else "NO"
            lista_fila[13] = "SI" if str(lista_fila[13]).strip().upper() == "TRUE" else "NO"
            filas_formateadas.append(tuple(lista_fila))
            
        app['clientes_datos'] = filas_formateadas
        conn.close()
        
        actualizar_tabla_clientes()
        
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo sincronizar el periodo: {e}")

def actualizar_tabla_clientes():
    for item in app['tabla_clientes'].get_children(): 
        app['tabla_clientes'].delete(item)
    for fila_datos in app.get('clientes_datos', []):
        app['tabla_clientes'].insert("", "end", values=fila_datos)

def actualizar_columnas_visibles():
    visibles = ['id', 'nom', 'libro', 'mes', 'ano', 'fecha_pago', 'env', 'fecha_asig', 'lib_ext', 'pagado', 'env_pag', 'est_env']
    for col_id, var in app['vars_columnas'].items():
        if var.get() == 1:
            visibles.append(col_id)
    app['tabla_clientes']['displaycolumns'] = visibles

def on_cell_edit(event):
    region = app['tabla_clientes'].identify_region(event.x, event.y)
    if region != "cell": return

    col_display_id = app['tabla_clientes'].identify_column(event.x)
    selected_col_name = app['tabla_clientes'].column(col_display_id, 'id')
    
    column_names = app['tabla_clientes']['columns']
    col_index = list(column_names).index(selected_col_name)

    mapeo_columnas_editables = {
        "fecha_pago": {"tabla": "suscripciones", "col": "fecha_pago"},
        "env": {"tabla": "suscripciones", "col": "metodo_entrega"},
        "fecha_asig": {"tabla": "asignaciones", "col": "fecha_asignacion"},
        "lib_ext": {"tabla": "asignaciones", "col": "libros_extras"},
        "pagado": {"tabla": "asignaciones", "col": "pagado"},
        "env_pag": {"tabla": "asignaciones", "col": "envio_pagado"},
        "est_env": {"tabla": "asignaciones", "col": "estado_envio"}
    }
    
    info_bd = mapeo_columnas_editables.get(selected_col_name)
    if not info_bd: return 

    target_table = info_bd["tabla"]
    db_col_name = info_bd["col"]

    selected_iid = app['tabla_clientes'].focus()
    valores = app['tabla_clientes'].item(selected_iid)['values']
    
    asignacion_id = valores[0]
    current_value = str(valores[col_index]) if len(valores) > col_index else ""

    x, y, width, height = app['tabla_clientes'].bbox(selected_iid, col_display_id)
    
    if selected_col_name in ["pagado", "env_pag"]:
        entry_edit = ttk.Combobox(app['tabla_clientes'], values=["SI", "NO"], state="readonly")
    elif selected_col_name == "est_env":
        entry_edit = ttk.Combobox(app['tabla_clientes'], values=["OK", "PENDIENTE"], state="readonly")
    elif selected_col_name == "env":
        entry_edit = ttk.Combobox(app['tabla_clientes'], values=["BLUEEXPRESS", "PAKET", "RETIRO"], state="readonly")
    else:
        entry_edit = ttk.Entry(app['tabla_clientes'])

    entry_edit.place(x=x, y=y, width=width, height=height)
    
    if isinstance(entry_edit, ttk.Combobox):
        entry_edit.set(current_value.upper())
    else:
        entry_edit.insert(0, current_value)
        
    entry_edit.focus()

    def save_edit(event_save=None):
        if not entry_edit.winfo_exists(): return
        
        nuevo_valor = entry_edit.get().strip()
        entry_edit.destroy()

        if selected_col_name in ["pagado", "env_pag"]:
            nuevo_valor_bd = "TRUE" if nuevo_valor.upper() == "SI" else "FALSE"
        else:
            nuevo_valor_bd = nuevo_valor

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            if target_table == "suscripciones":
                cursor.execute("SELECT cliente_id FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
                res = cursor.fetchone()
                if res:
                    cliente_id_oculto = res[0]
                    query = f"UPDATE suscripciones SET {db_col_name} = ? WHERE cliente_id = ?"
                    cursor.execute(query, (nuevo_valor_bd, cliente_id_oculto))
            else:
                query = f"UPDATE asignaciones SET {db_col_name} = ? WHERE asignacion_id = ?"
                cursor.execute(query, (nuevo_valor_bd, asignacion_id))
                
            conn.commit()
            conn.close()
            iniciar_sincronizacion_periodo()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el cambio: {e}")

    entry_edit.bind("<Return>", save_edit)
    entry_edit.bind("<FocusOut>", save_edit)
    if isinstance(entry_edit, ttk.Combobox):
        entry_edit.bind("<<ComboboxSelected>>", save_edit)

def refrescar_inventario():
    for item in app['tabla_inventario'].get_children(): 
        app['tabla_inventario'].delete(item)
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT libro_id, titulo, autor, genero, editorial, stock, precio FROM libros ORDER BY titulo")
        app['inventario_datos'] = cursor.fetchall()
        cursor.execute("SELECT DISTINCT genero FROM libros WHERE genero IS NOT NULL AND genero != '' ORDER BY genero")
        generos = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT editorial FROM libros WHERE editorial IS NOT NULL AND editorial != '' ORDER BY editorial")
        editoriales = [row[0] for row in cursor.fetchall()]
        conn.close()
        app['entries']['género']['values'] = generos
        app['entries']['editorial']['values'] = editoriales
        stock_total = sum(int(fila[5]) for fila in app['inventario_datos'] if fila[5] is not None)
        for fila in app['inventario_datos']:
            stock = int(fila[5]) if fila[5] is not None else 0
            tag = "agotado" if stock <= 0 else ("bajo" if stock <= 5 else "normal")
            app['tabla_inventario'].insert("", "end", values=fila, tags=(tag,))
        app['lbl_stock_total'].config(text=f"Unidades Totales en Inventario: {stock_total}")
        if 'txt_buscar_inv' in app:
            app['txt_buscar_inv'].delete(0, tk.END)
    except Exception as e:
        print(f"Error al refrescar inventario: {e}")

def disparar_script_externo(script, mensaje):
    try:
        root.config(cursor="watch")
        root.update()
        ruta_script = os.path.join(os.path.dirname(os.path.abspath(str(__file__))), '..', script)
        conexion.ejecutar_script_externo(ruta_script)
        root.config(cursor="")
        messagebox.showinfo("Exito", mensaje)
        iniciar_sincronizacion_periodo()
    except Exception as e:
        root.config(cursor="")
        messagebox.showerror("Error", str(e))

def filtrar_clientes_dinamico(event):
    termino = app['txt_buscar'].get().lower()
    if not termino:
        actualizar_tabla_clientes()
        return
    filtrados = [fila for fila in app['clientes_datos'] if termino in str(fila).lower()]
    for item in app['tabla_clientes'].get_children(): 
        app['tabla_clientes'].delete(item)
    for fila_datos in filtrados:
        app['tabla_clientes'].insert("", "end", values=fila_datos)

def filtrar_inventario_dinamico(event):
    if 'inventario_datos' not in app: return 
    termino = app['txt_buscar_inv'].get().lower()
    for item in app['tabla_inventario'].get_children(): 
        app['tabla_inventario'].delete(item)
    if not termino:
        filtrados = app['inventario_datos']
    else:
        filtrados = [lib for lib in app['inventario_datos'] if termino in str(lib).lower()]
    stock_total_busqueda = sum(int(fila[5]) for fila in filtrados if fila[5] is not None)
    for fila in filtrados:
        stock = int(fila[5]) if fila[5] is not None else 0
        tag = "agotado" if stock <= 0 else ("bajo" if stock <= 5 else "normal")
        app['tabla_inventario'].insert("", "end", values=fila, tags=(tag,))
    app['lbl_stock_total'].config(text=f"Unidades Totales (Búsqueda): {stock_total_busqueda}")

def guardar_nuevo_libro():
    try:
        titulo = app['entries']['título'].get().strip().upper()
        autor = app['entries']['autor'].get().strip().upper()
        genero = app['entries']['género'].get().strip().upper()
        editorial = app['entries']['editorial'].get().strip().upper()
        stock = app['entries']['stock'].get().strip()
        precio = app['entries']['precio'].get().strip()
        if not titulo or not stock:
            messagebox.showwarning("Advertencia", "El título y el stock son obligatorios.")
            return
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO libros (titulo, autor, genero, editorial, stock, precio) VALUES (?, ?, ?, ?, ?, ?)", (titulo, autor, genero, editorial, stock, precio))
        conn.commit()
        conn.close()
        messagebox.showinfo("Info", "Libro registrado exitosamente.")
        limpiar_formulario()
        refrescar_inventario()
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo guardar: {e}")

def modificar_libro_seleccionado():
    try:
        seleccion = app['tabla_inventario'].selection()
        if not seleccion:
            messagebox.showwarning("Advertencia", "Por favor, seleccione un libro de la tabla primero.")
            return
        item_seleccionado = app['tabla_inventario'].item(seleccion[0])
        libro_id = item_seleccionado['values'][0]
        titulo = app['entries']['título'].get().strip().upper()
        autor = app['entries']['autor'].get().strip().upper()
        genero = app['entries']['género'].get().strip().upper()
        editorial = app['entries']['editorial'].get().strip().upper()
        stock = app['entries']['stock'].get().strip()
        precio = app['entries']['precio'].get().strip()
        if not titulo or not stock:
            messagebox.showwarning("Advertencia", "El título y el stock son obligatorios.")
            return
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE libros SET titulo = ?, autor = ?, genero = ?, editorial = ?, stock = ?, precio = ? WHERE libro_id = ?", (titulo, autor, genero, editorial, stock, precio, libro_id))
        conn.commit()
        conn.close()
        messagebox.showinfo("Info", "Libro modificado exitosamente.")
        limpiar_formulario()
        refrescar_inventario()
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo modificar: {e}")

def eliminar_libro_seleccionado():
    try:
        seleccion = app['tabla_inventario'].selection()
        if not seleccion:
            messagebox.showwarning("Advertencia", "Por favor, seleccione un libro de la tabla primero.")
            return
        item_seleccionado = app['tabla_inventario'].item(seleccion[0])
        libro_id = item_seleccionado['values'][0]
        titulo = item_seleccionado['values'][1] 
        respuesta = messagebox.askyesno("Confirmar Eliminación", f"¿Está seguro de que desea eliminar el libro '{titulo}'?\n\nEsta acción no se puede deshacer.")
        if not respuesta:
            return
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM libros WHERE libro_id = ?", (libro_id,))
        conn.commit()
        conn.close()
        messagebox.showinfo("Info", "Libro eliminado exitosamente.")
        limpiar_formulario()
        refrescar_inventario()
    except sqlite3.IntegrityError:
        messagebox.showerror("Acción Denegada", "No se puede eliminar este libro porque ya ha sido asignado a un cliente en el historial.\n\nPara eliminarlo, primero debe removerlo de sus asignaciones o utilizar el script de limpieza profunda.")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo eliminar: {e}")

def al_seleccionar_libro(event):
    seleccion = app['tabla_inventario'].selection()
    if seleccion:
        # -- CORRECCIÓN: Limpiar solo los inputs SIN deseleccionar la tabla --
        app['entries']['título'].delete(0, tk.END)
        app['entries']['autor'].delete(0, tk.END)
        app['entries']['género'].set("")
        app['entries']['editorial'].set("")
        app['entries']['stock'].delete(0, tk.END)
        app['entries']['precio'].delete(0, tk.END)
        
        valores = app['tabla_inventario'].item(seleccion[0])['values']
        app['lbl_status_id'].config(text="Modo: Editando libro seleccionado", fg="#0277BD")
        app['entries']['título'].insert(0, valores[1])
        app['entries']['autor'].insert(0, valores[2])
        app['entries']['género'].set(valores[3])
        app['entries']['editorial'].set(valores[4])
        app['entries']['stock'].insert(0, valores[5])
        precio_val = valores[6] if len(valores) > 6 and str(valores[6]) != 'None' else ""
        app['entries']['precio'].insert(0, precio_val)

def limpiar_formulario():
    app['lbl_status_id'].config(text="Modo: Creando nuevo libro", fg="#C2185B")
    app['entries']['título'].delete(0, tk.END)
    app['entries']['autor'].delete(0, tk.END)
    app['entries']['género'].set("")
    app['entries']['editorial'].set("")
    app['entries']['stock'].delete(0, tk.END)
    app['entries']['precio'].delete(0, tk.END)
    if 'tabla_inventario' in app:
        for item in app['tabla_inventario'].selection():
            app['tabla_inventario'].selection_remove(item)

def asignar_libro_a_cliente():
    seleccion_cliente = app['tabla_clientes'].selection()
    if not seleccion_cliente:
        messagebox.showwarning("Advertencia", "Por favor, seleccione primero un cliente de la lista.")
        return
    
    item_cliente = app['tabla_clientes'].item(seleccion_cliente[0])
    asignacion_id = item_cliente['values'][0]
    nombre_cliente = item_cliente['values'][1] 
    mes_texto = item_cliente['values'][4]
    ano_fila = str(item_cliente['values'][5])

    ventana_asignacion = tk.Toplevel(root)
    ventana_asignacion.title("Asignar Libro")
    ventana_asignacion.geometry("500x320")
    ventana_asignacion.configure(bg="#FCE4EC")
    ventana_asignacion.transient(root) 
    ventana_asignacion.grab_set()

    font_bold_modal = ("Helvetica", 11, "bold")
    font_normal_modal = ("Helvetica", 10)

    tk.Label(ventana_asignacion, text=f"Seleccione el libro para:\n{nombre_cliente}\n(Período: {mes_texto} {ano_fila})", font=font_bold_modal, bg="#FCE4EC", fg="#1E1E2F").pack(pady=10)

    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        query = "SELECT libro_id, titulo, autor, COALESCE(stock, 0) FROM libros ORDER BY titulo"
        cursor.execute(query)
        libros_disponibles = cursor.fetchall()
        conn.close()
    except Exception as e:
        messagebox.showerror("Error", f"Error al consultar inventario: {e}", parent=ventana_asignacion)
        ventana_asignacion.destroy()
        return

    if not libros_disponibles:
        tk.Label(ventana_asignacion, text="No hay libros en el inventario.", bg="#FCE4EC", fg="#D32F2F", font=font_normal_modal).pack()
        return

    frame_buscador = tk.Frame(ventana_asignacion, bg="#FCE4EC")
    frame_buscador.pack(fill="x", padx=20, pady=(5, 5))
    tk.Label(frame_buscador, text="🔍 Buscar:", bg="#FCE4EC", font=font_normal_modal).pack(side="left")
    
    search_var = tk.StringVar()
    search_entry = ttk.Entry(frame_buscador, textvariable=search_var, font=font_normal_modal)
    search_entry.pack(side="left", expand=True, fill="x", padx=(5, 0))

    combo_libros = ttk.Combobox(ventana_asignacion, state="readonly", width=50, font=font_normal_modal)
    lista_opciones_original = [f"{l[0]} | {l[1]} - {l[2]} (Stock: {l[3]})" for l in libros_disponibles]
    combo_libros['values'] = lista_opciones_original
    combo_libros.pack(padx=20, pady=10)

    def actualizar_opciones_combo(*args):
        termino = search_var.get().lower()
        if not termino:
            combo_libros['values'] = lista_opciones_original
        else:
            filtradas = [opc for opc in lista_opciones_original if termino in opc.lower()]
            combo_libros['values'] = filtradas
        combo_libros.set('')

    search_var.trace("w", actualizar_opciones_combo)
    search_entry.focus()

    def confirmar_asignacion():
        seleccion_libro = combo_libros.get()
        if not seleccion_libro:
            messagebox.showwarning("Advertencia", "Debe seleccionar un libro.", parent=ventana_asignacion)
            return

        libro_id_seleccionado = seleccion_libro.split(" | ")[0]
        libro_titulo = seleccion_libro.split(" | ")[1].split(" - ")[0]

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (row[0],))
            
            cursor.execute("""
                UPDATE asignaciones 
                SET libro_suscripcion_id = ?, fecha_asignacion = CURRENT_TIMESTAMP
                WHERE asignacion_id = ?
            """, (libro_id_seleccionado, asignacion_id))
            
            cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = ?", (libro_id_seleccionado,))
            
            conn.commit()
            conn.close()

            mensaje_exito = f"Se ha asignado correctamente el libro:\n\n'{libro_titulo}'\n\na: {nombre_cliente}."
            messagebox.showinfo("Asignación Exitosa", mensaje_exito, parent=ventana_asignacion)
            
            ventana_asignacion.destroy()
            iniciar_sincronizacion_periodo()

        except Exception as e:
            messagebox.showerror("Error", f"Fallo al procesar la asignación: {e}", parent=ventana_asignacion)

    tk.Button(ventana_asignacion, text="Confirmar Asignación", command=confirmar_asignacion, bg="#00897B", fg="white", font=("Helvetica", 10, "bold"), relief="flat", cursor="hand2", padx=10).pack(pady=10)


# -- MAPEAR EVENTOS --
app['cmd_sincronizar_periodo'] = iniciar_sincronizacion_periodo
app['cmd_sync_clientes'] = lambda: disparar_script_externo("sync.py", "Sincronización con Google Sheets completada con éxito.")
app['cmd_import_catalogo'] = lambda: disparar_script_externo("import_catalogo.py", "Catálogo base de libros cargado masivamente.")
app['cmd_quitar_filtro'] = refrescar_inventario
app['cmd_limpiar_form'] = limpiar_formulario
app['cmd_filtrar_teclado'] = filtrar_clientes_dinamico
app['cmd_filtrar_inv_teclado'] = filtrar_inventario_dinamico
app['cmd_guardar_nuevo'] = guardar_nuevo_libro
app['cmd_modificar_sel'] = modificar_libro_seleccionado
app['cmd_eliminar_sel'] = eliminar_libro_seleccionado
app['cmd_asignar_libro'] = asignar_libro_a_cliente
app['cmd_actualizar_columnas'] = actualizar_columnas_visibles

# -- INICIALIZAR LA APLICACION --
conexion.realizar_respaldo_automatico(etiqueta="OPEN")
root = tk.Tk()
interfaz.construir_interfaz(root, app)

app['tabla_clientes'].bind("<Double-1>", on_cell_edit)
app['tabla_inventario'].bind("<<TreeviewSelect>>", al_seleccionar_libro)

iniciar_sincronizacion_periodo()
refrescar_inventario()

root.protocol("WM_DELETE_WINDOW", lambda: [conexion.realizar_respaldo_automatico(etiqueta="CLOSE"), root.destroy()])
root.mainloop()
