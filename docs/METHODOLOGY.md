# Metodología de HCNet Transport 1.0

## 1. Propósito y alcance

El motor 1.0 representa una intersección semaforizada aislada mediante grupos de
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

La versión 1.0 no deduce esos factores a partir de flujos opuestos, peatones, radios de
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

`d₃` representa demora por cola inicial. HCNet 1.0 no estima internamente esa cola: el
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

## 9. Validación requerida

Para declarar un módulo apto para uso profesional deben compararse, como mínimo:

1. factores individuales;
2. flujo de saturación;
3. capacidad;
4. grado de saturación;
5. componentes `d₁`, `d₂` y `d₃`;
6. demora agregada;
7. LOS;
8. comportamiento en casos límite.

La comparación debe utilizar casos resueltos de una copia legítima del HCM 7, sus
erratas vigentes y una versión identificada de HCS. Las diferencias por redondeo deben
documentarse; no deben ocultarse ajustando constantes sin fundamento.

## 10. Referencias

- Transportation Research Board. (2022). *Highway Capacity Manual, Seventh Edition:
  A Guide for Multimodal Mobility Analysis*. National Academies of Sciences,
  Engineering, and Medicine.
- Transportation Research Board, página oficial del HCM 7:
  <https://www.trb.org/Finance/Bookstore.aspx>
- McTrans Center, Highway Capacity Software:
  <https://mctrans.ce.ufl.edu/>

Las referencias identifican el marco metodológico; su inclusión no implica afiliación
ni autorización del proyecto.
