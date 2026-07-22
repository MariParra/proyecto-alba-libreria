import pandas as pd
import os
from tkinter import filedialog
import conexion

def exportar_a_excel():
    """
    Exporta la vista actual de la tabla de asignaciones a un archivo Excel,
    asegurándose de que todos los datos se traten como texto para evitar errores.
    """
    try:
        conn = conexion.conectar_db()
        query = """
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
        
        df = pd.read_sql_query(query, conn)
        conn.close()

        # --- LA CORRECCIÓN CLAVE ESTÁ AQUÍ ---
        # Convertimos todas las columnas a tipo 'str' (texto) ANTES de procesarlas.
        # Esto elimina los `NaN` (float) y los convierte en strings vacíos o "None".
        for col in df.columns:
            df[col] = df[col].astype(str)

        # Reemplazamos los 'None' o 'nan' textuales por celdas vacías para un Excel más limpio
        df.replace(['None', 'nan', 'NaT'], '', inplace=True)
        
        # Ahora el resto del proceso es seguro
        # ...

    except Exception as e:
        # Si la lectura de la BD falla, devolvemos el error
        raise Exception(f"Error al leer los datos de la base de datos: {e}")

    try:
        # Pedir al usuario dónde guardar el archivo
        ruta_guardado = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos de Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
            title="Guardar reporte de asignaciones",
            initialfile="Reporte_Asignaciones.xlsx"
        )

        if not ruta_guardado:
            # El usuario canceló el diálogo
            return "Exportación cancelada por el usuario."

        # Exportar el DataFrame a Excel
        df.to_excel(ruta_guardado, index=False, engine='openpyxl')
        
        return ruta_guardado

    except Exception as e:
        # Si falla la escritura del archivo, devolvemos el error
        raise Exception(f"Error al guardar el archivo Excel: {e}")