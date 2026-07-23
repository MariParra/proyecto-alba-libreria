import pandas as pd
from tkinter import filedialog

def exportar_a_excel(datos_asig, cols_asig, datos_cli, cols_cli, datos_inv, cols_inv, datos_vta, cols_vta):
    """
    Recibe los datos y columnas de las tablas y los exporta a un Excel multi-hoja.
    """
    try:
        df_asig = pd.DataFrame(datos_asig, columns=cols_asig)
        df_cli = pd.DataFrame(datos_cli, columns=cols_cli)
        df_inv = pd.DataFrame(datos_inv, columns=cols_inv)
        df_vta = pd.DataFrame(datos_vta, columns=cols_vta)

        ruta_guardado = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Archivos de Excel", "*.xlsx")],
            title="Guardar Reporte General",
            initialfile="Reporte_General_Libreria.xlsx"
        )

        if not ruta_guardado:
            return "Exportación cancelada."

        with pd.ExcelWriter(ruta_guardado, engine='openpyxl') as writer:
            df_asig.to_excel(writer, sheet_name='Asignaciones', index=False)
            df_cli.to_excel(writer, sheet_name='Clientes', index=False)
            df_inv.to_excel(writer, sheet_name='Inventario', index=False)
            df_vta.to_excel(writer, sheet_name='Historial de Ventas', index=False)
        
        return ruta_guardado

    except Exception as e:
        raise Exception(f"Error al guardar el archivo Excel: {e}")