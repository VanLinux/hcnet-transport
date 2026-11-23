# Metodología de HCNet Transport 3.2

## 1. Propósito y alcance

El motor representa una intersección semaforizada aislada mediante grupos de
carriles. Su propósito es hacer visible el proceso que conecta los datos observados con
la capacidad, el grado de saturación, la demora de control y el nivel de servicio.

La estructura se alinea con el marco analítico de intersecciones semaforizadas del
*Highway Capacity Manual, Seventh Edition* (HCM 7). No se afirma equivalencia completa
con HCS: faltan tratamientos que dependen de la geometría, control, interacción entre
movimientos, llegadas coordinadas y colas iniciales.

## 2. Convenciones

| Símbolo | Definición | Unidad |
|---|---|---|
| `V` | Volumen horario observado del grupo | veh/h |
| `FHMD` | Factor de hora de máxima demanda (PHF) | — |
| `v` | Tasa de flujo de demanda ajustada | veh/h |
| `s₀` | Flujo de saturación base por carril | pc/h/carril |
| `N` | Número de carriles del grupo | carriles |
| `s` | Flujo de saturación ajustado del grupo | veh/h |
| `g` | Verde efectivo | s |
| `C` | Longitud de ciclo | s |
| `c` | Capacidad del grupo | veh/h |
| `X` | Grado de saturación `v/c` | — |
| `T` | Periodo de análisis | h |
| `d` | Demora de control | s/veh |

Los porcentajes de vehículos pesados y pendiente se introducen en porcentaje. Los
demás factores se introducen como fracciones adimensionales.

### Geometría y convención de movimientos

La intersección puede tener dos, tres o cuatro ramales. Los ramales activos se identifican
con letras A–D y cada grupo se define mediante:

- ramal de origen y uno o varios ramales de destino;
- uno o varios carriles de entrada;
- fase semafórica;
- número de carriles del grupo, igual al número de carriles seleccionados.

La orientación se expresa como azimut desde el norte en sentido horario.

La notación `A → C` evita depender de nombres como izquierda o directo cuando se
analizan geometrías de tres ramales o configuraciones no ortogonales.

## 3. Demanda

La tasa equivalente de demanda se obtiene con:

```text
v = V / FHMD
```

El usuario debe evitar aplicar dos veces el ajuste. Si el dato ya es una tasa equivalente
de 15 minutos expresada por hora, debe utilizar `FHMD = 1.0`.

## 4. Flujo de saturación

HCNet utiliza:

```text
s = s₀ · N · fw · fHV · fg · fp · fbb · fLU · fa · fturn
```

### Factores calculados internamente

Ancho de carril en unidades SI:

```text
fw = 1 + (w - 3.6) / 9
```

Vehículos pesados:

```text
fHV = 1 / [1 + PHV(ET - 1)]
```

`PHV` se expresa como fracción y `ET` es la equivalencia de automóvil de pasajeros.

Pendiente, positiva en ascenso:

```text
fg = 1 - G / 200
```

Estacionamiento:

```text
fp = [N - 0.1 - 18(Nm/3600)] / N
```

La expresión de `fp` se activa cuando `Nm > 0`. Un valor igual a cero se interpreta
como ausencia de estacionamiento adyacente y produce `fp = 1`.

Bloqueos producidos por autobuses:

```text
fbb = [N - 14.4(Nb/3600)] / N
```

HCNet restringe factores calculados a dominios numéricos seguros. Esto no convierte un
dato extremo en metodológicamente válido; las advertencias deben revisarse.

### Factores definidos por el usuario

- `fLU`: distribución o utilización de carriles.
- `fa`: tipo de área.
- `fturn`: efecto conjunto del giro aplicable al grupo.

La versión 3.0 no deduce esos factores a partir de flujos opuestos, peatones, radios de
giro o asignación de carriles. El usuario debe obtenerlos de una fuente autorizada y
registrar el supuesto en las notas del grupo.

## 5. Capacidad y grado de saturación

