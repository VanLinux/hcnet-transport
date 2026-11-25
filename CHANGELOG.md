# Historial de cambios

Todos los cambios relevantes de HCNet Transport se documentan en este archivo.

## 3.6.0

- Constructor interactivo de rotondas con hasta ocho ramales, carriles independientes, edición de azimut y una sola demanda OD.
- Capacidad convencional HCM de uno y dos carriles, brechas, regresión y Kimber. Demora de control, LOS, acumulación, P95, ajuste y validación de capacidades.
- Diseño preliminar con dimensiones fijas, cribado de geometría, comparación de intervenciones y conversión desde intersecciones HCNet.
- Experimentos vehiculares SUMO por semillas y demanda común, colas reproducibles y emisiones. Exportación de insumos, resultados, SVG y reportes LaTeX.
- Nueve ejercicios explícitos y persistencia en esquema 8 con carga de proyectos anteriores.

## 3.5.0

- Navegación directa entre áreas de trabajo en la barra superior.
- Captura y resultados de transporte público en paneles ampliables o en paralelo. Formularios adaptables y estaciones en pestañas por sentido.
- Desplegables que muestran todas las opciones cuando caben en la pantalla.
- Transporte público con cálculo específico, análisis integral y recomendación preliminar de tecnología.
- Ocho sistemas y 16 fichas vehiculares con fuentes. Fichas de usuario reutilizables y editor gráfico de puertas por carro.
- Dimensionamiento de frecuencia, oferta y flota. Perfiles de carga por sentido, estaciones, esquema propio para telecabinas, espera y evaluación económica.
- Congestión lineal, BPR, Davidson y exponencial, con calibración y validación por CSV. Comparación de configuraciones y optimización con restricciones.
- Microsimulación de corredores viales con la instalación compartida de SUMO. Resultados de viajes, paradas, intervalos y colas por carril seleccionado.
- Siete casos demostrativos de carga explícita. Esquema 7 de `.hcnet`, lectura de proyectos anteriores, reportes carta en LaTeX y exportación CSV.

## 3.4.0

- Microsimulación opcional de intersecciones semaforizadas con SUMO en segundo plano.
- Factores empíricos por carril y calibración con flujo de saturación observado.
- Reproducción de colas de SUMO por ramal o carril, sincronizada con las señales reales.
- Evaluación de emisiones de SUMO y estimación independiente de escape en ralentí.
- Guardado de estudios por escenario, series comprimidas y ampliación de CSV y LaTeX.

## 3.3.2

- La intersección semaforizada amplía el panel de la pestaña elegida y deja las pestañas del otro panel a la vista.
- HCNet abre en Inicio y alcance.

## 3.3.1

- Rueda del ratón para desplazarse por los formularios. Edición de campos con flechas y teclado.
- Mayor contraste en modo claro y más espacio inicial para la captura en la vista de intersección.
- Panel lateral con el estado del cálculo, indicadores y una guía de la pestaña seleccionada.
- Diagramas de intersección y fases centrados en LaTeX. Preámbulo sin `inputenc` ni `fontenc`.

## 3.3.0

- Navegación contextual con paneles ajustables, esquema interactivo y tema claro u oscuro.
- Aforo, PHF y pesados por movimiento. Fases editables por tarjetas y bandas reproducibles.
- Evaluación original explícita, con alternativas comparables e historial al editar entradas.
- Webster, búsqueda directa con Akçelik, genético y búsqueda multiobjetivo con frente de Pareto.
- Reasignación de grupos compatibles con bloqueos por grupo en Genético y Pareto.
- Archivos `.hcnet` con fases y escenarios independientes. Lectura de esquemas anteriores.
- Informes LaTeX carta con bandas a color, trayectorias y comparativas. Informe general por proyecto.

## 3.2.0

- Ventana adaptable, formularios desplazables y altura mínima para los campos de captura.
- Inicio sin caso de ejemplo. La carga demostrativa se elige en el menú Proyecto.
- Proyectos `.hcnet` con datos y estado de los módulos, incluido el plan semafórico.
- Pestañas identificadas por relación entre cálculos y exportación LaTeX por módulo.
- Intersecciones con dos a cuatro ramales y azimut editable.
- Módulo independiente de rotondas de un carril con matriz OD, análisis operacional
  y predimensionamiento geométrico.

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
