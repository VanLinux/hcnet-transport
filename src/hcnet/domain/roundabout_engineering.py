"""Modelo de rotondas convencionales con trazabilidad de movimientos y carriles."""

from dataclasses import asdict, dataclass
from math import exp, hypot, isfinite, pi, radians, sqrt

from hcnet.domain.roundabout import RoundaboutInput, _trajectory_radius, level_of_service

METHODS = ("HCM", "Brechas", "Lineal", "Kimber")
KINDS = (
    "Minirotonda",
    "Compacta",
    "Un carril",
    "Dos carriles",
    "Personalizada",
    "Multicarril",
    "Turborrotonda",
)
MODES = (
    "Evaluar rotonda existente",
    "Diseñar rotonda",
    "Optimizar rotonda",
    "Convertir intersección",
)
MODEL_ID = "HCNet rotondas 3.6.0 · FHWA-SA-15-070 / CD 116 B"
# (carriles de entrada, carriles circulantes, carril relativo al exterior).
HCM = {
    (1, 1, 1): (1380, 0.00102),
    (1, 2, 1): (1420, 0.00085),
    (2, 1, 1): (1420, 0.00091),
    (2, 1, 2): (1420, 0.00091),
    (2, 2, 1): (1420, 0.00085),
    (2, 2, 2): (1350, 0.00092),
}
REFERENCE = {
    "HCM": "FHWA-SA-15-070 y HCM, cap. 22 · flujos en automóviles equivalentes/h.",
    "Brechas": "Modelo exponencial de Siegloch · llegadas conflictivas aleatorias.",
    "Lineal": "Regresión local de capacidad en saturación · dominio de calibración explícito.",
    "Kimber": "CD 116 rev. 2, apéndice B · capacidad total de acceso convencional.",
}


def check(value, label, low=0, high=float("inf")):
    if not isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label}: valor fuera del intervalo permitido.")
    return value


@dataclass(frozen=True)
class Arm:
    code: str
    azimuth: float
    name: str = ""
    inbound: int = 1
    outbound: int = 1
    entry: float = 0.0
    exit: float = 0.0
    approach: float = 0.0
    flare: float = 0.0
    entry_angle: float = 0.0
    curb_radius: float = 0.0
    entry_path: float = 0.0
    exit_path: float = 0.0
    entry_chord: float = 0.0
    entry_sagitta: float = 0.0
    sight: float = 0.0
    length: float = 0.0
    speed: float = 0.0
    storage: float = 0.0
    splitter: float = 0.0
    bypass_width: float = 0.0
    available_width: float = 0.0
    grade: float = 0.0
    pedestrians: float = 0.0
    cycles: float = 0.0
    crossing: float = 0.0
    pedestrian_factor: float = 1.0
    local_factor: float = 1.0
    factor_source: str = ""
    outer_queue: float = 0.0
    inner_queue: float = 0.0
    inner_conflicts: str = "Todos"
    outer_conflicts: str = "Todos"
    lock_lanes: bool = False
    lock_azimuth: bool = False


@dataclass(frozen=True)
class Movement:
    origin: str
    destination: str
    volume: float = 0.0
    heavy: float = 0.0
    bus: float = 0.0
    motorcycle: float = 0.0
    phf: float = 1.0
    lane2: float = 0.0
    enabled: bool = True
    source: str = ""


