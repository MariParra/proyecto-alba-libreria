-- 1. PRIMERO: Devolver el stock al inventario de los libros asignados en Agosto
UPDATE libros 
SET stock = stock + (
    SELECT COUNT(*) 
    FROM asignaciones 
    WHERE asignaciones.libro_suscripcion_id = libros.libro_id 
        AND asignaciones.ano = '2026' 
        AND asignaciones.mes = '08'
)
WHERE libro_id IN (
    SELECT libro_suscripcion_id 
    FROM asignaciones 
    WHERE ano = '2026' AND mes = '08' AND libro_suscripcion_id IS NOT NULL
);

-- 2. SEGUNDO: Eliminar todas las filas de asignación de Agosto 2026
DELETE FROM asignaciones WHERE ano = '2026' AND mes = '08';