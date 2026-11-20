# Metodología de HCNet Transport 3.1

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

La intersección puede tener tres o cuatro ramales. Los ramales activos se identifican
con letras A–D y cada grupo se define mediante:

- ramal de origen y uno o varios ramales de destino;
- uno o varios carriles de entrada;
- fase semafórica;
- número de carriles del grupo, igual al número de carriles seleccionados.

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

## 9. Optimización semafórica Webster

Los grupos se asocian a fases. Para cada fase se adopta como relación crítica el máximo
`v/s` de los grupos simultáneos; después se calcula:

```text
Y = Σ yi
L = n · l
C0 = (1.5L + 5)/(1 - Y)
gi = (yi/Y)(C0 - L)
```

El ciclo se limita al intervalo de 40 a 180 s y el reparto respeta el verde mínimo
capturado. El diagrama de bandas muestra, para cada semáforo, su intervalo verde,
amarillo y rojo dentro de un ciclo.

Webster proporciona una propuesta inicial de tiempo fijo. HCNet no comprueba todavía
matrices completas de conflictos, mínimos peatonales, traslapes, coordinación entre
intersecciones ni requisitos normativos locales. `Y ≥ 1` se rechaza porque no produce
un ciclo finito con este método.

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
