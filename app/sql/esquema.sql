-- TABLA DE CLIENTES
CREATE TABLE clientes (
    cliente_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    telefono TEXT DEFAULT 'SIN INFORMACION',
    instagram TEXT DEFAULT 'SIN INFORMACION',
    direccion TEXT DEFAULT 'SIN INFORMACION',
    rut TEXT DEFAULT 'SIN INFORMACION',
    status TEXT DEFAULT 'ACTIVA',
    fecha_nacimiento TEXT DEFAULT 'SIN INFORMACION' -- (Creada automáticamente por el motor de migraciones)
);

-- TABLA DE SUSCRIPCIONES
CREATE TABLE suscripciones (
    suscripcion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER UNIQUE,
    fecha_pago TEXT DEFAULT 'SIN INFORMACION',
    metodo_entrega TEXT DEFAULT 'SIN INFORMACION',
    generos_preferencia TEXT DEFAULT 'SIN INFORMACION',
    FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id)
);

-- TABLA DE LIBROS
CREATE TABLE libros (
    libro_id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    autor TEXT DEFAULT 'SIN INFORMACION',
    genero TEXT DEFAULT 'SIN INFORMACION',
    precio INTEGER DEFAULT 0,
    stock INTEGER DEFAULT 0,
    editorial TEXT DEFAULT 'SIN INFORMACION' -- (Creada automáticamente por el script de catálogo)
);

-- TABLA DE ASIGNACIONES
CREATE TABLE asignaciones (
    asignacion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    libro_suscripcion_id INTEGER,
    libros_extras TEXT DEFAULT 'SIN EXTRAS',
    mes_periodo TEXT NOT NULL,
    pagado TEXT DEFAULT 'FALSE',
    envio_pagado TEXT DEFAULT 'FALSE',
    estado_envio TEXT DEFAULT 'Pendiente', 
    fecha_asignacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id),
    FOREIGN KEY (libro_suscripcion_id) REFERENCES libros(libro_id),
    UNIQUE(cliente_id, mes_periodo)
);