@dataclass(frozen=True)
class Site:
    name: str = ""
    arms: tuple[Arm, ...] = ()
    movements: tuple[Movement, ...] = ()
    lanes: int = 1
    direction: str = "Antihorario"
    driving: str = "Derecha"
    kind: str = "Un carril"
    diameter: float = 0.0
    island: float = 0.0
    width: float = 0.0
    apron: float = 0.0
    speed: float = 0.0
    crossfall: float = -2
    friction: float = 0.20
    available_diameter: float = 0.0
    available_area: float = 0.0
    space_width: float = 0.0
    space_length: float = 0.0
    vehicle_name: str = ""
    vehicle_width: float = 0.0
    vehicle_length: float = 0.0
    wheelbase: float = 0.0
    minimum_turn: float = 0.0
    period: float = 0.25
    heavy_eq: float = 2.0
    bus_eq: float = 2.0
    motorcycle_eq: float = 1.0
    spacing: float = 7.5
    method: str = "HCM"
    critical_gap: float = 0.0
    followup: float = 0.0
    linear_a: float = 0.0
    linear_b: float = 0.0
    linear_min: float = 0.0
    linear_max: float = 0.0
    fitted_a: float = 0.0
    fitted_b: float = 0.0
    fitted_min: float = 0.0
    fitted_max: float = 0.0
    model_source: str = ""
    locks: tuple[str, ...] = ()
    hybrid: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, payload):
        data = dict(payload)
        arms = tuple(Arm(**row) for row in data.pop("arms", []))
        moves = tuple(Movement(**row) for row in data.pop("movements", []))
        locks = tuple(data.pop("locks", ()))
        return cls(arms=arms, movements=moves, locks=locks, **data)


def blank_arms(count=4):
    return tuple(Arm(chr(65 + i), i * 360 / count) for i in range(count))


def order(site):
    return tuple(
        sorted(site.arms, key=lambda a: a.azimuth, reverse=site.direction == "Antihorario")
    )


def network(site):
    """Lista de trayectorias con su carril continuo y las secciones atravesadas."""
    n = len(site.arms)
    codes = {a.code: a for a in site.arms}
    if not 2 <= n <= 8 or len(codes) != n or any(c not in "ABCDEFGH" or len(c) != 1 for c in codes):
        raise ValueError("Configura de dos a ocho ramales con identificadores distintos.")
    if (site.direction, site.driving) not in {("Horario", "Izquierda"), ("Antihorario", "Derecha")}:
        raise ValueError("El sentido del anillo debe ser coherente con el lado de conducción.")
    if type(site.lanes) is not int or not 1 <= site.lanes <= 4 or site.kind not in KINDS:
        raise ValueError("Selecciona de uno a cuatro carriles y un tipo de rotonda.")
    required_lanes = {"Minirotonda": 1, "Compacta": 1, "Un carril": 1, "Dos carriles": 2}
    required = required_lanes.get(site.kind)
    if (required and required != site.lanes) or (site.kind == "Multicarril" and site.lanes < 3):
        raise ValueError("El número de carriles debe corresponder al tipo de rotonda.")
    if len({a.azimuth for a in site.arms}) != n:
        raise ValueError("Los ejes de los ramales deben tener azimuts distintos.")
    for a in site.arms:
        check(a.azimuth, f"{a.code} · Azimut", 0, 359.999999)
        for key in (
            "entry",
            "exit",
            "approach",
            "flare",
            "entry_angle",
            "curb_radius",
            "entry_path",
            "exit_path",
            "entry_chord",
            "entry_sagitta",
            "sight",
            "length",
            "speed",
            "storage",
            "splitter",
            "bypass_width",
            "available_width",
            "pedestrians",
            "cycles",
            "crossing",
        ):
            check(getattr(a, key), f"{a.code} · {key}")
        check(a.grade, f"{a.code} · Pendiente longitudinal", -25, 25)
        if not all(type(k) is int and 0 <= k <= 4 for k in (a.inbound, a.outbound)):
            raise ValueError(f"{a.code}. Captura de cero a cuatro carriles por sentido.")
        if not a.inbound and not a.outbound:
            raise ValueError(f"{a.code}. El ramal necesita entrada o salida.")
        if a.inbound > 2 and site.lanes < a.inbound:
            raise ValueError(f"{a.code}. La conexión requiere canalización explícita.")
    for value, label in (
        (site.heavy_eq, "Equivalencia pesados"),
        (site.bus_eq, "Equivalencia bus"),
        (site.motorcycle_eq, "Equivalencia moto"),
        (site.period, "Periodo"),
        (site.spacing, "Espaciado en cola"),
    ):
        check(value, label, 0.00001)
    ordered = [a.code for a in order(site)]
    seen, routes = set(), []
    for m in site.movements:
        key = (m.origin, m.destination)
        if key in seen or any(c not in codes for c in key):
            raise ValueError(f"Movimiento {key}: revisa ramales o registros duplicados.")
        seen.add(key)
        if not m.enabled:
            continue
        check(m.volume, "Aforo")
        check(m.phf, "Factor de hora pico", 0.01, 1)
        for value in (m.heavy, m.bus, m.motorcycle, m.lane2):
            check(value, "Porcentaje", 0, 100)
        if m.heavy + m.bus + m.motorcycle > 100.00000001:
            raise ValueError(f"{m.origin} a {m.destination}. La composición excede el 100 %.")
        start, end = (codes[c] for c in key)
        if not start.inbound or not end.outbound:
            raise ValueError(f"{start.code} a {end.code}: falta conexión de entrada o salida.")
        if m.lane2 and (start.inbound < 2 or end.outbound < 2):
            raise ValueError(
                f"{start.code} a {end.code}: carril interior requiere dos carriles "
                "también en el acceso y la salida."
            )
        start_index = ordered.index(start.code)
        successors = ordered[start_index + 1 :] + ordered[: start_index + 1]
        segment = [start.code, *successors[: successors.index(end.code)]]
        equivalents = 1 + sum(
            share * (factor - 1) / 100
            for share, factor in (
                (m.heavy, site.heavy_eq),
                (m.bus, site.bus_eq),
                (m.motorcycle, site.motorcycle_eq),
            )
        )
        for lane, share in enumerate((1 - m.lane2 / 100, m.lane2 / 100), 1):
            if share:
                routes.append(
                    {
                        "od": key,
                        "lane": lane,
                        "ring_lane": min(lane, site.lanes),
                        "raw": m.volume * share,
                        "rate": m.volume / m.phf * share,
                        "eq": equivalents,
                        "segment": segment,
                        "heavy": m.heavy,
                        "bus": m.bus,
                        "motorcycle": m.motorcycle,
                    }
                )
    return routes


