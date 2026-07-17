import pandas as pd
import os
from datetime import datetime
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "2_database", "libreria.db"))
OUTPUT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "4_output_reports"))

def obtener_dataframes():
    conn = sqlite3.connect(DB_PATH)
    
    # AÑADIDO: 'encuadernacion' en la consulta de inventario
    df_inventario = pd.read_sql_query("SELECT libro_id, titulo, autor, genero, editorial, encuadernacion, stock, precio FROM libros ORDER BY titulo", conn)
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(clientes)")
    columnas_clientes = [col[1].lower() for col in cursor.fetchall()]
    
    posibles_opcionales = ['rut', 'email', 'correo', 'correo_electronico', 'telefono', 'celular', 'direccion']
    campos_extra = []
    for campo in posibles_opcionales:
        if campo in columnas_clientes: 
            if 'email' in campo and any('email' in c for c in campos_extra):
                continue
            campos_extra.append(f"c.{campo}")
            
    str_campos_extra = ", " + ", ".join(campos_extra) if campos_extra else ""

    # AÑADIDO: 'a.comentario' en la consulta de asignaciones
    query_asignaciones = f"""
        SELECT a.asignacion_id, c.cliente_id, c.nombre, a.ano, a.mes {str_campos_extra}, l.titulo AS libro, 
            s.metodo_entrega AS tipo_envio, a.fecha_asignacion, a.estado_envio, a.pagado, a.envio_pagado, a.comentario
        FROM asignaciones a
        JOIN clientes c ON a.cliente_id = c.cliente_id
        JOIN suscripciones s ON c.cliente_id = s.cliente_id
        LEFT JOIN libros l ON a.libro_suscripcion_id = l.libro_id
        ORDER BY a.ano DESC, a.mes DESC, c.nombre
    """
    
    df_asignaciones = pd.read_sql_query(query_asignaciones, conn)
    conn.close()
    
    df_asignaciones['libro'] = df_asignaciones['libro'].fillna("SIN ASIGNACIÓN")
    return df_inventario, df_asignaciones

def exportar_a_excel():
    try:
        df_inventario, df_asignaciones = obtener_dataframes()
        if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(OUTPUT_DIR, f"Reporte_Libreria_{timestamp}.xlsx")

        with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
            df_inventario.to_excel(writer, sheet_name='Inventario', index=False)
            df_asignaciones.to_excel(writer, sheet_name='Asignaciones', index=False)
            
            # Auto-ajuste de columnas
            for sheet_name, df in zip(['Inventario', 'Asignaciones'], [df_inventario, df_asignaciones]):
                worksheet = writer.sheets[sheet_name]
                for idx, col in enumerate(df.columns):
                    series = df[col]
                    max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2
                    worksheet.set_column(idx, idx, max_len)
                    
        return output_filename
    except Exception as e:
        raise Exception(f"Error en exportación a Excel: {e}")