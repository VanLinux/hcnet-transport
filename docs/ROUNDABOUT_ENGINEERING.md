# Ingeniería de rotondas de HCNet 3.6.0

## Captura y conservación OD

Cada ramal tiene azimut (0° norte, 90° este), entrada y salida independientes.
Identifica carril 1 como exterior y 2 como interior, también al invertir el
sentido. El constructor mantiene el identificador al rotar el ramal. La
opción para quitarlo pide confirmación si hay registros OD asociados.
La diagonal se reserva para retornos habilitados. Un guion en la matriz
restringe un giro.

El volumen horario por movimiento se divide entre el factor de hora pico
(FHMD). Los pesos por composición se aplican a pesados, autobuses y motos
en equivalentes de auto por vehículo. El porcentaje de carril interior
reparte el caudal ajustado. Una trayectoria interior continua exige
una salida con segundo carril. El flujo que sale antes del punto de
incorporación no entra en su conflicto. Se contabilizan por separado flujo
por segmento, salidas, conflicto por carril circulante y entradas.
El CSV acepta una matriz con `origen,A,B,...` o registros `origen,destino,volumen`
con columnas opcionales `fhmd,pesados,autobuses,motocicletas,interior,habilitado,fuente`.

## Modelos operacionales

Las ecuaciones se aplican a rotondas aisladas de prioridad y a las
configuraciones convencionales respaldadas por FHWA-SA-15-070 y el capítulo 22
del HCM. Los carriles 1/2 se refieren a exterior/interior respecto al anillo.
En el HCM se conserva la corriente conflictiva total con la cual se calibraron
los parámetros. Cuando existen dos corrientes circulantes, el conteo por
carril se informa por separado. El analista puede elegir una corriente
específica para comparar métodos alternativos y documentar su aplicación.

| Carriles de entrada | Anillo | Carril | A (eq/h) | B (h/eq) |
|---:|---:|---|---:|---:|
| 1 | 1 | Único | 1380 | 0.00102 |
| 2 | 1 | Ambos | 1420 | 0.00091 |
| 1 | 2 | Único | 1420 | 0.00085 |
| 2 | 2 | Exterior | 1420 | 0.00085 |
| 2 | 2 | Interior | 1350 | 0.00092 |

La base es $c_e=A\exp(-Bv_c)$ en automóviles equivalentes por hora.
Convierte la capacidad a veh/h con la equivalencia media de ese carril.
Los factores peatonales y locales capturados requieren fuente documentada.
El motor no aplica por sí mismo reducciones por cruces o por aforo ciclista.
En esta versión quedan fuera del HCM convencional los giros segregados,
minirotondas con isla transitable, turborrotondas y configuraciones de tres
o más carriles.

- **Siegloch**. $c_e=(3600/t_f)\exp[-v_c(t_c-t_f/2)/3600]$. Supone una
  corriente conflictiva aleatoria. $t_f$ es el seguimiento y $t_c$ la brecha
  crítica. Los parámetros se capturan o se calibran con observaciones.
- **Lineal**. $c_e=a-bv_c$. Exige dominio de ajuste. Fuera de éste, o ante una
  capacidad negativa, marca el resultado como no disponible.
- **Kimber**. Usa CD 116 rev. 2 apéndice B. Requiere ancho de entrada $e$,
  semiancho de aproximación $v$, abocinamiento efectivo $l'$, diámetro inscrito
  $D$, radio de bordillo $r$ y ángulo de entrada $\phi$.
  $S=1.6(e-v)/l'$, $x_2=v+(e-v)/(1+2S)$,
  $k=1-0.00347(\phi-30)-0.978(1/r-0.05)$,
  $t_D=1+0.5/[1+\exp((D-60)/10)]$ y
  $c_e=\max(0,k[303x_2-0.210t_D(1+0.2x_2)v_c])$.
  Se comprueban los rangos de la tabla B.1. La capacidad del acceso se
  presenta en accesos de un carril. Minirotondas, accesos a desnivel y
  distribuciones por carril de Kimber quedan fuera.

La demora de control es
$d=3600/c+900T[X-1+\sqrt{(X-1)^2+8X/(cT)}]+5\min(X,1)$.
El corte A–F por demora es 10/15/25/35/50 s/veh. Con $X>1$ un carril se
clasifica F. El LOS agregado usa demora ponderada por demanda.
La tasa de demora es $\dot D=vd/3600$ (veh·h/h) y el periodo acumula
$T\dot D$ (veh·h). La suma de capacidades describe los accesos bajo el patrón
de demanda y conflicto analizado.

$Q_{95}=Tc[X-1+\sqrt{(X-1)^2+24X/(cT)}]/4$. La P95 en metros emplea
longitud más separación por vehículo. La cola media equivalente usa $vd/3600$
como aproximación estable de Little a partir de la demora de control.
Con cola inicial se añade su área determinista durante el periodo y se
omiten la P95 y la cola media. El tiempo de viaje analítico suma el tiempo
libre del tramo de aproximación y la demora de control. La demora, el LOS
y las colas con otra capacidad aparecen sólo al habilitar el cálculo híbrido.
La P95 de una rotonda corresponde a su carril crítico por longitud, mientras
que la intersección original informa su grupo crítico por longitud.

## Calibración y diseño