def flows(site, routes):
    result = {
        a.code: {
            "entry": [0.0] * a.inbound,
            "entry_eq": [0.0] * a.inbound,
            "exit": 0.0,
            "segment": [0.0] * site.lanes,
            "conflict": [0.0] * site.lanes,
            "conflict_veh": [0.0] * site.lanes,
        }
        for a in site.arms
    }
    for r in routes:
        start, end = r["od"]
        lane, ring_lane = r["lane"] - 1, r["ring_lane"] - 1
        rate, eq = r["rate"], r["rate"] * r["eq"]
        result[start]["entry"][lane] += rate
        result[start]["entry_eq"][lane] += eq
        result[end]["exit"] += rate
        for index, code in enumerate(r["segment"]):
            result[code]["segment"][ring_lane] += rate
            if index:
                result[code]["conflict"][ring_lane] += eq
                result[code]["conflict_veh"][ring_lane] += rate
    return result


def design_geometry(site, *, propose=False):
    """Diámetros al borde exterior de la isla, incluida la corona transitable."""
    if not 1 <= site.lanes <= 4:
        raise ValueError("El número de carriles circulantes debe estar entre uno y cuatro.")
    diameter, island, width = (
        check(x, k)
        for x, k in (
            (site.diameter, "Diámetro inscrito"),
            (site.island, "Diámetro de isla"),
            (site.width, "Ancho anular"),
        )
    )
    check(site.apron, "Corona transitable")
    check(site.vehicle_width, "Ancho del vehículo de diseño")
    check(site.vehicle_length, "Longitud del vehículo de diseño")
    check(site.wheelbase, "Distancia entre ejes")
    check(site.minimum_turn, "Radio mínimo")
    if site.vehicle_length and site.wheelbase > site.vehicle_length:
        raise ValueError("La distancia entre ejes excede la longitud del vehículo.")

    check(site.speed, "Velocidad de comprobación", 0, 180)
    check(site.friction, "Fricción lateral", 0.001, 1)
    friction = check(site.friction + site.crossfall / 100, "Peralte más fricción", 0.001, 1)
    minimum_radius = site.speed**2 / (127 * friction) if site.speed else None
    values = {"diameter": diameter, "island": island, "width": width}
    statuses = {
        key: "Fijado" if key in site.locks else "Capturado" if v else "Pendiente"
        for key, v in values.items()
    }
    if any(not values[key] for key in site.locks if key in values):
        raise ValueError("Captura un valor para cada dimensión fijada.")
    if propose and sum(bool(x) for x in values.values()) < 2:
        # Anchos editables de tanteo, no mínimos de diseño normativo.
        if not width:
            width = site.lanes * max(4.0, site.vehicle_width + 1.0)
            statuses["width"] = "Propuesto"
        if not diameter and not island:
            reference = {"Minirotonda": 22, "Compacta": 30, "Un carril": 40, "Dos carriles": 50}
            diameter = max(
                reference.get(site.kind, 40),
                2 * (width + site.apron + 2),
                2 * (site.minimum_turn or 0) + width,
            )
            statuses["diameter"] = "Propuesto"
    if not diameter and island and width:
        diameter = island + 2 * width
        statuses["diameter"] = "Calculado"
    if not island and diameter and width:
        island = diameter - 2 * width
        statuses["island"] = "Calculado"
    if not width and diameter and island:
        width = (diameter - island) / 2
        statuses["width"] = "Calculado"
    if not (diameter and island and width):
        raise ValueError("Captura dos dimensiones del anillo o activa predimensionamiento.")
    if width <= 0 or island <= 0 or abs(diameter - island - 2 * width) > 0.02:
        raise ValueError("Geometría incompatible: D inscrito = D isla + dos anchos anulares.")
    if site.apron > island / 2 or (site.apron == island / 2 and site.kind != "Minirotonda"):
        raise ValueError("La corona transitable excede la isla o deja una isla dura nula.")
    area = pi * diameter**2 / 4
    limit_messages = []
    for need, available, label in (
        (diameter, site.available_diameter, "diámetro disponible"),
        (area, site.available_area, "superficie disponible"),
        (diameter, site.space_width, "ancho del rectángulo disponible"),
        (diameter, site.space_length, "largo del rectángulo disponible"),
    ):
        check(available, label)
        if available and need > available:
            limit_messages.append(f"Excede {label}.")
    centerline = (diameter - width) / 2
    speed = sqrt(127 * centerline * friction)
    return {
        "diameter": diameter,
        "island": island,
        "width": width,
        "apron": site.apron,
        "hard_island": island - 2 * site.apron,
        "lane_width": width / site.lanes,
        "area": area,
        "centerline": centerline,
        "centerline_speed": speed,
        "minimum_radius": minimum_radius,
        "statuses": statuses,
        "limit_issues": limit_messages,
        "space_verified": bool(site.available_diameter or site.space_width and site.space_length),
    }


