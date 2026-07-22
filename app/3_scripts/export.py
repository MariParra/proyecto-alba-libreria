import pandas as pd
from tkinter import filedialog
import conexion

def exportar_a_excel():
    """
    Exporta Asignaciones, Clientes, Inventario y el Historial de Ventas a un único
    archivo Excel con múltiples hojas, previniendo errores de formato.
    """
    try:
        conn = conexion.conectar_db()
        
        # --- 1. DATOS DE ASIGNACIONES ---
        query_asig = """
            SELECT a.asignacion_id AS "ID Asignación", c.cliente_id AS "ID Cliente", ...
            FROM asignaciones a ...
        """
        df_asig = pd.read_sql_query(query_asig, conn)
        
        # --- 2. DATOS DE CLIENTES ---
        query_cli = "SELECT cliente_id AS \"ID Cliente\", nombre, ... FROM clientes ORDER BY nombre;"
        df_cli = pd.read_sql_query(query_cli, conn)

        # --- 3. DATOS DE INVENTARIO ---
        query_lib = "SELECT libro_id AS \"ID Libro\", titulo, ... FROM libros ORDER BY titulo;"
        df_lib = pd.read_sql_query(query_lib, conn)

        # --- 4. NUEVO: HISTORIAL DE VENTAS DIRECTAS ---
        query_ventas = """
            SELECT 
                venta_id AS "ID Venta",
                fecha_venta AS "Fecha",
                (SELECT nombre FROM clientes c WHERE c.cliente_id = rv.cliente_id) AS "Nombre Cliente",
                libros_vendidos AS "Libros",
                subtotal_libros AS "Subtotal ($)",
                valor_envio AS "Envío ($)",
                monto_final AS "Monto Final ($)",
                metodo_envio AS "Método Envío",
                comentario AS "Comentario"
            FROM registro_ventas rv
            ORDER BY venta_id DESC;
        """
        df_ventas = pd.read_sql_query(query_ventas, conn)

        conn.close()

        # --- LIMPIEZA DE TODOS LOS DATAFRAMES ---
        tablas = [df_asig, df_cli, df_lib, df_ventas] # Añadimos la nueva tabla a la limpieza
        for df in tablas:
            for col in df.columns:
                df[col] = df[col].astype(str)
            df.replace(['None', 'nan', 'NaT', 'NaN', 'null', 'NULL'], '', inplace=True)
            
    except Exception as e:
        raise Exception(f"Error al leer los datos de la base de datos: {e}")

    try:
        ruta_guardado = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos de Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
            title="Guardar Reporte General de Librería",
            initialfile="Reporte_General_Libreria.xlsx"
        )

        if not ruta_guardado:
            return "Exportación cancelada por el usuario."

        # --- GUARDAR CON MÚLTIPLES HOJAS (Ahora con 4 pestañas) ---
        with pd.ExcelWriter(ruta_guardado, engine='openpyxl') as writer:
            df_asig.to_excel(writer, sheet_name='Asignaciones', index=False)
            df_cli.to_excel(writer, sheet_name='Clientes', index=False)
            df_lib.to_excel(writer, sheet_name='Inventario', index=False)
            df_ventas.to_excel(writer, sheet_name='Historial de Ventas', index=False)
        
        return ruta_guardado

    except Exception as e:
        raise Exception(f"Error al guardar el archivo Excel: {e}")

