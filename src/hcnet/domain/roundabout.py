"""Diagnóstico operacional y predimensionamiento de rotondas de un carril."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from math import exp, isfinite, radians, sqrt
from typing import Any

ARM_LIMIT = 8


@dataclass(slots=True)
class RoundaboutArm:
    name: str = ""
    azimuth_deg: float = 0
    entry_width_m: float = 0
    exit_width_m: float = 0
    entry_radius_m: float = 0
    exit_radius_m: float = 0
    storage_m: float = 0
    heavy_percent: float = 0
    pedestrian_factor: float = 1
    entry_chord_m: float = 0
    entry_sagitta_m: float = 0
    exit_chord_m: float = 0
    exit_sagitta_m: float = 0


def default_arms() -> list[RoundaboutArm]:
    return [RoundaboutArm(azimuth_deg=45 * i) for i in range(ARM_LIMIT)]


@dataclass(slots=True)
class RoundaboutInput:
    name: str = ""
    arm_count: int = 3
    circulation: str = "Antihorario"
    arms: list[RoundaboutArm] = field(default_factory=default_arms)
    flows: list[list[float]] = field(
        default_factory=lambda: [[0.0] * ARM_LIMIT for _ in range(ARM_LIMIT)]
    )
    diameter_m: float = 0
    circulating_width_m: float = 0
    apron_width_m: float = 0
    design_speed_kmh: float = 0
    cross_slope_percent: float = -2
    side_friction: float = 0.20
    braking_deceleration_m_s2: float = 3.4
    reaction_time_s: float = 2.5
    peak_hour_factor: float = 1
    period_h: float = 0.25
    heavy_equivalency: float = 2
    vehicle_spacing_m: float = 7.5
    capacity_a: float = 1130
    capacity_b: float = 0.001

    @classmethod
    def from_dict(cls, raw: Any) -> RoundaboutInput:
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError("La rotonda debe ser un objeto.")
        data = cls()
        converters = {"name": str, "circulation": str, "arm_count": int}
        for param in fields(cls):
            key = param.name
            if key not in raw or key in {"arms", "flows"}:
                continue
            convert = converters.get(key, float)
            setattr(data, key, convert(raw[key]))
        arms = raw.get("arms", [])
        flows = raw.get("flows", [])
        if not isinstance(arms, list) or not isinstance(flows, list):
            raise ValueError("Los ramales y la matriz OD de la rotonda deben ser listas.")
        for index, arm in enumerate(arms[:ARM_LIMIT]):
            if not isinstance(arm, dict):
                raise ValueError("Cada ramal de la rotonda debe ser un objeto.")
            for param in fields(RoundaboutArm):
                if param.name in arm:
                    convert = str if param.name == "name" else float
                    setattr(data.arms[index], param.name, convert(arm[param.name]))
        for i, row in enumerate(flows[:ARM_LIMIT]):
            if not isinstance(row, list):
                raise ValueError("Cada fila de la matriz OD debe ser una lista.")
            for j, value in enumerate(row[:ARM_LIMIT]):
                data.flows[i][j] = float(value)
        return data


@dataclass(frozen=True, slots=True)
class ArmResult:
    code: str
    entry: float
    exiting: float
    conflicting: float
    conflicting_equivalent: float
    capacity: float
    saturation: float
    delay: float
    los: str
    queue_95: float
    queue_95_m: float
    entry_radius: float | None
    exit_radius: float | None
    entry_speed: float | None
    exit_speed: float | None
    next_angle: float
    arc_length: float


@dataclass(frozen=True, slots=True)
class RoundaboutResult:
    arms: tuple[ArmResult, ...]
    total_entry: float
    delay: float
    los: str
    island_radius: float
    hard_island_radius: float
    centerline_radius: float
    design_min_radius: float
    centerline_speed: float
    stopping_distance: float
    warnings: tuple[str, ...]


def level_of_service(delay: float) -> str:
    return next((letter for limit, letter in zip((10, 15, 25, 35, 50), "ABCDE", strict=True)
                 if delay <= limit), "F")


def _trajectory_radius(direct: float, chord: float, sagitta: float) -> float | None:
    if any(not isfinite(v) or v < 0 for v in (direct, chord, sagitta)):
        raise ValueError("Los radios, cuerdas y flechas deben ser finitos y no negativos.")
    if not chord and not sagitta:
        return direct or None
    if not 0 < sagitta <= chord / 2 or direct:
        raise ValueError("Usa radio directo o cuerda y flecha positiva (hasta media cuerda).")
    return chord**2 / (8 * sagitta) + sagitta / 2


def calculate_roundabout(data: RoundaboutInput) -> RoundaboutResult:
    """Asigna aforos OD a los conflictos de entrada y aplica NCHRP 672, capítulo 4."""

    count = data.arm_count
    if not 2 <= count <= ARM_LIMIT or len(data.arms) < count:
        raise ValueError("Configura entre dos y ocho ramales.")
    arms = data.arms[:count]
    if data.circulation not in {"Horario", "Antihorario"}:
        raise ValueError("Selecciona el sentido de circulación.")
    if any(not isfinite(arm.azimuth_deg) or not 0 <= arm.azimuth_deg < 360 for arm in arms):
        raise ValueError("Los azimuts deben estar entre 0° y menos de 360°.")
    if len({arm.azimuth_deg for arm in arms}) != count:
        raise ValueError("Asigna un azimut distinto a cada ramal.")
    positive = (
        data.diameter_m, data.circulating_width_m, data.design_speed_kmh, data.period_h,
        data.braking_deceleration_m_s2, data.capacity_a, data.vehicle_spacing_m,
    )
    if any(not isfinite(x) or x <= 0 for x in positive):
        raise ValueError("Completa diámetro, ancho anular, velocidad y parámetros positivos.")
    if not all(isfinite(x) for x in (
        data.cross_slope_percent, data.side_friction, data.apron_width_m, data.capacity_b,
        data.reaction_time_s, data.heavy_equivalency, data.peak_hour_factor,
    )):
        raise ValueError("Los parámetros de la rotonda deben ser finitos.")
    friction = data.side_friction + data.cross_slope_percent / 100
    if (
        not 0 < data.peak_hour_factor <= 1 or data.heavy_equivalency < 1
        or min(data.apron_width_m, data.capacity_b, data.reaction_time_s) < 0
        or not 0 <= data.side_friction <= 1 or friction <= 0
    ):
        raise ValueError("Revisa FHMD, equivalencia, fricción, pendiente y calibración.")
    island = data.diameter_m / 2 - data.circulating_width_m
    if island <= data.apron_width_m:
        raise ValueError("El ancho anular y la corona montable deben dejar una isla central.")
    centerline = data.diameter_m / 2 - data.circulating_width_m / 2
    min_radius = data.design_speed_kmh**2 / (127 * friction)
    speed = data.design_speed_kmh / 3.6
    stopping = speed * data.reaction_time_s + speed**2 / (2 * data.braking_deceleration_m_s2)

    if len(data.flows) < count or any(len(row) < count for row in data.flows[:count]):
        raise ValueError("Completa la matriz origen–destino.")
    flows = [[value / data.peak_hour_factor for value in row[:count]]
             for row in data.flows[:count]]
    if any(not isfinite(value) or value < 0 for row in flows for value in row):
        raise ValueError("Los aforos OD deben ser finitos y no negativos.")
    factors = []
    for arm in arms:
        dimensions = (
            arm.entry_width_m, arm.exit_width_m, arm.entry_radius_m, arm.exit_radius_m,
            arm.storage_m,
        )
        if (any(not isfinite(x) or x < 0 for x in dimensions)
                or not 0 <= arm.heavy_percent <= 100 or not 0 < arm.pedestrian_factor <= 1):
            raise ValueError("Revisa dimensiones, porcentaje de pesados y factor peatonal.")
        factors.append(1 + arm.heavy_percent / 100 * (data.heavy_equivalency - 1))
    order = sorted(range(count), key=lambda i: arms[i].azimuth_deg,
                   reverse=data.circulation == "Antihorario")
    conflicting = [0.0] * count
    equivalent = [0.0] * count
    for index, origin in enumerate(order):
        route = order[index + 1:] + order[:index]
        for step, current in enumerate(route):
            # Al alcanzar un ramal, las salidas de ese ramal ya no cruzan su entrada.
            passed = sum(flows[origin][j] for j in route[step + 1:]) + flows[origin][origin]
            conflicting[current] += passed
            equivalent[current] += passed * factors[origin]

    def curve_speed(radius: float | None) -> float | None:
        return sqrt(127 * radius * friction) if radius else None

    results = []
    warnings = []
    total = sum(map(sum, flows))
    if not total:
        warnings.append("Sin aforo de entrada. El nivel de servicio queda sin evaluar.")
    for index, arm in enumerate(arms):
        code = chr(ord("A") + index)
        entry = sum(flows[index])
        exiting = sum(row[index] for row in flows)
        capacity = data.capacity_a * exp(-data.capacity_b * equivalent[index])
        capacity *= arm.pedestrian_factor / factors[index]
        if capacity < 0.001 or not isfinite(capacity):
            raise ValueError(f"Capacidad fuera del rango numérico en el ramal {code}.")
        x = entry / capacity
        period = data.period_h
        delay = (
            3600 / capacity + 900 * period * (x - 1 + sqrt((x - 1)**2 + 8*x/(capacity*period)))
            + 5 * min(x, 1)
        ) if entry else 0.0
        queue = period * capacity / 4 * (x - 1 + sqrt((x - 1)**2 + 24*x/(capacity*period)))
        queue_m = queue * data.vehicle_spacing_m
        after = order[(order.index(index) + 1) % count]
        difference = arms[after].azimuth_deg - arm.azimuth_deg
        angle = (difference if data.circulation == "Horario" else -difference) % 360
        try:
            entry_radius = _trajectory_radius(
                arm.entry_radius_m, arm.entry_chord_m, arm.entry_sagitta_m,
            )
            exit_radius = _trajectory_radius(
                arm.exit_radius_m, arm.exit_chord_m, arm.exit_sagitta_m,
            )
        except ValueError as exc:
            raise ValueError(f"Ramal {code}. {exc}") from exc
        results.append(ArmResult(
            code, entry, exiting, conflicting[index], equivalent[index], capacity, x, delay,
            ("F" if x > 1 else level_of_service(delay)) if entry else "—",
            queue, queue_m, entry_radius, exit_radius,
            curve_speed(entry_radius), curve_speed(exit_radius),
            angle, centerline * radians(angle),
        ))
        if x >= 0.85:
            warnings.append(f"{code}. Relación v/c ≥ 0.85. Revisa sensibilidad y colas.")
        if equivalent[index] > 1000:
            warnings.append(f"{code}. Flujo conflictivo > 1 000 eq/h. Revisa la extrapolación.")
        if arm.storage_m and queue_m > arm.storage_m:
            warnings.append(f"{code}. La cola P95 supera el almacenamiento disponible.")
        if angle < 30:
            warnings.append(f"{code}. Separación angular menor de 30°. Revisa encaje geométrico.")
        for label, radius in (("entrada", entry_radius), ("salida", exit_radius)):
            if radius is not None and radius < min_radius:
                warnings.append(
                    f"{code}. El radio de {label} es menor al requerido para la velocidad "
                    "de comprobación con la fricción y pendiente capturadas."
                )
    mean_delay = sum(row.entry * row.delay for row in results) / total if total else 0.0
    return RoundaboutResult(
        tuple(results), total, mean_delay, level_of_service(mean_delay) if total else "—",
        island, island - data.apron_width_m, centerline, min_radius, sqrt(127*centerline*friction),
        stopping, tuple(warnings),
    )
