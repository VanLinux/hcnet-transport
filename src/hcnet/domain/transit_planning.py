"""Dimensionamiento, calibración, comparación y selección tecnológica."""

from itertools import product
from math import ceil, exp, floor, isfinite, sqrt
from statistics import mean

from hcnet.domain.transit_engineering import (
    Door,
    Service,
    dwell,
    evaluate,
    fraction,
    number,
    service_quality,
    spacing,
    station_capacity,
)

MODELS = {
    "Lineal": r"t=t_0(1+\alpha x)",
    "BPR": r"t=t_0(1+\alpha x^\beta)",
    "Davidson": r"t=t_0[1+\alpha x/(1-x)]",
    "Exponencial": r"t=t_0\exp(\alpha x)",
}


def road_time(model, x, t0, alpha, beta=4):
    number(x, "Grado de saturación")
    number(t0, "Tiempo libre", positive=True)
    number(alpha, "Coeficiente")
    if model == "Davidson" and x >= 1:
        return None
    try:
        if model == "Exponencial":
            value = t0 * exp(alpha * x)
        else:
            term = {"Lineal": lambda: x, "BPR": lambda: x**beta, "Davidson": lambda: x / (1 - x)}[
                model
            ]()
            value = t0 * (1 + alpha * term)
        return value if isfinite(value) else None
    except OverflowError:
        return None


def fit(model, rows, capacity, fixed=None, validation=()):
    """Ajuste no lineal por mínimos cuadrados en minutos; capacidad externa y fija."""
    number(capacity, "Capacidad vial", positive=True)
    parameters = ["t0", "alpha"] + (["beta"] if model == "BPR" else [])
    fixed = dict(fixed or {})
    if any(key not in parameters for key in fixed):
        raise ValueError("Parámetro fijo desconocido.")
    for key, value in fixed.items():
        number(value, key, positive=key != "alpha")
    free = [key for key in parameters if key not in fixed]

    def observations(items):
        return [
            (number(q, "Flujo") / capacity, number(t, "Tiempo", positive=True)) for q, t in items
        ]

    data, test = observations(rows), observations(validation)
    if len({x for x, _ in data}) < max(1, len(free) + 1):
        raise ValueError("Registra más niveles distintos de flujo para separar los parámetros.")
    if model == "Davidson" and any(x >= 1 for x, _ in data + test):
        raise ValueError("Davidson requiere flujo inferior a capacidad en todas las observaciones.")
    if "beta" in free and fixed.get("alpha") == 0:
        raise ValueError("No se puede estimar beta cuando alfa está fijada en cero.")

    def error(values):
        params = dict(zip(free, values, strict=True)) | fixed
        predictions = [road_time(model, x, **params) for x, _ in data]
        if any(value is None for value in predictions):
            return float("inf")
        residuals = [abs(t - y) for (_, t), y in zip(data, predictions, strict=True)]
        return float("inf") if max(residuals) > 1e150 else sum(r * r for r in residuals)

    low_time = min(t for _, t in data)
    seeds = {
        "t0": [0.45 * low_time, 0.85 * low_time, low_time],
        "alpha": [0.05, 0.25, 1],
        "beta": [0.8, 2, 4, 8],
    }
    bounds = {
        "t0": (max(low_time * 1e-6, 1e-10), max(t for _, t in data) * 2),
        "alpha": (0, 100),
        "beta": (0.05, 20),
    }
    best, score, converged = None, float("inf"), False
    for guess in product(*(seeds[key] for key in free)):
        values = list(guess)
        current = error(values)
        steps = [max(value * 0.4, 0.1) for value in values]
        done = not free
        for _ in range(450):
            improved = False
            for i, key in enumerate(free):
                lower, upper = bounds[key]
                for direction in (-1, 1):
                    trial = values.copy()
                    trial[i] = min(upper, max(lower, values[i] + direction * steps[i]))
                    candidate = error(trial)
                    if candidate < current:
                        values, current, improved = trial, candidate, True
            if not improved:
                steps = [step * 0.5 for step in steps]
            if max(steps, default=0) < 1e-7:
                done = True
                break
        if current < score:
            best, score, converged = values, current, done
    if best is None:
        raise ValueError("No se encontró un conjunto finito de parámetros.")
    parameters = dict(zip(free, best, strict=True)) | fixed

    def metrics(items):
        if not items:
            return {}
        predicted = [road_time(model, x, **parameters) for x, _ in items]
        if any(value is None for value in predicted):
            raise ValueError("El modelo no produce tiempos finitos para estos flujos.")
        average = mean(t for _, t in items)
        variation = sum((t - average) ** 2 for _, t in items)
        points = [(x, t, est, t - est) for (x, t), est in zip(items, predicted, strict=True)]
        squared = sum(residual**2 for *_, residual in points)
        return {
            "r2": 1 - squared / variation if variation else None,
            "rmse": sqrt(squared / len(items)),
            "mae": mean(abs(row[3]) for row in points),
            "points": points,
        }

    return {
        "parameters": parameters,
        "calibration": metrics(data),
        "validation": metrics(test),
        "converged": converged,
        "bounds": {key: bounds[key] for key in free},
        "boundary": [
            key
            for key, value in zip(free, best, strict=True)
            if min(abs(value - bound) for bound in bounds[key]) <= 1e-6
        ],
    }


