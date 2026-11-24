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

## Estudios opcionales de intersecciones

### Factores por carril y calibración de campo

Se conserva la formulación base de HCNet. Si un grupo tiene `N` carriles, con
flujo de saturación base ajustado por carril `s_base`, la nueva expresión es

```text
s_grupo = s_base · k_cal · Σ_c producto(f_emp_c)
```

El producto para un carril sin ajustes es 1. El multiplicador empírico en el
informe es el promedio de los productos por carril multiplicado por `k_cal`.
La base por carril es uniforme dentro del grupo. El ajuste de campo es optativo
y guarda la observación, el cálculo de referencia y la fuente. Su coeficiente es
`s_observado / s_referencia`. La referencia incluye los factores analíticos de referencia
implementados en HCNet y los ajustes residuales capturados al calibrar. Revisa la
calibración si cambias posteriormente las condiciones de referencia.

Cada factor personalizado exige identificación, descripción, fuente y un efecto
residual. El editor distingue los símbolos base y valida que un mismo símbolo o
tipo de efecto no se repita en un carril. Si un efecto ya está representado por
ancho, pesados, pendiente, estacionamiento u otro parámetro existente, se registra
en el ajuste base correspondiente. Los reductores aceptan 0.10–0.90 y el valor
neutral 1.00. Un coeficiente de campo puede superar 1 si los flujos de referencia
y observados lo justifican.

### Generación, demanda y tiempos de SUMO

Se crea una intersección aislada de cuatro o menos ramales con control estático.
El carril 1 de HCNet se traduce al índice derecho 0 de SUMO. Se verifica el conjunto
de conexiones de `netconvert` antes de instalar las fases de HCNet. Los movimientos
protegidos y permisivos usan las prioridades correspondientes del semáforo.
El alcance cubre la entrada, el cruce y un tramo de salida. Si un ramal tiene
aforos de entrada, su salida adopta su misma longitud y velocidad de referencia.
Una entrada sin grupos asignados usa 150 m y 40 km/h como referencia geométrica.
Se capturan aforos independientes por destino cuando un grupo tiene varios giros.
Los accesos con geometría contradictoria, movimientos duplicados o programas
incompletos se rechazan mediante un mensaje.

La tasa de llegadas por movimiento es `V/FHMD`. El número total programado se
redondea al vehículo más cercano y se distribuye entre movimientos por mayores
restos. Las salidas se escalonan a lo largo del horizonte con variación reproducible
en cada intervalo. Se reparten por turno entre los carriles autorizados al insertar.
El porcentaje de pesados se redondea por movimiento y corrida. Las categorías de
motorización se seleccionan por semilla dentro de ligeros y pesados. El modelo
microscópico de seguimiento trabaja de forma independiente de los factores
analíticos. Los valores iniciales corresponden a un seguimiento de 1 s, una brecha
de 2.5 m, aceleración de 2.6 m/s², deceleración de 4.5 m/s² e intensidad estratégica
de cambio de carril de 1, editables en el cuadro avanzado.

Los valores iniciales del experimento son 900 s medidos, 180 s de calentamiento y
tres corridas. Un paso de integración dura 1 s. El intervalo de medición incluye
el primer segundo que sigue al calentamiento y excluye el instante final.
Las semillas consecutivas se registran en los resultados. La semilla automática
elige la inicial al ejecutar. Para los indicadores por viaje se cuentan viajes
completos que salen y llegan en la ventana medida. Se presentan tanto los completos
como el tamaño de la cohorte, que incluye los viajes sin acabar al cese de la medición.
Los vehículos que todavía no se insertan o llegan pueden ser relevantes en saturación.
La media y la DE se calculan entre corridas. El intervalo bilateral del 95 % usa
la distribución t de Student cuando existen por lo menos dos corridas.

La demora analítica es de control. `timeLoss` de SUMO se refiere al tiempo perdido
respecto a la velocidad deseada. La duración SUMO incluye el tramo de salida.
Los valores se muestran juntos como diagnóstico con sus respectivas definiciones.
SUMO no asigna niveles de servicio HCM. La red generada representa una intersección
aislada. Los efectos de intersecciones vecinas y las colas fuera del tramo simulado
exigen una red más extensa.

### Colas y estados semafóricos

La cola dinámica en metros utiliza `queueing_length` del motor. Se registra una
observación por segundo y por carril. La cola por ramal en un instante es la mayor
extensión entre sus carriles. La del cruce es la máxima extensión entre ramales.
El P95 de cada serie usa el rango superior de las observaciones ordenadas. Por
separado se cuentan vehículos detenidos con velocidad inferior a 0.1 m/s en los
accesos. Una cola próxima al extremo del tramo advierte sobre el almacenamiento
modelado. El esquema conserva la escala relativa a la longitud de cada acceso.
La fase mostrada se obtiene de la salida de estados de SUMO. Sin microsimulación,
la figura representa la P95 analítica estática.

