"""Resultados tabulares y gráficos reproducibles para rotondas."""

from hcnet.domain.roundabout_engineering import (
    METHODS,
    REFERENCE,
    Site,
    capacity,
    order,
    point,
)
from hcnet.domain.transit_reporting import section

SOURCES = [
    "https://doi.org/10.17226/26432",
    "https://rosap.ntl.bts.gov/view/dot/49387",
    "https://doi.org/10.17226/27069",
    "https://www.trl.co.uk/publications/the-traffic-capacity-of-roundabouts",
]
LABELS = {
    "demand": "Demanda ajustada (veh/h)",
    "capacity": "Suma de capacidades de acceso (veh/h)",
    "reserve": "Reserva agregada (veh/h)",
    "x": "Saturación crítica",
    "delay": "Demora ponderada de control (s/veh)",
    "delay_rate": "Tasa de demora (veh·h/h)",
    "delay_total": "Demora en el periodo (veh·h)",
    "los": "Nivel de servicio",
    "queue_m": "P95 máxima por carril o grupo (m)",
    "travel": "Viaje en tramo de aproximación + demora (s)",
    "critical": "Carril crítico",
    "area": "Área del círculo inscrito (m²)",
}
CAPACITY_FORMULAS = {
    "HCM": r"c_e=Ae^{-Bv_c},\qquad c_{\mathrm{veh}}=c_e f_p f_{\mathrm{loc}}/\bar{E}",
    "Brechas": r"c_e=\frac{3600}{t_f}\exp\left[-\frac{v_c}{3600}(t_c-t_f/2)\right]",
    "Lineal": r"c_e=a-bv_c",
    "Kimber": r"c_e=k(303x_2-0.210t_D(1+0.2x_2)v_c)",
}


def chart(title, x, y, series, **kwargs):
    return {
        "title": title,
        "x": x,
        "y": y,
        "series": {key: points for key, points in series.items() if points},
        **kwargs,
    }


def operational_record(site, result):
    lanes = result["lanes"]
    charts = []
    for key in ("delay", "x", "queue_m"):
        series = {
            f"{r['arm']}/{r['lane']}": [[i, r[key]]]
            for i, r in enumerate(lanes, 1)
            if r[key] is not None and r["demand"]
        }
        if series:
            charts.append(chart(LABELS[key], "Carril", LABELS[key], series, bars=True))
    critical = max(lanes, key=lambda r: r["q"], default=None)
    if critical:
        arm = next(a for a in site.arms if a.code == critical["arm"])
        flow = max(1500, critical["q"])
        series = {}
        for method in critical["models"]:
            points = []
            for i in range(41):
                q = flow * i / 40
                try:
                    points.append([q, capacity(site, arm, critical["lane"], q, method)])
                except (ValueError, ArithmeticError, KeyError):
                    continue
            series[method] = points
        if any(series.values()):
            charts.append(
                chart(
                    f"Curvas de capacidad · {arm.code}/{critical['lane']}",
                    "Flujo conflictivo (eq/h)",
                    "Capacidad base (eq/h)",
                    series,
                )
            )
    flows = result["flow"]
    table_od = {(m.origin, m.destination): m.volume for m in site.movements if m.enabled}
    codes = [a.code for a in site.arms]
    records = [
        (
            "Demanda horaria OD (veh/h capturados)",
            ["Origen", *codes],
            [[i, *[table_od.get((i, j)) for j in codes]] for i in codes],
        ),
        (
            "Flujos por acceso y segmento (ajustados)",
            (
                "Ramal",
                "Entrada (veh/h)",
                "Salida (veh/h)",
                "Anillo por carril (veh/h)",
                "Conflicto por carril (eq/h)",
            ),
            [
                [
                    k,
                    sum(v["entry"]),
                    v["exit"],
                    " / ".join(f"{x:.3f}" for x in v["segment"]),
                    " / ".join(f"{x:.3f}" for x in v["conflict"]),
                ]
                for k, v in flows.items()
            ],
        ),
        (
            "Resultados por carril",
            (
                "Carril",
                "Demanda (veh/h)",
                "Demanda (eq/h)",
                "Conflicto (eq/h)",
                "Capacidad (veh/h)",
                "v/c",
                "Demora (s/veh)",
                "LOS",
                "Cola media equivalente (veh)",
                "P95 (veh)",
                "P95 (m)",
                "Tasa demora (veh·h/h)",
                "Viaje (s)",
            ),
            [
                [
                    f"{r['arm']}/{r['lane']}",
                    *[
                        r.get(key)
                        for key in (
                            "demand",
                            "equivalent",
                            "q",
                            "capacity",
                            "x",
                            "delay",
                            "los",
                            "qmean",
                            "q95",
                            "queue_m",
                            "delay_rate",
                            "travel",
                        )
                    ],
                ]
                for r in lanes
            ],
        ),
        (
            "Resultados por acceso",
            [
                "Ramal",
                *[
                    LABELS[key]
                    for key in (
                        "demand",
                        "capacity",
                        "reserve",
                        "x",
                        "delay",
                        "los",
                        "delay_total",
                        "queue_m",
                    )
                ],
            ],
            [
                [
                    item["arm"],
                    *[
                        item[key]
                        for key in (
                            "demand",
                            "capacity",
                            "reserve",
                            "x",
                            "delay",
                            "los",
                            "delay_total",
                            "queue_m",
                        )
                    ],
                ]
                for item in result["arms"]
            ],
        ),
        (
            "Comparación de modelos por carril",
            (
                "Carril",
                "Método",
                "Base (eq/h)",
                "Capacidad (veh/h)",
                "v/c",
                "Demora (s/veh)",
                "LOS",
                "Alcance",
            ),
            [
                [
                    f"{r['arm']}/{r['lane']}",
                    key,
                    val["nominal"],
                    val["capacity"],
                    val["x"],
                    val["delay"],
                    val["los"],
                    val["status"],
                ]
                for r in lanes
                for key, val in r["models"].items()
            ],
        ),
    ]
    return {
        "title": "Evaluación operacional" + (f" · {site.name}" if site.name else ""),
        "metrics": {
            "Método": result["method"],
            "Modelo": result["model"],
            **{LABELS[key]: value for key, value in result["overall"].items()},
        },
        "inputs": site.to_dict(),
        "notes": [
            REFERENCE[result["method"]],
            "El total de capacidad suma accesos bajo sus flujos conflictivos actuales.",
            "La cola media equivalente incluye demora de control; no mide longitud observada.",
            *result["warnings"],
        ],
        "tables": records,
        "charts": charts,
        "sources": SOURCES,
        "formulas": [
            CAPACITY_FORMULAS[key] for key in METHODS if any(key in row["models"] for row in lanes)
        ]
        + [
            r"\dot D=vd/3600,\qquad D=T\dot D,\qquad X=v/c",
            r"Q_{95}=\tfrac{Tc}{4}\left[X-1+\sqrt{(X-1)^2+24X/(Tc)}\right]",
        ],
    }