def economics(
    frequency,
    length,
    trips_hours,
    days,
    paid_boardings,
    fare,
    cost_km,
    fixed,
    *,
    investment=0,
    years=0,
    discount=0,
    currency="MXN",
):
    for key, value in locals().copy().items():
        if key != "currency":
            number(value, key)
    if int(years) != years or years > 100:
        raise ValueError("El horizonte debe ser un entero de 0 a 100 años.")
    km = 2 * length * frequency * trips_hours * days
    revenue = fare * paid_boardings * days
    operating = km * cost_km + fixed
    annuity = sum((1 + discount) ** (-year) for year in range(1, int(years) + 1))
    return {
        "currency": currency,
        "annual_km": km,
        "revenue": revenue,
        "cost": operating,
        "balance": revenue - operating,
        "subsidy": max(0, operating - revenue),
        "cost_per_boarding": operating / (paid_boardings * days)
        if paid_boardings and days
        else None,
        "coverage": revenue / operating if operating else None,
        "npv": (revenue - operating) * annuity - investment if years else None,
    }


def recommend(
    rows,
    demand,
    available,
    grade,
    *,
    budget=0,
    radius=0,
    width=0,
    weights=(4, 3, 2, 1),
    method="Ponderado",
):
    """Filtros físicos previos y orden explícitamente condicionado a entradas comparables."""
    demand = number(demand, "Demanda de diseño", positive=True)
    for value, name in (
        (grade, "Pendiente"),
        (radius, "Radio"),
        (width, "Ancho"),
        (budget, "Presupuesto"),
    ):
        number(value, name)
    if method not in ("Ponderado", "TOPSIS") or len(weights) != 4:
        raise ValueError("Selecciona un método y cuatro pesos.")
    weights = tuple(number(w, "Peso") for w in weights)
    number(sum(weights), "Suma de pesos", positive=True)
    eligible, excluded = [], []
    for row in rows:
        reasons, pending = [], []
        for key, actual, label, violates in (
            ("capacity", demand, "capacidad", lambda a, b: a < b),
            ("cost", budget, "presupuesto", lambda a, b: b > 0 and a > b),
            ("grade", grade, "pendiente", lambda a, b: a < b),
            ("radius", radius, "radio", lambda a, b: b > 0 and a > b),
            ("width", width, "ancho", lambda a, b: b > 0 and a > b),
        ):
            value = row.get(key)
            if value is None or (key in {"radius", "width"} and not actual and value > 0):
                pending.append(label)
            elif violates(number(value, label), actual):
                reasons.append(label)
        if row.get("infra") not in available:
            reasons.append("infraestructura")
        for key in ("speed", "quality"):
            if row.get(key) is None:
                pending.append(key)
            else:
                number(row[key], key)
        if reasons or pending:
            excluded.append({"name": row["name"], "reasons": reasons, "pending": pending})
        else:
            eligible.append(row)
    if not eligible:
        return {"ranking": [], "excluded": excluded, "sensitivity": []}
    columns = list(
        zip(*[(r["capacity"], r["cost"], r["speed"], r["quality"]) for r in eligible], strict=False)
    )

    def rank(active_weights):
        normalized = []
        for i, column in enumerate(columns):
            lo, hi = min(column), max(column)
            if method == "TOPSIS":
                norm = sqrt(sum(value**2 for value in column))
                direction = -1 if i == 1 else 1
                normalized.append([direction * value / norm if norm else 0 for value in column])
            else:
                normalized.append(
                    [((hi - x if i == 1 else x - lo) / (hi - lo)) if hi > lo else 1 for x in column]
                )
        active_weights = [w / sum(active_weights) for w in active_weights]
        if method == "TOPSIS":
            weighted = [
                [value * w for value in col]
                for w, col in zip(active_weights, normalized, strict=True)
            ]
            ideal, anti = [max(col) for col in weighted], [min(col) for col in weighted]
            scores = []
            for row in zip(*weighted, strict=False):
                good = sqrt(sum((x - y) ** 2 for x, y in zip(row, ideal, strict=True)))
                bad = sqrt(sum((x - y) ** 2 for x, y in zip(row, anti, strict=True)))
                scores.append(bad / (bad + good) if good + bad else 1)
        else:
            scores = [
                sum(w * x for w, x in zip(active_weights, row, strict=True))
                for row in zip(*normalized, strict=False)
            ]
        return sorted(
            (dict(row, score=score) for row, score in zip(eligible, scores, strict=True)),
            key=lambda row: (-row["score"], row["name"]),
        )

    ranking = rank(weights)
    sensitivity = []
    for i, label in enumerate(("Capacidad", "Costo", "Velocidad", "Calidad")):
        for factor in (0.8, 1.2):
            changes = [w * factor if i == j else w for j, w in enumerate(weights)]
            sensitivity.append((label, factor, rank(changes)[0]["name"]))
    return {"ranking": ranking, "excluded": excluded, "sensitivity": sensitivity}


