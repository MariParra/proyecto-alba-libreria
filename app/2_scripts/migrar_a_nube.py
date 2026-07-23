import sqlite3
import psycopg2
import os
from dotenv import load_dotenv

# Configuración de rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_LOCAL = os.path.join(BASE_DIR, "app", "2_database", "libreria.db")
ENV_PATH = os.path.join(BASE_DIR, ".env")

def migrar_datos():
    load_dotenv(ENV_PATH)
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("ERROR: No se encontró DATABASE_URL en el archivo .env")
        return

    # Adaptar prefijo si es necesario (para compatibilidad con Heroku/Supabase)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    print("🔌 Conectando a bases de datos...")
    conn_local = sqlite3.connect(DB_LOCAL)
    cur_local = conn_local.cursor()
    
    try:
        conn_nube = psycopg2.connect(db_url)
        cur_nube = conn_nube.cursor()
    except Exception as e:
        print(f"ERROR: No se pudo conectar a la nube. Revisa tu DATABASE_URL. Detalle: {e}")
        return

    print("Creando estructura de tablas en la nube...")
    # 1. Crear Tablas en PostgreSQL (con sintaxis correcta SERIAL para IDs automáticos)
    tablas_pg = """
    DROP TABLE IF EXISTS clientes, libros, suscripciones, asignaciones, librero_historico, registro_ventas, meses_cerrados CASCADE;
    CREATE TABLE clientes (
        cliente_id SERIAL PRIMARY KEY, nombre TEXT, email TEXT, telefono TEXT, 
        instagram TEXT, direccion TEXT, rut TEXT, status TEXT
    );
    CREATE TABLE libros (
        libro_id SERIAL PRIMARY KEY, titulo TEXT, autor TEXT, genero TEXT, 
        editorial TEXT, encuadernacion TEXT, stock INTEGER, precio REAL, precio_original REAL
    );
    
    CREATE TABLE suscripciones (
        suscripcion_id SERIAL PRIMARY KEY,
        cliente_id INTEGER,
        fecha_pago TEXT,
        metodo_entrega TEXT,
        generos_preferencia TEXT
    );
    CREATE TABLE asignaciones (
        asignacion_id SERIAL PRIMARY KEY, cliente_id INTEGER, libro_suscripcion_id INTEGER, 
        ano INTEGER, mes INTEGER, extras TEXT, fecha_asignacion TEXT, estado_envio TEXT, 
        pagado TEXT, envio_pagado TEXT, comentario TEXT
    );
    CREATE TABLE librero_historico (
        registro_id SERIAL PRIMARY KEY, cliente_id INTEGER, libro_id INTEGER, 
        autor_historico TEXT, origen TEXT
    );
    CREATE TABLE registro_ventas (
        venta_id SERIAL PRIMARY KEY, cliente_id INTEGER, fecha_venta TEXT, 
        libros_vendidos TEXT, subtotal_libros REAL, valor_envio REAL, 
        monto_final REAL, metodo_envio TEXT, comentario TEXT
    );
    CREATE TABLE meses_cerrados (
        id SERIAL PRIMARY KEY, ano INTEGER, mes INTEGER, UNIQUE(ano, mes)
    );
    """
    cur_nube.execute(tablas_pg)
    
    # 2. Copiar Datos y Actualizar Secuencias de IDs
    tablas_a_migrar = ['clientes', 'libros', 'suscripciones', 'asignaciones', 'librero_historico', 'registro_ventas', 'meses_cerrados']
    
    for tabla in tablas_a_migrar:
        print(f"Migrando tabla: {tabla}...")
        try:
            cur_local.execute(f"SELECT * FROM {tabla}")
            filas = cur_local.fetchall()
            
            if filas:
                # Generar los %s dinámicamente
                placeholders = ', '.join(['%s'] * len(filas[0]))
                insert_query = f"INSERT INTO {tabla} VALUES ({placeholders})"
                
                # Insertar los datos
                cur_nube.executemany(insert_query, filas)
                
                if tabla == "clientes": pk_col = "cliente_id"
                elif tabla == "librero_historico": pk_col = "registro_id"
                elif tabla == "registro_ventas": pk_col = "venta_id"
                elif tabla == "meses_cerrados": pk_col = "id"
                else: pk_col = f"{tabla[:-2] if tabla.endswith('es') else tabla[:-1]}_id"

                
                
                # 1. Obtener el ID máximo de la tabla actual de forma segura
                cur_nube.execute(f"SELECT MAX({pk_col}) FROM {tabla}")
                max_id_result = cur_nube.fetchone()
                max_id = max_id_result[0] if max_id_result and max_id_result[0] is not None else 1

                # 2. Actualizar la secuencia de PostgreSQL para que empiece desde el siguiente número
                sequence_name = f"{tabla}_{pk_col}_seq" # Nombre estándar de la secuencia en PostgreSQL
                cur_nube.execute(f"SELECT setval('{sequence_name}', {max_id})")
                
        except sqlite3.OperationalError:
            print(f"   -> Tabla '{tabla}' no encontrada en la base de datos local. Omitiendo.")
            continue
            
    conn_nube.commit()
    conn_local.close()
    conn_nube.close()
    
    print("\n¡MIGRACIÓN COMPLETADA CON ÉXITO!.")

if __name__ == "__main__":
    migrar_datos()