La calibración utiliza caudales de descarga observados en saturación y
distingue muestras de ajuste y validación. Usa regresión lineal ordinaria
o log-lineal para el modelo exponencial. Publica parámetros, residuos,
dominio, RMSE, MAE y R² calculados en capacidad original, incluso cuando
se ajustó el logaritmo. Se puede trasladar la calibración exponencial a la
captura HCM como ajuste local con dominio explícito. En brechas, la conversión
indirecta usa $t_f=3600/A$ y $t_c=3600B+t_f/2$. Los pares individuales de rechazo
máximo y aceptación estiman una distribución lognormal por verosimilitud de
intervalo. Las muestras deben corresponder al comportamiento de un conductor
que aguardaba para entrar al anillo.

Dos dimensiones conocidas permiten despejar la tercera en $D=D_i+2w$.
El diseño conserva las dimensiones fijas y etiqueta los anchos o diámetros
de tanteo como propuestos. Las restricciones pueden incluir diámetro, superficie,
rectángulo disponible y ancho por ramal. La superficie inscrita $\pi D^2/4$
excluye accesos, banquetas y predios. La comprobación rectangular tampoco
certifica la implantación en un plano. Usa cartografía y proyecto geométrico.

La relación $V=\sqrt{127R(e+f)}$ sirve como comprobación teórica de la
curvatura capturada. El radio de bordillo de Kimber es un dato distinto del
radio de trayectoria. Los radios de trayectoria pueden capturarse u obtenerse
por cuerda y flecha. El vehículo de diseño es editable y se contrasta con
anchos y radios. Esta comprobación preliminar no calcula trayectoria barrida.
Los conflictos potenciales dependen de la continuidad y de los movimientos
habilitados. No se estiman choques, TTC ni PET. Registra flujos de peatones y
ciclistas, ubicación del cruce, refugio y visibilidad como parte del cribado.

## Comparación, microsimulación y archivos

La conversión importa un proyecto HCNet semaforizado o registra un original
manual con indicadores de campo y fuente. Para cambiar el tipo de control
sin un modelo analítico equivalente, se conservan los aforos y se omite la
métrica incierta. Las alternativas exploran tipos, diámetros y asignaciones
por carril sobre una malla finita que conserva la demanda y restricciones.
El objetivo puede ser demora, cola, saturación, capacidad, superficie o
puntuación ponderada de varios criterios. El orden sólo refleja las
alternativas ensayadas. Se recomienda verificar encaje y seguridad antes de
proyectar una intervención.

SUMO es opcional en modo avanzado. Se ejecuta por CLI con el motor compartido.
`netconvert` recibe explícitamente nodos de entrada y salida separados,
segmentos y conexiones de carril. HCNet comprueba que la red generada conserva
el anillo y la cesión de cada entrada al carril circulante. El modo horario usa
conducción por la izquierda. Las configuraciones con cruces interiores sin
canalización validada, giros segregados o isla transitable se rechazan en
la red generada. No se trasladan automáticamente los parámetros de brecha
analíticos a los vehículos en SUMO.

Las corridas comparables comparten calendario de demanda, composición,
calentamiento, medición y semillas. Los vehículos se insertan cuando existe
espacio. Se distinguen solicitados, insertados, completos y pendientes.
Las emisiones se integran en el periodo de medición usando las clases
capturadas. Para motos se dispone de una aproximación inicial por vehículo
ligero, que debe reemplazarse en estudios de emisiones. La normalización
por inserción se muestra aparte de los totales y no equivale a emisiones del
viaje completo. Las series de cola en metros se obtienen a intervalos de un
segundo, con longitud media, máxima, P95 y tiempos de presencia por carril.
El IC95 usa t de Student con al menos dos corridas. El asfalto y las
trayectorias de la red generada simplifican el proyecto vial y no incluyen
dinámica explícita de peatones o ciclistas.

El proyecto `.hcnet` guarda el estado, los originales y resultados. Los archivos
SUMO se generan en temporales, salvo exportación explícita. Se guardan
`network.net.xml`, los XML fuente, demanda por semilla, colas, emisiones y
tripinfo. Para reproducir una corrida en la carpeta del escenario, usa la
semilla anotada, la suma de calentamiento y medición como tiempo final, y los
mismos archivos. Por ejemplo:

```bash
sumo -n network.net.xml -r 42-demand.rou.xml --seed 42 --step-length 1 \
  --end 1080 --time-to-teleport -1 --tripinfo-output trips.xml \
  --tripinfo-output.write-unfinished true --queue-output queues.xml \
  --emission-output emissions.xml
```

## Referencias

- [Highway Capacity Manual, 7.ª ed., capítulo 22](https://doi.org/10.17226/26432).
- [FHWA-SA-15-070, Assessment of Roundabout Capacity Models](https://rosap.ntl.bts.gov/view/dot/49387).
- [NCHRP 1043, Guide for Roundabouts, con acceso a la fe de erratas](https://www.nationalacademies.org/publications/27069).
- [Kimber, The Traffic Capacity of Roundabouts, LR942](https://www.trl.co.uk/publications/the-traffic-capacity-of-roundabouts).
- [National Highways, CD 116 rev. 2, Apéndice B](https://www.standardsforhighways.co.uk/tses/attachments/2b5901c6-3477-4826-b780-cf99003fb5e0?inline=true).
- [Eclipse SUMO PlainXML](https://sumo.dlr.de/docs/Networks/PlainXML.html).
