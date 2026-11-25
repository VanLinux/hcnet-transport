"""Calibración, conservación de demanda y comparación de diseños de rotondas."""

from dataclasses import replace
from math import exp, isfinite, log, sqrt
from statistics import mean

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.roundabout_engineering import (
    Arm,
    Movement,
    Site,
    check,
    design_geometry,
    evaluate,
    network,
    safety,
)
from hcnet.domain.signals import prepare_project


def calibrate(rows, model):
    """Mínimos cuadrados, o ajuste log-lineal de la capacidad exponencial."""
    actual = [(float(x), float(y)) for x, y, phase in rows if phase == "ajuste"]
    test = [(float(x), float(y)) for x, y, phase in rows if phase == "validación"]
    for x, y in actual + test:
        check(x, "Caudal conflictivo")
        check(y, "Capacidad observada", 0.001)
    if len(actual) < 3 or len({x for x, _ in actual}) < 3:
        raise ValueError("Se necesitan tres caudales distintos observados en saturación.")
    if model not in ("Exponencial", "Lineal", "Brechas"):
        raise ValueError("Selecciona un modelo calibrable.")
    xs = [x for x, _ in actual]
    ys = [y if model == "Lineal" else log(y) for _, y in actual]
    xm, ym = mean(xs), mean(ys)
    sxx = sum((x - xm) ** 2 for x in xs)
    slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys, strict=True)) / sxx
    intercept = ym - slope * xm
    if slope >= 0 or (model == "Lineal" and intercept <= 0):
        raise ValueError("El ajuste no es decreciente con una capacidad base positiva.")
    a = intercept if model == "Lineal" else exp(intercept)
    b = -slope
    follow = 3600 / a
    critical = 3600 * b + follow / 2
    if model == "Brechas" and critical < follow:
        raise ValueError("La calibración indirecta produce una brecha inferior al seguimiento.")
    lo, hi = min(xs), max(xs)
    warnings = []

    def metrics(data):
        values = [(x, y, a - b * x if model == "Lineal" else a * exp(-b * x)) for x, y in data]
        if any(predicted < 0 or not isfinite(predicted) for _, _, predicted in values):
            raise ValueError("La calibración produce capacidades físicamente inconsistentes.")
        residuals = [(x, y, p, y - p) for x, y, p in values]
        if not values:
            return {"n": 0, "r2": None, "rmse": None, "mae": None, "rows": []}
        error = sum(e * e for *_, e in residuals)
        average = mean(y for _, y, _ in values)
        variance = sum((y - average) ** 2 for _, y, _ in values)
        return {
            "n": len(data),
            "r2": 1 - error / variance if variance else None,
            "rmse": sqrt(error / len(data)),
            "mae": mean(abs(e) for *_, e in residuals),
            "rows": residuals,
        }

    if any(x < lo or x > hi for x, _ in test):
        warnings.append("Hay observaciones de validación fuera del dominio de ajuste.")
    return {
        "model": model,
        "a": a,
        "b": b,
        "min": lo,
        "max": hi,
        "followup": follow if model == "Brechas" else None,
        "critical": critical if model == "Brechas" else None,
        "adjustment": metrics(actual),
        "validation": metrics(test),
        "warnings": warnings,
    }


def accepted_gap(records):
    """Mediana del estimador por intervalos con par rechazo máximo / aceptación."""
    if len(records) < 5:
        raise ValueError("Captura al menos cinco pares consecutivos del mismo conductor.")
    for rejected, accepted in records:
        check(rejected, "Brecha máxima rechazada", 0.01)
        check(accepted, "Brecha aceptada", rejected + 0.00001)
    # Lognormal de dos parámetros, verosimilitud de intervalos [rechazada, aceptada].
    from math import erf

    def loglik(mu, sigma):
        return sum(
            log(
                max(
                    1e-300,
                    0.5
                    * (
                        erf((log(a) - mu) / (sigma * sqrt(2)))
                        - erf((log(r) - mu) / (sigma * sqrt(2)))
                    ),
                )
            )
            for r, a in records
        )

    mu = mean((log(r) + log(a)) / 2 for r, a in records)
    sigma = 0.45
    step = 0.25
    score = loglik(mu, sigma)
    while step > 1e-6:
        trials = [
            (m, s)
            for m, s in (
                (mu - step, sigma),
                (mu + step, sigma),
                (mu, sigma - step),
                (mu, sigma + step),
            )
            if 0.05 <= s <= 3
        ]
        score_new, modified_mu, modified_sigma = max((loglik(m, s), m, s) for m, s in trials)
        if score_new <= score + 1e-11:
            step /= 2
        else:
            mu, sigma, score = modified_mu, modified_sigma, score_new
    return {
        "median": exp(mu),
        "mean": exp(mu + sigma * sigma / 2),
        "sigma_log": sigma,
        "n": len(records),
        "at_bound": sigma < 0.051 or sigma > 2.999,
    }


