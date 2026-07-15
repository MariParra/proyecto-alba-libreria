import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import datetime
import conexion

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
        # Llamar a la ventana emergente para asignar libro
        abrir_dialogo_asignar_libro(root, tabla, callback_refrescar, lambda: refrescar_inventario_global(widgets))
        return

    # Lógica de edición in-line para estados
    opciones_combo = None
    campo_bd = None
    # ... (código de edición in-line para estados sin cambios) ...
    estados = ["EN PREPARACION", "POR ENVIAR", "ENVIADO", "POR RETIRAR", "RETIRADO"]
    if selected_col_name == "estado":
        opciones_combo = estados
        campo_bd = "estado_envio"
    elif selected_col_name == "pagado":
        opciones_combo = ["Si", "No"]
        campo_bd = "pagado"
    elif selected_col_name == "tipo_envio":
        opciones_combo = ["STARKEN", "BLUEXPRESS", "CORREOS CHILE", "RETIRO"] # Ejemplo
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
                # Para el tipo de envío, la tabla es 'suscripciones', no 'asignaciones'
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
    asignacion_id = tabla.set(selected_iid, "asignacion_id")
    cliente_nombre = tabla.set(selected_iid, "nombre")
    
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
        current_libro_id = cursor.fetchone()[0]
        # --- MEJORA FUTURA: APLICAR AQUÍ "WHERE stock > 0" ---
        cursor.execute("SELECT libro_id, titulo, stock FROM libros ORDER BY titulo")
        libros_db = cursor.fetchall()
        conn.close()
    except Exception as e:
        messagebox.showerror("Error", f"Error al acceder a BD: {e}")
        return
        
    mapa_libros = {f"{t} (Stock: {s})": l_id for l_id, t, s in libros_db}
    opciones = ["(Sin Asignar)"] + list(mapa_libros.keys())
    
    # (Código de la ventana emergente y lógica de stock sin cambios)
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
            if current_libro_id:
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (current_libro_id,))
            if nuevo_id:
                cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = ?", (nuevo_id,))
            cursor.execute("UPDATE asignaciones SET libro_suscripcion_id = ? WHERE asignacion_id = ?", (nuevo_id, asignacion_id))
            conn.commit()
            conn.close()
            messagebox.showinfo("Asignación Exitosa", "Libro asignado y stock actualizado.", parent=win)
            win.destroy()
            callback_asignaciones()
            callback_inventario() # Refresca también la tabla de inventario
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al asignar el libro: {e}", parent=win)
            
    tk.Button(win, text="Confirmar Asignación", command=guardar_asignacion, bg="#4CAF50", fg="white", font=("Helvetica", 10, "bold"), pady=5, padx=10).pack(pady=10)

def abrir_dialogo_fecha(root, tabla, callback_refrescar):
    # (Código del diálogo de fecha sin cambios)
    selected_iid = tabla.focus()
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
    entry_fecha.insert(0, valor_actual)
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
    
# Esta función global es necesaria para que el pop-up de asignación pueda llamar al refresco del inventario
def refrescar_inventario_global(widgets):
    pass # Será reemplazada por la función real del controlador