```text
c = s(g/C)
X = v/c
```

`X > 1` indica que la demanda excede la capacidad durante el periodo analizado. HCNet
informa además una demanda residual diagnóstica:

```text
R = max[0, (v - c)T]
```

`R` no debe interpretarse como cola percentil 95 del HCM.

## 6. Demora de control

La demora total es:

```text
d = d₁ + d₂ + d₃
```

Componente uniforme:

```text
d₁ = {0.5C(1-g/C)² / [1-min(1,X)g/C]}PF
```

Componente incremental:

```text
d₂ = 900T[(X-1) + √((X-1)² + 8kIX/(cT))]
```

`PF` es el factor de progresión, `k` el factor de demora incremental e `I` el factor de
filtrado o medición aguas arriba. Los valores iniciales `PF=1`, `k=0.5` e `I=1`
representan un caso aislado básico; no son valores universales.

`d₃` representa demora por cola inicial. HCNet 3.0 no estima internamente esa cola: el
usuario introduce directamente su contribución en segundos por vehículo. El valor se
marca en la memoria para evitar confundirlo con un resultado del programa.

## 7. Nivel de servicio

| Demora de control `d` (s/veh) | LOS |
|---:|:---:|
| `d ≤ 10` | A |
| `10 < d ≤ 20` | B |
| `20 < d ≤ 35` | C |
| `35 < d ≤ 55` | D |
| `55 < d ≤ 80` | E |
| `d > 80` | F |

Para un grupo de carriles, HCNet asigna F si `X > 1`, incluso cuando la demora calculada
en un periodo corto sea menor que 80 s/veh. En el agregado de la intersección, el LOS se
determina mediante la demora ponderada por la tasa de demanda de los grupos.

## 8. Llegadas durante el rojo

Como apoyo docente se muestra:

```text
qrojo = v(C-g)/3600
```

Es el número esperado de llegadas durante el rojo bajo demanda uniforme. No incorpora
dispersión de pelotones y no constituye una estimación formal de longitud máxima de cola.

### Cola diagnóstica

HCNet añade dos indicadores transparentes para revisar almacenamiento:

```text
Qmedia = R + 0.5 qrojo
Q95 ≈ R + qrojo + 1.645 √qrojo
L95 = (Q95/N)e
```

`R` es la demanda residual, `N` el número de carriles y `e` el espaciamiento medio por
vehículo detenido. `Q95` usa una aproximación normal de llegadas Poisson y **no es la
ecuación formal de cola percentil 95 del HCM/HCS**. Su propósito es docente y de
diagnóstico preliminar; no debe presentarse como un resultado certificado.

### Tiempo de viaje

Para la longitud de aproximación `L` y la velocidad de flujo libre `VFL`:

```text
t0 = 3.6 L / VFL
tviaje = t0 + d
```

El resultado representa el recorrido por la aproximación más la demora de control. No
incluye tiempo en segmentos posteriores ni una asignación dinámica de rutas.

## 9. Programación semafórica y alternativas

Los movimientos de un mismo grupo de carriles comparten capacidad y verde. Para los
movimientos habilitados, la demanda equivalente del grupo es `Σ(Vi/PHFi)`. El PHF
equivalente es `ΣVi / Σ(Vi/PHFi)` y el porcentaje de pesados se pondera por `Vi/PHFi`.
La demanda de un movimiento se mide directamente. Su demora y LOS en la comparación
corresponden al resultado del grupo que utiliza. Las colas y la capacidad pertenecen al grupo.

Cada fase recibe un intervalo de verde, amarillo y todo rojo. La suma debe cerrar el
ciclo. El modelo usa verde efectivo igual al verde capturado y valida conflictos de
cruce y convergencia en un esquema de circulación por la derecha. Un movimiento
permisivo requiere un factor de giro calibrado; la comprobación admite una sola
corriente permisiva por par en conflicto. El controlador representado es secuencial.
Los grupos de carriles comparten una única fase y las cabezas del mismo grupo de control
se mantienen sincronizadas. No se modelan traslapes, intervalos protegidos/permisivos
múltiples, tiempos mínimos peatonales ni coordinación entre intersecciones.

