"""Estimación de escape en ralentí con factores aportados y documentados."""

from math import isfinite

from hcnet.domain.models import IntersectionProject
from hcnet.domain.signals import prepare_project
from hcnet.simulation.options import FleetType, validate_fleet

IDLE_POLLUTANTS = ("CO2", "CO", "NOx", "PMx")


def estimate_idle(
    project: IntersectionProject,
    fleet: tuple[FleetType, ...],
    duration: int,
    waiting: float,
    factors: dict,
    source: str,
) -> dict:
    validate_fleet(fleet, simulated=False)
    project = prepare_project(project)
    if not isfinite(waiting) or waiting < 0 or not 0 < duration or not source.strip():
        raise ValueError("Registra espera en ralentí, duración y fuente de los factores.")
    counts = {"ligero": 0.0, "pesado": 0.0}
    for group in project.lane_groups:
        volume = group.volume_veh_h / group.peak_hour_factor * duration / 3600
        heavy = volume * group.heavy_vehicles_percent / 100
        counts["ligero"] += volume - heavy
        counts["pesado"] += heavy
    active = [item for item in fleet if item.percent and counts[item.category]]
    pollutants = [
        key
        for key in IDLE_POLLUTANTS
        if active
        and all(
            "eléctrico" in item.label or factors.get(item.label, {}).get(key) is not None
            for item in active
        )
    ]
    if not pollutants:
        raise ValueError("Registra al menos un contaminante para todas las categorías con demanda.")
    by_type = {}
    for item in active:
        rates = factors.get(item.label, {})
        hours = counts[item.category] * item.percent / 100 * waiting / 3600
        totals = {}
        for key in pollutants:
            rate = 0 if "eléctrico" in item.label else float(rates[key])
            if not isfinite(rate) or rate < 0:
                raise ValueError("Los factores deben ser finitos y no negativos (g/veh·h).")
            totals[key] = hours * rate / (1000 if key == "CO2" else 1)
        by_type[item.label] = totals
    return {
        "duration": duration,
        "waiting": waiting,
        "source": source,
        "factors": factors,
        "composition": {item.label: item.percent for item in fleet},
        "demand": counts,
        "by_type": by_type,
        "totals": {key: sum(v[key] for v in by_type.values()) for key in pollutants},
    }


def emission_difference(reference, alternative, engine, pollutant):  # noqa: ANN001, ANN201
    if not reference:
        return None
    if engine == "simulation":
        comparable = ("sumo", "fleet", "demand", "lanes", "geometry")
        if any(reference.get(k) != alternative.get(k) for k in comparable):
            return None
        reference_options = {k: v for k, v in reference["options"].items() if k != "seed"}
        alternative_options = {k: v for k, v in alternative["options"].items() if k != "seed"}
        if reference_options != alternative_options:
            return None
        old = reference["emissions"][pollutant]["mean"]
        new = alternative["emissions"][pollutant]["mean"]
    else:
        comparable = ("duration", "composition", "factors", "source", "demand")
        if any(reference.get(k) != alternative.get(k) for k in comparable):
            return None
        old = reference["totals"].get(pollutant)
        new = alternative["totals"].get(pollutant)
        if old is None or new is None:
            return None
    delta = new - old
    return old, new, delta, 100 * delta / old if old else None