def import_intersection(project):
    """Consolida grupos con el mismo par OD conservando flujo por clase y periodo."""
    project = prepare_project(project)
    active = {b.code for b in project.active_branches}
    if not 2 <= len(active) <= 8 or any(code not in "ABCDEFGH" for code in active):
        raise ValueError("Los ramales de la intersección no tienen identificadores compatibles.")
    grouped, arm_data = {}, {}
    for group in project.lane_groups:
        if group.origin_branch not in active:
            continue
        arm_data.setdefault(group.origin_branch, []).append(group)
        items = [m for m in group.movements if m.enabled]
        if not group.movements:
            if len(group.destination_branches) != 1:
                raise ValueError(f"{group.label}: desagrega los aforos originales por destino.")
            from hcnet.domain.models import MovementInput

            items = [
                MovementInput(
                    group.destination_branches[0],
                    group.volume_veh_h,
                    group.peak_hour_factor,
                    group.heavy_vehicles_percent,
                )
            ]
        for m in items:
            if m.destination not in active:
                raise ValueError("La intersección contiene movimientos a un ramal inactivo.")
            check(m.volume, "Aforo original")
            check(m.phf, "FHMD original", 0.01, 1)
            check(m.heavy_percent, "Pesados originales", 0, 100)
            grouped.setdefault((group.origin_branch, m.destination), []).append(m)
    movements = []
    for (origin, dest), items in sorted(grouped.items()):
        volume = sum(m.volume for m in items)
        rate = sum(m.volume / m.phf for m in items)
        heavy = sum(m.volume / m.phf * m.heavy_percent for m in items)
        movements.append(
            Movement(
                origin,
                dest,
                volume,
                heavy / rate if rate else 0,
                phf=volume / rate if rate else 1,
                source="Intersección HCNet",
            )
        )
    # Se conserva la geometría original en el proyecto archivado. Esta captura es la propuesta.
    arms = []
    for branch in project.active_branches:
        inputs = arm_data.get(branch.code, [])
        groups = len(inputs)
        arms.append(
            Arm(
                branch.code,
                branch.azimuth,
                branch.name,
                min(branch.inbound_lanes, 1),
                min(branch.outbound_lanes, 1),
                approach=mean(g.lane_width_m for g in inputs) if groups else 0,
                length=mean(g.approach_length_m for g in inputs) if groups else 0,
                speed=mean(g.free_flow_speed_kmh for g in inputs) if groups else 0,
            )
        )
    equivalents = {g.heavy_vehicle_equivalency for g in project.lane_groups}
    return Site(
        name=project.name,
        arms=tuple(arms),
        movements=tuple(movements),
        period=project.analysis_period_h,
        heavy_eq=next(iter(equivalents)) if len(equivalents) == 1 else 2,
    )


def intersection_metrics(project):
    result = calculate_intersection(project)
    rate = sum(row.demand_flow_rate_veh_h for row in result.lane_groups)
    delay = result.weighted_control_delay_s_veh
    arms = {a.code: [] for a in project.active_branches}
    project = prepare_project(project)
    labels = {g.identifier: g.origin_branch for g in project.lane_groups}
    for lane in result.lane_groups:
        arms[labels[lane.identifier]].append(lane.queue_95_m)
    capacity = sum(r.capacity_veh_h for r in result.lane_groups)
    return {
        "demand": rate,
        "capacity": capacity,
        "reserve": capacity - rate,
        "x": result.critical_degree_of_saturation,
        "delay": delay,
        "delay_rate": rate * delay / 3600,
        "delay_total": rate * delay * project.analysis_period_h / 3600,
        "los": result.level_of_service,
        "queue_m": result.maximum_queue_95_m,
        "travel": result.weighted_travel_time_s,
        "arm_queue": {key: max(values, default=0) for key, values in arms.items()},
    }