### Emisiones y comparación

En ralentí, para cada tipo vehicular se multiplica el número de vehículos de la
ventana de estudio por la espera media observada en ralentí en horas y el factor
en g/(vehículo·h). El periodo usa el flujo de demanda ajustado. El analista registra
la fuente. Los factores faltantes dejan fuera los contaminantes incompletos.
Los vehículos eléctricos tienen cero emisiones de escape en este cálculo. El
resultado se limita al ralentí y no incluye emisiones de circulación, desgaste o
generación de electricidad.

SUMO integra por segundo las tasas vehiculares de emisiones y consumo en la red
representada. Los valores iniciales son ejemplos de clases HBEFA3 para gasolina,
diésel y autobús. Se puede editar la clase por motorización y SUMO verifica si
su instalación la admite. Los resultados expresan CO₂ en kg, CO, NOₓ y PMx en g,
combustible en g y energía eléctrica en Wh. La energía no se transforma en
emisiones indirectas. La comparación ambiental requiere el mismo motor,
composición, demanda, periodo y, para SUMO, geometría y parámetros de simulación.
El modelo de ralentí admite cambiar la espera por escenario.

La clave del escenario identifica su captura y operación. Las series de cada
corrida se comprimen dentro de `.hcnet` y los resultados quedan accesibles al reabrir.
Cuando cambia la captura, las corridas anteriores siguen disponibles como históricas.
Los resultados de un experimento cancelado se descartan sin afectar los estudios guardados.