def kimber(arm, diameter, q):
    """CD 116 B.1 para accesos convencionales. Dimensiones de bordillo en metros."""
    entered = (arm.entry, arm.approach, arm.flare, diameter, arm.entry_angle, arm.curb_radius)
    bounds = (
        (3.6, 16.5),
        (1.9, 12.5),
        (1, float("inf")),
        (13.5, 171.6),
        (0, 77),
        (3.4, float("inf")),
    )
    for value, (low, high) in zip(entered, bounds, strict=True):
        if not low <= value <= high:
            raise ValueError("Kimber: faltan dimensiones o están fuera del dominio CD 116 B.1.")
    e, v, length, diameter, angle, radius = entered
    sharpness = 1.6 * (e - v) / length
    check(sharpness, "Kimber · agudeza de abocinamiento", 0, 2.9)
    width = v + (e - v) / (1 + 2 * sharpness)
    k = 1 - 0.00347 * (angle - 30) - 0.978 * (1 / radius - 0.05)
    t = 1 + 0.5 / (1 + exp((diameter - 60) / 10))
    return max(0.0, k * (303 * width - 0.210 * t * (1 + 0.2 * width) * q))


def capacity(site, arm, lane, q, method):
    if site.kind in ("Turborrotonda", "Multicarril") or site.lanes > 2 or arm.inbound > 2:
        raise ValueError("No hay un modelo validado para esta configuración de carriles.")
    if arm.bypass_width:
        raise ValueError("Un carril de giro segregado requiere una metodología específica.")
    if method == "HCM":
        chosen_conflicts = arm.outer_conflicts if lane == 1 else arm.inner_conflicts
        if site.kind == "Minirotonda" or chosen_conflicts != "Todos":
            raise ValueError("HCM convencional exige su ámbito de carriles y flujo calibrado.")
        a, b = HCM[arm.inbound, site.lanes, lane]
        if site.fitted_a:
            check(q, "Flujo en el ajuste local", site.fitted_min, site.fitted_max)
            a, b = (
                check(site.fitted_a, "Intercepto local", 0.001),
                check(site.fitted_b, "Pendiente"),
            )
        return a * exp(-b * q)
    if method == "Brechas":
        follow = check(site.followup, "Tiempo de seguimiento (s)", 0.01)
        critical = check(site.critical_gap, "Brecha crítica (s)", follow)
        return 3600 / follow * exp(-q / 3600 * (critical - follow / 2))
    if method == "Lineal":
        if site.linear_max <= site.linear_min:
            raise ValueError("Define el dominio de calibración de la regresión lineal.")
        check(q, "Flujo en el dominio de regresión", site.linear_min, site.linear_max)
        result = check(site.linear_a, "Intercepto", 0.001) - check(site.linear_b, "Pendiente") * q
        if result < 0:
            raise ValueError("La extrapolación daría una capacidad negativa.")
        return result
    if method == "Kimber":
        if site.kind == "Minirotonda" or arm.inbound != 1:
            raise ValueError(
                "Kimber excluye minirotondas y aquí se informa en accesos de un carril."
            )
        return kimber(arm, design_geometry(site)["diameter"], q)
    raise ValueError("Selecciona un método de capacidad válido.")