def design(site):
    proposed = design_geometry(site, propose=True)
    return replace(
        site, diameter=proposed["diameter"], island=proposed["island"], width=proposed["width"]
    ), proposed


def _candidate(site, kind, lanes, diameter, share, converting):
    if lanes != site.lanes and "lanes" in site.locks:
        return None
    if kind != site.kind and "kind" in site.locks:
        return None
    if diameter != site.diameter and "diameter" in site.locks:
        return None
    if lanes != site.lanes and any(
        f"{a.code}.inbound" in site.locks or f"{a.code}.outbound" in site.locks for a in site.arms
    ):
        return None

    def resize_arm(arm):
        if arm.lock_lanes:
            return arm
        inbound = lanes if arm.inbound else 0
        outbound = lanes if arm.outbound else 0
        lane_width = max(3.5, site.vehicle_width + 0.5)
        return replace(
            arm,
            inbound=inbound,
            outbound=outbound,
            entry=max(arm.entry, inbound * lane_width) if inbound else 0,
            exit=max(arm.exit, outbound * lane_width) if outbound else 0,
        )

    arms = tuple(resize_arm(arm) for arm in site.arms) if lanes != site.lanes else site.arms
    by_code = {a.code: a for a in arms}
    moves = tuple(
        replace(
            m,
            lane2=(
                share
                if by_code[m.origin].inbound > 1 and by_code[m.destination].outbound > 1
                else 0
            ),
        )
        for m in site.movements
    )
    changes = {"kind": kind, "lanes": lanes, "arms": arms, "movements": moves, "diameter": diameter}
    if any(f"{m.origin}>{m.destination}.lane2" in site.locks for m in site.movements):
        changes["movements"] = tuple(
            m if f"{m.origin}>{m.destination}.lane2" in site.locks else move
            for m, move in zip(site.movements, moves, strict=True)
        )
    if "width" not in site.locks and (converting or lanes != site.lanes):
        changes["width"] = 0
    if "island" not in site.locks:
        changes["island"] = 0
    if not changes.get("width", site.width) and not changes.get("island", site.island):
        changes["width"] = max(4.0, site.vehicle_width + 1) * lanes
        if "width" in site.locks:
            return None
    return replace(site, **changes)


