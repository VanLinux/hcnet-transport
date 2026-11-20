# HCNet Transport

**Highway Capacity and Network Evaluation Tool**

Software libre y educativo para analizar capacidad, desempeño operacional y nivel de
servicio de instalaciones de transporte mediante metodologías del *Highway Capacity
Manual* (HCM).

[![Pruebas](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml/badge.svg)](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml)
[![Licencia: GPL v3](https://img.shields.io/badge/Licencia-GPLv3-blue.svg)](LICENSE)
[![Versión](https://img.shields.io/badge/versión-3.1.0-3f444b.svg)](CHANGELOG.md)

## Versión 3.1

HCNet Transport 3.0 analiza **intersecciones semaforizadas aisladas de tres o cuatro
ramales con control de tiempo fijo**. La geometría se describe con letras A–D y cada
movimiento se captura como un recorrido origen–destino, por ejemplo `A → C`, asignado
a carriles y fases concretas.

Calcula, por grupo de carriles:

- flujo de demanda ajustado por FHMD/PHF;
- factores por ancho, vehículos pesados, pendiente, estacionamiento y autobuses;
- flujo de saturación ajustado;
- capacidad y grado de saturación, `X = v/c`;
- demora uniforme `d₁`, incremental `d₂` y por cola inicial `d₃`;
- demora de control y nivel de servicio A–F;
- llegadas estimadas durante el rojo y demanda residual diagnóstica;
- cola media, cola percentil 95 aproximada y longitud de almacenamiento;
- tiempo de recorrido libre y tiempo de viaje con demora.

También proporciona:

- resumen ponderado de la intersección;
- gráfica comparativa del grado de saturación;
- inventario de semáforos por ramal, tipo, fase y movimientos controlados;
- optimización de ciclo y reparto de verdes con el método de Webster;
- diagrama de bandas verde–amarillo–rojo por semáforo;
- memoria de cálculo con ecuaciones y sustituciones;
- validación de entradas y advertencias operacionales;
- proyectos editables en JSON, resultados CSV y reporte técnico en LaTeX;
- caso demostrativo hipotético de Ciudad de México.

### Transporte público

El apartado independiente **Transporte público** vincula oferta, demanda e
infraestructura de parada para una línea bidireccional. Calcula:

- velocidad de operación y velocidad comercial;
- tiempo por sentido, tiempo de ciclo y espera media;
- frecuencia, intervalo requerido por demanda y capacidad de línea;
- flota mínima, reserva y flota total;
- margen y relación oferta/demanda;
- tiempos de ascenso, descenso y permanencia en parada;
- espaciamiento actual, acceso peatonal medio, espaciamiento óptimo aproximado y
  número recomendado de paradas;
- capacidad de la parada crítica en autobuses y pasajeros por hora;
- flujo vial equivalente al incorporar la frecuencia de autobuses;
- comparación gráfica y tabular de funciones lineal, BPR, Davidson y exponencial.

La lógica toma como referencia conceptual la separación entre demanda, oferta
operativa e infraestructura utilizada por modelos integrados como TRANUS. HCNet 3.1
no realiza asignación de red, modelación de uso de suelo, transbordos ni equilibrio
multimodal.

La interfaz separa proyecto, geometría, movimientos, semaforización, resultados y
reporte técnico. Los proyectos anteriores se migran al abrirse y los nuevos datos se
conservan en JSON, CSV y LaTeX.

## Uso básico

1. Revisa la presentación y las limitaciones en **Inicio y alcance**.
2. Define nombre, ubicación, analista, ciclo y periodo de análisis en **Proyecto**.
3. Define tres o cuatro ramales y sus carriles en **Geometría**.
4. Captura recorridos A–D, carriles, demanda y fase en **Movimientos y carriles**.
5. Configura los semáforos y ejecuta **Optimizar y aplicar** si deseas usar Webster.
6. Captura servicio, demanda, paradas y oferta vial en **Transporte público**.
7. Presiona **Calcular línea** para dimensionar la operación y comparar congestión.
8. Presiona **Calcular proyecto** o `F5` para actualizar todos los módulos válidos.
9. Examina LOS, demora, colas y tiempo de viaje en **Resultados intersección**.
10. Abre **Reporte técnico** para revisar o exportar la memoria `.tex`.
11. Guarda el proyecto como `*.hcnet.json` o exporta los resultados a CSV.

La exportación LaTeX requiere capturar el nombre del analista. El archivo generado
puede compilarse con una distribución LaTeX convencional:

```bash
pdflatex nombre_del_reporte.tex
pdflatex nombre_del_reporte.tex
```

Al abrir el programa se carga automáticamente un caso hipotético para explorar la
interfaz. El archivo
[`examples/interseccion_demo_cdmx.hcnet.json`](examples/interseccion_demo_cdmx.hcnet.json)
contiene el mismo tipo de información y puede abrirse desde el menú **Archivo**.

## Transparencia matemática

El motor se mantiene separado de la interfaz gráfica:

```text
src/hcnet/domain/   modelos, validación, cálculo y trazabilidad
src/hcnet/io/       proyectos JSON y exportaciones CSV/LaTeX
src/hcnet/ui/       interfaz de escritorio y visualizaciones
tests/              verificación numérica y pruebas de persistencia
```

Las ecuaciones, unidades, supuestos y límites están documentados en
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Desarrollo y pruebas

```bash
source .venv/bin/activate
ruff check .
pytest
```

Para ejecutar únicamente el motor no es necesario crear una ventana:

```python
from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.sample import demonstration_project

resultado = calculate_intersection(demonstration_project())
print(resultado.level_of_service)
print(resultado.weighted_control_delay_s_veh)
```

## Alcance y uso responsable

HCNet Transport es un proyecto independiente. **No está afiliado, certificado ni
respaldado** por el Transportation Research Board, National Academies, McTrans Center
ni Highway Capacity Software (HCS).

El módulo de intersecciones implementa un subconjunto educativo del procedimiento y
todavía no reproduce todos los tratamientos especiales del HCM 7. No debe considerarse un
sustituto del manual ni utilizarse sin verificación en estudios profesionales firmados.
Consulta [`NOTICE.md`](NOTICE.md) antes de aplicar sus resultados.

El HCM es una publicación protegida. Este repositorio no incluye su texto, tablas ni
ejemplos. Para aplicar correctamente sus metodologías se requiere acceso legítimo a la
edición y erratas correspondientes.

## Ruta de desarrollo

- Validación exhaustiva del módulo semaforizado contra casos autorizados del HCM 7/HCS.
- Validación geométrica automática de conflictos y control actuado.
- Intersecciones no semaforizadas y glorietas.
- Segmentos básicos de autopista y carreteras multicarril.
- Carreteras de dos carriles y análisis multimodal.
- Corredores, comparación de escenarios y calibración con datos mexicanos.
- Redes multimodales, matrices OD, transbordos y evaluación económica de líneas.

## Autor y licencia

Desarrollador: **Héctor Alonso Benítez García**.

HCNet Transport se distribuye bajo la [GNU General Public License v3.0](LICENSE).