def optimize(
    line: Service,
    min_s,
    max_s,
    step_s,
    fleet_limit,
    cost_per_hour,
    budget,
    objective,
    alternatives=(),
):
    from dataclasses import replace

    for value, label in (
        (min_s, "Intervalo mínimo"),
        (max_s, "Intervalo máximo"),
        (step_s, "Paso"),
        (fleet_limit, "Flota límite"),
    ):
        number(value, label, positive=True)
    number(cost_per_hour, "Costo unitario")
    number(budget, "Presupuesto horario")
    if objective not in ("Espera", "Flota", "Costo", "Viaje", "Ocupación", "Pareto"):
        raise ValueError("Objetivo desconocido.")
    count = floor((max_s - min_s) / step_s + 1e-9) + 1
    if not 0 < count <= 800 or count * (len(alternatives) + 1) > 2500:
        raise ValueError("Ajusta el intervalo y el paso para limitar la búsqueda.")
    original = evaluate(line)
    rows = []
    for candidate in (line, *alternatives):
        reference = evaluate(candidate)
        base_frequency = reference["frequency"]
        if candidate.passenger_units == "Por unidad" and (candidate.stations or candidate.reverse):

            def hourly(stations, frequency):
                return tuple(
                    replace(s, board=s.board * frequency, alight=s.alight * frequency)
                    for s in stations
                )

            candidate = replace(
                candidate,
                stations=hourly(candidate.stations, base_frequency),
                reverse=hourly(candidate.reverse, base_frequency),
                passenger_units="Por hora",
                initial_pax=candidate.initial_pax * base_frequency,
                initial_reverse_pax=candidate.initial_reverse_pax * base_frequency,
            )
        for index in range(count):
            seconds = min_s + step_s * index
            updated = replace(candidate, headway_min=seconds / 60)
            if candidate.technology == "cable":
                updated = replace(updated, cable_spacing_m=seconds * candidate.speed_kmh / 3.6)
                if updated.cable_spacing_m < updated.cable_min_spacing_m:
                    continue
            result = evaluate(updated)
            cost = result["fleet"] * cost_per_hour
            if (
                result["fleet_total"] > fleet_limit
                or result["margin"] < -1e-8
                or result["frequency"] > result["max_frequency"] + 1e-8
                or (budget and cost > budget)
                or any(
                    row["platform_pax_h"] and row["platform_load"] > row["platform_pax_h"]
                    for profile in result["profiles"]
                    for row in profile
                )
            ):
                continue
            rows.append(
                {
                    "name": candidate.name,
                    "headway_s": seconds,
                    "wait": seconds / 120,
                    "fleet": result["fleet_total"],
                    "cost": cost,
                    "offer": result["achievable"],
                    "margin": result["margin"],
                    "cycle": result["cycle"],
                    "travel_min": result["travel_min"],
                    "travel": mean(result["travel_min"]),
                    "occupation": result["occupation"],
                    "dwell": sum(result["dwell_total_s"]),
                    "station_limit": result["max_frequency"],
                    "warnings": result["warnings"],
                }
            )
    if objective == "Pareto":
        # A igualdad de espera y flota se conserva el costo mínimo.
        ordered = sorted(rows, key=lambda row: (row["wait"], row["fleet"], row["cost"]))
        rows = []
        best_costs = {}
        for row in ordered:
            size, cost = row["fleet"], row["cost"]
            if any(fleet <= size and best <= cost for fleet, best in best_costs.items()):
                continue
            rows.append(row)
            best_costs[size] = cost
    else:
        key = {
            "Espera": "wait",
            "Flota": "fleet",
            "Costo": "cost",
            "Viaje": "travel",
            "Ocupación": "occupation",
        }[objective]
        rows.sort(
            key=lambda row: (
                -row[key] if objective == "Ocupación" else row[key],
                row["wait"],
                row["cost"],
                row["fleet"],
            )
        )
    return {"original": original, "alternatives": rows[:30], "objective": objective}


