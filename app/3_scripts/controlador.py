import tkinter as tk
from tkinter import messagebox, ttk
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
        
        self.autocompletado_data = {
            'autor': [],
            'genero': [],
            'editorial': []
        }
        
        # Variable para controlar el slider de stock
        self.stock_filter_var = tk.IntVar()

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
            'cmd_validar_int': validar_int,
            'cmd_validar_float': validar_float,
            'cmd_toggle_columnas': self.toggle_columnas_opcionales
        }

        refrescar_inventario_global.__globals__['refrescar_inventario_global'] = lambda: self.refrescar_inventario(widgets=self.widgets)

        interfaz.construir_interfaz(self.root, self.widgets, comandos_ui)
        
        mes_actual = list(MAPEO_MESES.keys())[datetime.datetime.now().month - 1]
        self.widgets['meses_vars'][mes_actual].set(True)
        self.widgets['cmb_ano'].set(str(datetime.datetime.now().year))
        
        self.widgets['cmb_ano'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_estado'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_pagado'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_envio'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['cmb_filtro_libro'].bind("<<ComboboxSelected>>", lambda e: self.iniciar_sincronizacion_periodo())
        self.widgets['tabla_clientes'].bind("<Double-1>", lambda event: manejar_edicion_celda(event, self.root, self.widgets, self.iniciar_sincronizacion_periodo))
        self.widgets['tabla_libros'].bind("<<TreeviewSelect>>", self.al_seleccionar_libro)
        
        # Vincular Enter a la nueva función de filtros
        self.widgets['entry_busqueda_libros'].bind("<Return>", self.aplicar_filtros_inventario)
        
        # Configurar eventos del slider
        if 'slider_stock' in self.widgets:
            self.widgets['slider_stock'].config(variable=self.stock_filter_var)
            self.widgets['slider_stock'].bind("<ButtonRelease-1>", self.aplicar_filtros_inventario)
            self.stock_filter_var.trace_add("write", self.actualizar_label_stock)
        
        self.refrescar_todas_las_tablas()
        self.configurar_eventos_autocompletado()
        self.configurar_slider_stock()

    # --- LÓGICA DE AUTOCOMPLETADO ---
    def refrescar_listas_autocompletado(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            for campo in self.autocompletado_data.keys():
                cursor.execute(f"SELECT DISTINCT {campo} FROM libros WHERE {campo} IS NOT NULL AND {campo} != '' AND {campo} != 'SIN INFORMACION' ORDER BY {campo}")
                valores = [str(row[0]) for row in cursor.fetchall()]
                self.autocompletado_data[campo] = valores
                
                # Mantener valor actual si existe
                if campo in self.widgets['form_libro_entries']:
                    current_value = self.widgets['form_libro_entries'][campo].get()
                    self.widgets['form_libro_entries'][campo]['values'] = valores
                    if current_value in valores:
                        self.widgets['form_libro_entries'][campo].set(current_value)
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
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab', 'Shift_L', 'Shift_R', 'Escape', 'Control_L', 'Alt_L'):
            return
        valor_escrito = widget.get()
        lista_completa = self.autocompletado_data[campo_actual]
        if valor_escrito == '':
            widget['values'] = lista_completa
        else:
            data = [item for item in lista_completa if valor_escrito.lower() in item.lower()]
            widget['values'] = data

    # --- LÓGICA DEL SLIDER Y FILTROS DE INVENTARIO ---
    def configurar_slider_stock(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(stock) FROM libros")
            max_stock = cursor.fetchone()[0]
            conn.close()
            
            if max_stock and 'slider_stock' in self.widgets:
                self.widgets['slider_stock'].config(to=max_stock)
                self.stock_filter_var.set(max_stock)
        except Exception as e:
            print(f"Error al configurar el slider de stock: {e}")
            if 'slider_stock' in self.widgets:
                self.widgets['slider_stock'].config(to=100)
                self.stock_filter_var.set(100)

    def actualizar_label_stock(self, *args):
        if 'lbl_filtro_stock' in self.widgets:
            valor_actual = self.stock_filter_var.get()
            self.widgets['lbl_filtro_stock'].config(text=f"Stock máx: {valor_actual}")
    
    def aplicar_filtros_inventario(self, event=None):
        termino_busqueda = self.widgets['entry_busqueda_libros'].get().strip()
        stock_maximo = self.stock_filter_var.get()

        query = "SELECT libro_id, titulo, autor, genero, editorial, encuadernacion, stock, precio FROM libros"
        condiciones = []
        params = []

        if termino_busqueda:
            condiciones.append("(titulo LIKE ? OR autor LIKE ?)")
            params.extend([f"%{termino_busqueda}%", f"%{termino_busqueda}%"])

        condiciones.append("stock <= ?")
        params.append(stock_maximo)
        
        if condiciones:
            query += " WHERE " + " AND ".join(condiciones)
        
        query += " ORDER BY titulo"
        self.refrescar_inventario(query=query, params=tuple(params))

    def limpiar_filtros_inventario(self, event=None):
        self.widgets['entry_busqueda_libros'].delete(0, tk.END)
        if 'slider_stock' in self.widgets:
            max_val = self.widgets['slider_stock'].cget("to")
            self.stock_filter_var.set(int(float(max_val)))
        self.aplicar_filtros_inventario()

    # --- RESTO DE LA LÓGICA ---
    def toggle_columnas_opcionales(self):
        columnas_base = ["asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag", "comentario"]
        opcionales_visibles = []
        if self.widgets['vars_opcionales']['rut'].get(): opcionales_visibles.append("rut")
        if self.widgets['vars_opcionales']['email'].get(): opcionales_visibles.append("email")
        if self.widgets['vars_opcionales']['telefono'].get(): opcionales_visibles.append("telefono")
        if self.widgets['vars_opcionales']['direccion'].get(): opcionales_visibles.append("direccion")
        self.widgets['tabla_clientes']['displaycolumns'] = columnas_base + opcionales_visibles

    def refrescar_todas_las_tablas(self):
        self.iniciar_sincronizacion_periodo()
        self.refrescar_inventario()

    def iniciar_sincronizacion_periodo(self):
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
            cursor.execute("PRAGMA table_info(clientes)")
            columnas_clientes = [col[1].lower() for col in cursor.fetchall()]
            
            mapa_opcionales = {'rut': 'rut', 'email': 'email', 'telefono': 'telefono', 'direccion': 'direccion'}
            if 'correo' in columnas_clientes and 'email' not in columnas_clientes: mapa_opcionales['email'] = 'correo'
            if 'correo_electronico' in columnas_clientes and 'email' not in columnas_clientes: mapa_opcionales['email'] = 'correo_electronico'
            
            select_extras = []
            for key, col_name in mapa_opcionales.items():
                if col_name in columnas_clientes: select_extras.append(f"c.{col_name}")
                else: select_extras.append("''") 
            
            str_extras = ", " + ", ".join(select_extras)
            
            meses_nums = [MAPEO_MESES[m] for m in meses_seleccionados]
            placeholders_meses = ",".join("?" * len(meses_nums))
            
            query = f"""
                SELECT a.asignacion_id, c.cliente_id, c.nombre, a.ano, a.mes, l.titulo, 
                       s.metodo_entrega, a.fecha_asignacion, a.estado_envio, a.pagado, a.envio_pagado, a.comentario {str_extras}
                FROM asignaciones a
                JOIN clientes c ON a.cliente_id = c.cliente_id
                JOIN suscripciones s ON c.cliente_id = s.cliente_id
                LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
                WHERE a.ano = ? AND a.mes IN ({placeholders_meses})
            """
            params = [ano_str] + meses_nums

            filtro_estado = self.widgets['cmb_filtro_estado'].get()
            filtro_pagado = self.widgets['cmb_filtro_pagado'].get()
            filtro_envio = self.widgets['cmb_filtro_envio'].get()
            filtro_libro = self.widgets['cmb_filtro_libro'].get()

            if filtro_estado != "TODOS":
                query += " AND a.estado_envio = ?"
                params.append(filtro_estado)
            if filtro_pagado != "Todos":
                query += " AND a.pagado = ?"
                params.append("TRUE" if filtro_pagado == "Si" else "FALSE")
            if filtro_envio != "Todos":
                query += " AND a.envio_pagado = ?"
                params.append("TRUE" if filtro_envio == "Si" else "FALSE")
            if filtro_libro == "Asignados":
                query += " AND l.titulo IS NOT NULL"
            elif filtro_libro == "Sin Asignar":
                query += " AND l.titulo IS NULL"
                
            query += " ORDER BY c.nombre"

            cursor.execute(query, params)
            for f in cursor.fetchall():
                fila_formateada = list(f)
                fila_formateada[5] = fila_formateada[5] if fila_formateada[5] else "SIN ASIGNACIÓN"
                fila_formateada[9] = "Si" if str(fila_formateada[9]).upper() == "TRUE" else "No"
                fila_formateada[10] = "Si" if str(fila_formateada[10]).upper() == "TRUE" else "No"
                tabla.insert("", "end", values=tuple(fila_formateada))
            conn.close()
        except Exception as e:
            messagebox.showerror("Error BD", f"Error al cargar asignaciones: {e}")

    def refrescar_inventario(self, widgets=None, query="SELECT libro_id, titulo, autor, genero, editorial, encuadernacion, stock, precio FROM libros ORDER BY titulo", params=()):
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
            if isinstance(entry, tk.Entry):
                entry.config(validate="none") 
                entry.delete(0, tk.END)
                entry.insert(0, valor if valor else "")
                entry.config(validate="key") 
            elif isinstance(entry, ttk.Combobox):
                entry.set(valor if valor else "")

    def limpiar_formulario_libro(self):
        self.widgets['lbl_status_libro'].config(text="Modo: Creando nuevo libro", fg="#C2185B")
        for entry in self.widgets['form_libro_entries'].values():
            if isinstance(entry, tk.Entry):
                entry.config(validate="none")
                entry.delete(0, tk.END)
                entry.config(validate="key")
            elif isinstance(entry, ttk.Combobox):
                entry.set("")
        self.widgets['form_libro_entries']['encuadernacion'].set('TAPA BLANDA')
        tabla = self.widgets['tabla_libros']
        if tabla.selection():
            tabla.selection_remove(tabla.selection()[0])

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
            if libro_id:
                cursor.execute("""
                    UPDATE libros SET titulo=?, autor=?, genero=?, editorial=?, encuadernacion=?, stock=?, precio=? 
                    WHERE libro_id=?
                """, (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], datos['encuadernacion'], 
                      int(datos['stock']), float(datos['precio'] if datos['precio'] else 0), libro_id))
            else:
                cursor.execute("""
                    INSERT INTO libros (titulo, autor, genero, editorial, encuadernacion, stock, precio) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], datos['encuadernacion'],
                      int(datos['stock']), float(datos['precio'] if datos['precio'] else 0)))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", "Libro guardado correctamente.")
            self.limpiar_formulario_libro()
            
            # Recargar configuración del slider por si el max stock cambió
            self.configurar_slider_stock() 
            self.aplicar_filtros_inventario()
            
        except Exception as e:
            messagebox.showerror("Error BD", str(e))

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
        except Exception as e:
            messagebox.showerror("Error BD", str(e))

    def exportar_excel(self):
        try:
            self.root.config(cursor="watch"); self.root.update()
            ruta = export.exportar_a_excel()
            self.root.config(cursor="")
            messagebox.showinfo("Éxito", f"Excel generado en:\n{ruta}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error", str(e))

    def disparar_script_externo(self, script, mensaje_exito):
        try:
            self.root.config(cursor="watch"); self.root.update()
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', script)
            resultado = subprocess.run(["python", script_path], capture_output=True, text=True, check=True, encoding='utf-8')
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
                
                if reporte.get("error"):
                    messagebox.showerror("Error en Script", reporte["error"])
                else:
                    messagebox.showinfo("Completado", mensaje)
            except (json.JSONDecodeError, IndexError):
                messagebox.showinfo("Completado", f"{mensaje_exito}\n(No se encontró un reporte JSON detallado)")
            self.refrescar_todas_las_tablas()
        except subprocess.CalledProcessError as e:
            self.root.config(cursor="")
            messagebox.showerror("Error de Ejecución", f"Fallo al ejecutar '{script}':\n{e.stderr}")
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error", f"Error inesperado al ejecutar '{script}':\n{e}")

    def sync_clientes(self): self.disparar_script_externo("sync.py", "Sincronización de clientes completada.")
    def importar_catalogo(self): self.disparar_script_externo("import_catalogo.py", "Importación de catálogo completada.")
    
    def ordenar_columna_inventario(self, col, reverse):
        """Ordena la tabla de libros al hacer clic en el encabezado."""
        if 'tabla_libros' not in self.widgets: return
        tabla = self.widgets['tabla_libros']
        
        # Obtener todos los valores de la columna clickeada
        lista_valores = [(tabla.set(k, col), k) for k in tabla.get_children('')]
        
        # 1. Limpiar las flechas de TODOS los encabezados para resetearlos
        for c in tabla['columns']:
            texto_original = c.replace("_", " ").title()
            # Restauramos el comando base
            tabla.heading(c, text=texto_original, command=lambda _col=c: self.ordenar_columna_inventario(_col, False))
            
        # 2. Intentar ordenar numéricamente (para stock, precio, id). Si falla, ordenar alfabéticamente.
        try:
            lista_valores.sort(key=lambda t: float(t[0]) if t[0] else 0.0, reverse=reverse)
        except ValueError:
            lista_valores.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        # 3. Reorganizar los elementos visualmente en la tabla
        for index, (val, k) in enumerate(lista_valores):
            tabla.move(k, '', index)

        # 4. Añadir la flecha visual al encabezado clickeado e invertir la acción para el próximo clic
        texto_heading = col.replace("_", " ").title()
        flecha = "  ▼" if reverse else "  ▲"
        tabla.heading(col, text=texto_heading + flecha, command=lambda _col=col: self.ordenar_columna_inventario(_col, not reverse))