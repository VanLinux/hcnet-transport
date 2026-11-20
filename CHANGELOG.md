# Historial de cambios

Todos los cambios relevantes de HCNet Transport se documentan en este archivo.

## [3.1.0] - 2026-11-20

### Añadido

- Apartado independiente de planeación de transporte público.
- Velocidad comercial, tiempos por sentido y de ciclo, frecuencia y espera media.
- Capacidad direccional, intervalo requerido, flota mínima y flota de reserva.
- Tiempos de ascenso, descenso y permanencia para intercambio simultáneo o secuencial.
- Espaciamiento y acceso peatonal, con óptimo aproximado y número recomendado de paradas.
- Capacidad de la parada crítica y diagnóstico de cuellos de botella operacionales.
- Balance oferta/demanda y efecto de la frecuencia sobre el flujo vial equivalente.
- Comparación gráfica y tabular de funciones lineal, BPR, Davidson y exponencial.
- Persistencia del módulo en el esquema 3 y resumen dentro del reporte LaTeX.

### Cambiado

- Navegación ampliada a ocho apartados y versión actualizada a 3.1.0.
- Caso demostrativo ampliado con una línea hipotética de transporte público.

## [3.0.0] - 2026-11-20

### Añadido

- Geometría configurable para intersecciones de tres o cuatro ramales.
- Identificación A–D y carriles de entrada/salida por ramal.
- Movimientos origen–destino asignables a carriles específicos y fases semafóricas.
- Velocidad de flujo libre, longitud de aproximación y espaciamiento vehicular en cola.
- Cola media, cola percentil 95 aproximada, longitud de cola y tiempo de viaje.
- Inventario de semáforos por ubicación, tipo, fase y movimientos controlados.
- Optimización de ciclo y reparto de verdes mediante el método de Webster.
- Diagrama de bandas verde–amarillo–rojo por semáforo.
- Persistencia y exportación de los nuevos datos en JSON, CSV y LaTeX.

### Cambiado

- Navegación reorganizada en siete apartados para separar geometría, movimientos y control.
- Esquema de proyecto actualizado a la versión 2 con migración de archivos anteriores.
- Caso demostrativo ampliado con ramales, fases y ocho grupos semafóricos.

## [2.0.0] - 2026-09-11

### Añadido

- Exportación de un reporte técnico completo y compilable en LaTeX.
- Portada e identificación del analista dentro del reporte.
- Resultados generales, tabla comparativa, memoria por grupo y diagnóstico en el `.tex`.
- Pantalla inicial de presentación con alcance, licencia, plataforma y desarrollador.

### Cambiado

- Paleta visual neutral con mayor contraste para menús, pestañas, títulos y controles.
- Eliminación de los acentos amarillos de la interfaz y del icono.
- Reordenamiento de la navegación para presentar el alcance antes de capturar datos.
- Renombrado de la memoria como **Reporte técnico**.

## [1.0.0] - 2026-09-11

### Añadido

- Primera aplicación de escritorio para Linux basada en Python y Qt.
- Proyecto para intersecciones semaforizadas aisladas con control de tiempo fijo.
- Cálculo transparente de factores de ajuste, flujo de saturación, capacidad,
  grado de saturación, demora de control y nivel de servicio.
- Resumen de la intersección, resultados por grupo de carriles y memoria de cálculo.
- Apertura y guardado de proyectos en JSON.
- Exportación de resultados en CSV.
- Caso de demostración precargado y archivo de ejemplo.
- Validaciones de dominio, advertencias metodológicas y pruebas automatizadas.

[2.0.0]: https://github.com/VanLinux/hcnet-transport/releases/tag/v2.0.0
[1.0.0]: https://github.com/VanLinux/hcnet-transport/releases/tag/v1.0.0
[3.0.0]: https://github.com/VanLinux/hcnet-transport/releases/tag/v3.0.0
[3.1.0]: https://github.com/VanLinux/hcnet-transport/releases/tag/v3.1.0
