-- 1. Limpiar la tabla de asignaciones para evitar conflictos de claves foráneas
DELETE FROM asignaciones;

-- 2. Limpiar la tabla de libros por completo
DELETE FROM libros;

-- 3. Reiniciar los contadores automáticos para que los nuevos IDs vuelvan a empezar desde 1
DELETE FROM sqlite_sequence WHERE name IN ('asignaciones', 'libros');