def compare_designs(site, *, conversion=False, advanced=False, objective="Demora", weights=None):
    network(site)
    original = None if conversion else evaluate(site, advanced=advanced)
    if not conversion and (
        not original["overall"]["demand"] or original["overall"]["capacity"] is None
    ):
        raise ValueError(
            "Evalúa primero una configuración original con demanda y capacidad válidas."
        )
    if objective not in (
        "Demora",
        "Cola",
        "Saturación",
        "Capacidad",
        "Superficie",
        "Multicriterio",
    ):
        raise ValueError("Selecciona un objetivo de búsqueda.")
    if objective == "Multicriterio" and not advanced:
        raise ValueError("La evaluación multicriterio se habilita en modo avanzado.")
    types = [
        ("Minirotonda", 1, 22),
        ("Compacta", 1, 30),
        ("Un carril", 1, 40),
        ("Dos carriles", 2, 50),
    ]
    if not conversion:
        types.append((site.kind, site.lanes, site.diameter or 40))
    results, seen = [], set()
    for kind, lanes, nominal in types:
        for diameter in dict.fromkeys(
            [site.diameter]
            if "diameter" in site.locks
            else [
                nominal,
                nominal + 5,
                site.diameter or nominal,
            ]
        ):
            for share in (0, 30, 50) if lanes == 2 else (0,):
                key = (kind, lanes, diameter, share)
                if key in seen:
                    continue
                seen.add(key)
                candidate = _candidate(site, kind, lanes, diameter, share, conversion)
                if candidate is None:
                    continue
                row = {
                    "label": f"{kind} · {diameter:g} m · {share}% interior",
                    "site": candidate.to_dict(),
                    "metrics": {},
                    "reasons": [],
                    "geometry": None,
                }
                try:
                    candidate, geometry = design(candidate)
                    row["geometry"] = geometry
                    row["site"] = candidate.to_dict()
                    row["reasons"].extend(geometry["limit_issues"])
                    evidence = safety(candidate, geometry)
                    row["reasons"].extend(
                        f"{a['arm']}. {issue}"
                        for a in evidence["checks"]
                        for issue in a["flags"]
                        if any(
                            word in issue
                            for word in ("excede", "exceden", "inferior", "Visibilidad")
                        )
                    )
                    result = evaluate(candidate, advanced=advanced)
                    row["metrics"] = result["overall"]
                    overall = result["overall"]
                    if overall["capacity"] is None:
                        row["reasons"].append(
                            "Capacidad sin estimación aplicable para todos los accesos."
                        )
                    if overall["x"] is None or overall["x"] > 1:
                        row["reasons"].append("Demanda no compatible con los límites de capacidad.")
                    if overall["demand"] <= 0:
                        row["reasons"].append("Falta demanda para evaluar.")
                    row["metrics"]["area"] = geometry["area"]
                except (ValueError, ArithmeticError) as exc:
                    row["reasons"].append(str(exc))
                row["preliminary"] = not row["reasons"]
                results.append(row)
    columns = {
        "Demora": "delay",
        "Cola": "queue_m",
        "Saturación": "x",
        "Capacidad": "capacity",
        "Superficie": "area",
    }
    if objective in columns:
        key = columns[objective]
        for row in results:
            value = row["metrics"].get(key)
            row["score"] = (-value if key == "capacity" else value) if value is not None else None
    else:
        keys = ("delay", "queue_m", "x", "area")
        ws = [check(float(w), "Peso multicriterio") for w in (weights or [4, 2, 2, 1])]
        if len(ws) != 4 or not sum(ws):
            raise ValueError("Captura cuatro pesos y al menos uno positivo.")
        eligible = [
            r
            for r in results
            if r["preliminary"] and all(r["metrics"].get(k) is not None for k in keys)
        ]
        bounds = (
            [
                (min(r["metrics"][k] for r in eligible), max(r["metrics"][k] for r in eligible))
                for k in keys
            ]
            if eligible
            else []
        )
        for row in results:
            row["score"] = (
                sum(
                    w * (row["metrics"][k] - lo) / (hi - lo) if hi > lo else 0
                    for k, w, (lo, hi) in zip(keys, ws, bounds, strict=True)
                )
                / sum(ws)
                if (row in eligible)
                else None
            )
    if advanced:
        objectives = ("delay", "queue_m", "x", "area")
        eligible = [
            row
            for row in results
            if row["preliminary"] and all(row["metrics"].get(k) is not None for k in objectives)
        ]
        for row in eligible:
            current = [row["metrics"][k] for k in objectives]
            row["pareto"] = not any(
                all(
                    other["metrics"][k] <= value
                    for k, value in zip(objectives, current, strict=True)
                )
                and any(
                    other["metrics"][k] < value
                    for k, value in zip(objectives, current, strict=True)
                )
                for other in eligible
                if other is not row
            )
    results.sort(key=lambda r: (not r["preliminary"], r["score"] is None, r["score"] or 0))
    recommendation = next(
        (r["label"] for r in results if r["preliminary"] and r["score"] is not None), None
    )
    return {
        "original": original,
        "alternatives": results,
        "recommendation": recommendation,
        "objective": objective,
    }


def same_demand(original, proposal):
    def demand(site):
        return {
            (m.origin, m.destination): (m.volume, m.phf, m.heavy, m.bus, m.motorcycle)
            for m in site.movements
            if m.enabled and m.volume
        }

    a, b = demand(original), demand(proposal)
    return a.keys() == b.keys() and all(
        abs(x - y) < 1e-7 for k in a for x, y in zip(a[k], b[k], strict=True)
    )
