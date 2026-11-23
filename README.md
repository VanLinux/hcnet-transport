# HCNet Transport

**Highway Capacity and Network Evaluation Tool**

Software libre y educativo para analizar capacidad, desempeño operacional y nivel de
servicio de instalaciones de transporte mediante metodologías del *Highway Capacity
Manual* (HCM).

[![Pruebas](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml/badge.svg)](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml)
[![Licencia: GPL v3](https://img.shields.io/badge/Licencia-GPLv3-blue.svg)](LICENSE)
[![Versión](https://img.shields.io/badge/versión-3.4.0-3f444b.svg)](CHANGELOG.md)

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

El selector superior cambia entre los módulos. Los divisores ajustables redistribuyen
el espacio entre captura, esquema, resumen y resultados. El menú **Ver** cambia el tema.
`↔` indica pestañas vinculadas y `◇` indica módulos independientes con reporte propio.

### Rotondas

El módulo independiente analiza rotondas de un carril con dos a ocho ramales,
azimuts y sentido de circulación editables. A partir de aforos origen–destino
estima flujos conflictivos, capacidad, demora, relación v/c, LOS y cola P95.
Incluye un esquema y calcula radios de trayectoria por cuerda y flecha, radios
de isla y anillo, velocidad teórica y distancia de parada. La geometría es de
predimensionamiento. Véase [la metodología](docs/METHODOLOGY.md#14-rotondas).

## Actualizar y ejecutar en Fedora

Desde la carpeta del repositorio, con Python 3.11 o superior:

```bash
git switch main
git pull --ff-only
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

Actualización y arranque en Fedora o Ubuntu, desde el clon existente en `main`:

```bash
git pull --ff-only origin main
.venv/bin/python -m pip install -e .
.venv/bin/hcnet
```

Si es el primer uso, crea el entorno con `python3 -m venv .venv` antes de ejecutar
la instalación editable. En Ubuntu puede ser necesario `sudo apt install python3-venv`.

El motor analítico funciona por separado. Para habilitar la microsimulación, HCNet
busca `sumo` y `netconvert` del mismo paquete mediante `SUMO_HOME`, el entorno
Python o `PATH`. También puedes seleccionar el ejecutable `sumo` desde la
interfaz. Se requiere SUMO 1.14 o posterior para utilizar las unidades actuales
de combustible.

- **Ubuntu:** `sudo apt update && sudo apt install sumo`. Comprueba la versión con
  `sumo --version` y que `netconvert --version` responda.
- **Fedora:** si tu repositorio no ofrece el paquete, instala el paquete oficial
  opcional en el entorno de HCNet con `.venv/bin/python -m pip install eclipse-sumo`.
  Comprueba `.venv/bin/sumo --version` y `.venv/bin/netconvert --version`.
  También está disponible esta vía en Ubuntu. Si tu plataforma carece de rueda
  compatible, usa los binarios de Linux del proyecto SUMO y selecciona `bin/sumo`
  en la interfaz.

[Instalación oficial de SUMO](https://sumo.dlr.de/docs/Installing/index.html) ·
[Metodología y alcance de los estudios](docs/METHODOLOGY.md#estudios-opcionales-de-intersecciones)
