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


def abrir_dialogo_asignar_libro(root, tabla, callback_asignaciones, callback_inventario):
    selected_iid = tabla.focus()
    if not selected_iid: return
    
    asignacion_id = tabla.set(selected_iid, "asignacion_id")
    cliente_nombre = tabla.set(selected_iid, "nombre")
    
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
        current_libro_id = cursor.fetchone()[0]
        cursor.execute("SELECT libro_id, titulo, stock FROM libros WHERE stock > 0 ORDER BY titulo")
        libros_disponibles = cursor.fetchall()

        # Si el libro actual ya no tiene stock, lo buscamos aparte para mostrarlo en la lista
        if current_libro_id and not any(l[0] == current_libro_id for l in libros_disponibles):
                cursor.execute("SELECT libro_id, titulo, stock FROM libros WHERE libro_id = ?", (current_libro_id,))
                libro_actual_info = cursor.fetchone()
                if libro_actual_info:
                    libros_disponibles.insert(0, libro_actual_info)

        conn.close()
    except Exception as e:
        messagebox.showerror("Error", f"Error al acceder a BD: {e}")
        return
        
    mapa_libros = {f"{t} (Stock: {s})": l_id for l_id, t, s in libros_disponibles}
    opciones = ["(Sin Asignar)"] + list(mapa_libros.keys())
    
    valor_actual_str = "(Sin Asignar)"
    if current_libro_id:
        for txt, l_id in mapa_libros.items():
            if l_id == current_libro_id:
                valor_actual_str = txt
                break

    win = tk.Toplevel(root)
    win.title("Asignar Libro")
    win.geometry("420x220")
    win.transient(root)
    win.grab_set()
    win.configure(bg="#FFF8E1")
    tk.Label(win, text=f"Asignando libro a:\n{cliente_nombre}", bg="#FFF8E1", font=("Helvetica", 11, "bold")).pack(pady=(15, 10))
    cb_libros = ttk.Combobox(win, values=opciones, state="readonly", width=45, font=("Helvetica", 10))
    cb_libros.pack(pady=10)
    cb_libros.set(valor_actual_str)
    
    def guardar_asignacion():
        nuevo_valor_str = cb_libros.get()
        nuevo_id = mapa_libros.get(nuevo_valor_str, None)

        if nuevo_id == current_libro_id:
            win.destroy()
            return
            
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()

            # Lógica robusta para actualizar stock
            # Restaura el stock del libro anterior si existía
            if current_libro_id:
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (current_libro_id,))
            
            # Reduce el stock del nuevo libro si se asignó uno
            if nuevo_id:
                cursor.execute("SELECT stock FROM libros WHERE libro_id = ?", (nuevo_id,))
                stock_actual_nuevo_libro = cursor.fetchone()[0]
                if stock_actual_nuevo_libro <= 0:
                     messagebox.showwarning("Sin Stock", "El libro seleccionado ya no tiene stock disponible. La operación fue cancelada.", parent=win)
                     conn.rollback() # Revertir el aumento de stock del libro anterior
                     conn.close()
                     win.destroy()
                     callback_inventario()
                     return
                cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = ?", (nuevo_id,))

            # Actualiza la asignación
            cursor.execute("UPDATE asignaciones SET libro_suscripcion_id = ? WHERE asignacion_id = ?", (nuevo_id, asignacion_id))

            conn.commit()
            conn.close()
            messagebox.showinfo("Asignación Exitosa", "Libro asignado y stock actualizado.", parent=win)
            win.destroy()
            callback_asignaciones()
            callback_inventario()
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al asignar el libro: {e}", parent=win)
            
    tk.Button(win, text="Confirmar Asignación", command=guardar_asignacion, bg="#4CAF50", fg="white", font=("Helvetica", 10, "bold"), pady=5, padx=10).pack(pady=10)


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