def control(rate, cap, period, initial=0.0):
    """Capítulo 22 con cola inicial superpuesta como aproximación determinista explícita."""
    if cap <= 1e-8:
        return {
            "x": None,
            "delay": None,
            "q95": None,
            "qmean": None,
            "queue_initial_delay": None,
            "los": "F" if rate else "—",
        }
    x = rate / cap
    d = 0.0
    queue = 0.0
    initial_delay = 0.0
    if rate:
        delta = x - 1
        d = (
            3600 / cap
            + 900 * period * (delta + sqrt(delta * delta + 8 * x / (cap * period)))
            + 5 * min(x, 1)
        )
        queue = period * cap / 4 * (delta + sqrt(delta * delta + 24 * x / (cap * period)))
        if initial:
            clearance = min(period, initial / (cap - rate)) if cap > rate else period
            initial_delay = (
                3600
                * initial
                * clearance
                * (1 - clearance * (cap - rate) / (2 * initial) if cap > rate else 1)
                / (rate * period)
            )
    return {
        "x": x,
        "delay": d + initial_delay if rate else None,
        "q95": queue if not initial else None,
        "qmean": d * rate / 3600 if x < 1 and not initial else None,
        "queue_initial_delay": initial_delay,
        "los": ("F" if x > 1 else level_of_service(d + initial_delay)) if rate else "—",
    }


def _q(arm, lane, values):
    setting = arm.outer_conflicts if lane == 1 else arm.inner_conflicts
    if setting == "Todos":
        return sum(values["conflict"])
    if setting not in ("Exterior", "Interior"):
        raise ValueError("Selecciona Todos, Exterior o Interior como flujo conflictivo.")
    index = int(setting == "Interior")
    if index >= len(values["conflict"]):
        raise ValueError("El carril conflictivo seleccionado no existe.")
    return values["conflict"][index]


