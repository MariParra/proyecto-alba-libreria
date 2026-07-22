import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import json
import os
import datetime
import subprocess
import conexion
import interfaz
import export
from ui_dialogos import manejar_edicion_celda, refrescar_inventario_global

MAPEO_MESES = {"Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04", "Mayo": "05", "Junio": "06", "Julio": "07", "Agosto": "08", "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"}

class AppControlador:
    def __init__(self, root):
        self.root = root
        self.widgets = {}
        self.datos_inventario_actual = []
        self.autocompletado_data = { 'autor': [], 'genero': [], 'editorial': [] }
        
        self.stock_min_var = tk.IntVar()
        self.stock_max_var = tk.IntVar()

        def validar_int(P): return P.isdigit() or P == ""
        def validar_float(P):
            if P == "" or P == ".": return True
            try: float(P); return True
            except ValueError: return False

        comandos_ui = {
            'cmd_sincronizar_periodo': self.iniciar_sincronizacion_periodo,
            'cmd_sync_clientes': self.sync_clientes,
            'cmd_import_catalogo': self.importar_catalogo,
            'cmd_exportar_excel': self.exportar_excel,
            'cmd_guardar_libro': self.guardar_libro,
            'cmd_limpiar_form_libro': self.limpiar_formulario_libro,
            'cmd_eliminar_libro': self.eliminar_libro,
            'cmd_aplicar_filtros': self.aplicar_filtros_inventario,
            'cmd_limpiar_filtros': self.limpiar_filtros_inventario,
            'cmd_ordenar_libros': self.ordenar_columna_inventario,
            'cmd_ordenar_asignaciones': self.ordenar_columna_asignaciones,
            'cmd_ordenar_gestion': self.ordenar_columna_gestion,
            'cmd_validar_int': validar_int,
            'cmd_validar_float': validar_float,
            'cmd_toggle_columnas': self.toggle_columnas_opcionales,
            'cmd_guardar_cliente': self.guardar_cliente,
            'cmd_limpiar_form_cliente': self.limpiar_formulario_cliente,
            'cmd_eliminar_cliente': self.eliminar_cliente,
            'cmd_aplicar_descuento': self.aplicar_descuento_masivo,
            'cmd_quitar_descuentos': self.quitar_descuentos,
            'cmd_actualizar_stock': self.actualizar_stock_masivo,
            'cmd_eliminar_asignacion': self.eliminar_asignacion_manual,
            'cmd_asignar_aleatorio': self.asignar_pendientes_aleatorio,
            'cmd_ver_historial': self.mostrar_librero_historico,
            'cmd_cerrar_mes': self.cerrar_mes_actual,
            'cmd_importar_historicos': self.importar_historicos_clientes,
            'cmd_v_add_libro': self.v_add_libro_al_carrito,
            'cmd_v_remove_libro': self.v_remove_libro_del_carrito,
            'cmd_v_guardar': self.v_guardar_venta,
            'cmd_v_limpiar': self.v_limpiar_formulario
        }

        refrescar_inventario_global.__globals__['refrescar_inventario_global'] = lambda: self.refrescar_inventario(widgets=self.widgets)
        interfaz.construir_interfaz(self.root, self.widgets, comandos_ui)
        
        mes_actual = list(MAPEO_MESES.keys())[datetime.datetime.now().month - 1]
        self.widgets['meses_vars'][mes_actual].set(True)
        self.widgets['cmb_ano'].set(str(datetime.datetime.now().year))
        
        # BINDS ASIGNACIONES
        self.widgets['cmb_ano'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_estado'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_pagado'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_envio'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_libro'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['tabla_clientes'].bind("<Double-1>", self.manejar_edicion_celda_asignacion)
        self.widgets['entry_busqueda_asignaciones'].bind("<KeyRelease>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['tabla_clientes'].bind("<Button-3>", lambda e: self.habilitar_copiar_celda(e, self.widgets['tabla_clientes']))
        
        # BINDS INVENTARIO
        self.widgets['tabla_libros'].bind("<<TreeviewSelect>>", self.al_seleccionar_libro)
        self.widgets['entry_busqueda_libros'].bind("<Return>", self.aplicar_filtros_inventario)
        self.widgets['tabla_libros'].bind("<Button-3>", lambda e: self.habilitar_copiar_celda(e, self.widgets['tabla_libros']))
        for campo in ['autor', 'genero', 'editorial']:
            key = f'list_filtro_{campo}'
            if key in self.widgets: self.widgets[key].bind("<<ListboxSelect>>", self.aplicar_filtros_inventario)

        if 'slider_stock_min' in self.widgets:
            self.widgets['slider_stock_min'].config(variable=self.stock_min_var)
            self.widgets['slider_stock_max'].config(variable=self.stock_max_var)
            self.widgets['slider_stock_min'].bind("<ButtonRelease-1>", self.aplicar_filtros_inventario)
            self.widgets['slider_stock_max'].bind("<ButtonRelease-1>", self.aplicar_filtros_inventario)
            self.stock_min_var.trace_add("write", self.actualizar_label_stock)
            self.stock_max_var.trace_add("write", self.actualizar_label_stock)
        
        # BINDS GESTION CLIENTES
        self.widgets['tabla_gestion_clientes'].bind("<<TreeviewSelect>>", self.al_seleccionar_cliente)
        self.widgets['entry_busqueda_clientes'].bind("<KeyRelease>", self.buscar_cliente_gestion)
        self.widgets['tabla_gestion_clientes'].bind("<Button-3>", lambda e: self.habilitar_copiar_celda(e, self.widgets['tabla_gestion_clientes']))

        # --- BINDS PARA LA PESTAÑA DE VENTAS ---
        self.widgets['cmb_v_cliente'].bind('<KeyRelease>', self.v_autocompletar_cliente)
        self.widgets['cmb_v_libros'].bind('<KeyRelease>', self.v_autocompletar_libro)
        self.widgets['entry_v_costo_envio'].bind('<KeyRelease>', self.v_actualizar_totales)
        self.widgets['cmb_v_envio'].bind('<<ComboboxSelected>>', self.v_on_select_envio)
        
        self.refrescar_todas_las_tablas()
        self.configurar_eventos_autocompletado()
        self.configurar_slider_stock()
        self.v_iniciar_tab() 

    # ==========================================
    # LÓGICA DE AUTOCOMPLETADO
    # ==========================================
    def refrescar_listas_autocompletado(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            for campo in self.autocompletado_data.keys():
                cursor.execute(f"SELECT DISTINCT {campo} FROM libros WHERE {campo} IS NOT NULL AND {campo} != '' AND {campo} != 'SIN INFORMACION' ORDER BY {campo}")
                valores = [str(row[0]) for row in cursor.fetchall()]
                self.autocompletado_data[campo] = valores
                
                if campo in self.widgets['form_libro_entries']:
                    current_value = self.widgets['form_libro_entries'][campo].get()
                    self.widgets['form_libro_entries'][campo]['values'] = valores
                    if current_value in valores:
                        self.widgets['form_libro_entries'][campo].set(current_value)

                lst_filtro = self.widgets.get(f'list_filtro_{campo}')
                if lst_filtro:
                    seleccionados = [lst_filtro.get(i) for i in lst_filtro.curselection()]
                    lst_filtro.delete(0, tk.END)
                    for val in valores:
                        lst_filtro.insert(tk.END, val)
                        if val in seleccionados: lst_filtro.selection_set(lst_filtro.size()-1)

            conn.close()
        except Exception as e:
            print(f"Error cargando listas de autocompletado: {e}")

    def configurar_eventos_autocompletado(self):
        for campo in self.autocompletado_data.keys():
            if campo in self.widgets['form_libro_entries']:
                combobox = self.widgets['form_libro_entries'][campo]
                combobox.bind('<KeyRelease>', lambda event, c=campo: self.on_keyrelease_autocompletar(event, c))

    def on_keyrelease_autocompletar(self, event, campo_actual):
        widget = event.widget
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab', 'Shift_L', 'Shift_R', 'Escape', 'Control_L', 'Alt_L'): return
        valor_escrito = widget.get()
        lista_completa = self.autocompletado_data[campo_actual]
        if valor_escrito == '': widget['values'] = lista_completa
        else:
            data = [item for item in lista_completa if valor_escrito.lower() in item.lower()]
            widget['values'] = data

    # ==========================================
    # LÓGICA DE INVENTARIO Y DESCUENTOS
    # ==========================================
    def configurar_slider_stock(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(stock) FROM libros")
            max_stock = cursor.fetchone()[0]
            conn.close()
            
            if max_stock is None: max_stock = 100
            
            if 'slider_stock_max' in self.widgets:
                self.widgets['slider_stock_min'].config(to=max_stock)
                self.widgets['slider_stock_max'].config(to=max_stock)
                self.stock_min_var.set(0)
                self.stock_max_var.set(max_stock)
        except Exception as e: print(f"Error al configurar los sliders de stock: {e}")

    def actualizar_label_stock(self, *args):
        if 'lbl_filtro_stock_min' in self.widgets:
            self.widgets['lbl_filtro_stock_min'].config(text=f"Stock Min: {self.stock_min_var.get()}")
            self.widgets['lbl_filtro_stock_max'].config(text=f"Stock Max: {self.stock_max_var.get()}")
    
    def aplicar_filtros_inventario(self, event=None):
        termino_busqueda = self.widgets['entry_busqueda_libros'].get().strip()
        stock_min = self.stock_min_var.get()
        stock_max = self.stock_max_var.get()
        if stock_min > stock_max: stock_min, stock_max = stock_max, stock_min

        query = "SELECT libro_id, titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original FROM libros"
        condiciones = []
        params = []

        if termino_busqueda:
            condiciones.append("(titulo LIKE ? OR autor LIKE ?)")
            params.extend([f"%{termino_busqueda}%", f"%{termino_busqueda}%"])

        for campo in ['autor', 'genero', 'editorial']:
            lst_filtro = self.widgets.get(f'list_filtro_{campo}')
            if lst_filtro:
                seleccionados = [lst_filtro.get(i) for i in lst_filtro.curselection()]
                if seleccionados:
                    placeholders = ', '.join(['?'] * len(seleccionados))
                    condiciones.append(f"{campo} IN ({placeholders})")
                    params.extend(seleccionados)

        condiciones.append("stock >= ? AND stock <= ?")
        params.extend([stock_min, stock_max])
        
        if condiciones: query += " WHERE " + " AND ".join(condiciones)
        query += " ORDER BY titulo"
        self.refrescar_inventario(query=query, params=tuple(params))

    def limpiar_filtros_inventario(self, event=None):
        self.widgets['entry_busqueda_libros'].delete(0, tk.END)
        for campo in ['autor', 'genero', 'editorial']:
            lst = self.widgets.get(f'list_filtro_{campo}')
            if lst: lst.selection_clear(0, tk.END)
        
        if 'slider_stock_max' in self.widgets:
            max_val = self.widgets['slider_stock_max'].cget("to")
            self.stock_min_var.set(0)
            self.stock_max_var.set(int(float(max_val)))
            
        self.aplicar_filtros_inventario()

    def refrescar_inventario(self, widgets=None, query="SELECT libro_id, titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original FROM libros ORDER BY titulo", params=()):
        if widgets is None: widgets = self.widgets
        if 'tabla_libros' not in widgets: return
        tabla = widgets['tabla_libros']
        for item in tabla.get_children(): tabla.delete(item)
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute(query, params)
            self.datos_inventario_actual = cursor.fetchall()
            conn.close()
            for fila in self.datos_inventario_actual: tabla.insert("", "end", values=fila)

            stock_total = sum(int(fila[6]) for fila in self.datos_inventario_actual if fila[6])
            widgets['lbl_stock_total'].config(text=f"Unidades Totales en Inventario: {stock_total}")
            self.refrescar_listas_autocompletado()
        except Exception as e: print(f"Error al cargar inventario: {e}")

    def al_seleccionar_libro(self, event=None):
        tabla = self.widgets['tabla_libros']
        seleccion = tabla.selection()
        if not seleccion: return
        item_id = seleccion[0]
        libro_id = tabla.set(item_id, "libro_id")
        self.widgets['lbl_status_libro'].config(text=f"Modo: Editando libro ID {libro_id}", fg="#0277BD")
        entries = self.widgets['form_libro_entries']
        
        for col_id, entry in entries.items():
            valor = tabla.set(item_id, col_id)
            if isinstance(entry, ttk.Combobox): entry.set(valor if valor else "")
            elif isinstance(entry, tk.Entry):
                entry.config(validate="none") 
                entry.delete(0, tk.END)
                entry.insert(0, valor if valor else "")
                entry.config(validate="key") 

    def limpiar_formulario_libro(self):
        self.widgets['lbl_status_libro'].config(text="Modo: Creando nuevo libro", fg="#C2185B")
        for entry in self.widgets['form_libro_entries'].values():
            if isinstance(entry, ttk.Combobox): entry.set("")
            elif isinstance(entry, tk.Entry):
                entry.config(validate="none")
                entry.delete(0, tk.END)
                entry.config(validate="key")
        self.widgets['form_libro_entries']['encuadernacion'].set('TAPA BLANDA')
        tabla = self.widgets['tabla_libros']
        if tabla.selection(): tabla.selection_remove(tabla.selection()[0])

    def guardar_libro(self):
        entries = self.widgets['form_libro_entries']
        datos = {col_id: entry.get().strip().upper() for col_id, entry in entries.items()}
        if not datos['titulo'] or not datos['stock']:
            messagebox.showwarning("Campos Vacíos", "El Título y el Stock son obligatorios.")
            return
            
        libro_id = None
        seleccion = self.widgets['tabla_libros'].selection()
        if seleccion: libro_id = self.widgets['tabla_libros'].set(seleccion[0], "libro_id")
        
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            precio_base = float(datos['precio_original'] if datos['precio_original'] else 0)
            
            if libro_id:
                cursor.execute("""
                    UPDATE libros SET titulo=?, autor=?, genero=?, editorial=?, encuadernacion=?, stock=?, precio=?, precio_original=? 
                    WHERE libro_id=?
                """, (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], datos['encuadernacion'], 
                      int(datos['stock']), precio_base, precio_base, libro_id))
            else:
                cursor.execute("""
                    INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], datos['encuadernacion'],
                      int(datos['stock']), precio_base, precio_base))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", "Libro guardado correctamente.")
            self.limpiar_formulario_libro()
            self.configurar_slider_stock() 
            self.aplicar_filtros_inventario()
        except Exception as e: messagebox.showerror("Error BD", str(e))

    def eliminar_libro(self):
        seleccion = self.widgets['tabla_libros'].selection()
        if not seleccion: return messagebox.showwarning("Atención", "Seleccione un libro para eliminar.")
        libro_id = self.widgets['tabla_libros'].set(seleccion[0], "libro_id")
        titulo = self.widgets['tabla_libros'].set(seleccion[0], "titulo")
        if not messagebox.askyesno("Confirmar", f"¿Eliminar '{titulo}'?"): return
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM libros WHERE libro_id=?", (libro_id,))
            conn.commit()
            conn.close()
            self.limpiar_formulario_libro()
            self.configurar_slider_stock()
            self.aplicar_filtros_inventario()
        except Exception as e: messagebox.showerror("Error BD", str(e))

    def ordenar_columna_inventario(self, col, reverse):
        if 'tabla_libros' not in self.widgets: return
        tabla = self.widgets['tabla_libros']
        lista_valores = [(tabla.set(k, col), k) for k in tabla.get_children('')]
        
        for c in tabla['columns']:
            texto_original = c.replace("_", " ").title()
            tabla.heading(c, text=texto_original, command=lambda _col=c: self.ordenar_columna_inventario(_col, False))
            
        try: lista_valores.sort(key=lambda t: float(t[0]) if t[0] else 0.0, reverse=reverse)
        except ValueError: lista_valores.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        for index, (val, k) in enumerate(lista_valores): tabla.move(k, '', index)

        texto_heading = col.replace("_", " ").title()
        flecha = "  ▼" if reverse else "  ▲"
        tabla.heading(col, text=texto_heading + flecha, command=lambda _col=col: self.ordenar_columna_inventario(_col, not reverse))

    def aplicar_descuento_masivo(self):
        porcentaje_str = simpledialog.askstring("Descuento Masivo", "Introduce el porcentaje de descuento a aplicar (ej: 15 para 15%):", parent=self.root)
        if not porcentaje_str: return
        
        try:
            porcentaje = float(porcentaje_str)
            if not (0 < porcentaje < 100): raise ValueError("El porcentaje debe estar entre 0 y 100.")
            multiplicador = 1 - (porcentaje / 100)
        except (ValueError, TypeError):
            messagebox.showerror("Valor Inválido", "Por favor, introduce un número válido para el porcentaje (ej: 15 o 15.5).")
            return

        respuesta = messagebox.askquestion("Aplicar Descuento",
                                             f"¿Quieres aplicar el {porcentaje}% de descuento a los libros actualmente filtrados en la tabla?\n\n"
                                             " - 'Sí' para aplicar solo a los filtrados.\n"
                                             " - 'No' para aplicar a TODOS los libros del inventario.",
                                             icon='question')

        ids_a_actualizar = []
        if respuesta == 'yes':
            tabla = self.widgets['tabla_libros']
            for item_id in tabla.get_children(): ids_a_actualizar.append(tabla.set(item_id, "libro_id"))
            if not ids_a_actualizar: return messagebox.showinfo("Sin Libros", "No hay libros en la tabla para aplicar el descuento.")
        
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            query = "UPDATE libros SET precio = ROUND(precio_original * ?, 2)"
            params = [multiplicador]
            
            if respuesta == 'yes':
                placeholders = ', '.join('?' for _ in ids_a_actualizar)
                query += f" WHERE libro_id IN ({placeholders})"
                params.extend(ids_a_actualizar)
            
            cursor.execute(query, tuple(params))
            libros_afectados = cursor.rowcount
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", f"Se aplicó un {porcentaje}% de descuento a {libros_afectados} libros.")
            self.aplicar_filtros_inventario()
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudo aplicar el descuento: {e}")

    def quitar_descuentos(self):
        respuesta = messagebox.askquestion("Quitar Descuentos",
                                            "¿Quieres quitar el descuento a los libros actualmente filtrados en la tabla?\n\n"
                                            " - 'Sí' para restaurar precio original solo a los filtrados.\n"
                                            " - 'No' para quitar el descuento a TODOS los libros.",
                                            icon='warning')

        ids_a_actualizar = []
        if respuesta == 'yes':
            tabla = self.widgets['tabla_libros']
            for item_id in tabla.get_children(): ids_a_actualizar.append(tabla.set(item_id, "libro_id"))
            if not ids_a_actualizar: return messagebox.showinfo("Sin Libros", "No hay libros en la tabla para restaurar el precio.")
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            query = "UPDATE libros SET precio = precio_original"
            params = []
            
            if respuesta == 'yes':
                placeholders = ', '.join('?' for _ in ids_a_actualizar)
                query += f" WHERE libro_id IN ({placeholders})"
                params.extend(ids_a_actualizar)
            
            cursor.execute(query, tuple(params))
            libros_afectados = cursor.rowcount
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", f"Se ha restaurado el precio original a {libros_afectados} libros.")
            self.aplicar_filtros_inventario()
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudieron quitar los descuentos: {e}")


    # ==========================================
    # LÓGICA DE LA PESTAÑA GESTIÓN CLIENTES
    # ==========================================
    def refrescar_tabla_clientes_gestion(self, termino_busqueda=None):
        if 'tabla_gestion_clientes' not in self.widgets: return
        tabla = self.widgets['tabla_gestion_clientes']
        for item in tabla.get_children(): tabla.delete(item)
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            # SE AÑADIÓ RUT Y DIRECCION
            query = "SELECT cliente_id, nombre, email, telefono, rut, direccion, status FROM clientes"
            params = []
            if termino_busqueda:
                query += " WHERE nombre LIKE ? OR email LIKE ? OR telefono LIKE ? OR rut LIKE ?"
                params.extend([f"%{termino_busqueda}%"] * 4)
            query += " ORDER BY nombre"
            cursor.execute(query, tuple(params))
            for cliente in cursor.fetchall(): tabla.insert("", "end", values=cliente)
            conn.close()
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudo cargar la lista de clientes: {e}")

    def buscar_cliente_gestion(self, event=None):
        termino = self.widgets['entry_busqueda_clientes'].get().strip()
        self.refrescar_tabla_clientes_gestion(termino)

    def ordenar_columna_gestion(self, col, reverse):
        if 'tabla_gestion_clientes' not in self.widgets: return
        tabla = self.widgets['tabla_gestion_clientes']
        lista_valores = [(tabla.set(k, col), k) for k in tabla.get_children('')]
        
        for c in tabla['columns']:
            texto_original = c.replace("_", " ").title()
            tabla.heading(c, text=texto_original, command=lambda _col=c: self.ordenar_columna_gestion(_col, False))
            
        try: lista_valores.sort(key=lambda t: float(t[0]) if t[0] else 0.0, reverse=reverse)
        except ValueError: lista_valores.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        for index, (val, k) in enumerate(lista_valores): tabla.move(k, '', index)

        texto_heading = col.replace("_", " ").title()
        flecha = "  ▼" if reverse else "  ▲"
        tabla.heading(col, text=texto_heading + flecha, command=lambda _col=col: self.ordenar_columna_gestion(_col, not reverse))

    def al_seleccionar_cliente(self, event=None):
        if 'tabla_gestion_clientes' not in self.widgets: return
        tabla = self.widgets['tabla_gestion_clientes']
        seleccion = tabla.selection()
        if not seleccion: return
        
        cliente_id = tabla.set(seleccion[0], "cliente_id")
        self.widgets['lbl_status_cliente'].config(text=f"Modo: Editando Cliente ID {cliente_id}", fg="#0277BD")
        
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, email, telefono, direccion, rut, instagram, status FROM clientes WHERE cliente_id = ?", (cliente_id,))
            datos_cliente = cursor.fetchone()
            conn.close()

            if datos_cliente:
                campos = ['nombre', 'email', 'telefono', 'direccion', 'rut', 'instagram', 'status']
                for i, campo_id in enumerate(campos):
                    widget = self.widgets['form_cliente_entries'][campo_id]
                    valor = datos_cliente[i] if datos_cliente[i] else ""
                    if isinstance(widget, ttk.Combobox): widget.set(valor)
                    else:
                        widget.delete(0, tk.END)
                        widget.insert(0, valor)
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudieron cargar los datos del cliente: {e}")

    def limpiar_formulario_cliente(self):
        self.widgets['lbl_status_cliente'].config(text="Seleccione un cliente para editar", fg="#0277BD")
        for widget in self.widgets['form_cliente_entries'].values():
            if isinstance(widget, ttk.Combobox): widget.set('')
            else: widget.delete(0, tk.END)
        tabla = self.widgets['tabla_gestion_clientes']
        if tabla.selection(): tabla.selection_remove(tabla.selection()[0])

    def guardar_cliente(self):
        if 'tabla_gestion_clientes' not in self.widgets: return
        tabla = self.widgets['tabla_gestion_clientes']
        seleccion = tabla.selection()
        if not seleccion: return messagebox.showwarning("Sin Selección", "Por favor, seleccione un cliente de la lista para guardar.")

        cliente_id = tabla.set(seleccion[0], "cliente_id")
        datos_nuevos = {campo: widget.get().strip() for campo, widget in self.widgets['form_cliente_entries'].items()}
        if not datos_nuevos['nombre']: return messagebox.showwarning("Campo Obligatorio", "El nombre del cliente no puede estar vacío.")
            
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE clientes SET nombre = ?, email = ?, telefono = ?, direccion = ?, rut = ?, instagram = ?, status = ? WHERE cliente_id = ?
            """, (datos_nuevos['nombre'], datos_nuevos['email'], datos_nuevos['telefono'], datos_nuevos['direccion'], datos_nuevos['rut'], datos_nuevos['instagram'], datos_nuevos['status'], cliente_id))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", "Los datos del cliente se han actualizado correctamente.")
            self.refrescar_tabla_clientes_gestion()
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudo guardar al cliente: {e}")

    def eliminar_cliente(self):
        if 'tabla_gestion_clientes' not in self.widgets: return
        tabla = self.widgets['tabla_gestion_clientes']
        seleccion = tabla.selection()
        if not seleccion: return messagebox.showwarning("Atención", "Seleccione un cliente de la lista para eliminar.")

        cliente_id = tabla.set(seleccion[0], "cliente_id")
        nombre = tabla.set(seleccion[0], "nombre")
        if not messagebox.askyesno("Confirmar Eliminación", f"¿Está seguro de eliminar al cliente '{nombre}'?\n\nADVERTENCIA: Esto eliminará de forma permanente sus suscripciones y todas sus asignaciones de libros históricas."): return

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("DELETE FROM asignaciones WHERE cliente_id = ?", (cliente_id,))
            cursor.execute("DELETE FROM suscripciones WHERE cliente_id = ?", (cliente_id,))
            cursor.execute("DELETE FROM clientes WHERE cliente_id = ?", (cliente_id,))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", f"El cliente '{nombre}' ha sido eliminado.")
            self.limpiar_formulario_cliente()
            self.refrescar_todas_las_tablas() 
        except Exception as e: messagebox.showerror("Error BD", f"No se pudo eliminar al cliente: {e}")

    # ==========================================
    # ASIGNACIONES, SINCRONIZACIÓN Y EXPORTACIÓN
    # ==========================================
    def toggle_columnas_opcionales(self):
        columnas_base = ["asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario"]
        opcionales_visibles = []
        if self.widgets['vars_opcionales']['rut'].get(): opcionales_visibles.append("rut")
        if self.widgets['vars_opcionales']['email'].get(): opcionales_visibles.append("email")
        if self.widgets['vars_opcionales']['telefono'].get(): opcionales_visibles.append("telefono")
        if self.widgets['vars_opcionales']['direccion'].get(): opcionales_visibles.append("direccion")
        self.widgets['tabla_clientes']['displaycolumns'] = columnas_base + opcionales_visibles

    def manejar_edicion_celda_asignacion(self, event):
        item_id = self.widgets['tabla_clientes'].focus()
        if not item_id: return
        
        columna_num_str = self.widgets['tabla_clientes'].identify_column(event.x)
        if not columna_num_str: return
        
        col_index = int(columna_num_str.replace('#', ''))
        col_name = self.widgets['tabla_clientes']['columns'][col_index - 1]

        # 1. Si es la columna LIBRO, abre el diálogo inteligente de asignación
        if col_name == 'libro':
            from ui_dialogos import abrir_dialogo_asignar_libro 
            abrir_dialogo_asignar_libro(self.root, self.widgets['tabla_clientes'], item_id, 
                                        self.iniciar_sincronizacion_periodo, self.refrescar_inventario)
                                        
        # 2. Si es la columna EXTRAS, abre la ventana de gestión de extras
        elif col_name == 'extras':
            from ui_dialogos import abrir_dialogo_extras
            abrir_dialogo_extras(self.root, self.widgets['tabla_clientes'], item_id, self.iniciar_sincronizacion_periodo)
            
        # 3. Si es CUALQUIER OTRA COLUMNA (estado, pagado, envio_pag, comentario)
        else:
            from ui_dialogos import manejar_edicion_celda
            manejar_edicion_celda(event, self.root, self.widgets, self.iniciar_sincronizacion_periodo)



    def ordenar_columna(self, tabla, col, reverse):
        lista_valores = [(tabla.set(k, col), k) for k in tabla.get_children('')]
        
        for c in tabla['columns']:
            titulo_col = c.replace("_", " ").title()
            if c == "tipo_envio": titulo_col = "Tipo De Envio"
            if c == "envio_pag": titulo_col = "Envio Pagado"
            if c == "ano": titulo_col = "Año" 
            # Restauramos el comando base sin flecha
            tabla.heading(c, text=titulo_col, command=lambda _col=c: self.ordenar_columna(tabla, _col, False))
            
        try: 
            # Intentar ordenar como números
            lista_valores.sort(key=lambda t: float(t[0]) if t[0] and t[0] != 'None' else 0.0, reverse=reverse)
        except ValueError: 
            # Si falla, ordenar como texto
            lista_valores.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        for index, (val, k) in enumerate(lista_valores): 
            tabla.move(k, '', index)

        titulo_col = col.replace("_", " ").title()
        if col == "ano": titulo_col = "Año" 
        if col == "tipo_envio": titulo_col = "Tipo De Envio"
        if col == "envio_pag": titulo_col = "Envio Pagado"
        flecha = "  ▼" if reverse else "  ▲"
        tabla.heading(col, text=titulo_col + flecha, command=lambda _col=col: self.ordenar_columna(tabla, _col, not reverse))
        
    def refrescar_todas_las_tablas(self):
        self.iniciar_sincronizacion_periodo()
        self.refrescar_inventario()
        self.refrescar_tabla_clientes_gestion()
        self.v_iniciar_tab()
        
    def ordenar_columna_asignaciones(self, col, reverse):
        self.ordenar_columna(self.widgets['tabla_clientes'], col, reverse)

    def ordenar_columna_gestion(self, col, reverse):
        self.ordenar_columna(self.widgets['tabla_gestion_clientes'], col, reverse)
        
    def iniciar_sincronizacion_periodo(self, event=None):
        meses_seleccionados = [m for m, var in self.widgets['meses_vars'].items() if var.get()]
        if not meses_seleccionados: self.widgets['mb_meses'].config(text="Ninguno")
        elif len(meses_seleccionados) == 1: self.widgets['mb_meses'].config(text=meses_seleccionados[0])
        elif len(meses_seleccionados) == 12: self.widgets['mb_meses'].config(text="Todos")
        else: self.widgets['mb_meses'].config(text=f"{len(meses_seleccionados)} selecc.")
        
        tabla = self.widgets['tabla_clientes']
        for item in tabla.get_children(): tabla.delete(item)
        ano_str = self.widgets['cmb_ano'].get()
        if not meses_seleccionados or not ano_str: return
        
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            # --- LÓGICA DE PROTECCIÓN DE MESES ---
            from datetime import datetime
            ano_actual = datetime.now().year
            mes_actual = datetime.now().month
            meses_nums = [MAPEO_MESES[m] for m in meses_seleccionados]
            
            # La "Magia" de auto-creación/limpieza solo se ejecuta si se selecciona UN solo mes
            if len(meses_nums) == 1:
                mes_num = meses_nums[0]
                ano_seleccionado = int(ano_str)
                mes_seleccionado = int(mes_num)
                
                # Verificamos si el mes es pasado
                periodo_es_pasado = ano_seleccionado < ano_actual or (ano_seleccionado == ano_actual and mes_seleccionado < mes_actual)
                
                # Verificamos si el mes está cerrado manualmente
                cursor.execute("SELECT 1 FROM meses_cerrados WHERE ano = ? AND mes = ?", (ano_str, mes_num))
                mes_cerrado_explicitamente = cursor.fetchone() is not None

                # Si el período NO es pasado Y NO está cerrado, se ejecuta la magia
                if not periodo_es_pasado and not mes_cerrado_explicitamente:
                    # 1. Limpieza de Inactivos
                    cursor.execute("""
                        DELETE FROM asignaciones WHERE ano = ? AND mes = ? AND estado_envio = 'EN PREPARACION' 
                        AND libro_suscripcion_id IS NULL AND cliente_id IN (SELECT cliente_id FROM clientes WHERE status = 'INACTIVA')
                    """, (ano_str, mes_num))

                    # 2. Creación de Nuevas Asignaciones
                    cursor.execute("""
                        INSERT OR IGNORE INTO asignaciones (cliente_id, ano, mes, estado_envio, pagado, envio_pagado, comentario)
                        SELECT c.cliente_id, ?, ?, 'EN PREPARACION', 'FALSE', 'FALSE', 'Sin comentario'
                        FROM clientes c
                        WHERE c.status = 'ACTIVA'
                    """, (ano_str, mes_num))
                    conn.commit()

            # --- BLOQUE PARA MOSTRAR DATOS (SIEMPRE SE EJECUTA) ---
            cursor.execute("PRAGMA table_info(clientes)")
            columnas_clientes = [col[1].lower() for col in cursor.fetchall()]
            
            mapa_opcionales = {'rut': 'rut', 'email': 'email', 'telefono': 'telefono', 'direccion': 'direccion'}
            if 'correo' in columnas_clientes and 'email' not in columnas_clientes: mapa_opcionales['email'] = 'correo'
            if 'correo_electronico' in columnas_clientes and 'email' not in columnas_clientes: mapa_opcionales['email'] = 'correo_electronico'
            
            select_extras = [f"c.{mapa_opcionales.get(key, '')}" if mapa_opcionales.get(key) in columnas_clientes else "''" for key in ['rut', 'email', 'telefono', 'direccion']]
            str_extras = ", " + ", ".join(select_extras)
            
            placeholders_meses = ",".join("?" * len(meses_nums))
            
            query = f"""
                SELECT a.asignacion_id, c.cliente_id, c.nombre, a.ano, a.mes, l.titulo, 
                    a.extras, s.metodo_entrega, a.fecha_asignacion, a.estado_envio, a.pagado, a.envio_pagado, a.comentario {str_extras}
                FROM asignaciones a
                JOIN clientes c ON a.cliente_id = c.cliente_id
                JOIN suscripciones s ON c.cliente_id = s.cliente_id
                LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
                WHERE a.ano = ? AND a.mes IN ({placeholders_meses})
            """
            params = [ano_str] + meses_nums

            # ... (El resto de la lógica de filtros y búsqueda no cambia) ...
            filtro_estado = self.widgets['cmb_filtro_estado'].get()
            if filtro_estado != "TODOS":
                query += " AND a.estado_envio = ?"
                params.append(filtro_estado)
            # ... (etc. para los otros filtros) ...

            termino_busqueda = self.widgets.get('entry_busqueda_asignaciones')
            if termino_busqueda and termino_busqueda.get().strip():
                termino_val = termino_busqueda.get().strip()
                query += " AND (c.nombre LIKE ? OR c.email LIKE ? OR c.rut LIKE ?)"
                params.extend([f"%{termino_val}%"] * 3)
            
            query += " ORDER BY c.nombre"
            cursor.execute(query, params)
            
            for f in cursor.fetchall():
                fila_formateada = list(f)
                fila_formateada[5] = fila_formateada[5] if fila_formateada[5] else "SIN ASIGNACIÓN"
                fila_formateada[6] = fila_formateada[6] if fila_formateada[6] else ""
                fila_formateada[10] = "Si" if str(fila_formateada[10]).upper() == "TRUE" else "No"
                fila_formateada[11] = "Si" if str(fila_formateada[11]).upper() == "TRUE" else "No"
                
                tabla.insert("", "end", values=tuple(fila_formateada))

        except Exception as e:
            messagebox.showerror("Error BD", f"Error al cargar asignaciones: {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()



    def exportar_excel(self):
        try:
            self.root.config(cursor="watch"); self.root.update()
            ruta = export.exportar_a_excel()
            self.root.config(cursor="")
            messagebox.showinfo("Éxito", f"Excel generado en:\n{ruta}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error", str(e))

    def disparar_script_externo(self, script_name, mensaje_exito):
        try:
            self.root.config(cursor="watch"); self.root.update()
            current_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(current_dir, script_name)
            if not os.path.exists(script_path): raise FileNotFoundError(f"No se encontró el script en: {script_path}")
            resultado = subprocess.run(["python", script_path], capture_output=True, text=True, check=True, errors='ignore')
            self.root.config(cursor="")
            output_str = resultado.stdout
            try:
                json_part = output_str[output_str.find('{'):]
                reporte = json.loads(json_part)
                mensaje = f"{mensaje_exito}\n"
                if "libros_procesados" in reporte:
                    mensaje += (f"\nLibros Procesados: {reporte.get('libros_procesados', 0)}"
                                f"\nNuevos: {reporte.get('nuevos_libros', 0)}"
                                f"\nActualizados: {reporte.get('libros_actualizados', 0)}")
                if reporte.get("error"): messagebox.showerror("Error en Script", reporte["error"])
                else: messagebox.showinfo("Completado", mensaje)
            except (json.JSONDecodeError, IndexError):
                messagebox.showinfo("Completado", f"{mensaje_exito}\n(No se encontró un reporte JSON detallado)")
            self.refrescar_todas_las_tablas()
        except FileNotFoundError as e:
            self.root.config(cursor="")
            messagebox.showerror("Error de Archivo", str(e))
        except subprocess.CalledProcessError as e:
            self.root.config(cursor="")
            messagebox.showerror("Error de Ejecución", f"Fallo al ejecutar '{script_name}':\n{e.stderr}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error", f"Error inesperado al ejecutar '{script_name}':\n{e}")

    def sync_clientes(self): self.disparar_script_externo("sync.py", "Sincronización de clientes completada.")
    def importar_catalogo(self): self.disparar_script_externo("import_catalogo.py", "Importación de catálogo completada.")
    
    def actualizar_stock_masivo(self):
        """Llama al script para actualizar stock y precios desde un CSV."""
        if messagebox.askokcancel("Actualizar Stock", "Asegúrate de haber guardado tu archivo Excel como 'stock_precios.csv' dentro de la carpeta '1_input_data'.\n\nEl archivo debe tener las columnas: titulo, stock, precio.\n\n¿Deseas continuar?"):
            self.disparar_script_externo("actualizar_stock.py", "Proceso completado.\nSi hubo libros no encontrados, revisa el archivo 'libros_no_encontrados_stock.txt' en la carpeta 1_input_data.\n\n(La métrica 'Nuevos' de abajo indica los libros omitidos)")
    
    def eliminar_asignacion_manual(self):
        """
        Elimina una fila de asignación completa de la base de datos.
        Si había un libro asignado, lo devuelve al stock.
        """
        tabla = self.widgets['tabla_clientes']
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showwarning("Sin Selección", "Por favor, selecciona una fila de asignación de la tabla para eliminar.")
            return

        item_id = seleccion[0]
        asignacion_id = tabla.set(item_id, "asignacion_id")
        nombre_cliente = tabla.set(item_id, "nombre")
        mes = tabla.set(item_id, "mes")
        ano = tabla.set(item_id, "ano")

        if not messagebox.askyesno("Confirmar Eliminación", 
                                f"¿Estás seguro de que quieres eliminar la asignación de {nombre_cliente} para el período {mes}/{ano}?\n\n"
                                "Esta acción no se puede deshacer. Si había un libro asignado, será devuelto al inventario."):
            return

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()

            # 1. Verificar si hay un libro asignado para devolverlo al stock
            cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
            resultado = cursor.fetchone()
            if resultado and resultado[0]:
                libro_id_a_devolver = resultado[0]
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = ?", (libro_id_a_devolver,))
                print(f"Devolviendo libro ID {libro_id_a_devolver} al stock.")

            # 2. Eliminar la fila de asignación
            cursor.execute("DELETE FROM asignaciones WHERE asignacion_id = ?", (asignacion_id,))
            
            conn.commit()
            conn.close()

            messagebox.showinfo("Éxito", f"La asignación para {nombre_cliente} ({mes}/{ano}) ha sido eliminada.")
            
            # Refrescar la vista para que la fila desaparezca
            self.iniciar_sincronizacion_periodo()

        except Exception as e:
            messagebox.showerror("Error de BD", f"No se pudo eliminar la asignación: {e}")

    def asignar_pendientes_aleatorio(self):
        """
        Asigna libros de forma aleatoria a todas las clientas del período
        seleccionado que estén sin asignación, respetando gustos y stock.
        """
        meses_seleccionados = [m for m, var in self.widgets['meses_vars'].items() if var.get()]
        ano_str = self.widgets['cmb_ano'].get()

        if not meses_seleccionados or not ano_str:
            messagebox.showwarning("Sin Período", "Por favor, selecciona al menos un mes y un año para la asignación.")
            return

        if not messagebox.askyesno("Confirmar Asignación Automática", 
                                f"Se intentará asignar un libro a todas las clientas sin asignación para los meses seleccionados del {ano_str}.\n\n"
                                "El proceso respetará los géneros preferidos y el stock disponible.\n\n¿Deseas continuar?"):
            return

        libros_asignados_count = 0
        clientes_pendientes_count = 0
        
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            # Iniciar una transacción para asegurar que todo se guarde o nada
            cursor.execute("BEGIN TRANSACTION")

            meses_nums = [MAPEO_MESES[m] for m in meses_seleccionados]
            placeholders_meses = ",".join("?" * len(meses_nums))

            # 1. Obtener todas las asignaciones pendientes del período
            query_pendientes = f"""
                SELECT a.asignacion_id, s.cliente_id, s.generos_preferencia
                FROM asignaciones a
                JOIN suscripciones s ON a.cliente_id = s.cliente_id
                WHERE a.ano = ? AND a.mes IN ({placeholders_meses}) AND a.libro_suscripcion_id IS NULL
            """
            params_pendientes = [ano_str] + meses_nums
            cursor.execute(query_pendientes, params_pendientes)
            asignaciones_pendientes = cursor.fetchall()

            if not asignaciones_pendientes:
                messagebox.showinfo("Nada que Asignar", "No se encontraron clientas pendientes de asignación en el período seleccionado.")
                conn.close()
                return

            # 2. Obtener todos los libros con stock
            cursor.execute("SELECT libro_id, genero FROM libros WHERE stock > 0")
            libros_con_stock = cursor.fetchall()
            
            import random

            # 3. Iterar sobre cada clienta pendiente
            for asignacion_id, cliente_id, generos_str in asignaciones_pendientes:
                generos_preferidos = [g.strip().upper() for g in (generos_str or "").split(',') if g.strip()]
                
                # Filtrar libros que coincidan con los gustos de la clienta
                libros_candidatos = []
                if generos_preferidos:
                    for libro_id, genero_libro in libros_con_stock:
                        gen_upper = str(genero_libro).strip().upper()
                        if any(pref in gen_upper or gen_upper in pref for pref in generos_preferidos):
                            libros_candidatos.append(libro_id)
                
                # Si no tiene gustos definidos o no hay coincidencias, usar cualquier libro con stock
                if not libros_candidatos:
                    libros_candidatos = [libro_id for libro_id, _ in libros_con_stock]

                if libros_candidatos:
                    # Elegir un libro al azar y asignarlo
                    libro_elegido_id = random.choice(libros_candidatos)
                    
                    cursor.execute("UPDATE asignaciones SET libro_suscripcion_id = ? WHERE asignacion_id = ?", (libro_elegido_id, asignacion_id))
                    cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = ?", (libro_elegido_id,))
                    
                    # Quitar el libro elegido de la lista de disponibles para no reasignarlo
                    libros_con_stock = [libro for libro in libros_con_stock if libro[0] != libro_elegido_id]
                    libros_asignados_count += 1
                else:
                    clientes_pendientes_count += 1
            
            conn.commit()
            messagebox.showinfo("Proceso Completado", 
                                f"Asignación automática finalizada.\n\n"
                                f"Libros asignados con éxito: {libros_asignados_count}\n"
                                f"Clientas que quedaron pendientes (sin stock compatible): {clientes_pendientes_count}")
            
        except Exception as e:
            if conn: conn.rollback()
            messagebox.showerror("Error Crítico", f"Ocurrió un error durante la asignación masiva y todos los cambios fueron revertidos.\n\nError: {e}")
        finally:
            if conn: conn.close()
            self.refrescar_todas_las_tablas()
            
    def habilitar_copiar_celda(self, event, tabla):
        """Muestra un menú con clic derecho para copiar el valor de la celda específica."""
        # 1. Identificar en qué fila y columna exacta se hizo el clic derecho
        row_id = tabla.identify_row(event.y)
        col_id = tabla.identify_column(event.x)
        
        if not row_id or not col_id:
            return # Si hizo clic fuera de los datos, no hacer nada
            
        # 2. Extraer el valor exacto de esa celda
        valor_celda = tabla.set(row_id, col_id)
        
        if not valor_celda:
            return
            
        # 3. Seleccionar la fila visualmente para dar feedback
        tabla.selection_set(row_id)
        
        # 4. Crear el menú emergente
        menu = tk.Menu(self.root, tearoff=0)
        
        # Función interna para mandar el texto al portapapeles de Windows
        def copiar_al_portapapeles():
            self.root.clipboard_clear()
            self.root.clipboard_append(valor_celda)
            self.root.update() # Asegura que se copie al sistema operativo
            
        # 5. Añadir la opción al menú y mostrarlo donde está el ratón
        texto_mostrar = valor_celda if len(valor_celda) < 20 else valor_celda[:17] + "..."
        menu.add_command(label=f"Copiar '{texto_mostrar}'", command=copiar_al_portapapeles)
        menu.tk_popup(event.x_root, event.y_root)

    def mostrar_librero_historico(self):
        """Abre la ventana con los libros leídos por la clienta."""
        # Como está en otro archivo, lo importamos aquí
        try:
            from ui_dialogos import abrir_dialogo_ver_historial
            abrir_dialogo_ver_historial(self.root, self.widgets['tabla_gestion_clientes'])
        except ImportError:
            # Por si tu archivo aún se llama ui_dialogos
            from ui_dialogos import abrir_dialogo_ver_historial
            abrir_dialogo_ver_historial(self.root, self.widgets['tabla_gestion_clientes'])

    def cerrar_mes_actual(self):
        """
        Marca el mes/año actualmente seleccionado como "Cerrado" para que 
        no se generen nuevas asignaciones automáticas para él.
        """
        meses_seleccionados = [m for m, var in self.widgets['meses_vars'].items() if var.get()]
        ano_str = self.widgets['cmb_ano'].get()

        if not meses_seleccionados or not ano_str:
            messagebox.showwarning("Sin Período", "Por favor, selecciona al menos un mes y un año para cerrar.")
            return

        if len(meses_seleccionados) > 1:
            messagebox.showwarning("Múltiples Meses", "Por favor, selecciona solo un mes a la vez para cerrar.")
            return
        
        mes_a_cerrar_str = meses_seleccionados[0]
        mes_a_cerrar_num = MAPEO_MESES[mes_a_cerrar_str]

        if not messagebox.askyesno("Confirmar Cierre de Mes", 
                                f"¿Estás seguro de que quieres cerrar {mes_a_cerrar_str} de {ano_str}?\n\n"
                                "Una vez cerrado, ninguna clienta nueva que se sincronice recibirá una asignación automática para este período.\n"
                                "Esta acción no se puede deshacer fácilmente."):
            return

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO meses_cerrados (ano, mes) VALUES (?, ?)", (ano_str, mes_a_cerrar_num))
            conn.commit()
            conn.close()
            messagebox.showinfo("Mes Cerrado", f"{mes_a_cerrar_str} de {ano_str} ha sido cerrado con éxito.")
        except Exception as e:
            messagebox.showerror("Error de BD", f"No se pudo cerrar el mes: {e}")

    def importar_historicos_clientes(self):
        """Llama al script para cargar los Excel del historial de clientas."""
        if messagebox.askokcancel("Importar Historiales", "Asegúrate de colocar los archivos Excel/CSV con el nombre de cada clienta dentro de la carpeta '6_libreros'.\n\nEl sistema intentará encontrar los libros aunque los nombres no sean exactos.\n\n¿Deseas comenzar?"):
            self.disparar_script_externo("libreros.py", "Importación de historiales completada.\n\nRevisa la carpeta '4_output_reports' si hubo libros que no se encontraron en tu base de datos.")

    # =========================================================================
    # LÓGICA DE LA PESTAÑA DE CAJA / VENTAS (FASE 6)
    # =========================================================================

    def v_iniciar_tab(self):
        """Se ejecuta al iniciar el programa para cargar los datos en memoria"""
        self.v_carrito_libros = [] # Ahora guardará diccionarios: {'titulo': 'DUNE', 'precio': 15000}
        self.v_refrescar_autocompletado()
        self.v_refrescar_tabla_historial()
        self.v_limpiar_formulario()

    def v_refrescar_autocompletado(self):
        try:
            conn = conexion.conectar_db()
            # Cargar Clientes
            clientes_db = conn.execute("SELECT nombre FROM clientes ORDER BY nombre").fetchall()
            self.v_lista_clientes = [row[0] for row in clientes_db] if clientes_db else []
            # Cargar Libros (Título y Precio)
            libros_db = conn.execute("SELECT titulo, precio FROM libros").fetchall()
            self.v_mapa_libros = {row[0].upper(): row[1] for row in libros_db} if libros_db else {}
            conn.close()

            self.widgets['cmb_v_cliente']['values'] = self.v_lista_clientes
            self.widgets['cmb_v_libros']['values'] = list(self.v_mapa_libros.keys())
        except Exception as e:
            print("Error cargando autocompletado:", e)

    def v_autocompletar_cliente(self, event):
        valor = self.widgets['cmb_v_cliente'].get()
        if valor == '': self.widgets['cmb_v_cliente']['values'] = self.v_lista_clientes
        else:
            data = [item for item in self.v_lista_clientes if valor.lower() in item.lower()]
            self.widgets['cmb_v_cliente']['values'] = data

    def v_autocompletar_libro(self, event):
        valor = self.widgets['cmb_v_libros'].get()
        if valor == '': self.widgets['cmb_v_libros']['values'] = list(self.v_mapa_libros.keys())
        else:
            data = [item for item in self.v_mapa_libros.keys() if valor.lower() in item.lower()]
            self.widgets['cmb_v_libros']['values'] = data

    def v_add_libro_al_carrito(self):
        titulo = self.widgets['cmb_v_libros'].get().strip().upper()
        if not titulo: return
        
        # 1. ¿El libro existe? Si no, lo creamos
        if titulo not in self.v_mapa_libros:
            if messagebox.askyesno("Nuevo Libro", f"'{titulo}' NO existe en inventario.\n\n¿Crearlo ahora con stock 0?"):
                conn = conexion.conectar_db()
                conn.execute("INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original) VALUES (?, 'SIN INFORMACION', 'SIN INFORMACION', 'SIN INFORMACION', 'TAPA BLANDA', 0, 0.0, 0.0)", (titulo,))
                conn.commit()
                conn.close()
                self.v_refrescar_autocompletado()
            else:
                return

        # 2. Determinar el Precio (Normal vs Especial)
        precio_especial_str = self.widgets['entry_v_precio_custom'].get().strip()
        if precio_especial_str:
            precio_final = float(precio_especial_str) # Precio personalizado
        else:
            precio_final = self.v_mapa_libros[titulo] # Precio de la base de datos

        # 3. Añadir al Carrito
        self.v_carrito_libros.append({'titulo': titulo, 'precio': precio_final})
        self.v_actualizar_carrito_visual()
        
        # Limpiar campos de ingreso
        self.widgets['cmb_v_libros'].set('')
        self.widgets['entry_v_precio_custom'].delete(0, tk.END)

    def v_remove_libro_del_carrito(self):
        seleccion = self.widgets['list_v_libros'].curselection()
        if not seleccion: return
        
        # Quitar de la lista en memoria usando el índice visual
        indice = seleccion[0]
        self.v_carrito_libros.pop(indice)
        self.v_actualizar_carrito_visual()

    def v_actualizar_carrito_visual(self):
        self.widgets['list_v_libros'].delete(0, tk.END)
        subtotal = 0
        for item in self.v_carrito_libros:
            texto = f"{item['titulo']} (${item['precio']:,.0f})"
            self.widgets['list_v_libros'].insert(tk.END, texto)
            subtotal += item['precio']
            
        self.v_actualizar_totales()

    def v_on_select_envio(self, event=None):
        if self.widgets['cmb_v_envio'].get() == 'RETIRO':
            self.widgets['entry_v_costo_envio'].delete(0, tk.END)
            self.widgets['entry_v_costo_envio'].insert(0, '0')
        self.v_actualizar_totales()

    def v_actualizar_totales(self, *args):
        subtotal = sum(item['precio'] for item in self.v_carrito_libros)
        
        costo_envio_str = self.widgets['entry_v_costo_envio'].get()
        costo_envio = float(costo_envio_str) if costo_envio_str else 0

        self.widgets['lbl_v_subtotal'].config(text=f"$ {subtotal:,.0f}")
        self.widgets['lbl_v_costo_envio'].config(text=f"$ {costo_envio:,.0f}")
        self.widgets['lbl_v_total_final'].config(text=f"$ {subtotal + costo_envio:,.0f}")

    def v_limpiar_formulario(self):
        self.v_carrito_libros.clear()
        self.widgets['list_v_libros'].delete(0, tk.END)
        self.widgets['cmb_v_cliente'].set('')
        self.widgets['cmb_v_libros'].set('')
        self.widgets['entry_v_precio_custom'].delete(0, tk.END)
        self.widgets['cmb_v_envio'].set('SIN INFORMACION')
        self.widgets['entry_v_costo_envio'].delete(0, tk.END)
        self.widgets['entry_v_comentario'].delete(0, tk.END)
        try:
            from datetime import date
            self.widgets['de_v_fecha'].set_date(date.today())
        except: pass
        self.v_actualizar_totales()
        
    def v_guardar_venta(self):
        if not self.v_carrito_libros:
            messagebox.showwarning("Carrito Vacío", "No hay libros para vender.")
            return
            
        cliente_nombre = self.widgets['cmb_v_cliente'].get().strip().upper()
        if not cliente_nombre:
            messagebox.showwarning("Sin Cliente", "Por favor, ingresa el nombre del cliente.")
            return

        fecha = self.widgets['de_v_fecha'].get()
        envio = self.widgets['cmb_v_envio'].get()
        comentario = self.widgets['entry_v_comentario'].get()
        
        subtotal = sum(item['precio'] for item in self.v_carrito_libros)
        costo_envio_str = self.widgets['entry_v_costo_envio'].get()
        costo_envio = float(costo_envio_str) if costo_envio_str else 0
        total_final = subtotal + costo_envio
        
        nombres_libros_str = ", ".join([item['titulo'] for item in self.v_carrito_libros])

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            # --- LÓGICA DE CREACIÓN DE CLIENTE MEJORADA ---
            # 1. ¿El cliente existe?
            cursor.execute("SELECT cliente_id FROM clientes WHERE UPPER(nombre) = ?", (cliente_nombre,))
            res = cursor.fetchone()
            
            if res:
                cliente_id = res[0]
            else:
                # 2. Si no existe, lo creamos con el estado correcto
                if messagebox.askyesno("Cliente Nuevo", f"El cliente '{cliente_nombre}' no existe.\n\n¿Deseas crearlo como un 'CLIENTE REGULAR' (no suscriptor)?"):
                    # Se crea en la tabla clientes con el nuevo estado
                    cursor.execute("INSERT INTO clientes (nombre, status) VALUES (?, 'CLIENTE REGULAR')", (cliente_nombre,))
                    cliente_id = cursor.lastrowid
                    
                    # ¡IMPORTANTE! Se crea una suscripción genérica para evitar errores
                    # en otras partes de la app que unen las tablas.
                    cursor.execute("""
                        INSERT INTO suscripciones (cliente_id, plan, metodo_entrega, generos_preferencia) 
                        VALUES (?, 'NINGUNO', 'SIN INFORMACION', '')
                    """, (cliente_id,))
                else:
                    # Si el usuario cancela, no continuamos con la venta
                    conn.close()
                    return
                
            # 2. GUARDAR LA VENTA
            cursor.execute("""
                INSERT INTO registro_ventas (cliente_nombre, fecha_venta, libros_vendidos, monto_total, metodo_envio, comentario)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cliente_nombre, fecha, nombres_libros_str, total_final, envio, comentario))
            
            # 3. DESCONTAR STOCK (MÁGICO)
            for item in self.v_carrito_libros:
                cursor.execute("UPDATE libros SET stock = stock - 1 WHERE UPPER(titulo) = ?", (item['titulo'],))

            conn.commit()
            conn.close()
            
            messagebox.showinfo("Éxito", f"Venta registrada por ${total_final:,.0f} y stock actualizado.")
            self.v_limpiar_formulario()
            self.v_refrescar_tabla_historial()
            self.refrescar_inventario() # Actualiza la pestaña de inventario
            self.v_refrescar_autocompletado() # Por si se creó un cliente nuevo
            
        except Exception as e:
            messagebox.showerror("Error de Venta", f"Ocurrió un error al guardar: {e}")

    def v_refrescar_tabla_historial(self):
        tabla = self.widgets['tabla_ventas']
        for item in tabla.get_children(): tabla.delete(item)
        try:
            conn = conexion.conectar_db()
            ventas = conn.execute("SELECT venta_id, fecha_venta, cliente_nombre, libros_vendidos, monto_total, metodo_envio, comentario FROM registro_ventas ORDER BY venta_id DESC").fetchall()
            for v in ventas:
                fila = list(v)
                fila[4] = f"${fila[4]:,.0f}" # Formatear dinero
                tabla.insert("", "end", values=tuple(fila))
            conn.close()
        except:
            pass