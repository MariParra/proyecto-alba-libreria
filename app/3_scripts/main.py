import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import os
import conexion
import interfaz

# -- DEFINIR DICCIONARIO CENTRAL PARA ENLAZAR WIDGETS Y EVENTOS --
app = {}

def iniciar_sincronizacion_periodo():
    # -- OBTENER DATOS DEL PERIODO SELECCIONADO --
    mes = app['combo_mes'].get()
    anio_var = app['combo_anio'].get()
    app['txt_buscar'].delete(0, tk.END)
    
    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()

        # -- ASEGURAR QUE LA TABLA ASIGNACIONES EXISTA --
        # Esta logica ya esta en sync.py, pero la dejamos por seguridad
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asignaciones (
                asignacion_id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER,
                libro_suscripcion_id INTEGER, ano TEXT, mes TEXT,
                FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id),
                FOREIGN KEY (libro_suscripcion_id) REFERENCES libros(libro_id)
            )
        """)
        
        # -- PRE-POBLAR TABLA CON PLANTILLAS PENDIENTES --
        cursor.execute("""
            INSERT INTO asignaciones (cliente_id, mes, ano)
            SELECT cliente_id, ?, ? 
            FROM clientes 
            WHERE status = 'ACTIVA' 
            AND cliente_id NOT IN (
                SELECT cliente_id FROM asignaciones WHERE mes = ? AND ano = ?
            )
        """, (mes, anio_var, mes, anio_var))
        conn.commit()

        # -- OBTENER LA LISTA DE CLIENTES DEL PERIODO (CORREGIDO JOIN) --
        cursor.execute("""
            SELECT c.cliente_id, c.nombre, c.email, COALESCE(l.titulo, 'PENDIENTE')
            FROM asignaciones a
            JOIN clientes c ON a.cliente_id = c.cliente_id
            LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
            WHERE a.mes = ? AND a.ano = ?
        """, (mes, anio_var))
        
        app['clientes_datos'] = cursor.fetchall()
        conn.close()
        
        # -- ACTUALIZAR TABLA DE CLIENTES EN LA INTERFAZ --
        for item in app['tabla_clientes'].get_children(): 
            app['tabla_clientes'].delete(item)
        for fila in app['clientes_datos']: 
            app['tabla_clientes'].insert("", "end", values=fila[:4])
            
        refrescar_inventario()
        
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo sincronizar el periodo: {e}")

# ... (El resto del código de main.py no necesita cambios para este error)
# ... (Te lo incluyo completo abajo por si acaso)

def refrescar_inventario():
    # -- LIMPIAR LA VISTA DE INVENTARIO ACTUAL --
    for item in app['tabla_inventario'].get_children(): 
        app['tabla_inventario'].delete(item)
    try:
        # -- CONECTAR A LA BASE DE DATOS Y OBTENER DATOS --
        conn = conexion.conectar_db()
        cursor = conn.cursor()

        # 1. OBTENER TODOS LOS LIBROS PARA LA TABLA
        cursor.execute("SELECT libro_id, titulo, autor, genero, editorial, stock, precio FROM libros ORDER BY titulo")
        app['inventario_datos'] = cursor.fetchall()

        # 2. OBTENER GÉNEROS ÚNICOS PARA EL DESPLEGABLE
        cursor.execute("SELECT DISTINCT genero FROM libros WHERE genero IS NOT NULL AND genero != '' ORDER BY genero")
        generos = [row[0] for row in cursor.fetchall()]

        # 3. OBTENER EDITORIALES ÚNICAS PARA EL DESPLEGABLE
        cursor.execute("SELECT DISTINCT editorial FROM libros WHERE editorial IS NOT NULL AND editorial != '' ORDER BY editorial")
        editoriales = [row[0] for row in cursor.fetchall()]

        conn.close()

        # -- ACTUALIZAR MENÚS DESPLEGABLES EN LA INTERFAZ --
        app['entries']['género']['values'] = generos
        app['entries']['editorial']['values'] = editoriales
        
        # -- POBLAR TABLA DE INVENTARIO Y CALCULAR SUMA DE STOCK --
        stock_total = 0
        for fila in app['inventario_datos']:
            stock = int(fila[5]) if fila[5] is not None else 0
            stock_total += stock
            tag = "agotado" if stock == 0 else ("bajo" if stock <= 5 else "normal")
            app['tabla_inventario'].insert("", "end", values=fila, tags=(tag,))
            
        # -- ACTUALIZAR ETIQUETA DE SUMA TOTAL --
        app['lbl_stock_total'].config(text=f"Unidades Totales en Inventario: {stock_total}")
            
        # -- LIMPIAR CAMPO DE BUSQUEDA AL REFRESCAR --
        if 'txt_buscar_inv' in app:
            app['txt_buscar_inv'].delete(0, tk.END)
            
    except Exception as e:
        print(f"Error al refrescar inventario: {e}")


def disparar_script_externo(script, mensaje):
    # -- EJECUTAR UN SCRIPT EXTERNO Y MOSTRAR FEEDBACK --
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
    # -- FILTRAR LA TABLA DE CLIENTES EN MEMORIA A MEDIDA QUE EL USUARIO ESCRIBE --
    if 'clientes_datos' not in app or not app['clientes_datos']:
        return
        
    termino = app['txt_buscar'].get().lower()
    
    # -- RESTAURAR LA LISTA SI EL BUSCADOR ESTA VACIO --
    if not termino:
        for item in app['tabla_clientes'].get_children(): 
            app['tabla_clientes'].delete(item)
        for fila in app['clientes_datos']: 
            app['tabla_clientes'].insert("", "end", values=fila[:4])
        return
        
    # -- FILTRAR EN MEMORIA COMPARANDO EL TEXTO ESCRITO --
    filtrados = [c for c in app['clientes_datos'] if termino in str(c).lower()]
    
    # -- LIMPIAR Y REDIBUJAR LA TABLA CON LOS RESULTADOS FILTRADOS --
    for item in app['tabla_clientes'].get_children(): 
        app['tabla_clientes'].delete(item)
    for fila in filtrados: 
        app['tabla_clientes'].insert("", "end", values=fila[:4])

def filtrar_inventario_dinamico(event):
    # -- FILTRAR LA TABLA DE INVENTARIO EN MEMORIA A MEDIDA QUE EL USUARIO ESCRIBE --
    if 'inventario_datos' not in app or not app['inventario_datos']:
        return
        
    termino = app['txt_buscar_inv'].get().lower()
    
    # Limpiar tabla
    for item in app['tabla_inventario'].get_children(): 
        app['tabla_inventario'].delete(item)
        
    # Si esta vacio, mostrar todo
    if not termino:
        filtrados = app['inventario_datos']
    else:
        # Filtrar convirtiendo la fila a string
        filtrados = [lib for lib in app['inventario_datos'] if termino in str(lib).lower()]
        
    # Redibujar y recalcular el total mostrado en la busqueda
    stock_total_busqueda = 0
    for fila in filtrados:
        stock = int(fila[5]) if fila[5] is not None else 0
        stock_total_busqueda += stock
        tag = "agotado" if stock == 0 else ("bajo" if stock <= 5 else "normal")
        app['tabla_inventario'].insert("", "end", values=fila, tags=(tag,))
        
    # Actualizar etiqueta con lo que se encontro en la busqueda
    app['lbl_stock_total'].config(text=f"Unidades Totales (Búsqueda): {stock_total_busqueda}")

def guardar_nuevo_libro():
    # -- GUARDAR UN NUEVO LIBRO EN LA BASE DE DATOS --
    try:
        # -- EXTRAER VALORES Y APLICAR MAYUSCULAS Y STRIP (LIMPIEZA DE ESPACIOS) --
        titulo = app['entries']['título'].get().strip().upper()
        autor = app['entries']['autor'].get().strip().upper()
        genero = app['entries']['género'].get().strip().upper()
        editorial = app['entries']['editorial'].get().strip().upper()
        stock = app['entries']['stock'].get().strip()
        precio = app['entries']['precio'].get().strip()

        # -- VALIDAR CAMPOS OBLIGATORIOS BASICOS --
        if not titulo or not stock:
            messagebox.showwarning("Advertencia", "El título y el stock son obligatorios.")
            return

        # -- CONECTAR A DB Y EJECUTAR INSERT --
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO libros (titulo, autor, genero, editorial, stock, precio) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (titulo, autor, genero, editorial, stock, precio))
        conn.commit()
        conn.close()

        # -- MOSTRAR MENSAJE, LIMPIAR Y REFRESCAR LA TABLA --
        messagebox.showinfo("Info", "Libro registrado exitosamente.")
        app['cmd_limpiar_form']()
        refrescar_inventario()

    except Exception as e:
        messagebox.showerror("Error", f"No se pudo guardar: {e}")

def modificar_libro_seleccionado():
    # -- ACTUALIZAR UN LIBRO EXISTENTE EN LA BASE DE DATOS --
    try:
        # -- OBTENER EL ELEMENTO SELECCIONADO EN LA TABLA --
        seleccion = app['tabla_inventario'].selection()
        if not seleccion:
            messagebox.showwarning("Advertencia", "Por favor, seleccione un libro de la tabla primero.")
            return

        # -- OBTENER EL ID DEL LIBRO SELECCIONADO --
        item_seleccionado = app['tabla_inventario'].item(seleccion[0])
        libro_id = item_seleccionado['values'][0]

        # -- EXTRAER VALORES Y APLICAR MAYUSCULAS Y STRIP --
        titulo = app['entries']['título'].get().strip().upper()
        autor = app['entries']['autor'].get().strip().upper()
        genero = app['entries']['género'].get().strip().upper()
        editorial = app['entries']['editorial'].get().strip().upper()
        stock = app['entries']['stock'].get().strip()
        precio = app['entries']['precio'].get().strip()

        if not titulo or not stock:
            messagebox.showwarning("Advertencia", "El título y el stock son obligatorios.")
            return

        # -- CONECTAR A DB Y EJECUTAR UPDATE --
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE libros 
            SET titulo = ?, autor = ?, genero = ?, editorial = ?, stock = ?, precio = ? 
            WHERE libro_id = ?
        """, (titulo, autor, genero, editorial, stock, precio, libro_id))
        conn.commit()
        conn.close()

        # -- MOSTRAR MENSAJE, LIMPIAR Y REFRESCAR LA TABLA --
        messagebox.showinfo("Info", "Libro modificado exitosamente.")
        app['cmd_limpiar_form']()
        refrescar_inventario()

    except Exception as e:
        messagebox.showerror("Error", f"No se pudo modificar: {e}")