Referencias de SUMO sobre
[colas](https://sumo.dlr.de/docs/Simulation/Output/QueueOutput.html),
[estados semafóricos](https://sumo.dlr.de/docs/Simulation/Output/Traffic_Lights.html),
[viajes](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html),
[emisiones](https://sumo.dlr.de/docs/Simulation/Output/EmissionOutput.html) y
[clases HBEFA3](https://sumo.dlr.de/docs/Models/Emissions/HBEFA3-based.html).

## Transporte público 3.5.0

Las unidades de diseño por defecto son pasajeros por hora y sentido, minutos,
kilómetros y vehículos o formaciones completas. Los corredores viales, los
ferroviarios y el teleférico comparten indicadores de oferta, con restricciones y
modelos de infraestructura propios. La capacidad física y la carga de diseño
se manejan por separado.

### Línea, flota y estaciones

Para un intervalo \(h\) en minutos, la frecuencia programada es \(60/h\).
Una capacidad física \(C\) y una ocupación de diseño \(\lambda\) producen
\(C\lambda\) plazas de diseño por unidad y \(fC\lambda\) por hora y sentido.
En el método por área se suman plazas sentadas y la parte entera del producto
del área útil de pie por la densidad. El tiempo comercial liga marcha, detenciones
interiores y pérdidas por maniobra. Las regulaciones terminales son por sentido
y se agregan al ciclo. La flota operativa redondea hacia arriba el cociente del
ciclo y el intervalo. La flota de reserva relaciona el porcentaje indicado y la
disponibilidad, tomando la mayor de las dos asignaciones.

Para una estación con \(n\) posiciones efectivas, permanencia \(t_p\) y
despeje \(t_d\), la capacidad aproximada es \(3600n/(t_p+t_d)\). Usa el número
efectivo de posiciones, que refleja bloqueos, interferencia o falta de rebase.
También pueden limitar la frecuencia las bahías de regulación, el intervalo
mínimo que admite la infraestructura y la capacidad de embarque en un cable.
El límite de plataforma en el perfil se expresa en movimientos de pasajeros
por hora y se contrasta con ascensos más descensos.

En las tablas, los valores por hora se convierten a promedio por unidad
dividiendo entre la frecuencia. La carga solicitada que sale de cada estación
es la carga inicial más ascensos menos descensos. Se valida que haya pasajeros
suficientes para bajar. El déficit incremental compara el ascenso solicitado
con las plazas físicas libres después de bajar. Puede haber sobrecarga en el
perfil de demanda resultante. Un modelo explícito de colas y reasignación de
destinos sería necesario para predecir abordajes efectivos y arrastre entre
salidas.

En una línea de cable, la separación espacial dividida entre la velocidad del
cable determina el intervalo. El ciclo usa la longitud completa de circulación
y los tiempos adicionales de paso y retorno que se capturen. La frecuencia
máxima considera separación mínima, tiempos y capacidad de embarque. La
permanencia de una cabina se modela mediante tiempos de estación capturados.

### Puertas, acceso y espera

Por puerta y movimiento, la demanda se distribuye conforme a los pesos entre
puertas habilitadas y se multiplica por segundos por pasajero, divididos por
canales. El régimen secuencial suma el mayor tiempo de ascenso y el mayor
tiempo de descenso. En operación simultánea por puertas distintas se usa el
mayor de los dos. En puertas compartidas se usa el mayor tiempo agregado por
puerta, con interferencia en las puertas con ambos flujos. Se agrega el máximo
tiempo fijo y adicional de accesibilidad entre las puertas. Los valores iniciales
del editor y los ejercicios son supuestos editables. Sustituye las tasas por
observaciones que representen las condiciones de pago y acceso del corredor.

El acceso longitudinal medio con separación uniforme \(s\) es \(s/(4v_p)\).
Para espaciamiento de diseño se minimiza la suma de acceso y egreso longitudinal
más demora por detenciones en un viaje medio de longitud \(L_m\). Con unidades
coherentes, \(J(s)=s/(2v_p)+L_m\,t_p/s\). Ubicaciones demandadas, seguridad vial,
transferencias y accesibilidad requieren un estudio de campo.

Con llegadas aleatorias independientes y un conjunto de intervalos observados
\(h_i\), la espera es \(\sum h_i^2/(2\sum h_i)\). Con servicio regular y
llegadas aleatorias puede usarse \(h/2\). Para el CV de intervalos se utiliza
la desviación estándar muestral dividida por la media observada.

### Congestión, evaluación y optimización

Para v/c igual a \(x\) la demora depende del modelo lineal, BPR, Davidson o
exponencial. Davidson sólo tiene dominio operativo para \(0\le x<1\). El
calibrador minimiza los residuos cuadrados en tiempo con capacidad vial fijada
externamente y cotas en los parámetros libres. Puede fijarse tiempo en flujo
libre, alfa o beta según la función. Lee CSV con columnas
`flujo,tiempo,muestra`, tiempos en minutos, punto decimal y etiquetas
`ajuste` o `validación`. La validación se mantiene fuera del ajuste.
Se presentan RMSE, MAE, R², residuos y advertencias de convergencia y cotas.
La comparabilidad requiere aforos, capacidad y tiempos del mismo tramo, sentido
y periodo. La extrapolación fuera del intervalo observado requiere verificación.

El modelo económico calcula unidades-km, ingresos a partir de ascensos de pago,
costos fijos y por unidad-km, subsidio, recuperación de costos y valor presente
con flujo anual uniforme. La recomendación filtra por demanda futura,
infraestructura, presupuesto, pendiente, radio y ancho antes de ponderar
capacidad, costo, velocidad y calidad. Las alternativas con evidencia insuficiente
figuran como pendientes. Con puntuación ponderada se normaliza por rango; con
TOPSIS se comparan distancias a los perfiles ideal y antiideal. La sensibilidad
varía un peso a la vez en ±20 %. Mantén escalas y monedas comunes.

Se explora una malla de intervalos para la configuración original y la
alternativa que capture el usuario. Los perfiles por unidad se convierten a
flujos horarios al intervalo de referencia antes de variar la frecuencia.
Se filtran proyectos que excedan la separación, capacidad, flota o presupuesto.
La búsqueda ofrece objetivos individuales y un conjunto no dominado en espera,
flota y costo dentro de la malla muestreada. La espera de los candidatos se
compara bajo el supuesto regular. Los cambios de trazado, número de puertas o
compatibilidad con el derecho de vía requieren capturar una alternativa factible.

### SUMO de corredor vial

Para Metrobús, Trolebús, RTP, concesionado y Combi puede ejecutarse una
configuración existente con red, rutas y, cuando aplica, paradas y señalización.
La copia de ejecución utiliza los archivos declarados y las opciones de
tiempo, paso, teletransporte y dispersión de velocidad compatibles. Omite otras
opciones y archivos de salida del proyecto original. Los detectores y archivos
adicionales con referencias externas deben retirarse de la configuración de
trabajo. Registra la semilla, versión y huella de los archivos. La ejecución
ocurre en segundo plano mediante el mismo SUMO que usa intersecciones.

El prefijo identifica vehículos de un mismo servicio o sentido. Con una parada
común se estiman intervalos entre las salidas de esos vehículos; las salidas
simultáneas se contabilizan por separado. Los viajes se resumen con los
vehículos que completan su itinerario. La detención y los intercambios provienen
de la salida de paradas de SUMO. Los ascensos requieren viajeros explícitos
en el escenario. Las colas son medidas viales del carril solicitado, expresadas
en metros.

- [TCRP Report 165, Transit Capacity and Quality of Service Manual, 3.ª ed.](https://trid.trb.org/View/1260509)
- [ITDP, BRT Planning Guide](https://brtguide.itdp.org/)
- [SUMO TripInfo](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html)
- [SUMO StopOutput](https://sumo.dlr.de/docs/Simulation/Output/StopOutput.html)
- [SUMO QueueOutput](https://sumo.dlr.de/docs/Simulation/Output/QueueOutput.html)
