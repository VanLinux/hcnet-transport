# HCNet Transport

**Highway Capacity and Network Evaluation Tool**

Software libre y educativo para analizar capacidad, desempeño operacional y nivel de
servicio de instalaciones de transporte mediante metodologías del *Highway Capacity
Manual* (HCM).

[![Pruebas](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml/badge.svg)](https://github.com/VanLinux/hcnet-transport/actions/workflows/tests.yml)
[![Licencia: GPL v3](https://img.shields.io/badge/Licencia-GPLv3-blue.svg)](LICENSE)
[![Versión](https://img.shields.io/badge/versión-2.0.0-3f444b.svg)](CHANGELOG.md)
[![Plataforma](https://img.shields.io/badge/plataforma-Linux-fcc624.svg)](#instalación-en-linux)

## Versión 2.0

HCNet Transport 2.0 analiza **intersecciones semaforizadas aisladas
con control de tiempo fijo**. El programa conserva los resultados intermedios para que
el procedimiento pueda revisarse, enseñarse y compararse con un cálculo manual.

Calcula, por grupo de carriles:

- flujo de demanda ajustado por FHMD/PHF;
- factores por ancho, vehículos pesados, pendiente, estacionamiento y autobuses;
- flujo de saturación ajustado;
- capacidad y grado de saturación, `X = v/c`;
- demora uniforme `d₁`, incremental `d₂` y por cola inicial `d₃`;
- demora de control y nivel de servicio A–F;
- llegadas estimadas durante el rojo y demanda residual diagnóstica.

También proporciona:

- resumen ponderado de la intersección;
- gráfica comparativa del grado de saturación;
- memoria de cálculo con ecuaciones y sustituciones;
- validación de entradas y advertencias operacionales;
- proyectos editables en JSON, resultados CSV y reporte técnico en LaTeX;
- caso demostrativo hipotético de Ciudad de México.

La versión 2.0 incorpora una interfaz de contraste neutral, una pantalla inicial con
la identidad y alcance del software, y un reporte LaTeX completo con portada,
identificación del analista, parámetros, resultados y memoria matemática.

## Instalación en Linux

HCNet 2.0 requiere Python 3.11 o posterior. Por ahora, Linux es la única plataforma
soportada y probada.

### Fedora

```bash
sudo dnf install python3 python3-pip
git clone https://github.com/VanLinux/hcnet-transport.git
cd hcnet-transport
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
hcnet
```

### Ubuntu y derivados

```bash
sudo apt install python3 python3-venv python3-pip libxcb-cursor0
git clone https://github.com/VanLinux/hcnet-transport.git
cd hcnet-transport
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
hcnet
```

En ejecuciones posteriores basta con:

```bash
cd ~/hcnet-transport
source .venv/bin/activate
hcnet
```

También puede iniciarse con:

```bash
python -m hcnet
```

Para salir del entorno virtual al terminar:

```bash
deactivate
```

## Uso básico

1. Revisa la presentación y las limitaciones en **Inicio y alcance**.
2. Define nombre, ubicación, analista, ciclo y periodo de análisis en **Proyecto**.
3. Agrega o edita los movimientos en **Grupos de carriles**.
4. Presiona **Calcular proyecto** o `F5`.
5. Examina LOS, demora y grado de saturación en **Resultados**.
6. Abre **Reporte técnico** para revisar la memoria o exportar el documento `.tex`.
7. Guarda el proyecto como `*.hcnet.json` o exporta los resultados a CSV.

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

El módulo actual implementa un subconjunto educativo del procedimiento y todavía
no reproduce todos los tratamientos especiales del HCM 7. No debe considerarse un
sustituto del manual ni utilizarse sin verificación en estudios profesionales firmados.
Consulta [`NOTICE.md`](NOTICE.md) antes de aplicar sus resultados.

El HCM es una publicación protegida. Este repositorio no incluye su texto, tablas ni
ejemplos. Para aplicar correctamente sus metodologías se requiere acceso legítimo a la
edición y erratas correspondientes.

## Ruta de desarrollo

- Validación exhaustiva del módulo semaforizado contra casos autorizados del HCM 7/HCS.
- Giros permitidos, carriles compartidos, colas iniciales y control actuado.
- Intersecciones no semaforizadas y glorietas.
- Segmentos básicos de autopista y carreteras multicarril.
- Carreteras de dos carriles y análisis multimodal.
- Corredores, comparación de escenarios y calibración con datos mexicanos.

## Autor y licencia

Desarrollador: **Héctor Alonso Benítez García**.

HCNet Transport se distribuye bajo la [GNU General Public License v3.0](LICENSE).
