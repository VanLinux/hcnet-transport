# Manual de usuario de HCNet Transport

La fuente `HCNet_Transport_Manual_Usuario.tex` se compila con LuaLaTeX. El manual
usa tamaño carta, tipografía Unicode y reglas de idioma español mediante `babel`.
No requiere `inputenc`, `fontenc` ni `makeindex`.

## Compilación

Desde el directorio `docs/manual`:

```bash
lualatex HCNet_Transport_Manual_Usuario.tex
lualatex HCNet_Transport_Manual_Usuario.tex
```

También puede utilizar XeLaTeX con las mismas dos ejecuciones:

```bash
xelatex HCNet_Transport_Manual_Usuario.tex
xelatex HCNet_Transport_Manual_Usuario.tex
```

La segunda ejecución actualiza el índice general, las referencias cruzadas y la
numeración definitiva. Para evitar errores de recursos, conserve la carpeta
`assets` junto al archivo `.tex`. También es posible compilar desde la raíz del
repositorio:

```bash
lualatex docs/manual/HCNet_Transport_Manual_Usuario.tex
lualatex docs/manual/HCNet_Transport_Manual_Usuario.tex
```

Si una captura no está disponible, el manual compila con un recuadro de reserva
que muestra el nombre del archivo faltante. Ese recuadro sólo es apropiado para
una revisión de trabajo; el PDF publicado debe contener las capturas definitivas.

## Capturas requeridas

Guarde las imágenes en formato PNG, sin modificar ni escapar los guiones bajos de
los nombres. La aplicación debe usar el caso demostrativo integrado y mostrar la
versión 2.0.0.

| Archivo | Encuadre | Contenido requerido |
|---|---:|---|
| `01_inicio_alcance.png` | Ventana completa | Pestaña **Inicio y alcance**, con versión, licencia, desarrollador y supuestos principales visibles. |
| `02_proyecto.png` | Ventana completa | Pestaña **Proyecto**, con identificación del caso, analista, ciclo, periodo y esquema de la intersección. |
| `03_grupos_carriles.png` | Ventana completa | Pestaña **Grupos de carriles**, con los ocho grupos del caso demostrativo visibles. |
| `04_grupo_datos_basicos.png` | Sólo el diálogo | Edición de **Norte - Izquierda** en la pestaña **Datos básicos**. |
| `05_grupo_ajustes.png` | Sólo el diálogo | El mismo grupo en la pestaña **Ajustes**, con todos los factores y parámetros de demora visibles. |
| `06_resultados.png` | Ventana completa | Pestaña **Resultados** después de presionar F5, con indicadores, gráfica, tabla y diagnóstico. |
| `07_reporte_tecnico.png` | Ventana completa | Pestaña **Reporte técnico** con **Norte - Izquierda** seleccionado y el inicio de la memoria visible. |

Resoluciones de referencia:

- ventana completa: aproximadamente 1380 por 880 px;
- diálogo: aproximadamente 690 por 650 px;
- escala de pantalla: 100 %;
- formato de color: RGB;
- sin cursores, menús desplegados, ventanas superpuestas ni datos personales.

Las capturas se almacenan en:

```text
docs/manual/assets/
```

Al reemplazarlas, conserve exactamente los nombres anteriores y vuelva a compilar
el manual dos veces con LuaLaTeX.