def eliminar_libro_seleccionado():
    # -- ELIMINAR UN LIBRO DE LA BASE DE DATOS --
    try:
        # -- VERIFICAR SELECCION --
        seleccion = app['tabla_inventario'].selection()
        if not seleccion:
            messagebox.showwarning("Advertencia", "Por favor, seleccione un libro de la tabla primero.")
            return

        # -- OBTENER ID Y TITULO PARA CONFIRMACION --
        item_seleccionado = app['tabla_inventario'].item(seleccion[0])
        libro_id = item_seleccionado['values'][0]
        titulo = item_seleccionado['values'][1] 

        # -- MOSTRAR VENTANA DE CONFIRMACION --
        respuesta = messagebox.askyesno("Confirmar Eliminación", f"¿Está seguro de que desea eliminar el libro '{titulo}'?\n\nEsta acción no se puede deshacer.")
        if not respuesta:
            return

        # -- CONECTAR A DB Y EJECUTAR DELETE --
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM libros WHERE libro_id = ?", (libro_id,))
        conn.commit()
        conn.close()

        # -- MOSTRAR MENSAJE, LIMPIAR Y REFRESCAR --
        messagebox.showinfo("Info", "Libro eliminado exitosamente.")
        app['cmd_limpiar_form']()
        refrescar_inventario()

    except Exception as e:
        messagebox.showerror("Error", f"No se pudo eliminar: {e}")