def geometry_record(site, geometry, review):
    limits = geometry["limit_issues"]
    return {
        "title": "Predimensionamiento y comprobaciones",
        "metrics": {
            "Diámetro inscrito (m)": geometry["diameter"],
            "Diámetro de isla (m)": geometry["island"],
            "Isla dura (m)": geometry["hard_island"],
            "Calzada anular (m)": geometry["width"],
            "Ancho uniforme de carril (m)": geometry["lane_width"],
            "Corona (m)": geometry["apron"],
            "Área inscrita (m²)": geometry["area"],
            "Radio medio del anillo (m)": geometry["centerline"],
            "Radio para velocidad objetivo (m)": geometry["minimum_radius"],
            "Vel. teórica en anillo (km/h)": geometry["centerline_speed"],
        },
        "notes": [
            "Predimensionamiento de esquema circular. Requiere verificación de huella, "
            "trayectoria barrida, visibilidad y velocidad de trayectoria real.",
            *limits,
        ],
        "tables": [
            (
                "Procedencia de las dimensiones",
                ("Dimensión", "Estado"),
                [[key, geometry["statuses"][key]] for key in ("diameter", "width", "island")],
            ),
            (
                "Comprobaciones por acceso",
                (
                    "Ramal",
                    "Ángulo al siguiente (grados)",
                    "Radio entrada (m)",
                    "Radio salida (m)",
                    "V entrada (km/h)",
                    "V anillo (km/h)",
                    "V salida (km/h)",
                    "Parada (m)",
                    "Visible (m)",
                    "Hallazgos",
                ),
                [
                    [
                        p["arm"],
                        p["separation"],
                        p["entry_path"],
                        p["exit_path"],
                        *p["speeds"],
                        p["stopping"],
                        p["sight"],
                        " ".join(p["flags"]),
                    ]
                    for p in review["checks"]
                ],
            ),
            (
                "Conflictos potenciales con movimientos habilitados",
                ("Ramal", "Carril", "Tipo"),
                [list(row[:3]) for row in review["conflicts"]],
            ),
        ],
        "inputs": site.to_dict(),
        "sources": SOURCES,
        "geometry": geometry,
        "conflicts": review["conflicts"],
        "formulas": [r"D=D_i+2w,\qquad R=L^2/(8h)+h/2,\qquad V=\sqrt{127 R(e+f)}"],
    }


