import tkinter as tk
from tkinter import messagebox
import os
import conexion
import interfaz

# -- DEFINIR DICCIONARIO CENTRAL PARA ENLAZAR WIDGETS Y EVENTOS --
app = {}

def iniciar_sincronizacion_periodo():
    # -- OBTENER DATOS DEL PERIODO Y LIMPIAR BUSQUEDA --
    mes = app['combo_mes'].get()
    app['txt_buscar'].delete(0, tk.END)
    try:
        # -- CONECTAR A LA BASE DE DATOS Y OBTENER CLIENTES DEL PERIODO --
        conn = conexion.conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.cliente_id, c.nombre, c.email, s.metodo_entrega, s.generos_preferencia
            FROM clientes c
            JOIN suscripciones s ON c.cliente_id = s.cliente_id
            WHERE c.status = 'ACTIVA' AND s.fecha_pago = ?
        """, (mes,))
        app['clientes_datos'] = cursor.fetchall()
        conn.close()
        
        # -- ACTUALIZAR TABLA DE CLIENTES EN LA INTERFAZ --
        for item in app['tabla_clientes'].get_children(): 
            app['tabla_clientes'].delete(item)
        for fila in app['clientes_datos']: 
            app['tabla_clientes'].insert("", "end", values=fila[:4])
        refrescar_inventario()
    except Exception as e:
        messagebox.showerror("Error", str(e))

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

        # 2. OBTENER GENEROS UNICOS PARA EL DESPLEGABLE
        cursor.execute("SELECT DISTINCT genero FROM libros WHERE genero IS NOT NULL AND genero != '' ORDER BY genero")
        generos = [row[0] for row in cursor.fetchall()]

        # 3. OBTENER EDITORIALES UNICAS PARA EL DESPLEGABLE
        cursor.execute("SELECT DISTINCT editorial FROM libros WHERE editorial IS NOT NULL AND editorial != '' ORDER BY editorial")
        editoriales = [row[0] for row in cursor.fetchall()]

        conn.close()

        # -- ACTUALIZAR MENUS DESPLEGABLES EN LA INTERFAZ --
        app['entries']['género']['values'] = generos
        app['entries']['editorial']['values'] = editoriales
        
        # -- POBLAR LA TABLA DE INVENTARIO CON TAGS DE COLOR SEGUN STOCK --
        for fila in app['inventario_datos']:
            stock = int(fila[5]) if fila[5] is not None else 0
            tag = "agotado" if stock == 0 else ("bajo" if stock <= 5 else "normal")
            app['tabla_inventario'].insert("", "end", values=fila, tags=(tag,))
            
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
        conexion.ejecutar_script_externo(script)
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
        
    # Redibujar manteniendo las reglas de color de stock
    for fila in filtrados:
        stock = int(fila[5]) if fila[5] is not None else 0
        tag = "agotado" if stock == 0 else ("bajo" if stock <= 5 else "normal")
        app['tabla_inventario'].insert("", "end", values=fila, tags=(tag,))

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
        valores = app['tabla_inventario'].item(seleccion[0])['values']
        app['cmd_limpiar_form']() # -- LIMPIAR PRIMERO --
        
        # -- CAMBIAR LABEL A MODO EDICION (AZUL PARA DIFERENCIAR) --
        app['lbl_status_id'].config(text="Modo: Editando libro seleccionado", fg="#0277BD")
        
        # -- ASIGNAR CAMPOS USANDO LOS INDICES CORRECTOS DE LA FILA --
        app['entries']['título'].insert(0, valores[1])
        app['entries']['autor'].insert(0, valores[2])
        app['entries']['género'].set(valores[3])
        app['entries']['editorial'].set(valores[4])
        app['entries']['stock'].insert(0, valores[5])
        
        # -- MANEJAR EL PRECIO QUE PODRIA SER NULO EN ALGUNOS REGISTROS --
        precio_val = valores[6] if len(valores) > 6 and str(valores[6]) != 'None' else ""
        app['entries']['precio'].insert(0, precio_val)

# -- FUNCION LIMPIAR FORMULARIO ACTUALIZADA (RESTAURA MODO CREACION) --
def limpiar_formulario():
    # -- DESELECCIONAR CUALQUIER ITEM DE LA TABLA --
    for item in app['tabla_inventario'].selection():
        app['tabla_inventario'].selection_remove(item)
        
    # -- RESTAURAR LABEL A MODO CREACION (ROSA/MAGENTA) --
    app['lbl_status_id'].config(text="Modo: Creando nuevo libro", fg="#C2185B")
    
    # -- LIMPIAR INPUTS --
    app['entries']['título'].delete(0, tk.END)
    app['entries']['autor'].delete(0, tk.END)
    app['entries']['género'].set("")
    app['entries']['editorial'].set("")
    app['entries']['stock'].delete(0, tk.END)
    app['entries']['precio'].delete(0, tk.END)

# -- MAPEAR EVENTOS A LA ESTRUCTURA QUE REQUIERE LA INTERFAZ --
app['cmd_sincronizar_periodo'] = iniciar_sincronizacion_periodo
app['cmd_sync_clientes'] = lambda: disparar_script_externo("sync.py", "Formulario de clientes importado con éxito.")
app['cmd_import_catalogo'] = lambda: disparar_script_externo("import_catalogo.py", "Catálogo base de libros cargado masivamente.")
app['cmd_quitar_filtro'] = refrescar_inventario
app['cmd_limpiar_form'] = limpiar_formulario
app['cmd_asignar_libro'] = lambda: messagebox.showinfo("Info", "Lógica de asignación ejecutada")
app['cmd_filtrar_teclado'] = filtrar_clientes_dinamico
app['cmd_filtrar_inv_teclado'] = filtrar_inventario_dinamico
app['cmd_guardar_nuevo'] = guardar_nuevo_libro
app['cmd_modificar_sel'] = modificar_libro_seleccionado
app['cmd_eliminar_sel'] = eliminar_libro_seleccionado
app['cmd_eliminar_sel'] = eliminar_libro_seleccionado

# -- INICIALIZAR LA APLICACION --
conexion.realizar_respaldo_automatico()
root = tk.Tk()
interfaz.construir_interfaz(root, app)

# -- VINCULAR EVENTO DE SELECCION A LA TABLA INVENTARIO --
app['tabla_inventario'].bind("<<TreeviewSelect>>", al_seleccionar_libro)

refrescar_inventario()

# -- ESTABLECER RESPALDO AUTOMATICO AL CERRAR (CLOSE) --
root.protocol("WM_DELETE_WINDOW", lambda: [conexion.realizar_respaldo_automatico(etiqueta="CLOSE"), root.destroy()])
root.mainloop()