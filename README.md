# HCNet Transport

**Highway Capacity and Network Evaluation Tool**

Software libre y educativo para analizar capacidad, desempeño operacional y nivel de
servicio de instalaciones de transporte mediante metodologías del *Highway Capacity
Manual* (HCM).

[![Pruebas](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml/badge.svg)](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml)
[![Licencia: GPL v3](https://img.shields.io/badge/Licencia-GPLv3-blue.svg)](LICENSE)
[![Versión](https://img.shields.io/badge/versión-3.6.0-3f444b.svg)](CHANGELOG.md)

## Versión 3.3

HCNet Transport analiza **intersecciones semaforizadas aisladas de dos, tres o cuatro
ramales con control de tiempo fijo**. Cada ramal tiene azimut editable. La geometría
se describe con letras A–D y cada
movimiento se captura como un recorrido origen–destino, por ejemplo `A → C`, asignado
a carriles y fases concretas. Captura aforo, PHF y porcentaje de pesados por
movimiento. Configura la geometría y las fases desde esquemas interactivos.

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
- inventario de semáforos por ramal, tipo, grupo de control, fase y movimientos;
- tarjetas de fase con orden, verdes, amarillos y todo rojo;
- optimización con Webster, Akçelik con búsqueda directa, algoritmo genético o Pareto;
- reasignación de grupos compatibles en Genético y Pareto, con bloqueos configurables;
- bandas por grupo de control con escala en segundos, reproducción y hasta tres ciclos;
- comparación de alternativas frente a la evaluación original, que permanece archivada;
- memoria de cálculo con ecuaciones y sustituciones;
- validación de entradas y advertencias operacionales;
- proyectos `.hcnet`, resultados CSV e informes LaTeX en tamaño carta;
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
operativa e infraestructura utilizada por modelos integrados como TRANUS. El módulo
evalúa una línea por vez.

La barra superior cambia entre los módulos. Los divisores ajustables redistribuyen
el espacio entre captura, esquema, resumen y resultados. En **Vista** puedes elegir
**Modo claro** o **Modo oscuro**. Los controles en violeta identifican la microsimulación.
**Ayuda** incluye **Acerca de**, **Manual** y **Link Overleaf** para abrir Overleaf
y compilar el reporte `.tex` exportado.
`↔` indica pestañas vinculadas y `◇` indica módulos independientes con reporte propio.

### Ingeniería de rotondas en 3.6.0

Abre **Rotonda → Ingeniería de rotondas**. Selecciona **Evaluar**, **Diseñar**,
**Optimizar** o **Convertir intersección**. El constructor admite entre dos y
ocho ramales. Arrastra cada acceso para girarlo. Selecciona dos ramales con
**Vincular origen y destino** para habilitar o restringir un movimiento.
La matriz y la tabla de composición representan el mismo aforo.

- **Normal**. Capacidad HCM por carril para configuraciones convencionales de uno
  y dos carriles, aceptación de brechas, modelo lineal, demora, LOS, P95,
  predimensionamiento y comparación analítica de conversiones.
- **Avanzado**. Kimber para accesos de un carril dentro de su dominio, calibración
  con datos de saturación o pares de brecha, factores documentados, comprobaciones
  de trayectoria, seguridad geométrica preliminar y simulación opcional con SUMO.

En **Modelo y dimensiones** registra valores medidos o fija los que se deben
conservar. **Diseñar** completa la relación entre diámetro, isla y ancho anular.
En **Original y alternativas** puedes importar la intersección semaforizada de
este proyecto u otro `.hcnet`. La comparación conserva aforos OD, composición y
FHMD, y descarta las variantes que exceden restricciones registradas.
**Caso demostrativo…** ofrece nueve ejercicios hipotéticos de carga explícita.

En **SUMO**, captura dimensiones, longitud y velocidad de los ramales.
Puedes simular una rotonda convencional o cotejarla con el cruce original bajo
las mismas llegadas y semillas. HCNet reutiliza el motor instalado. **Colas de
SUMO** reproduce la longitud medida por carril. Los reportes Carta en LaTeX y
los resultados CSV se exportan desde **Resultados**. Guarda estudios completos
en `.hcnet`. Los archivos de la versión anterior se abren también en
**Cálculo clásico** y pueden copiarse a la nueva captura.

[Modelos, fuentes y límites](docs/ROUNDABOUT_ENGINEERING.md)

## Transporte público en 3.5.0

En la barra superior, elige **Transporte público** y selecciona un tipo de análisis.
Pulsa **Captura** o **Resultados** para ampliar ese panel. En ventanas anchas,
**En paralelo** muestra ambos paneles y puedes ajustar el ancho de cada uno.
En **Estaciones**, elige **Ida** o **Regreso** para editar el sentido correspondiente.

| Modalidad | Para qué sirve |
|---|---|
| **Cálculo específico** | Frecuencia, intervalo, capacidad, flota, viaje, permanencia, estaciones, espaciamiento, acceso, ocupación, espera o congestión con los datos de ese cálculo. |
| **Análisis integral** | Configura servicio, vehículo, puertas, estaciones de ida y regreso y demanda. Usa **Análisis avanzado** para congestión, economía, optimización y SUMO vial. |
| **Recomendación de sistema** | Compara alternativas con restricciones de capacidad e infraestructura y analiza la sensibilidad del orden a los pesos utilizados. |

Las fichas distinguen parámetros documentados y datos que debe capturar el analista.
Para probar el flujo completo, pulsa **Cargar caso demostrativo…** y elige RTP,
Metrobús, Metro, Cablebús, Combi, selección tecnológica o calibración BPR.
Los casos didácticos se cargan únicamente por solicitud. Guarda los datos,
comparaciones y resultados en `.hcnet`. Los insumos externos de una corrida SUMO
se conservan por referencia y huella SHA-256. Guarda sus archivos por separado si
vas a repetir el experimento en otra computadora.

El informe integral se exporta desde **Configuración y operación**, después de
calcular la línea y los análisis avanzados aplicados. El selector de herramientas
permite abrir **Cálculo de línea vial** y consultar sus proyectos anteriores.

[Metodología de transporte público](docs/METHODOLOGY.md#transporte-público-350) ·
[Fuentes de las fichas](docs/TRANSIT_CATALOG.md)

## Actualizar y ejecutar en Fedora o Ubuntu

Desde la carpeta del repositorio, con Python 3.11 o superior. En una instalación nueva,
usa `sudo dnf install git python3` en Fedora o `sudo apt install git python3 python3-venv`
en Ubuntu.

```bash
git switch main
git pull --ff-only origin main
python3 -m venv .venv  # Solo la primera vez
.venv/bin/python -m pip install -e .
.venv/bin/hcnet
```

## Uso básico

1. Selecciona el tipo de análisis. En una intersección semaforizada captura ciclo y
   periodo en **Proyecto**. Define ramales, carriles de entrada/salida y azimuts en **Geometría**.
2. En **Movimientos** selecciona carriles y habilita rutas como `A → C`. Captura el aforo,
   PHF y pesados de cada ruta y los parámetros del grupo.
3. En **Semaforización** construye las fases, asigna grupos y captura los intervalos.
   La suma de intervalos debe cerrar el ciclo. Registra los semáforos que correspondan.
4. Presiona **Calcular situación actual** o `F5`. Consulta el diagnóstico y los resultados.
   Los cambios de entrada marcan el cálculo anterior como desactualizado.
5. Usa **Optimizar intersección**. Elige método, objetivo y restricciones. Abre **Comparar
   escenarios** y selecciona una o varias alternativas con el mismo escenario original.
6. Exporta la intersección en **Reporte técnico**. Rotondas y Transporte público disponen
   de exportación propia. En **Archivo** puedes exportar los análisis vigentes en un informe general.
7. Guarda como `.hcnet`. El archivo conserva entradas, fases, alternativas y estado de
   cálculo de los tres módulos. También se pueden abrir proyectos anteriores `.hcnet.json`.

La exportación LaTeX solicita el nombre del analista y el nombre y destino del archivo.
El archivo generado
puede compilarse con una distribución LaTeX convencional:

```bash
pdflatex nombre_del_reporte.tex
pdflatex nombre_del_reporte.tex
```

El programa abre un proyecto vacío. Para explorar la interfaz, usa **Proyecto →
Cargar caso demostrativo**. El archivo
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
- Validación geométrica detallada de conflictos y control actuado.
- Cruces con prioridad y rotondas multicarril.
- Segmentos básicos de autopista y carreteras multicarril.
- Carreteras de dos carriles y análisis multimodal.
- Coordinación de corredores y calibración con datos mexicanos.
- Redes multimodales, matrices OD, transbordos y evaluación económica de líneas.

## Autor y licencia

Desarrollador: **Héctor Alonso Benítez García**.

HCNet Transport se distribuye bajo la [GNU General Public License v3.0](LICENSE).

### Estudios opcionales con SUMO y calibración

En **Intersección semaforizada**, captura y calcula el proyecto. En **Resultados actuales**
abre **Microsimulación, colas y emisiones…** y elige las condiciones actuales o un
escenario optimizado. Configura el periodo medido, el calentamiento, las repeticiones
y la semilla. El caso demostrativo contiene geometría, aforos por movimiento y fases
compatibles para probar el flujo completo. Guarda el proyecto en `.hcnet` para
conservar las corridas, las series y los estudios de emisiones.

- **Movimientos → editar grupo → Factores de ajuste y calibración…** permite revisar
  los factores base, aplicar factores a carriles y contrastar el flujo de saturación
  con un aforo de campo.
- **Análisis de colas** muestra la P95 analítica como estimación estática. Al ejecutar
  SUMO, selecciona la corrida y el instante para ver las longitudes medidas.
- **Evaluación ambiental y emisiones** permite capturar la composición, clases SUMO
  y factores de ralentí documentados. Para el cálculo de ralentí se requiere el
  tiempo medio en ralentí y la fuente de los factores.

Para los estudios de intersección y corredor se utiliza la misma instalación de SUMO.
Si ya está disponible en Fedora o Ubuntu, comprueba `sumo --version` y
`netconvert --version`. HCNet encuentra ambos vía `SUMO_HOME`, el entorno Python o
`PATH`. Todos los cálculos analíticos también funcionan sin el motor.
La microsimulación de corredores importa una configuración `.sumocfg` con red y
rutas explícitas; consulta la metodología para conocer las opciones compatibles.

[Instalación oficial de SUMO](https://sumo.dlr.de/docs/Installing/index.html) ·
[Metodología y alcance de los estudios](docs/METHODOLOGY.md#estudios-opcionales-de-intersecciones)