def comparison_record(comparison, original, site):
    cols = ("capacity", "x", "delay", "delay_total", "los", "queue_m", "area")
    first = next(
        (r for r in comparison["alternatives"] if r["label"] == comparison["recommendation"]), None
    )
    winning = first["metrics"] if first else {}
    pairs = []
    for key, text in LABELS.items():
        left, right = original.get(key), winning.get(key)
        delta = (
            right - left
            if isinstance(left, (float, int)) and isinstance(right, (float, int))
            else None
        )
        pairs.append(
            [text, left, right, delta, delta / left * 100 if delta is not None and left else None]
        )
    notes = [
        "Comparación preliminar con la misma demanda de entrada; revisa los límites, "
        "entorno peatonal y compatibilidad geométrica.",
        "Indicadores de viaje y cola dependen de las longitudes y de la agrupación de carriles.",
    ]
    if first and not first["geometry"]["space_verified"]:
        notes.append("El espacio disponible para la alternativa recomendada queda por verificar.")
    if not first:
        notes.append("Ninguna propuesta cumple las restricciones y dispone del indicador objetivo.")
    return {
        "title": "Comparación de escenarios",
        "notes": notes,
        "metrics": {
            "Objetivo": comparison["objective"],
            "Alternativa preliminar": comparison["recommendation"],
            "Propuestas evaluadas": len(comparison["alternatives"]),
        },
        "tables": [
            (
                "Original y alternativa recomendada",
                ("Indicador", "Original", "Alternativa", "Diferencia", "Variación (%)"),
                pairs,
            ),
            (
                "Alternativas",
                [
                    "Configuración",
                    *[LABELS[key] for key in cols],
                    "Frente de Pareto",
                    "Restricciones",
                ],
                [
                    [
                        r["label"],
                        *[r["metrics"].get(key) for key in cols],
                        r.get("pareto"),
                        " ".join(r["reasons"]),
                    ]
                    for r in comparison["alternatives"]
                ],
            ),
        ],
        "charts": [
            chart(
                "Demora de control por alternativa",
                "Alternativa",
                "s/veh",
                {
                    f"R{i}": [[i, r["metrics"]["delay"]]]
                    for i, r in enumerate(comparison["alternatives"][:8], 1)
                    if r["metrics"].get("delay") is not None
                },
                bars=True,
            )
        ],
        "inputs": site.to_dict(),
        "sources": SOURCES,
    }


def calibration_record(result, observations):
    a, v = result["adjustment"], result["validation"]
    return {
        "title": f"Calibración de capacidad · {result['model']}",
        "notes": result["warnings"],
        "metrics": {
            "Intercepto": result["a"],
            "Pendiente": result["b"],
            "Mín. flujo (eq/h)": result["min"],
            "Máx. flujo (eq/h)": result["max"],
            "Brecha indirecta (s)": result["critical"],
            "Seguimiento indirecto (s)": result["followup"],
        },
        "tables": [
            (
                "Evaluación estadística",
                ("Muestra", "n", "R²", "RMSE (eq/h)", "MAE (eq/h)"),
                [
                    [label, *[m[k] for k in ("n", "r2", "rmse", "mae")]]
                    for label, m in (("Ajuste", a), ("Validación", v))
                ],
            ),
            (
                "Residuos",
                ("Muestra", "Flujo (eq/h)", "Observado", "Predicho", "Residuo (eq/h)"),
                [
                    [label, *row]
                    for label, m in (("Ajuste", a), ("Validación", v))
                    for row in m["rows"]
                ],
            ),
        ],
        "charts": [
            chart(
                "Capacidad observada y estimada",
                "Conflicto (eq/h)",
                "Capacidad (eq/h)",
                {
                    "Ajuste": [[x, y] for x, y, *_ in a["rows"]],
                    "Validación": [[x, y] for x, y, *_ in v["rows"]],
                    "Ajustado": sorted([[x, p] for x, _, p, _ in a["rows"]]),
                },
                markers=["Ajuste", "Validación"],
            )
        ],
        "inputs": {"observations": observations},
        "sources": SOURCES,
    }