# Los campos describen captura, unidad y si se permite cero. Cada método es independiente.
SPECIFIC = {
    "Frecuencia": ("f=60/h", [("h", "Intervalo (min)")]),
    "Intervalo": ("h=60/f", [("f", "Frecuencia (unid/h)")]),
    "Capacidad de línea": (
        r"Q=fC\lambda",
        [
            ("f", "Frecuencia (unid/h)"),
            ("c", "Capacidad por unidad (pax)"),
            ("l", "Factor de ocupación (0–1)"),
        ],
    ),
    "Tamaño mínimo de unidad": (
        r"C=\lceil D/(f\lambda)\rceil",
        [
            ("d", "Demanda (pax/h)"),
            ("f", "Frecuencia (unid/h)"),
            ("l", "Factor de ocupación (0–1)"),
        ],
    ),
    "Flota mínima": (
        r"N=\lceil T_c/h\rceil",
        [("t", "Tiempo de ciclo (min)"), ("h", "Intervalo (min)")],
    ),
    "Frecuencia con flota disponible": (
        "f=60N/T_c",
        [("n", "Flota operativa (unid)"), ("t", "Tiempo de ciclo (min)")],
    ),
    "Velocidad comercial": (
        "v_c=60L/T_v",
        [("l", "Longitud (km)"), ("t", "Tiempo de viaje (min)")],
    ),
    "Viaje y ciclo": (
        r"T_v=60L/v+t_p,\quad T_c=2(T_v+t_r)",
        [
            ("l", "Longitud por sentido (km)"),
            ("v", "Velocidad en marcha (km/h)"),
            ("p", "Permanencia total por sentido (min)"),
            ("r", "Regulación por terminal (min)"),
        ],
    ),
    "Ascenso, descenso y permanencia": (
        r"t_p=t_f+t_b b+t_a a",
        [
            ("b", "Ascensos (pax/unidad)"),
            ("a", "Descensos (pax/unidad)"),
            ("tb", "Ascenso unitario (s/pax)"),
            ("ta", "Descenso unitario (s/pax)"),
            ("tf", "Tiempo fijo (s)"),
        ],
    ),
    "Capacidad de estación": (
        "q=3600N/(t_p+t_d)",
        [("n", "Posiciones de atención"), ("p", "Permanencia (s)"), ("d", "Despeje (s)")],
    ),
    "Espaciamiento y acceso": (
        r"e=1000L/(n-1),\quad E[t_a]=e/(240v_p)",
        [
            ("l", "Longitud (km)"),
            ("n", "Estaciones incluidas terminales"),
            ("v", "Velocidad peatonal (m/s)"),
            ("x", "Longitud media del viaje (km, opcional)"),
            ("p", "Pérdida por parada (s, opcional)"),
        ],
    ),
    "Oferta, demanda y ocupación": (
        r"Q=fC\lambda,\quad \rho=D/(fC)",
        [
            ("d", "Demanda crítica (pax/h/sentido)"),
            ("f", "Frecuencia (unid/h)"),
            ("c", "Capacidad nominal (pax/unidad)"),
            ("l", "Factor de ocupación (0–1)"),
        ],
    ),
    "Calidad y espera": (
        r"E[W]=\sum h_i^2/(2\sum h_i)",
        [("h", "Intervalo programado (min, opcional)")],
    ),
}