def al_seleccionar_libro(event):
    # -- LLENAR EL FORMULARIO AL SELECCIONAR UN LIBRO EN LA TABLA Y CAMBIAR MODO --
    seleccion = app['tabla_inventario'].selection()
    if seleccion:
        limpiar_formulario()
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
    # -- RESTAURAR LABEL A MODO CREACION Y LIMPIAR CAMPOS --
    app['lbl_status_id'].config(text="Modo: Creando nuevo libro", fg="#C2185B")
    app['entries']['título'].delete(0, tk.END)
    app['entries']['autor'].delete(0, tk.END)
    app['entries']['género'].set("")
    app['entries']['editorial'].set("")
    app['entries']['stock'].delete(0, tk.END)
    app['entries']['precio'].delete(0, tk.END)
    for item in app['tabla_inventario'].selection():
        app['tabla_inventario'].selection_remove(item)

def asignar_libro_a_cliente():
    # -- LOGICA PARA ASIGNAR UN LIBRO AL CLIENTE SELECCIONADO --
    seleccion_cliente = app['tabla_clientes'].selection()
    if not seleccion_cliente:
        messagebox.showwarning("Advertencia", "Por favor, seleccione primero un cliente de la lista.")
        return

    item_cliente = app['tabla_clientes'].item(seleccion_cliente[0])
    cliente_id = item_cliente['values'][0]
    nombre_cliente = item_cliente['values'][1]

    ventana_asignacion = tk.Toplevel(root)
    ventana_asignacion.title("Asignar Libro")
    ventana_asignacion.geometry("500x250")
    ventana_asignacion.configure(bg="#FCE4EC")
    ventana_asignacion.transient(root) 
    ventana_asignacion.grab_set()

    font_bold_modal = ("Helvetica", 11, "bold")
    font_normal_modal = ("Helvetica", 10)

    tk.Label(ventana_asignacion, text=f"Seleccione el libro para:\n{nombre_cliente}", font=font_bold_modal, bg="#FCE4EC", fg="#1E1E2F").pack(pady=15)

    try:
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT libro_id, titulo, autor, stock FROM libros WHERE stock > 0 ORDER BY titulo")
        libros_disponibles = cursor.fetchall()
        conn.close()
    except Exception as e:
        messagebox.showerror("Error", f"Error al consultar inventario: {e}", parent=ventana_asignacion)
        ventana_asignacion.destroy()
        return

    if not libros_disponibles:
        tk.Label(ventana_asignacion, text="No hay libros con stock disponible.", bg="#FCE4EC", fg="#D32F2F", font=font_normal_modal).pack()
        return

    combo_libros = ttk.Combobox(ventana_asignacion, state="readonly", width=50, font=font_normal_modal)
    lista_opciones = [f"{l[0]} | {l[1]} - {l[2]} (Stock: {l[3]})" for l in libros_disponibles]
    combo_libros['values'] = lista_opciones
    combo_libros.pack(padx=20, pady=10)

    def confirmar_asignacion():
        seleccion_libro = combo_libros.get()
        if not seleccion_libro:
            messagebox.showwarning("Advertencia", "Debe seleccionar un libro.", parent=ventana_asignacion)
            return

        libro_id_seleccionado = seleccion_libro.split(" | ")[0]
        mes = app['combo_mes'].get()
        anio_var = app['combo_anio'].get()

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE cliente_id = ? AND mes = ? AND ano = ?", (cliente_id, mes, anio_var))
            row = cursor.fetchone()
            if row and row[0] is not None:
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (row[0],))
            
            # -- ACTUALIZAR LA FILA PENDIENTE CON EL NUEVO LIBRO (CORREGIDO) --
            cursor.execute("""
                UPDATE asignaciones 
                SET libro_suscripcion_id = ?
                WHERE cliente_id = ? AND mes = ? AND ano = ?
            """, (libro_id_seleccionado, cliente_id, mes, anio_var))
            
            cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = ?", (libro_id_seleccionado,))
            
            conn.commit()
            conn.close()

            messagebox.showinfo("Exito", "El libro ha sido asignado.", parent=ventana_asignacion)
            ventana_asignacion.destroy()
            iniciar_sincronizacion_periodo()

        except Exception as e:
            messagebox.showerror("Error", f"Fallo al procesar la asignación: {e}", parent=ventana_asignacion)

    tk.Button(ventana_asignacion, text="Confirmar Asignación", command=confirmar_asignacion, bg="#00897B", fg="white", font=("Helvetica", 10, "bold"), relief="flat", cursor="hand2", padx=10).pack(pady=20)