### 9.1 Webster

Para cada fase se adopta como relación crítica `yi` el mayor `v/s` de los grupos
simultáneos. `l` es el tiempo perdido capturado por fase, `n` el número de fases y
`D` la suma de los amarillos y todo rojo. El cálculo aplica:

```text
Y = Σ yi
L = n · l
C0 = (1.5L + 5)/(1 - Y)
gi = (yi/Y)(C - D), antes de imponer verdes mínimos
```

El ciclo `C` usa los límites seleccionados (40 a 180 s por defecto) y además debe
alojar los despejes y verdes mínimos. El reparto fija las fases que quedarían por
debajo del verde mínimo y vuelve a repartir el tiempo restante. `Y ≥ 1` se rechaza
porque no produce un ciclo teórico finito. Si se fija el ciclo, se calcula el reparto
con ese ciclo.

### 9.2 Akçelik con búsqueda directa

Con `s` en veh/h, `g` en segundos, capacidad `c` en veh/h, `X = v/c` y `T` en horas,
se usan el umbral `X0` y la cola de desbordamiento `N`:

```text
X0 = 0.67 + (s/3600)g/600
N = 0                                                   para X ≤ X0
N = (cT/4)[X - 1 + sqrt((X - 1)² + 12(X - X0)/(cT))]     para X > X0
d = C(1 - g/C)²/[2(1 - min(1, X)g/C)] + 3600N/c         en s/veh
```

