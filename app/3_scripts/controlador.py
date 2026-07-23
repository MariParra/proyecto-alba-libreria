# VERSIÓN ÍNTEGRA Y COMPLETAMENTE TRADUCIDA PARA POSTGRESQL (NUBE)

import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import json
import os
import datetime
import subprocess
import conexion
import interfaz
import export
from ui_dialogos import manejar_edicion_celda, refrescar_inventario_global, abrir_dialogo_ver_historial

MAPEO_MESES = {"Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04", "Mayo": "05", "Junio": "06", "Julio": "07", "Agosto": "08", "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"}

class AppControlador:
    def __init__(self, root):
        self.root = root
        self.widgets = {}
        self.datos_inventario_actual = []
        self.autocompletado_data = { 'autor': [], 'genero': [], 'editorial': [] }
        self.v_carrito_libros = []
        self.v_mapa_libros = {}
        self.v_lista_clientes = []
        
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
            'cmd_v_limpiar': self.v_limpiar_formulario,
            'cmd_v_eliminar_venta': self.v_eliminar_venta
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
        
        # BINDS PESTAÑA VENTAS
        self.widgets['cmb_v_cliente'].bind('<KeyRelease>', self.v_autocompletar_cliente)
        self.widgets['cmb_v_libros'].bind('<KeyRelease>', self.v_autocompletar_libro)
        self.widgets['entry_v_costo_envio'].bind('<KeyRelease>', self.v_actualizar_totales)
        self.widgets['cmb_v_envio'].bind('<<ComboboxSelected>>', self.v_on_select_envio)

        self.refrescar_todas_las_tablas()
        self.configurar_eventos_autocompletado()
        self.configurar_slider_stock()
        self.v_iniciar_tab()

    # --- AUTOCOMPLETADO (TRADUCIDO) ---
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

    # --- INVENTARIO Y DESCUENTOS (TRADUCIDO) ---
    def configurar_slider_stock(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(stock) FROM libros")
            max_stock_result = cursor.fetchone()
            conn.close()
            max_stock = max_stock_result[0] if max_stock_result and max_stock_result[0] is not None else 100
            
            if 'slider_stock_max' in self.widgets:
                self.widgets['slider_stock_min'].config(to=max_stock)
                self.widgets['slider_stock_max'].config(to=max_stock)
                self.stock_min_var.set(0)
                self.stock_max_var.set(int(max_stock))
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
            condiciones.append("(titulo ILIKE %s OR autor ILIKE %s)")
            params.extend([f"%{termino_busqueda}%", f"%{termino_busqueda}%"])

        for campo in ['autor', 'genero', 'editorial']:
            lst_filtro = self.widgets.get(f'list_filtro_{campo}')
            if lst_filtro:
                seleccionados = [lst_filtro.get(i) for i in lst_filtro.curselection()]
                if seleccionados:
                    placeholders = ', '.join(['%s'] * len(seleccionados))
                    condiciones.append(f"{campo} IN ({placeholders})")
                    params.extend(seleccionados)

        condiciones.append("stock >= %s AND stock <= %s")
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
            for fila in self.datos_inventario_actual:
                tabla.insert("", "end", values=fila)

            stock_total = sum(int(fila[6]) for fila in self.datos_inventario_actual if fila[6])
            widgets['lbl_stock_total'].config(text=f"Unidades Totales en Inventario: {stock_total}")
            self.refrescar_listas_autocompletado()
        except Exception as e:
            print(f"Error al cargar inventario: {e}")

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
                    UPDATE libros SET titulo=%s, autor=%s, genero=%s, editorial=%s, encuadernacion=%s, stock=%s, precio=%s, precio_original=%s 
                    WHERE libro_id=%s
                """, (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], datos['encuadernacion'], 
                      int(datos['stock']), precio_base, precio_base, libro_id))
            else:
                cursor.execute("""
                    INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            cursor.execute("DELETE FROM libros WHERE libro_id=%s", (libro_id,))
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
            query = "UPDATE libros SET precio = ROUND(CAST(precio_original AS numeric) * %s, -1)" #Redondeo a la decena
            params = [multiplicador]
            
            if respuesta == 'yes':
                placeholders = ', '.join('%s' for _ in ids_a_actualizar)
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
                placeholders = ', '.join('%s' for _ in ids_a_actualizar)
                query += f" WHERE libro_id IN ({placeholders})"
                params.extend(ids_a_actualizar)
            
            cursor.execute(query, tuple(params))
            libros_afectados = cursor.rowcount
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", f"Se ha restaurado el precio original a {libros_afectados} libros.")
            self.aplicar_filtros_inventario()
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudieron quitar los descuentos: {e}")

    # --- GESTIÓN CLIENTES (TRADUCIDA) ---
    def refrescar_tabla_clientes_gestion(self, termino_busqueda=None):
        if 'tabla_gestion_clientes' not in self.widgets: return
        tabla = self.widgets['tabla_gestion_clientes']
        for item in tabla.get_children(): tabla.delete(item)
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            query = "SELECT cliente_id, nombre, email, telefono, rut, direccion, status FROM clientes"
            params = []
            if termino_busqueda:
                query += " WHERE nombre ILIKE %s OR email ILIKE %s OR telefono ILIKE %s OR rut ILIKE %s"
                params.extend([f"%{termino_busqueda}%"] * 4)
            query += " ORDER BY nombre"
            cursor.execute(query, tuple(params))
            for cliente in cursor.fetchall(): tabla.insert("", "end", values=cliente)
            conn.close()
        except Exception as e: messagebox.showerror("Error de BD", f"No se pudo cargar la lista de clientes: {e}")

    def buscar_cliente_gestion(self, event=None):
        termino = self.widgets['entry_busqueda_clientes'].get().strip()
        self.refrescar_tabla_clientes_gestion(termino)

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
            cursor.execute("SELECT nombre, email, telefono, direccion, rut, instagram, status FROM clientes WHERE cliente_id = %s", (cliente_id,))
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
                UPDATE clientes SET nombre = %s, email = %s, telefono = %s, direccion = %s, rut = %s, instagram = %s, status = %s WHERE cliente_id = %s
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
            # PRAGMA se elimina, no existe en PostgreSQL
            cursor.execute("DELETE FROM asignaciones WHERE cliente_id = %s", (cliente_id,))
            cursor.execute("DELETE FROM suscripciones WHERE cliente_id = %s", (cliente_id,))
            cursor.execute("DELETE FROM clientes WHERE cliente_id = %s", (cliente_id,))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", f"El cliente '{nombre}' ha sido eliminado.")
            self.limpiar_formulario_cliente()
            self.refrescar_todas_las_tablas() 
        except Exception as e: messagebox.showerror("Error BD", f"No se pudo eliminar al cliente: {e}")

    # --- ASIGNACIONES Y SINCRONIZACIÓN (TRADUCIDA) ---
    def toggle_columnas_opcionales(self):
        columnas_base = ["asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "extras", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario"]
        opcionales_visibles = []
        if self.widgets['vars_opcionales']['rut'].get(): opcionales_visibles.append("rut")
        if self.widgets['vars_opcionales']['email'].get(): opcionales_visibles.append("email")
        if self.widgets['vars_opcionales']['telefono'].get(): opcionales_visibles.append("telefono")
        if self.widgets['vars_opcionales']['direccion'].get(): opcionales_visibles.append("direccion")
        self.widgets['tabla_clientes']['displaycolumns'] = columnas_base + opcionales_visibles

    def manejar_edicion_celda_asignacion(self, event):
        manejar_edicion_celda(event, self.root, self.widgets, self.iniciar_sincronizacion_periodo)
        
    def ordenar_columna(self, tabla, col, reverse):
        lista_valores = [(tabla.set(k, col), k) for k in tabla.get_children('')]
        
        for c in tabla['columns']:
            titulo_col = c.replace("_", " ").title()
            if c == "tipo_envio": titulo_col = "Tipo De Envio"
            if c == "envio_pag": titulo_col = "Envio Pagado"
            if c == "ano": titulo_col = "Año" 
            tabla.heading(c, text=titulo_col, command=lambda _col=c: self.ordenar_columna(tabla, _col, False))
            
        try: 
            lista_valores.sort(key=lambda t: float(t[0]) if t[0] and t[0] != 'None' else 0.0, reverse=reverse)
        except ValueError: 
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
        self.v_refrescar_autocompletado()
        self.v_refrescar_tabla_historial()
        
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
        
        conn = None
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            ano_actual = datetime.datetime.now().year
            mes_actual = datetime.datetime.now().month
            meses_nums = [MAPEO_MESES[m] for m in meses_seleccionados]
            
            if len(meses_nums) == 1:
                mes_num = meses_nums[0]
                ano_seleccionado = int(ano_str)
                mes_seleccionado = int(mes_num)
                
                periodo_es_pasado = ano_seleccionado < ano_actual or (ano_seleccionado == ano_actual and mes_seleccionado < mes_actual)
                
                cursor.execute("SELECT 1 FROM meses_cerrados WHERE ano = %s AND mes = %s", (ano_seleccionado, mes_seleccionado))
                mes_cerrado_explicitamente = cursor.fetchone() is not None

                if not periodo_es_pasado and not mes_cerrado_explicitamente:
                    cursor.execute("""
                        DELETE FROM asignaciones WHERE ano = %s AND mes = %s AND estado_envio = 'EN PREPARACION' 
                        AND libro_suscripcion_id IS NULL AND cliente_id IN (SELECT cliente_id FROM clientes WHERE status = 'INACTIVA')
                    """, (ano_seleccionado, mes_seleccionado))

                    cursor.execute("""
                        INSERT INTO asignaciones (cliente_id, ano, mes, estado_envio, pagado, envio_pagado, comentario)
                        SELECT c.cliente_id, %s, %s, 'EN PREPARACION', 'FALSE', 'FALSE', 'Sin comentario'
                        FROM clientes c
                        WHERE c.status = 'ACTIVA'
                        AND NOT EXISTS (
                            SELECT 1 FROM asignaciones a 
                            WHERE a.cliente_id = c.cliente_id AND a.ano = %s AND a.mes = %s
                        )
                    """, (ano_seleccionado, mes_seleccionado, ano_seleccionado, mes_seleccionado))
                    conn.commit()

            placeholders_meses = ",".join(["%s"] * len(meses_nums))
            
            query = f"""
                SELECT a.asignacion_id, c.cliente_id, c.nombre, a.ano, a.mes, l.titulo, 
                    a.extras, s.metodo_entrega, a.fecha_asignacion, a.estado_envio, a.pagado, a.envio_pagado, a.comentario,
                    c.rut, c.email, c.telefono, c.direccion
                FROM asignaciones a
                JOIN clientes c ON a.cliente_id = c.cliente_id
                JOIN suscripciones s ON c.cliente_id = s.cliente_id
                LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
                WHERE a.ano = %s AND a.mes IN ({placeholders_meses})
            """
            params = [int(ano_str)] + [int(m) for m in meses_nums]

            filtro_estado = self.widgets['cmb_filtro_estado'].get()
            if filtro_estado != "TODOS":
                query += " AND a.estado_envio = %s"
                params.append(filtro_estado)

            termino_busqueda = self.widgets.get('entry_busqueda_asignaciones')
            if termino_busqueda and termino_busqueda.get().strip():
                termino_val = termino_busqueda.get().strip()
                query += " AND (c.nombre ILIKE %s OR c.email ILIKE %s OR c.rut ILIKE %s)"
                params.extend([f"%{termino_val}%"] * 3)
            
            query += " ORDER BY c.nombre"
            cursor.execute(query, tuple(params))
            
            for f in cursor.fetchall():
                fila_formateada = list(f)
                fila_formateada[5] = fila_formateada[5] if fila_formateada[5] else "SIN ASIGNACIÓN"
                fila_formateada[9] = "Si" if str(fila_formateada[9]).upper() == "TRUE" else "No"
                fila_formateada[10] = "Si" if str(fila_formateada[10]).upper() == "TRUE" else "No"
                tabla.insert("", "end", values=tuple(fila_formateada))

        except Exception as e:
            messagebox.showerror("Error BD", f"Error al cargar asignaciones: {e}")
        finally:
            if conn: conn.close()

    def eliminar_asignacion_manual(self):
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
            cursor.execute("SELECT libro_suscripcion_id FROM asignaciones WHERE asignacion_id = %s", (asignacion_id,))
            resultado = cursor.fetchone()
            if resultado and resultado[0]:
                libro_id_a_devolver = resultado[0]
                cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = %s", (libro_id_a_devolver,))
                print(f"Devolviendo libro ID {libro_id_a_devolver} al stock.")

            cursor.execute("DELETE FROM asignaciones WHERE asignacion_id = %s", (asignacion_id,))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", f"La asignación para {nombre_cliente} ({mes}/{ano}) ha sido eliminada.")
            self.iniciar_sincronizacion_periodo()
        except Exception as e:
            messagebox.showerror("Error de BD", f"No se pudo eliminar la asignación: {e}")

    def asignar_pendientes_aleatorio(self):
        meses_seleccionados = [m for m, var in self.widgets['meses_vars'].items() if var.get()]
        ano_str = self.widgets['cmb_ano'].get()
        if not meses_seleccionados or not ano_str:
            messagebox.showwarning("Sin Período", "Por favor, selecciona al menos un mes y un año para la asignación.")
            return

        if not messagebox.askyesno("Confirmar Asignación Automática", 
                                f"Se intentará asignar un libro a todas las clientas sin asignación para los meses seleccionados del {ano_str}.\n\n"
                                "El proceso respetará los géneros preferidos y el stock disponible.\n\n¿Deseas continuar?"):
            return

        libros_asignados_count = 0; clientes_pendientes_count = 0; conn = None
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            meses_nums = [MAPEO_MESES[m] for m in meses_seleccionados]
            placeholders_meses = ",".join(["%s"] * len(meses_nums))
            query_pendientes = f"""
                SELECT a.asignacion_id, s.cliente_id, s.generos_preferencia
                FROM asignaciones a JOIN suscripciones s ON a.cliente_id = s.cliente_id
                WHERE a.ano = %s AND a.mes IN ({placeholders_meses}) AND a.libro_suscripcion_id IS NULL
            """
            params_pendientes = [int(ano_str)] + [int(m) for m in meses_nums]
            cursor.execute(query_pendientes, tuple(params_pendientes))
            asignaciones_pendientes = cursor.fetchall()
            if not asignaciones_pendientes:
                messagebox.showinfo("Nada que Asignar", "No se encontraron clientas pendientes de asignación en el período seleccionado.")
                conn.close(); return

            cursor.execute("SELECT libro_id, genero FROM libros WHERE stock > 0")
            libros_con_stock = cursor.fetchall()
            
            import random
            for asignacion_id, cliente_id, generos_str in asignaciones_pendientes:
                generos_preferidos = [g.strip().upper() for g in (generos_str or "").split(',') if g.strip()]
                libros_candidatos = []
                if generos_preferidos:
                    for libro_id, genero_libro in libros_con_stock:
                        gen_upper = str(genero_libro).strip().upper()
                        if any(pref in gen_upper or gen_upper in pref for pref in generos_preferidos):
                            libros_candidatos.append(libro_id)
                
                if not libros_candidatos:
                    libros_candidatos = [libro_id for libro_id, _ in libros_con_stock]

                if libros_candidatos:
                    libro_elegido_id = random.choice(libros_candidatos)
                    cursor.execute("UPDATE asignaciones SET libro_suscripcion_id = %s WHERE asignacion_id = %s", (libro_elegido_id, asignacion_id))
                    cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = %s", (libro_elegido_id,))
                    libros_con_stock = [libro for libro in libros_con_stock if libro[0] != libro_elegido_id]
                    libros_asignados_count += 1
                else:
                    clientes_pendientes_count += 1
            
            conn.commit()
            messagebox.showinfo("Proceso Completado", f"Asignación finalizada.\nLibros asignados: {libros_asignados_count}\nClientas pendientes: {clientes_pendientes_count}")
        except Exception as e:
            if conn: conn.rollback()
            messagebox.showerror("Error Crítico", f"Ocurrió un error y todos los cambios fueron revertidos.\nError: {e}")
        finally:
            if conn: conn.close()
            self.refrescar_todas_las_tablas()

    def cerrar_mes_actual(self):
        meses_seleccionados = [m for m, var in self.widgets['meses_vars'].items() if var.get()]
        ano_str = self.widgets['cmb_ano'].get()
        if not meses_seleccionados or not ano_str or len(meses_seleccionados) > 1:
            messagebox.showwarning("Selección Inválida", "Por favor, selecciona solo un mes y un año para cerrar.")
            return
        
        mes_a_cerrar_str = meses_seleccionados[0]
        mes_a_cerrar_num = MAPEO_MESES[mes_a_cerrar_str]

        if not messagebox.askyesno("Confirmar Cierre de Mes", f"¿Cerrar {mes_a_cerrar_str} de {ano_str}?\n\nUna vez cerrado, no se crearán nuevas asignaciones automáticas para este período."):
            return

        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO meses_cerrados (ano, mes) VALUES (%s, %s) ON CONFLICT (ano, mes) DO NOTHING", (int(ano_str), int(mes_a_cerrar_num)))
            conn.commit()
            conn.close()
            messagebox.showinfo("Mes Cerrado", f"{mes_a_cerrar_str} de {ano_str} ha sido cerrado con éxito.")
        except Exception as e:
            messagebox.showerror("Error de BD", f"No se pudo cerrar el mes: {e}")
            
    # --- PESTAÑA DE CAJA / VENTAS (TRADUCIDA) ---
    def v_iniciar_tab(self):
        self.v_limpiar_formulario()
        self.v_refrescar_autocompletado()
        self.v_refrescar_tabla_historial()
        self.widgets['de_v_fecha'].set_date(datetime.date.today())


    # En controlador.py

    def v_refrescar_autocompletado(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            # --- Clientes ---
            cursor.execute("SELECT nombre FROM clientes ORDER BY nombre")
            self.v_lista_clientes = [row[0] for row in cursor.fetchall()]
            
            # Actualizamos las opciones visibles
            self.widgets['cmb_v_cliente']['values'] = self.v_lista_clientes
            self.widgets['cmb_v_cliente'].lista_original = self.v_lista_clientes 
            
            # --- Libros ---
            query = """
                SELECT 
                    libro_id, 
                    titulo, 
                    CASE 
                        WHEN precio > 0 THEN precio 
                        ELSE precio_original 
                    END AS precio_venta
                FROM libros
            """
            cursor.execute(query)
            
            self.v_mapa_libros = {row[1].upper(): {'id': row[0], 'precio': row[2]} for row in cursor.fetchall()}
            lista_libros = list(self.v_mapa_libros.keys())
            
            # Actualizamos las opciones visibles
            self.widgets['cmb_v_libros']['values'] = lista_libros
            # ¡NUEVO! Guardamos la lista completa "en secreto" dentro del widget
            self.widgets['cmb_v_libros'].lista_original = lista_libros
            
            conn.close()
        except Exception as e:
            print(f"Error actualizando autocompletados de venta: {e}")




    def v_autocompletar_cliente(self, event):
        widget = event.widget
        valor_escrito = widget.get().lower()
        if valor_escrito == '':
            widget['values'] = self.v_lista_clientes
        else:
            widget['values'] = [item for item in self.v_lista_clientes if valor_escrito in item.lower()]

    def v_autocompletar_libro(self, event):
        widget = event.widget
        valor_escrito = widget.get().lower()
        if valor_escrito == '':
            widget['values'] = list(self.v_mapa_libros.keys())
        else:
            widget['values'] = [item for item in self.v_mapa_libros.keys() if valor_escrito in item.lower()]

    def v_add_libro_al_carrito(self):
        titulo = self.widgets['cmb_v_libros'].get().strip().upper()
        if not titulo: return
        
        if titulo not in self.v_mapa_libros:
            if messagebox.askyesno("Nuevo Libro", f"'{titulo}' NO existe en inventario.\n\n¿Crearlo ahora con stock 0?"):
                conn = conexion.conectar_db()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio, precio_original) VALUES (%s, 'SIN INFORMACION', 'SIN INFORMACION', 'SIN INFORMACION', 'TAPA BLANDA', 0, 0.0, 0.0)", (titulo,))
                conn.commit()
                conn.close()
                self.v_refrescar_autocompletado()
            else:
                return
        precio_base = self.v_mapa_libros.get(titulo, {}).get('precio', 0)
        libro_id = self.v_mapa_libros.get(titulo, {}).get('id')
        precio_especial_str = self.widgets['entry_v_precio_custom'].get().strip()
        precio_final = float(precio_especial_str) if precio_especial_str else precio_base
        self.v_carrito_libros.append({'titulo': titulo, 'precio': precio_final, 'id': libro_id})
        self.v_actualizar_carrito_visual()
        
        self.widgets['cmb_v_libros'].set('')
        self.widgets['entry_v_precio_custom'].delete(0, tk.END)

    def v_remove_libro_del_carrito(self):
        seleccion = self.widgets['list_v_carrito'].curselection()
        if seleccion:
            self.v_carrito_libros.pop(seleccion[0])
            self.v_actualizar_carrito_visual()

    def v_actualizar_carrito_visual(self):
        lista = self.widgets['list_v_carrito']
        lista.delete(0, tk.END)
        for item in self.v_carrito_libros:
            lista.insert(tk.END, f"{item['titulo']} (${item['precio']:,.0f})")
        self.v_actualizar_totales()

    # En controlador.py

    def v_actualizar_totales(self, event=None):
        subtotal = sum(item['precio'] for item in self.v_carrito_libros)
        
        costo_envio_str = self.widgets['entry_v_costo_envio'].get()
        try:
            costo_envio = float(costo_envio_str) if costo_envio_str else 0
        except ValueError:
            costo_envio = 0
            
        total_final = subtotal + costo_envio
    
        self.widgets['lbl_v_subtotal'].config(text=f"${subtotal:,.0f}")
        self.widgets['lbl_v_costo_envio'].config(text=f"${costo_envio:,.0f}")
        self.widgets['lbl_v_total'].config(text=f"${total_final:,.0f}")


    def v_on_select_envio(self, event=None):
        metodo = self.widgets['cmb_v_envio'].get()
        costo_envio_entry = self.widgets['entry_v_costo_envio']
        costo_envio_entry.delete(0, tk.END)
        if metodo == "RETIRO":
            costo_envio_entry.insert(0, "0")
        self.v_actualizar_totales()

    def v_limpiar_formulario(self):
        self.v_carrito_libros = []
        self.v_actualizar_carrito_visual()
        self.widgets['cmb_v_cliente'].set('')
        self.widgets['cmb_v_libros'].set('')
        self.widgets['entry_v_precio_custom'].delete(0, tk.END)
        self.widgets['cmb_v_envio'].set('')
        self.widgets['entry_v_costo_envio'].delete(0, tk.END)
        self.widgets['entry_v_comentario'].delete(0, tk.END)
        self.widgets['de_v_fecha'].set_date(datetime.date.today())

    
    def v_guardar_venta(self):
        if not self.v_carrito_libros:
            messagebox.showwarning("Carrito Vacío", "No hay libros para vender."); return
            
        cliente_nombre = self.widgets['cmb_v_cliente'].get().strip().upper()
        if not cliente_nombre:
            messagebox.showwarning("Sin Cliente", "Por favor, ingresa el nombre del cliente."); return

        fecha_str = self.widgets['de_v_fecha'].get()
        envio = self.widgets['cmb_v_envio'].get()
        comentario = self.widgets['entry_v_comentario'].get()
        
        subtotal = sum(item['precio'] for item in self.v_carrito_libros)
        costo_envio = float(self.widgets['entry_v_costo_envio'].get() or 0)
        total_final = subtotal + costo_envio
        nombres_libros_str = ", ".join([item['titulo'] for item in self.v_carrito_libros])
        
        conn = None
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            cursor.execute("SELECT cliente_id FROM clientes WHERE nombre ILIKE %s", (cliente_nombre,))
            res = cursor.fetchone()
            
            if res:
                cliente_id = res[0]
            else:
                if messagebox.askyesno("Cliente Nuevo", f"El cliente '{cliente_nombre}' no existe.\n\n¿Deseas crearlo como un 'CLIENTE REGULAR' (no suscriptor)?"):
                    cursor.execute("INSERT INTO clientes (nombre, status) VALUES (%s, 'CLIENTE REGULAR') RETURNING cliente_id", (cliente_nombre,))
                    cliente_id = cursor.fetchone()[0]
                    cursor.execute("INSERT INTO suscripciones (cliente_id, fecha_pago, metodo_entrega, generos_preferencia) VALUES (%s, NULL, 'SIN INFORMACION', '')", (cliente_id,))
                else:
                    conn.close(); return
            
            cursor.execute("""
                INSERT INTO registro_ventas (cliente_id, fecha_venta, libros_vendidos, subtotal_libros, valor_envio, monto_final, metodo_envio, comentario)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (cliente_id, fecha_str, nombres_libros_str, subtotal, costo_envio, total_final, envio, comentario))
            
                
            for item in self.v_carrito_libros:
                # 1. Actualizar stock
                cursor.execute("UPDATE libros SET stock = stock - 1 WHERE libro_id = %s", (item['id'],))
                
                # 2. Insertar en el librero histórico, evitando duplicados
                # El autor histórico se deja como NULL porque el autor canónico está en la tabla 'libros'
                cursor.execute("""
                    INSERT INTO librero_historico (cliente_id, libro_id, autor_historico, origen)
                    VALUES (%s, %s, NULL, 'Venta Directa')
                    ON CONFLICT (cliente_id, libro_id) DO NOTHING;
                """, (cliente_id, item['id'])) 
            conn.commit()
            messagebox.showinfo("Éxito", f"Venta registrada por ${total_final:,.0f} y stock actualizado.")
            self.v_limpiar_formulario()
            self.v_refrescar_tabla_historial()
            self.refrescar_inventario()
            self.v_refrescar_autocompletado()
        except Exception as e:
            if conn: conn.rollback()
            messagebox.showerror("Error de Venta", f"Ocurrió un error al guardar: {e}")
        finally:
            if conn: conn.close()

    def v_editar_comentario_venta(self, event):
        tabla = self.widgets.get('tabla_ventas')
        if not tabla: return
        
        region = tabla.identify_region(event.x, event.y)
        if region != "cell": return

        col_display_id = tabla.identify_column(event.x)
        selected_col_name = tabla.column(col_display_id, 'id')
        selected_iid = tabla.focus()
        if not selected_iid: return

        # 2. Comprobamos que sea la columna de comentario (sin importar mayúsculas)
        if "coment" in selected_col_name.lower():
            
            try:
                venta_id = tabla.set(selected_iid, "id")
            except:
                try:
                    venta_id = tabla.set(selected_iid, "venta_id")
                except:
                    messagebox.showerror("Error", "No se encontró el ID de la venta.")
                    return
                    
            valor_actual = tabla.set(selected_iid, "comentario")

            # 3. Construir la ventana emergente
            win = tk.Toplevel()
            win.title("Editar Comentario de Venta")
            win.geometry("400x280")
            win.configure(bg="#F1F8E9") 
            win.grab_set()

            tk.Label(win, text="Editar Comentario:", bg="#F1F8E9", font=("Helvetica", 10, "bold")).pack(pady=(15, 5))
            
            text_widget = tk.Text(win, wrap="word", height=8, width=40, font=("Helvetica", 10))
            text_widget.pack(padx=15, pady=5, fill="both", expand=True)
            text_widget.insert("1.0", valor_actual if valor_actual and valor_actual != 'None' else "")

            def guardar():
                nuevo_valor = text_widget.get("1.0", tk.END).strip()
                conn = None
                try:
                    conn = conexion.conectar_db()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE registro_ventas SET comentario = %s WHERE venta_id = %s", (nuevo_valor, venta_id))
                    conn.commit()
                    win.destroy()
                    self.v_refrescar_tabla_historial() # Refrescamos para ver el cambio
                except Exception as e:
                    if conn: conn.rollback()
                    messagebox.showerror("Error", f"No se pudo guardar el comentario: {e}", parent=win)
                finally:
                    if conn: conn.close()

            tk.Button(win, text="Guardar Cambios", command=guardar, bg="#81BFB7", fg="white", font=("Helvetica", 10, "bold")).pack(pady=15)


    def v_refrescar_tabla_historial(self, cliente=None, fecha_desde=None, fecha_hasta=None):
        self.widgets['tabla_ventas'].bind("<Double-1>", self.v_editar_comentario_venta)
        tabla = self.widgets['tabla_ventas']
        for item in tabla.get_children(): tabla.delete(item)
        
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            query = "SELECT venta_id, fecha_venta, (SELECT nombre FROM clientes c WHERE c.cliente_id=rv.cliente_id), libros_vendidos, monto_final, metodo_envio, comentario FROM registro_ventas rv"
            condiciones, params = [], []

            if cliente:
                condiciones.append("(SELECT nombre FROM clientes c WHERE c.cliente_id=rv.cliente_id) ILIKE %s")
                params.append(f"%{cliente}%")
            if fecha_desde:
                condiciones.append("fecha_venta >= %s")
                params.append(fecha_desde)
            if fecha_hasta:
                condiciones.append("fecha_venta <= %s")
                params.append(fecha_hasta)

            if condiciones: query += " WHERE " + " AND ".join(condiciones)
            query += " ORDER BY venta_id DESC"
            
            cursor.execute(query, tuple(params))
            ventas = cursor.fetchall()
            for v in ventas:
                fila = list(v)
                fila = ["" if x is None else x for x in fila]
                try:
                    if isinstance(fila[1], (datetime.date, datetime.datetime)):
                        fila[1] = fila[1].strftime('%Y-%m-%d')
                    monto = float(fila[4]) if str(fila[4]).strip() != "" else 0
                    fila[4] = f"${monto:,.0f}"
                except (ValueError, TypeError):
                    fila[4] = "$0"
                tabla.insert("", "end", values=tuple(fila), iid=fila[0])
            conn.close()
        except Exception as e:
            messagebox.showerror("Error Cargando Historial", f"No se pudo cargar la tabla de ventas.\nDetalle: {e}")

    def v_eliminar_venta(self):
        seleccion = self.widgets['tabla_v_historial'].selection()
        if not seleccion:
            messagebox.showwarning("Sin Selección", "Por favor, selecciona una venta de la tabla para eliminar.")
            return
            
        # --- BLINDAJE: Buscamos el ID en los dos nombres posibles ---
        try:
            venta_id = self.widgets['tabla_v_historial'].set(seleccion[0], "id")
        except:
            try:
                venta_id = self.widgets['tabla_v_historial'].set(seleccion[0], "venta_id")
            except:
                messagebox.showerror("Error", "No se encontró la columna de ID en la tabla.")
                return
        
        if not messagebox.askyesno("Confirmar Eliminación", f"¿Estás seguro de que deseas eliminar la venta con ID {venta_id}?\n\nEsta acción devolverá los libros al stock y los eliminará del historial de la clienta. Esta acción no se puede deshacer."):
            return
            
        conn = None
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            # 1. Obtenemos los detalles de la venta ANTES de borrarla
            cursor.execute("SELECT cliente_id, libros_vendidos FROM registro_ventas WHERE venta_id = %s", (venta_id,))
            venta_info = cursor.fetchone()
            if not venta_info:
                messagebox.showerror("Error", "La venta ya no existe."); return
            
            cliente_id, libros_str = venta_info
            
            # 2. Devolvemos el stock y eliminamos del historial
            if libros_str:
                titulos_vendidos = [titulo.strip().upper() for titulo in libros_str.split(',')]
                for titulo in titulos_vendidos:
                    # Buscamos el ID del libro para las operaciones
                    cursor.execute("SELECT libro_id FROM libros WHERE titulo ILIKE %s", (titulo,))
                    res_libro = cursor.fetchone()
                    if res_libro:
                        libro_id = res_libro[0]
                        # Devolvemos el stock
                        cursor.execute("UPDATE libros SET stock = stock + 1 WHERE libro_id = %s", (libro_id,))
                        # Eliminamos del historial
                        cursor.execute("DELETE FROM librero_historico WHERE cliente_id = %s AND libro_id = %s AND origen = 'Venta Directa'", (cliente_id, libro_id))
                        
            # 3. Finalmente, eliminamos el registro de la venta
            cursor.execute("DELETE FROM registro_ventas WHERE venta_id = %s", (venta_id,))
            conn.commit()
            
            messagebox.showinfo("Éxito", f"Venta ID {venta_id} eliminada correctamente. El stock y el historial han sido restaurados.")
            
            # Actualizamos la interfaz
            self.v_refrescar_tabla_historial()
            self.refrescar_inventario()
            
        except Exception as e:
            if conn: conn.rollback()
            messagebox.showerror("Error de Eliminación", f"No se pudo eliminar la venta: {e}")
        finally:
            if conn: conn.close()

    
    # --- MÉTODOS GENÉRICOS Y EXTERNOS ---
    def habilitar_copiar_celda(self, event, tabla):
        row_id = tabla.identify_row(event.y)
        col_id = tabla.identify_column(event.x)
        if not row_id or not col_id: return
        valor_celda = tabla.set(row_id, col_id)
        if not valor_celda: return
        tabla.selection_set(row_id)
        menu = tk.Menu(self.root, tearoff=0)
        def copiar_al_portapapeles():
            self.root.clipboard_clear()
            self.root.clipboard_append(valor_celda)
            self.root.update()
        texto_mostrar = valor_celda if len(valor_celda) < 20 else valor_celda[:17] + "..."
        menu.add_command(label=f"Copiar '{texto_mostrar}'", command=copiar_al_portapapeles)
        menu.tk_popup(event.x_root, event.y_root)

    def mostrar_librero_historico(self):
        abrir_dialogo_ver_historial(self.root, self.widgets['tabla_gestion_clientes'])

    def exportar_excel(self):
        try:
            self.root.config(cursor="watch"); self.root.update()

            # 1. Recolectar datos de la tabla de Asignaciones
            datos_asignaciones = [self.widgets['tabla_clientes'].item(i)['values'] for i in self.widgets['tabla_clientes'].get_children()]
            columnas_asignaciones = [self.widgets['tabla_clientes'].heading(c, "text") for c in self.widgets['tabla_clientes']['columns']]
            
            # 2. Recolectar datos de la tabla de Gestión de Clientes
            datos_clientes = [self.widgets['tabla_gestion_clientes'].item(i)['values'] for i in self.widgets['tabla_gestion_clientes'].get_children()]
            columnas_clientes = [self.widgets['tabla_gestion_clientes'].heading(c, "text") for c in self.widgets['tabla_gestion_clientes']['columns']]

            # 3. Recolectar datos de la tabla de Inventario
            datos_inventario = [self.widgets['tabla_libros'].item(i)['values'] for i in self.widgets['tabla_libros'].get_children()]
            columnas_inventario = [self.widgets['tabla_libros'].heading(c, "text") for c in self.widgets['tabla_libros']['columns']]

            # 4. Recolectar datos de la tabla de Historial de Ventas
            datos_ventas = [self.widgets['tabla_ventas'].item(i)['values'] for i in self.widgets['tabla_ventas'].get_children()]
            columnas_ventas = [self.widgets['tabla_ventas'].heading(c, "text") for c in self.widgets['tabla_ventas']['columns']]

            # Llamar a la función de exportación en export.py con todos los datos
            # Asegúrate de importar 'export' al principio de tu controlador.py
            import export 
            ruta = export.exportar_a_excel(
                datos_asignaciones, columnas_asignaciones,
                datos_clientes, columnas_clientes,
                datos_inventario, columnas_inventario,
                datos_ventas, columnas_ventas
            )
            
            self.root.config(cursor="")
            if isinstance(ruta, str):
                messagebox.showinfo("Éxito", f"Excel generado en:\n{ruta}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error de Exportación", str(e))
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
    def actualizar_stock_masivo(self): self.disparar_script_externo("actualizar_stock.py", "Proceso completado.")
    def importar_historicos_clientes(self): self.disparar_script_externo("libreros.py", "Importación de historiales completada.")