# -- MAPEAR EVENTOS A LA ESTRUCTURA QUE REQUIERE LA INTERFAZ --
app['cmd_sincronizar_periodo'] = iniciar_sincronizacion_periodo
app['cmd_sync_clientes'] = lambda: disparar_script_externo("sync.py", "Formulario de clientes importado con éxito.")
app['cmd_import_catalogo'] = lambda: disparar_script_externo("import_catalogo.py", "Catálogo base de libros cargado masivamente.")
app['cmd_quitar_filtro'] = refrescar_inventario
app['cmd_limpiar_form'] = limpiar_formulario
app['cmd_filtrar_teclado'] = filtrar_clientes_dinamico
app['cmd_filtrar_inv_teclado'] = filtrar_inventario_dinamico
app['cmd_guardar_nuevo'] = guardar_nuevo_libro
app['cmd_modificar_sel'] = modificar_libro_seleccionado
app['cmd_eliminar_sel'] = eliminar_libro_seleccionado
app['cmd_asignar_libro'] = asignar_libro_a_cliente

# -- INICIALIZAR LA APLICACION Y CREAR RESPALDO DE APERTURA --
conexion.realizar_respaldo_automatico(etiqueta="OPEN")
root = tk.Tk()
interfaz.construir_interfaz(root, app)

# -- VINCULAR EVENTO DE SELECCION A LA TABLA INVENTARIO --
app['tabla_inventario'].bind("<<TreeviewSelect>>", al_seleccionar_libro)

iniciar_sincronizacion_periodo()

# -- ESTABLECER RESPALDO AUTOMATICO AL CERRAR (CLOSE) --
root.protocol("WM_DELETE_WINDOW", lambda: [conexion.realizar_respaldo_automatico(etiqueta="CLOSE"), root.destroy()])
root.mainloop()