def _weights(rows, field):
    demand = sum(row["demand"] for row in rows)
    if not demand or any(row[field] is None for row in rows if row["demand"]):
        return None
    return sum(row["demand"] * row[field] for row in rows if row["demand"]) / demand


def evaluate(site, *, compare=True, advanced=False):
    routes = network(site)
    flow = flows(site, routes)
    geometry = (
        design_geometry(site)
        if sum(bool(x) for x in (site.diameter, site.island, site.width)) >= 2
        else None
    )
    if site.method not in METHODS or (site.method == "Kimber" and not advanced):
        raise ValueError("El método seleccionado requiere el modo avanzado.")
    methods = METHODS[: 4 if advanced else 3] if compare else (site.method,)
    lanes, warnings = [], []
    for arm in site.arms:
        f = flow[arm.code]
        pedestrian = check(arm.pedestrian_factor, "Factor peatonal", 0.001, 1)
        local = check(arm.local_factor, "Factor local", 0.001, 2)
        if (local != 1 or pedestrian != 1) and not arm.factor_source.strip():
            raise ValueError(f"{arm.code}. Documenta la procedencia del factor de ajuste.")
        if arm.pedestrians or arm.cycles:
            warnings.append(
                f"{arm.code}. Aforos no motorizados registrados; efecto sólo mediante "
                "factor documentado, si se ha indicado."
            )
        for i in range(arm.inbound):
            lane = i + 1
            demand = f["entry"][i]
            mix = f["entry_eq"][i] / demand if demand else 1.0
            q = _q(arm, lane, f)
            initial = check(arm.outer_queue if i == 0 else arm.inner_queue, "Cola inicial")
            comparisons = {}
            for method in methods:
                try:
                    nominal = capacity(site, arm, lane, q, method)
                    adjusted = nominal * pedestrian * local / mix
                    status = (
                        "HCM"
                        if method == "HCM"
                        else "Híbrido capacidad alternativa / demora HCM"
                        if site.hybrid
                        else "Sólo capacidad"
                    )
                    metrics = (
                        control(demand, adjusted, site.period, initial)
                        if (method == "HCM" or site.hybrid)
                        else {
                            "x": demand / adjusted if adjusted else None,
                            "delay": None,
                            "q95": None,
                            "qmean": None,
                            "los": "—",
                        }
                    )
                    comparisons[method] = {
                        "capacity": adjusted,
                        "nominal": nominal,
                        **metrics,
                        "status": status,
                    }
                except (ValueError, ArithmeticError, KeyError) as exc:
                    comparisons[method] = {
                        "capacity": None,
                        "nominal": None,
                        "x": None,
                        "delay": None,
                        "q95": None,
                        "qmean": None,
                        "los": "—",
                        "status": str(exc),
                    }
            selected = comparisons[site.method]
            length = selected["q95"] * site.spacing if selected["q95"] is not None else None
            if selected["capacity"] is None and demand:
                warnings.append(f"{arm.code}/{lane}. {selected['status']}")
            if q > 1200 and site.method == "HCM":
                warnings.append(
                    f"{arm.code}/{lane}. Flujo elevado: verifica ajuste local y dominio."
                )
            if selected["x"] is not None and selected["x"] >= 0.85:
                warnings.append(f"{arm.code}/{lane}. Saturación de {selected['x']:.2f}.")
            if initial:
                warnings.append(
                    f"{arm.code}/{lane}. Cola inicial: superposición determinista; P95 omitida."
                )
            if arm.storage and length is not None and length > arm.storage:
                warnings.append(f"{arm.code}/{lane}. La P95 supera el almacenamiento.")
            delay = selected["delay"]
            free = 3600 * arm.length / 1000 / arm.speed if arm.length and arm.speed else None
            lanes.append(
                {
                    "arm": arm.code,
                    "lane": lane,
                    "demand": demand,
                    "equivalent": f["entry_eq"][i],
                    "q": q,
                    "queue_m": length,
                    "initial": initial,
                    **selected,
                    "delay_rate": demand * delay / 3600 if delay is not None else None,
                    "travel": free + delay if free is not None and delay is not None else None,
                    "models": comparisons,
                }
            )
    approaches = []
    for arm in site.arms:
        rows = [r for r in lanes if r["arm"] == arm.code]
        if rows:
            approaches.append({"arm": arm.code, **aggregate(rows, site.period)})
    overall = aggregate(lanes, site.period)
    if not overall["demand"]:
        warnings.append("Captura aforos para evaluar el desempeño operacional.")
    if overall["x"] is not None:
        critical = max(
            (r for r in lanes if r["x"] is not None and r["demand"]),
            key=lambda r: r["x"],
            default=None,
        )
        overall["critical"] = f"{critical['arm']}/{critical['lane']}" if critical else None
    return {
        "model": MODEL_ID,
        "method": site.method,
        "overall": overall,
        "arms": approaches,
        "lanes": lanes,
        "flow": flow,
        "geometry": geometry,
        "warnings": list(dict.fromkeys(warnings)),
        "raw": sum(r["raw"] for r in routes),
    }