def simulation_record(data):
    from hcnet.simulation.options import POLLUTANTS

    names = {"HC": "g", **POLLUTANTS}
    tables = []
    results = data["scenarios"]
    for scenario in results:
        scenario_name = scenario["name"]
        rows = [
            [
                metric,
                value["n"],
                value["mean"],
                value["sd"],
                value["ci95"][0] if value["ci95"] else None,
                value["ci95"][1] if value["ci95"] else None,
            ]
            for metric, value in (
                list(scenario["metrics"].items())
                + [(f"{k} ({names[k]})", v) for k, v in scenario["emissions"].items()]
            )
        ]
        tables.append(
            (
                f"SUMO · {scenario_name}",
                ("Indicador", "n", "Media", "DE", "IC95 inf.", "IC95 sup."),
                rows,
            )
        )
        tables.append(
            (
                f"Corridas · {scenario_name}",
                (
                    "Semilla",
                    "Solicitados",
                    "Insertados",
                    "Llegadas",
                    "Completos en medición",
                    "CO2 (kg, periodo)",
                    "Suma de colas positivas por carril (s)",
                ),
                [
                    [
                        run["seed"],
                        run["planned"],
                        run["departed"],
                        run["arrived"],
                        run["completed"],
                        run["emissions"]["CO2"],
                        sum(run["duration_positive_s"]),
                    ]
                    for run in scenario["runs"]
                ],
            )
        )
        queue_rows = []
        for run in scenario["runs"]:
            for (arm, lane, _), stats, duration, interval in zip(
                scenario["lanes"],
                run["lanes"].values(),
                run["duration_positive_s"],
                run["queue_intervals"],
                strict=True,
            ):
                queue_rows.append(
                    [
                        run["seed"],
                        f"{arm}/{lane}",
                        stats["mean"],
                        stats["max"],
                        stats["p95"],
                        duration,
                        *interval,
                    ]
                )
        tables.append(
            (
                f"Colas por carril · {scenario_name}",
                (
                    "Semilla",
                    "Carril",
                    "Media (m)",
                    "Máx. (m)",
                    "P95 (m)",
                    "Duración positiva (s)",
                    "Primer tiempo (s)",
                    "Último tiempo (s)",
                    "Cola al cierre",
                ),
                queue_rows,
            )
        )
    paired = len(results) > 1
    if paired:
        first = results[0]
        common = []
        for candidate in results[1:]:
            for key in (
                "Solicitados en medición",
                "Viajes completos de la cohorte",
                "Demora SUMO (timeLoss), s",
                "Duración de viaje, s",
                "CO2 (g por inserción; normalización de periodo)",
            ):
                base = first["metrics"].get(key, {}).get("mean")
                alternative = candidate["metrics"].get(key, {}).get("mean")
                common.append(
                    [
                        candidate["name"],
                        key,
                        base,
                        alternative,
                        alternative - base
                        if base is not None and alternative is not None
                        else None,
                    ]
                )
        tables.insert(
            0,
            (
                "Comparación de medias con plan de demanda común",
                ("Alternativa", "Indicador", "Original", "Alternativa", "Diferencia"),
                common,
            ),
        )
    return {
        "title": "Experimento de microsimulación vehicular",
        "metrics": {
            "Motor": data["sumo"],
            "Escenarios": len(results),
            "Corridas": len(data["seeds"]),
        },
        "notes": [
            "Tripinfo: viajes completos de la cohorte insertada en el periodo medido. "
            "Emisiones integradas para todos los vehículos presentes durante la medición.",
            "Compara volúmenes atendidos y pendientes antes de interpretar "
            "diferencias ambientales.",
        ],
        "tables": tables,
        "inputs": {
            "options": data["options"],
            "seeds": data["seeds"],
            "clases": data["classes"],
            "redes": [s["topology"] for s in results],
        },
        "sources": [
            "https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html",
            "https://sumo.dlr.de/docs/Simulation/Output/QueueOutput.html",
            "https://sumo.dlr.de/docs/Models/Emissions.html",
        ],
    }


def _diagram(record):
    geometry = record.get("geometry")
    raw = record.get("inputs", {})
    if not geometry or not raw.get("arms"):
        return ""
    site = Site.from_dict(raw)
    cx, cy, radius = 142, 86, 55
    island = 2 * radius * geometry["island"] / geometry["diameter"]
    lines = [
        r"\begin{center}\begin{picture}(285,175)",
        rf"\put({cx},{cy}){{\circle{{{2 * radius}}}}}",
        rf"\put({cx},{cy}){{\circle{{{island:.2f}}}}}",
    ]
    for arm in order(site):
        x, y = point(arm.azimuth, radius)
        x2, y2 = point(arm.azimuth, radius + 13)
        a, b = point(arm.azimuth, radius + 22)
        lines.extend(
            [
                rf"\Line({cx + x:.2f},{cy + y:.2f})({cx + x2:.2f},{cy + y2:.2f})",
                rf"\put({cx + a - 3:.2f},{cy + b - 3:.2f}){{{arm.code}}}",
            ]
        )
    return "\n".join([*lines, r"\end{picture}\end{center}"])


def sections(record):
    content = section(record)
    picture = _diagram(record)
    if not picture:
        return content
    head, _, body = content.partition("\n")
    return "\n".join((head, picture, body))


def report(project, record):
    from hcnet.domain.reporting import _module_latex

    return _module_latex(project, "Ingeniería de rotondas", sections(record))