def specific(method, values, observed=(), random_arrivals=False, regular=False):
    a = values
    for key, label in SPECIFIC[method][1]:
        positive = key in {"f", "h", "n", "l", "t", "v", "c", "tb", "ta"} and (
            method != "Calidad y espera" or not observed
        )
        number(a[key], label, positive=positive)
        if key == "n" and a[key] != int(a[key]):
            raise ValueError(f"{label} se expresa en unidades enteras.")
    if method == "Frecuencia":
        return {"Frecuencia (unid/h)": 60 / a["h"]}
    if method == "Intervalo":
        return {"Intervalo (min)": 60 / a["f"]}
    if method == "Tamaño mínimo de unidad":
        return {
            "Capacidad mínima (pax/unidad)": ceil(a["d"] / (a["f"] * fraction(a["l"], "Factor")))
        }
    if method == "Flota mínima":
        return {"Flota operativa (unid)": ceil(a["t"] / a["h"])}
    if method == "Frecuencia con flota disponible":
        f = 60 * a["n"] / a["t"]
        return {"Frecuencia (unid/h)": f, "Intervalo (min)": 60 / f}
    if method == "Velocidad comercial":
        return {"Velocidad comercial (km/h)": 60 * a["l"] / a["t"]}
    if method == "Viaje y ciclo":
        trip = 60 * a["l"] / a["v"] + a["p"]
        return {"Viaje por sentido (min)": trip, "Tiempo de ciclo (min)": 2 * (trip + a["r"])}
    if method == "Ascenso, descenso y permanencia":
        result = dwell(
            a["b"],
            a["a"],
            (Door(board_s=a["tb"], alight_s=a["ta"], fixed_s=a["tf"]),),
            "Secuencial",
        )
        return {
            "Ascenso (s)": result["boarding_s"],
            "Descenso (s)": result["alighting_s"],
            "Permanencia (s)": result["seconds"],
        }
    if method == "Capacidad de estación":
        return {"Capacidad (unid/h)": station_capacity(a["n"], a["p"], a["d"])}
    if method == "Espaciamiento y acceso":
        result = spacing(a["l"], a["n"], a["v"], a["x"], a["p"])
        return dict(
            zip(
                (
                    "Espaciamiento (m)",
                    "Acceso medio (min)",
                    "Espaciamiento óptimo (m)",
                    "Número de estaciones sugerido",
                ),
                result.values(),
                strict=True,
            )
        )
    if method == "Calidad y espera":
        result = service_quality(a["h"], observed, random_arrivals, regular)
        return dict(
            zip(
                (
                    "Espera media (min)",
                    "Intervalo observado medio (min)",
                    "Coeficiente de variación",
                    "Intervalo máximo (min)",
                ),
                result.values(),
                strict=True,
            )
        )
    nominal = a["f"] * a["c"]
    design = nominal * fraction(a["l"], "Factor")
    ret = {"Oferta física (pax/h)": nominal, "Oferta de diseño (pax/h)": design}
    if method == "Oferta, demanda y ocupación":
        ret.update(
            {"Ocupación proyectada (%)": 100 * a["d"] / nominal, "Margen (pax/h)": design - a["d"]}
        )
    return ret