La búsqueda local explora cambios del ciclo y transferencias de verde entre fases.
Parte de las mejores semillas factibles (reparto actual o Webster). Empieza con
pasos de 5 s, divide el paso por dos cuando el objetivo no mejora y termina al bajar
de 0.1 s o alcanzar el límite elegido. Esta formulación de búsqueda omite el factor
de progresión y la cola inicial. La evaluación final vuelve a usar el motor HCNet.
La formulación de desbordamiento está documentada en el capítulo 9 de
[*Traffic Flow Theory*, FHWA](https://www.fhwa.dot.gov/publications/research/operations/tft/chap9.pdf).

### 9.3 Genético y Pareto

Un candidato contiene el ciclo, el reparto de verdes y una asignación de grupos a
fases. Se combinan y perturban repartos y ciclos, con poda de candidatos incompatibles.
Cuando el analista lo habilita se pueden mover o intercambiar grupos completos entre
fases existentes. Se preservan los bloqueos de asignación, la secuencia, los despejes
y las relaciones entre semáforos y grupos de carriles.

El algoritmo genético selecciona por demora media, P95 máxima o `v/c` crítico. En
Pareto se retienen candidatos no dominados en las tres métricas, con hasta doce
alternativas elegidas por su separación en el frente encontrado. El frente es una
aproximación entre candidatos examinados. La semilla predeterminada 42 facilita
reproducir los resultados. Los valores iniciales (24 candidatos, 25 generaciones,
8 generaciones sin cambio) limitan el coste de búsqueda interactiva y son ajustables.

Toda alternativa se evalúa con las ecuaciones operacionales de los apartados anteriores
para compararla con la situación original. El proyecto guarda la configuración de
búsqueda, el plan resultante y una copia de sus entradas originales. Así se puede
reconstruir la comparación aunque se edite la situación actual.

## 10. Transporte público

Este módulo es independiente del análisis de intersecciones. Representa una línea
bidireccional y relaciona la demanda de pasajeros con la oferta de vehículos, el
servicio de las paradas y la capacidad vial. Comparte con TRANUS la separación
conceptual entre demanda, oferta operativa e infraestructura, pero no implementa su
modelo de asignación, equilibrio, uso de suelo ni evaluación económica.

### 10.1 Intercambio de pasajeros y permanencia

Con `Psub` y `Pbaj` pasajeros por parada, tiempos unitarios `tsub` y `tbaj`, `npuertas`
puertas útiles y tiempo de apertura/cierre `tpuertas`:

```text
Tsub = Psub · tsub / npuertas
Tbaj = Pbaj · tbaj / npuertas
```

Para intercambio simultáneo:

```text
tdwell = tpuertas + max(Tsub, Tbaj)
```

Para intercambio secuencial:

```text
tdwell = tpuertas + Tsub + Tbaj
```

La captura representa condiciones medias en la parada crítica. El modelo no estima
distribuciones estocásticas de llegadas, pago de tarifa, interferencia entre puertas ni
accesibilidad universal; esos efectos deben incorporarse a los tiempos unitarios.

### 10.2 Velocidad comercial, ciclo y flota

Para longitud por sentido `L`, velocidad de operación entre paradas `Vop`, número de
paradas por sentido `Np`, penalización de aceleración/deceleración `tp` y regulación
por terminal `tr`:

```text
trodamiento = 60L/Vop
tcomercial = trodamiento + (Np - 2)(tdwell + tp)/60
Vcomercial = 60L/tcomercial
tciclo = 2tcomercial + 2tr
```

Con intervalo programado `h`, capacidad nominal `Kveh`, factor de ocupación objetivo
`fo` y reserva `r`:

```text
f = 60/h
Kefectiva = Kveh · fo
Klínea = f · Kefectiva
Nservicio = techo(tciclo/h)
Nreserva = techo(Nservicio · r/100)
Ntotal = Nservicio + Nreserva
```

Para demanda direccional pico `D`, el requerimiento teórico es:

```text
frequerida = D/Kefectiva
h requerido = 60/frequerida
espera media = h/2
```

La espera media supone llegadas aleatorias y servicio regular. No incorpora variabilidad
del intervalo ni penalizaciones por transbordo.

### 10.3 Espaciamiento y acceso

Con longitud de línea en metros `Lm`, el espaciamiento actual es:

```text
sactual = Lm/(Np - 1)
```

Para demanda distribuida uniformemente y acceso al punto más cercano, el tiempo medio
de caminata con velocidad `Vcam` es:

```text
tacceso = sactual/(4Vcam)
```

HCNet minimiza una función simplificada que suma acceso e incremento de tiempo dentro
del vehículo para una longitud media de viaje `Lviaje`:

```text
T(s) = s/(4Vcam) + (Lviaje/s)(tdwell + tp)
sóptimo = √[4Vcam · Lviaje · (tdwell + tp)]
```

Es una aproximación de planeación. La recomendación debe contrastarse con cobertura,
topografía, seguridad vial, conectividad, demanda espacial y accesibilidad universal.

### 10.4 Capacidad de parada crítica

Con `b` posiciones de atención y tiempo de despeje `tdespeje`:

```text
fparada = 3600b/(tdwell + tdespeje)
Kparada = fparada · Kefectiva
```

La expresión es determinista y no incluye variabilidad de permanencia, colas entre
autobuses, bloqueo de carril ni semáforos adyacentes.

### 10.5 Oferta vial y funciones de congestión

El flujo equivalente en el sentido analizado agrega al flujo de fondo `qfondo` la
frecuencia de autobuses multiplicada por su equivalencia `Ebus`:

```text
qeq = qfondo + f · Ebus
x = qeq/cvial
```

Con tiempo de flujo libre `t0 = trodamiento`, HCNet compara:

```text
Lineal:      t = t0(1 + αx)
BPR:         t = t0(1 + αx^β)
Davidson:    t = t0[1 + Jx/(1-x)]     para x < 1
Exponencial: t = t0 exp(αx)
```

Los parámetros son editables para permitir calibración. La función de Davidson se
declara no finita para `x ≥ 1`; no se extrapola artificialmente. Estas curvas son una
comparación estática y no constituyen una asignación de equilibrio ni una simulación
dinámica de tráfico.

## 11. Trazabilidad y reporte LaTeX

La vista **Reporte técnico** conserva la sustitución numérica de cada grupo de
carriles. La exportación `.tex` amplía esa trazabilidad e incluye:

1. identificación del proyecto y nombre del analista;
2. parámetros generales;
3. resumen operacional de la intersección;
4. tabla comparativa de grupos de carriles;
5. entradas, factores, ecuaciones y resultados por grupo;
6. advertencias automáticas y alcance metodológico.

Los textos capturados por el usuario se escapan antes de incorporarse al código LaTeX
para conservar caracteres reservados como `&`, `%`, `_`, `#` y llaves.

## 12. Validación requerida

Para declarar un módulo apto para uso profesional deben compararse, como mínimo:

1. factores individuales;
2. flujo de saturación;
3. capacidad;
4. grado de saturación;
5. componentes `d₁`, `d₂` y `d₃`;
6. demora agregada;
7. LOS;
8. colas y tiempo de viaje;
9. ciclo y reparto de verdes;
10. comportamiento en casos límite.

La comparación debe utilizar casos resueltos de una copia legítima del HCM 7, sus
erratas vigentes y una versión identificada de HCS. Las diferencias por redondeo deben
documentarse; no deben ocultarse ajustando constantes sin fundamento.

## 13. Referencias

- Transportation Research Board. (2022). *Highway Capacity Manual, Seventh Edition:
  A Guide for Multimodal Mobility Analysis*. National Academies of Sciences,
  Engineering, and Medicine.
- Transportation Research Board, página oficial del HCM 7:
  <https://www.trb.org/Finance/Bookstore.aspx>
- McTrans Center, Highway Capacity Software:
  <https://mctrans.ce.ufl.edu/>
- Modelística, documentación oficial de TRANUS:
  <https://modelistica.com.mx/en/download/>

Las referencias identifican el marco metodológico; su inclusión no implica afiliación
ni autorización del proyecto.

## 14. Rotondas

Se representa una rotonda de un carril de circulación y un carril por entrada.
El modelo ordena los ramales según su azimut y el sentido de circulación.
Cada flujo OD aporta al conflicto de los ramales intermedios. La diagonal
representa retornos en U. Los vehículos que salen en un ramal se retiran antes
de contabilizar el conflicto de su entrada. El modelo usa la demanda ajustada
por FHMD y no impone restricciones de descarga en entradas sobresaturadas.

La capacidad de entrada en veh/h es `c = A exp(-B q_c) f_p / E_i`, donde
`q_c` es flujo conflictivo en vehículos equivalentes por hora, `f_p` es
el factor peatonal y `E_i = 1 + P_i (E_p - 1)` convierte la mezcla de la
entrada. Los coeficientes iniciales `A=1130` y `B=0.001` proceden de la
ecuación 4-3 del [NCHRP Report 672](https://www.fdot.gov/docs/default-source/traffic/doc_library/pdf/nchrp_rpt_672.pdf).
La demora y P95 siguen las ecuaciones 4-10 y 4-13 para un periodo sin cola
inicial. Los umbrales de demora A a E son 10, 15, 25, 35 y 50 s/veh.
La entrada también pasa a F si `v/c > 1`. El LOS global usa la demora ponderada.

El eje anular se aproxima mediante un círculo de radio `D/2 - w/2`;
el radio de isla con corona es `D/2 - w`. Los radios de entrada y salida
pueden medirse directamente o calcularse con una cuerda `L` y la flecha
`s` de un arco circular mediante `R = L²/(8s) + s/2`. Para fricción lateral
`f` y pendiente transversal con signo `e`, en fracción, se calcula el radio
de comprobación `V²/[127(e+f)]`. La distancia de parada en rasante plana
suma percepción-reacción y frenado con desaceleración constante.

El resultado geométrico sirve para predimensionamiento. El trazado definitivo
requiere comprobar trayectorias rápidas y barrido del vehículo de diseño,
visibilidad, deflexión, cruces peatonales y condiciones locales. Véase
[NCHRP Report 1043, Guide for Roundabouts](https://www.nationalacademies.org/publications/27069).
