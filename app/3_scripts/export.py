import pandas as pd
import os
from tkinter import filedialog
import conexion

def exportar_a_excel():
    """
    Exporta Asignaciones, Clientes e Inventario a un único archivo Excel
    con múltiples hojas (pestañas), previniendo errores de formato.
    """
    try:
        conn = conexion.conectar_db()
        
        # --- 1. DATOS DE ASIGNACIONES ---
        query_asig = """
            SELECT 
                a.asignacion_id AS "ID Asignación",
                c.cliente_id AS "ID Cliente",
                c.nombre AS "Nombre Cliente",
                a.ano AS "Año",
                a.mes AS "Mes",
                l.titulo AS "Libro Asignado",
                a.extras AS "Extras",
                s.metodo_entrega AS "Tipo de Envío",
                a.fecha_asignacion AS "Fecha Asignación",
                a.estado_envio AS "Estado",
                CASE WHEN a.pagado = 'TRUE' THEN 'Si' ELSE 'No' END AS "Pagado",
                CASE WHEN a.envio_pagado = 'TRUE' THEN 'Si' ELSE 'No' END AS "Envío Pagado",
                a.comentario AS "Comentario",
                c.rut AS "RUT",
                c.email AS "Email",
                c.telefono AS "Teléfono",
                c.direccion AS "Dirección"
            FROM asignaciones a
            JOIN clientes c ON a.cliente_id = c.cliente_id
            JOIN suscripciones s ON c.cliente_id = s.cliente_id
            LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
            ORDER BY a.ano, a.mes, c.nombre;
        """
        df_asig = pd.read_sql_query(query_asig, conn)
        
        # --- 2. DATOS DE CLIENTES ---
        query_cli = """
            SELECT 
                cliente_id AS "ID Cliente", 
                nombre AS "Nombre", 
                email AS "Email", 
                telefono AS "Teléfono", 
                instagram AS "Instagram", 
                direccion AS "Dirección", 
                rut AS "RUT", 
                status AS "Estado" 
            FROM clientes 
            ORDER BY nombre;
        """
        df_cli = pd.read_sql_query(query_cli, conn)

        # --- 3. DATOS DE INVENTARIO (LIBROS) ---
        query_lib = """
            SELECT 
                libro_id AS "ID Libro", 
                titulo AS "Título", 
                autor AS "Autor", 
                genero AS "Género", 
                editorial AS "Editorial", 
                encuadernacion AS "Encuadernación", 
                stock AS "Stock", 
                precio AS "Precio", 
                precio_original AS "Precio Original" 
            FROM libros 
            ORDER BY titulo;
        """
        df_lib = pd.read_sql_query(query_lib, conn)

        conn.close()

        # --- LIMPIEZA DE LOS 3 DATAFRAMES (Evita el error 'float has no len') ---
        tablas = [df_asig, df_cli, df_lib]
        for df in tablas:
            for col in df.columns:
                df[col] = df[col].astype(str)
            df.replace(['None', 'nan', 'NaT', 'NaN', 'null', 'NULL'], '', inplace=True)
            
    except Exception as e:
        raise Exception(f"Error al leer los datos de la base de datos: {e}")

    try:
        # Pedir al usuario dónde guardar el archivo
        ruta_guardado = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos de Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
            title="Guardar Reporte General de Librería",
            initialfile="Reporte_General_Libreria.xlsx"
        )

        if not ruta_guardado:
            return "Exportación cancelada por el usuario."

        # --- GUARDAR CON MÚLTIPLES HOJAS (ExcelWriter) ---
        with pd.ExcelWriter(ruta_guardado, engine='openpyxl') as writer:
            df_asig.to_excel(writer, sheet_name='Asignaciones', index=False)
            df_cli.to_excel(writer, sheet_name='Clientes', index=False)
            df_lib.to_excel(writer, sheet_name='Inventario', index=False)
        
        return ruta_guardado

    except Exception as e:
        raise Exception(f"Error al guardar el archivo Excel: {e}")