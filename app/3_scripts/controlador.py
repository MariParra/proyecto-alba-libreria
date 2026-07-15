import tkinter as tk
from tkinter import messagebox
import json
import os
import datetime
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
            'cmd_exportar_gsheets': self.exportar_gsheets,
            'cmd_guardar_libro': self.guardar_libro,
            'cmd_limpiar_form_libro': self.limpiar_formulario_libro,
            'cmd_eliminar_libro': self.eliminar_libro,
            'cmd_buscar_libro': self.buscar_libro,
            'cmd_quitar_filtro': self.quitar_filtro,
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
        
        self.refrescar_todas_las_tablas()
        
    def toggle_columnas_opcionales(self):
        columnas_base = ["asignacion_id", "cliente_id", "nombre", "ano", "mes", "libro", "tipo_envio", "fecha_asig", "estado", "pagado", "envio_pag"]
        opcionales_visibles = []
        if self.widgets['vars_opcionales']['rut'].get(): opcionales_visibles.append("rut")
        if self.widgets['vars_opcionales']['email'].get(): opcionales_visibles.append("email")
        if self.widgets['vars_opcionales']['telefono'].get(): opcionales_visibles.append("telefono")
        if self.widgets['vars_opcionales']['direccion'].get(): opcionales_visibles.append("direccion")
        self.widgets['tabla_clientes']['displaycolumns'] = columnas_base + opcionales_visibles

    def refrescar_todas_las_tablas(self):
        self.iniciar_sincronizacion_periodo()
        self.refrescar_inventario()

    # --- NUEVA LÓGICA DE AUTOCOMPLETADO INTELIGENTE ---
    def refrescar_listas_autocompletado(self):
        try:
            conn = conexion.conectar_db()
            cursor = conn.cursor()
            
            for campo in ['autor', 'genero', 'editorial']:
                cursor.execute(f"SELECT DISTINCT {campo} FROM libros WHERE {campo} IS NOT NULL AND {campo} != ''")
                valores = [str(row[0]) for row in cursor.fetchall()]
                
                cb = self.widgets['form_libro_entries'][campo]
                cb['values'] = valores
                
                def on_keyrelease(event, combobox=cb, lista=valores):
                    # No interrumpir el uso normal de las flechas, Tab o Enter
                    if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab', 'Shift_L', 'Shift_R'):
                        return
                    
                    value = combobox.get()
                    if value == '':
                        combobox['values'] = lista
                    else:
                        # Filtrar coincidencias
                        data = [item for item in lista if value.lower() in item.lower()]
                        combobox['values'] = data
                        
                        # Si hay coincidencias, abrir la lista
                        if data:
                            combobox.event_generate('<Down>')
                            
                    # Mantener el foco en la caja de texto
                    combobox.focus()
                    combobox.icursor(tk.END)
                
                cb.bind('<KeyRelease>', on_keyrelease)
                
            conn.close()
        except Exception as e:
            print("Error cargando listas de autocompletado:", e)

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
                       s.metodo_entrega, a.fecha_asignacion, a.estado_envio, a.pagado, a.envio_pagado {str_extras}
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

    def refrescar_inventario(self, widgets=None, query="SELECT libro_id, titulo, autor, genero, editorial, stock, precio FROM libros ORDER BY titulo", params=()):
        if widgets is None: widgets = self.widgets
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
            stock_total = sum(int(fila[5]) for fila in self.datos_inventario_actual if fila[5])
            widgets['lbl_stock_total'].config(text=f"Unidades Totales en Inventario: {stock_total}")
            
            # Recargar las listas del autocompletado
            self.refrescar_listas_autocompletado()
            
        except Exception as e:
            print(f"Error al cargar inventario: {e}")

    def buscar_libro(self):
        termino = self.widgets['entry_busqueda_libros'].get().strip()
        if not termino: return self.quitar_filtro()
        query = "SELECT libro_id, titulo, autor, genero, editorial, stock, precio FROM libros WHERE titulo LIKE ? OR autor LIKE ? ORDER BY titulo"
        self.refrescar_inventario(query=query, params=(f"%{termino}%", f"%{termino}%"))

    def quitar_filtro(self):
        self.widgets['entry_busqueda_libros'].delete(0, tk.END)
        self.refrescar_inventario()

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
        tabla = self.widgets['tabla_libros']
        if tabla.selection():
            tabla.selection_remove(tabla.selection()[0])

    def guardar_libro(self):
        entries = self.widgets['form_libro_entries']
        datos = {col_id: entry.get().strip() for col_id, entry in entries.items()}
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
                cursor.execute("UPDATE libros SET titulo=?, autor=?, genero=?, editorial=?, stock=?, precio=? WHERE libro_id=?", 
                               (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], int(datos['stock']), float(datos['precio'] if datos['precio'] else 0), libro_id))
            else:
                cursor.execute("INSERT INTO libros (titulo, autor, genero, editorial, stock, precio) VALUES (?, ?, ?, ?, ?, ?)", 
                               (datos['titulo'], datos['autor'], datos['genero'], datos['editorial'], int(datos['stock']), float(datos['precio'] if datos['precio'] else 0)))
            conn.commit()
            conn.close()
            messagebox.showinfo("Éxito", "Libro guardado correctamente.")
            self.limpiar_formulario_libro()
            self.refrescar_inventario()
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
            self.refrescar_inventario()
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

    def exportar_gsheets(self):
        try:
            self.root.config(cursor="watch"); self.root.update()
            url = export.exportar_a_google_sheets()
            self.root.config(cursor="")
            win = tk.Toplevel(self.root)
            win.title("Google Sheet Generado")
            tk.Label(win, text="Reporte exportado.", font=("Helvetica", 10, "bold")).pack(pady=10)
            entry = tk.Entry(win, width=60)
            entry.pack(padx=20, pady=5)
            entry.insert(0, url)
            entry.config(state="readonly") 
            tk.Button(win, text="Cerrar", command=win.destroy).pack(pady=10)
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error", str(e))

    def disparar_script_externo(self, script, mensaje_exito):
        try:
            self.root.config(cursor="watch"); self.root.update()
            output = conexion.ejecutar_script_externo(os.path.join(os.path.dirname(os.path.abspath(__file__)), script))
            self.root.config(cursor="")
            try:
                reporte = json.loads(output)
                if reporte.get("error"): messagebox.showerror("Error", reporte["error"])
                else: messagebox.showinfo("Completado", f"{mensaje_exito}\nProcesados: {reporte.get('clientes_procesados', 0)}\nNuevos: {reporte.get('nuevos_clientes', 0)}\nActualizados: {reporte.get('clientes_actualizados', 0)}")
            except: messagebox.showinfo("Completado", mensaje_exito)
            self.refrescar_todas_las_tablas()
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Error", str(e))

    def sync_clientes(self): self.disparar_script_externo("sync.py", "Sincronización completada.")
    def importar_catalogo(self): self.disparar_script_externo("import_catalogo.py", "Catálogo cargado.")