def aggregate(rows, period):
    delay = _weights(rows, "delay")
    demand = sum(r["demand"] for r in rows)
    caps = [r["capacity"] for r in rows]
    cap = sum(caps) if all(c is not None for c in caps) else None
    queue = [r["queue_m"] for r in rows if r["demand"]]
    selected = [r for r in rows if r["demand"]]
    critical = max((r["x"] for r in selected if r["x"] is not None), default=None)
    return {
        "demand": demand,
        "capacity": cap,
        "reserve": cap - demand if cap is not None else None,
        "x": critical if all(r["x"] is not None for r in selected) else None,
        "delay": delay,
        "delay_rate": delay * demand / 3600 if delay is not None else None,
        "delay_total": delay * demand * period / 3600 if delay is not None else None,
        "los": level_of_service(delay) if delay is not None else "—",
        "queue_m": max(queue) if queue and all(length is not None for length in queue) else None,
        "travel": _weights(rows, "travel"),
    }


def safety(site, geometry):
    """Cribado geométrico. Rutas esquemáticas con nodos de divergencia antes de convergencia."""
    routes = network(site)
    ordered = order(site)
    angles = {a.code: a.azimuth for a in ordered}
    sign = -1 if site.direction == "Antihorario" else 1
    friction = site.friction + site.crossfall / 100
    nodes, conflicts, checks = [], [], []
    for i, arm in enumerate(ordered):
        code = arm.code
        separation = ((ordered[(i + 1) % len(ordered)].azimuth - angles[code]) * sign) % 360
        position = sum(1 for r in routes if r["od"][0] == code)
        exiting = sum(1 for r in routes if r["od"][1] == code)
        through = [r for r in routes if code in r["segment"][1:]]
        for lane in range(1, site.lanes + 1):
            for tag, endpoint, enabled in (
                (
                    "Convergencia",
                    0,
                    any(r["od"][0] == code and r["ring_lane"] == lane for r in routes),
                ),
                (
                    "Divergencia",
                    1,
                    any(r["od"][1] == code and r["ring_lane"] == lane for r in routes),
                ),
            ):
                if enabled and any(r["ring_lane"] == lane for r in through):
                    conflicts.append((code, lane, tag, endpoint))
        if any(r["od"][1] == code and r["ring_lane"] == 2 for r in routes) and any(
            r["ring_lane"] == 1 for r in through
        ):
            conflicts.append((code, 2, "Cruce interior–exterior potencial", 1))
        entry = _trajectory_radius(arm.entry_path, arm.entry_chord, arm.entry_sagitta)
        out = arm.exit_path or None
        for radius in (entry, out):
            if radius is not None:
                check(radius, f"{code} · radio de trayectoria")
        speeds = [
            sqrt(127 * r * friction) if r else None for r in (entry, geometry["centerline"], out)
        ]
        speed = (site.speed or speeds[1]) / 3.6
        braking = check(3.4 + 9.81 * arm.grade / 100, "Desaceleración longitudinal efectiva", 0.1)
        stopping = 2.5 * speed + speed**2 / (2 * braking)
        flags = []
        if arm.sight and arm.sight < stopping:
            flags.append("Visibilidad capturada menor a distancia de parada.")
        if separation < 30:
            flags.append("Separación angular menor a 30°; revisar encaje.")
        if arm.pedestrians or arm.cycles:
            if not arm.crossing or not arm.splitter:
                flags.append("Revisar ubicación de cruce y refugio.")
        if site.minimum_turn and any(r < site.minimum_turn for r in (entry, out) if r):
            flags.append("Radio de trayectoria inferior al radio mínimo del vehículo de diseño.")
        if (
            arm.available_width
            and arm.entry + arm.exit + arm.splitter + arm.bypass_width > arm.available_width
        ):
            flags.append("Anchos de entrada, salida e islas exceden el ramal disponible.")
        if site.vehicle_width and any(
            value < site.vehicle_width
            for value in (
                [geometry["lane_width"]]
                + ([arm.entry / arm.inbound] if arm.entry and arm.inbound else [])
                + ([arm.exit / arm.outbound] if arm.exit and arm.outbound else [])
            )
        ):
            flags.append("El ancho del vehículo de diseño excede un carril.")
        if speeds[0] and site.speed and speeds[0] > site.speed:
            flags.append("Velocidad teórica de entrada supera la meta; revisar deflexión.")
        if any(abs(a - b) > 20 for a, b in zip(speeds, speeds[1:], strict=False) if a and b):
            flags.append("Diferencia teórica de velocidad superior a 20 km/h.")
        if position or exiting:
            nodes.append((code, position, exiting))
        checks.append(
            {
                "arm": code,
                "separation": separation,
                "entry_path": entry,
                "exit_path": out,
                "speeds": speeds,
                "stopping": stopping,
                "sight": arm.sight or None,
                "flags": flags,
            }
        )
    return {"checks": checks, "conflicts": conflicts, "routes": nodes}


def from_legacy(data: RoundaboutInput):
    arms = tuple(
        Arm(
            chr(65 + i),
            a.azimuth_deg,
            a.name,
            entry=a.entry_width_m,
            exit=a.exit_width_m,
            storage=a.storage_m,
            entry_path=a.entry_radius_m,
            exit_path=a.exit_radius_m,
            entry_chord=a.entry_chord_m,
            entry_sagitta=a.entry_sagitta_m,
            pedestrian_factor=a.pedestrian_factor,
            factor_source="Proyecto HCNet previo",
        )
        for i, a in enumerate(data.arms[: data.arm_count])
    )
    movements = tuple(
        Movement(
            a.code,
            b.code,
            data.flows[i][j],
            data.arms[i].heavy_percent,
            phf=data.peak_hour_factor,
            source="Proyecto HCNet previo",
        )
        for i, a in enumerate(arms)
        for j, b in enumerate(arms)
        if data.flows[i][j]
    )
    return Site(
        name=data.name,
        arms=arms,
        movements=movements,
        direction=data.circulation,
        driving="Derecha" if data.circulation == "Antihorario" else "Izquierda",
        diameter=data.diameter_m,
        width=data.circulating_width_m,
        apron=data.apron_width_m,
        speed=data.design_speed_kmh,
        crossfall=data.cross_slope_percent,
        friction=data.side_friction,
        period=data.period_h,
        heavy_eq=data.heavy_equivalency,
        spacing=data.vehicle_spacing_m,
    )


def point(azimuth, radius):
    from math import cos, sin

    rad = radians(azimuth)
    return radius * sin(rad), radius * cos(rad)


def separated(site, radius, lane_width):
    """Comprobación geométrica mínima para evitar enlaces superpuestos en la red."""
    points = [point(a.azimuth, radius) for a in order(site)]
    return all(
        hypot(a[0] - b[0], a[1] - b[1]) > 2 * lane_width
        for a, b in zip(points, points[1:] + points[:1], strict=True)
    )
