"""Modelos operacionales de una línea y sus alternativas, independientes de Qt."""

from dataclasses import dataclass, replace
from math import ceil, floor, isfinite, sqrt

ROLES = ("Ascenso", "Descenso", "Mixta", "Deshabilitada")
STRATEGIES = ("Secuencial", "Simultáneo", "Compartida")
DOOR_PRESETS = (
    "Delantera / traseras",
    "Una puerta mixta",
    "Todas ascenso",
    "Todas descenso",
    "Todas mixtas",
)


def number(value: float, label: str, *, positive: bool = False) -> float:
    if not isfinite(value) or value < 0 or (positive and value == 0):
        domain = "positivo" if positive else "no negativo"
        raise ValueError(f"{label} debe ser un número finito y {domain}.")
    return value


def fraction(value: float, label: str) -> float:
    if not 0 < value <= 1:
        raise ValueError(f"{label} debe estar entre 0 (excluido) y 1.")
    return value


@dataclass(frozen=True)
class Door:
    role: str = "Mixta"
    car: int = 1
    width: float = 0
    channels: int = 1
    board_s: float = 2.5
    alight_s: float = 1.8
    board_weight: float = 1
    alight_weight: float = 1
    interference: float = 1
    fixed_s: float = 4
    accessibility_s: float = 0
    access: str = ""
    payment: str = ""
    notes: str = ""


def preset_doors(doors: tuple[Door, ...], preset: str) -> tuple[Door, ...]:
    if preset not in DOOR_PRESETS:
        raise ValueError("Selecciona una configuración de puertas.")
    roles = {
        DOOR_PRESETS[0]: lambda i: "Ascenso" if i == 0 else "Descenso",
        DOOR_PRESETS[1]: lambda i: "Mixta" if i == 0 else "Deshabilitada",
        DOOR_PRESETS[2]: lambda i: "Ascenso",
        DOOR_PRESETS[3]: lambda i: "Descenso",
        DOOR_PRESETS[4]: lambda i: "Mixta",
    }
    return tuple(replace(door, role=roles[preset](i)) for i, door in enumerate(doors))


def dwell(board: float, alight: float, doors: tuple[Door, ...], strategy: str) -> dict:
    number(board, "Ascensos")
    number(alight, "Descensos")
    if not doors or strategy not in STRATEGIES:
        raise ValueError("Define puertas y un modo de intercambio válido.")
    active = [(i, door) for i, door in enumerate(doors, 1) if door.role != "Deshabilitada"]
    for door in doors:
        if (
            door.role not in ROLES
            or door.channels < 1
            or int(door.channels) != door.channels
            or door.car < 1
            or int(door.car) != door.car
        ):
            raise ValueError("Revisa la función, el carro y el número de canales de las puertas.")
        for label, value in (
            ("Ancho", door.width),
            ("Peso de ascenso", door.board_weight),
            ("Peso de descenso", door.alight_weight),
            ("Tiempo fijo", door.fixed_s),
            ("Accesibilidad", door.accessibility_s),
        ):
            number(value, label)
        number(door.board_s, "Tiempo unitario de ascenso", positive=True)
        number(door.alight_s, "Tiempo unitario de descenso", positive=True)
        if not isfinite(door.interference) or door.interference < 1:
            raise ValueError("El factor de interferencia debe ser finito y al menos 1.")
    if not active:
        raise ValueError("Habilita al menos una puerta.")
    ups = {i: d.board_weight for i, d in active if d.role in {"Ascenso", "Mixta"}}
    downs = {i: d.alight_weight for i, d in active if d.role in {"Descenso", "Mixta"}}
    totals = sum(ups.values()), sum(downs.values())
    if (board and not totals[0]) or (alight and not totals[1]):
        raise ValueError("No hay puertas habilitadas o ponderadas para todos los movimientos.")
    rows = []
    for index, door in active:
        b = board * ups.get(index, 0) / totals[0] if totals[0] else 0
        a = alight * downs.get(index, 0) / totals[1] if totals[1] else 0
        tb, ta = b * door.board_s / door.channels, a * door.alight_s / door.channels
        shared = (tb + ta) * door.interference if b and a else tb + ta
        if strategy == "Simultáneo" and b and a:
            raise ValueError("El modo simultáneo requiere flujos separados por puerta.")
        rows.append((index, b, a, tb, ta, shared))
    fixed = max(door.fixed_s + door.accessibility_s for _, door in active)
    boarding, alighting = max(row[3] for row in rows), max(row[4] for row in rows)
    critical = max(rows, key=lambda row: row[5])[0]
    service = {
        "Secuencial": boarding + alighting,
        "Simultáneo": max(boarding, alighting),
        "Compartida": max(row[5] for row in rows),
    }[strategy]
    return {
        "seconds": fixed + service,
        "boarding_s": boarding,
        "alighting_s": alighting,
        "critical_door": critical if strategy == "Compartida" else None,
        "doors": rows,
    }


def capacity_for(nominal: float, seats: float, area: float, density: float, mode: str) -> float:
    number(nominal, "Capacidad nominal")
    if mode == "Nominal":
        return number(nominal, "Capacidad nominal", positive=True)
    if mode != "Por área":
        raise ValueError("Selecciona un método de capacidad válido.")
    for value, label in ((seats, "Asientos"), (area, "Superficie"), (density, "Densidad")):
        number(value, label)
    physical = number(seats + floor(area * density), "Capacidad calculada", positive=True)
    if nominal and physical > nominal:
        raise ValueError("La capacidad calculada excede el límite nominal registrado.")
    return physical


@dataclass(frozen=True)
class Station:
    name: str
    km: float
    board: float = 0
    alight: float = 0
    speed: float = 0
    dwell_s: float | None = None
    berths: int = 1
    clearance_s: float = 8
    platform_pax_h: float = 0
    accessible: bool | None = None


@dataclass(frozen=True)
class Service:
    name: str
    technology: str
    length_km: float
    speed_kmh: float
    headway_min: float
    demand: float
    nominal: float
    load_factor: float
    min_headway_s: float
    reserve_percent: float = 10
    availability: float = 1
    terminal_min: float = 5
    intermediate: int = 0
    board: float = 0
    alight: float = 0
    stop_positions: int = 1
    stop_clearance_s: float = 8
    movement_penalty_s: float = 0
    exchange: str = "Compartida"
    doors: tuple[Door, ...] = ()
    stations: tuple[Station, ...] = ()
    reverse: tuple[Station, ...] = ()
    passenger_units: str = "Por unidad"
    initial_pax: float = 0
    initial_reverse_pax: float = 0
    cable_spacing_m: float = 0
    cable_min_spacing_m: float = 0
    cable_circuit_km: float = 0
    cable_station_s: float = 0
    cable_station_limit: float = 0
    headways_observed: tuple[float, ...] = ()
    random_arrivals: bool = False
    regular_service: bool = False
    seats: float | None = None
    standing_area: float | None = None
    homogeneous_dwell_s: float | None = None
    terminal_positions: int = 0


def station_capacity(positions: int, dwell_s: float, clearance_s: float) -> float:
    if positions < 1 or int(positions) != positions:
        raise ValueError("Se requiere al menos una posición entera de atención.")
    number(dwell_s, "Permanencia")
    number(clearance_s, "Despeje")
    occupancy = number(dwell_s + clearance_s, "Tiempo de ocupación", positive=True)
    return 3600 * positions / occupancy


def calculate_profile(
    line: Service, stations: tuple[Station, ...], frequency: float, initial: float
) -> list[dict]:
    if len(stations) < 2:
        raise ValueError("El perfil individual necesita origen y destino.")
    if (
        stations[0].km != 0
        or not isfinite(stations[-1].km)
        or (abs(stations[-1].km - line.length_km) > 0.0001)
    ):
        raise ValueError("El perfil debe comenzar en km 0 y terminar en la longitud de la línea.")
    divide = frequency if line.passenger_units == "Por hora" else 1
    load = number(initial, "Carga inicial") / divide
    profile = []
    last_km = -1.0
    total_board = total_alight = 0.0
    if len({row.name.strip().casefold() for row in stations}) != len(stations):
        raise ValueError("Cada estación de un sentido debe tener un nombre único.")
    for row in stations:
        number(row.km, "Distancia acumulada")
        if not row.name.strip() or row.km <= last_km:
            raise ValueError("Nombra las estaciones y ordénalas por distancia creciente.")
        board, alight = (
            number(row.board, "Ascensos") / divide,
            number(row.alight, "Descensos") / divide,
        )
        if alight - load > 1e-8:
            raise ValueError(f"{row.name}: los descensos exceden los pasajeros a bordo.")
        available = max(0, line.nominal - (load - alight))
        deficit = max(0, board - available)
        load = load - alight + board
        total_board += board
        total_alight += alight
        if row.dwell_s is not None:
            seconds = number(row.dwell_s, "Permanencia observada")
        elif line.technology == "cable":
            seconds = line.cable_station_s
        else:
            seconds = dwell(board, alight, line.doors, line.exchange)["seconds"]
        units_h = station_capacity(row.berths, seconds, row.clearance_s)
        running = (
            60 * (row.km - last_km) / (number(row.speed, "Velocidad del tramo") or line.speed_kmh)
            if last_km >= 0
            else 0
        )
        profile.append(
            {
                "name": row.name,
                "km": row.km,
                "board": board,
                "alight": alight,
                "load": load,
                "occupation": load / line.nominal,
                "deficit": deficit,
                "available_after": max(0, line.nominal - load),
                "accumulated_board": total_board,
                "accumulated_alight": total_alight,
                "station_saturation": frequency / units_h,
                "dwell": seconds,
                "station_units": units_h,
                "station_pax": units_h * line.nominal * line.load_factor,
                "platform_pax_h": number(row.platform_pax_h, "Límite de plataforma"),
                "platform_load": (board + alight) * frequency,
                "running_min": running,
                "accessible": row.accessible,
                "seats_available": (max(0, line.seats - load) if line.seats is not None else None),
                "density": (
                    max(0, load - line.seats) / line.standing_area
                    if line.standing_area and line.seats is not None
                    else None
                ),
            }
        )
        last_km = row.km
    return profile


def service_quality(
    headway: float, observed: tuple[float, ...], random_arrivals: bool, regular_service: bool
) -> dict:
    from statistics import mean, stdev

    if observed:
        for interval in observed:
            number(interval, "Intervalo observado", positive=True)
        avg = mean(observed)
        variation = stdev(observed) / avg if len(observed) > 1 else None
        wait = sum(h * h for h in observed) / (2 * sum(observed)) if random_arrivals else None
        return {"wait": wait, "observed_mean": avg, "cv": variation, "max_headway": max(observed)}
    return {
        "wait": headway / 2 if random_arrivals and regular_service else None,
        "observed_mean": None,
        "cv": None,
        "max_headway": None,
    }


def evaluate(line: Service) -> dict:
    for label, value in (
        ("Longitud", line.length_km),
        ("Velocidad de operación", line.speed_kmh),
        ("Límite de separación", line.min_headway_s),
        ("Capacidad", line.nominal),
    ):
        number(value, label, positive=True)
    for label, value in (
        ("Demanda", line.demand),
        ("Reserva", line.reserve_percent),
        ("Regulación", line.terminal_min),
        ("Paradas interiores", line.intermediate),
        ("Tiempo por maniobra", line.movement_penalty_s),
        ("Bahías de regulación", line.terminal_positions),
    ):
        number(value, label)
    if line.passenger_units not in {"Por unidad", "Por hora"}:
        raise ValueError("Especifica si los ascensos y descensos son por unidad o por hora.")
    if int(line.intermediate) != line.intermediate:
        raise ValueError("Las paradas interiores deben expresarse como un entero.")
    if line.terminal_positions != int(line.terminal_positions):
        raise ValueError("Las posiciones de regulación deben expresarse como un entero.")
    fraction(line.load_factor, "Ocupación objetivo")
    fraction(line.availability, "Disponibilidad")
    road_or_rail = line.technology != "cable"
    if road_or_rail:
        headway = number(line.headway_min, "Intervalo", positive=True)
        station_exchange = 0
        if (not line.stations or not line.reverse) and line.intermediate:
            if line.homogeneous_dwell_s is not None:
                station_exchange = number(line.homogeneous_dwell_s, "Permanencia observada")
            else:
                station_exchange = dwell(line.board, line.alight, line.doors, line.exchange)[
                    "seconds"
                ]
        station_max = None
    else:
        separation = number(line.cable_spacing_m, "Separación de cabinas", positive=True)
        minimum = number(line.cable_min_spacing_m, "Separación mínima", positive=True)
        circuit = number(line.cable_circuit_km, "Longitud del circuito", positive=True)
        station_exchange = number(line.cable_station_s, "Permanencia de cabina")
        station_max = number(
            line.cable_station_limit, "Capacidad de embarque (pax/h)", positive=True
        )
        if separation < minimum or circuit < 2 * line.length_km:
            raise ValueError("Revisa separación mínima y longitud de ida y retorno del circuito.")
        headway = separation / (line.speed_kmh / 3.6) / 60
    frequency = 60 / headway
    profiles = [
        calculate_profile(line, rows, frequency, initial) if rows else []
        for rows, initial in (
            (line.stations, line.initial_pax),
            (line.reverse, line.initial_reverse_pax),
        )
    ]
    runs, dwells, trips, limits = [], [], [], []
    critical = ""
    for i, profile in enumerate(profiles):
        if profile:
            segment_minutes = sum(row["running_min"] for row in profile)
            dwell_seconds = sum(row["dwell"] for row in profile[1:-1])
            positions = [(row["station_units"], row["name"]) for row in profile]
        else:
            segment_minutes = 60 * line.length_km / line.speed_kmh
            dwell_seconds = line.intermediate * station_exchange
            positions = (
                [
                    (
                        station_capacity(
                            line.stop_positions, station_exchange, line.stop_clearance_s
                        ),
                        "Parada homogénea",
                    )
                ]
                if road_or_rail and line.intermediate
                else []
            )
        runs.append(segment_minutes)
        dwells.append(dwell_seconds)
        stops = max(0, len(profile) - 2) if profile else line.intermediate
        trips.append(segment_minutes + (dwell_seconds + stops * line.movement_penalty_s) / 60)
        limits.extend(
            (maximum, f"{'Ida' if i == 0 else 'Regreso'} · {name}") for maximum, name in positions
        )
    if road_or_rail and line.terminal_positions and line.terminal_min:
        limits.append((60 * line.terminal_positions / line.terminal_min, "Bahías de regulación"))
    station_limit = min(limits) if limits else None
    cap_unit = line.nominal * line.load_factor
    if road_or_rail:
        cycle = sum(trips) + 2 * line.terminal_min
        max_frequency = 3600 / line.min_headway_s
        if station_limit and station_limit[0] < max_frequency:
            max_frequency, critical = station_limit
    else:
        # El circuito mide la circulación en ambos sentidos. Los tiempos adicionales
        # corresponden a las zonas de estación y retorno no incluidas en L/v.
        cycle = 60 * line.cable_circuit_km / line.speed_kmh + sum(dwells) / 60
        cycle += 2 * line.terminal_min
        max_frequency = min(
            3600 / line.min_headway_s,
            1000 * line.speed_kmh / line.cable_min_spacing_m,
            station_max / line.nominal,
        )
        critical = "Embarque de cabinas" if max_frequency == station_max / line.nominal else ""
        if station_limit and station_limit[0] < max_frequency:
            max_frequency, critical = station_limit
    profile_demand = max((row["load"] * frequency for rows in profiles for row in rows), default=0)
    demand = max(line.demand, profile_demand)
    fleet = ceil(cycle / headway - 1e-10)
    reserve = max(ceil(fleet * line.reserve_percent / 100), ceil(fleet / line.availability) - fleet)
    offered = frequency * cap_unit
    achievable = min(frequency, max_frequency) * cap_unit
    warnings = []
    if frequency > max_frequency + 1e-8:
        warnings.append("El intervalo programado excede la frecuencia alcanzable.")
    if demand > achievable + 1e-8:
        warnings.append("La oferta alcanzable es insuficiente para la demanda crítica.")
    for direction, profile in zip(("Ida", "Regreso"), profiles, strict=True):
        if profile and profile[-1]["load"] > 1e-8:
            warnings.append(f"{direction}: hay pasajeros a bordo al final del tramo.")
        for row in profile:
            if row["platform_pax_h"] and row["platform_load"] > row["platform_pax_h"]:
                warnings.append(f"{direction} · {row['name']}: supera el límite de plataforma.")
    maximum_load = max(
        ((row["load"], row["name"]) for rows in profiles for row in rows), default=(0, "")
    )
    return {
        "frequency": frequency,
        "required_frequency": demand / cap_unit,
        "operational_frequency": ceil(demand / cap_unit),
        "headway": headway,
        "nominal_unit": line.nominal,
        "design_unit": cap_unit,
        "offered": offered,
        "physical_offer": frequency * line.nominal,
        "achievable": achievable,
        "demand": demand,
        "margin": achievable - demand,
        "occupation": demand / (line.nominal * frequency),
        "cycle": cycle,
        "fleet": fleet,
        "reserve": reserve,
        "fleet_total": fleet + reserve,
        "running_min": runs,
        "dwell_total_s": dwells,
        "station_count": [
            len(profile) if profile else line.intermediate + 2 for profile in profiles
        ],
        "operating_kmh": [60 * line.length_km / time for time in runs],
        "travel_min": trips,
        "commercial_kmh": [60 * line.length_km / time for time in trips],
        "max_frequency": max_frequency,
        "critical_station": critical,
        "station_limit": station_limit[0] if station_limit else None,
        "profiles": profiles,
        "critical_load": maximum_load[0],
        "critical_section": maximum_load[1],
        "quality": service_quality(
            headway, line.headways_observed, line.random_arrivals, line.regular_service
        ),
        "warnings": warnings,
    }


def spacing(
    length_km: float,
    stations: int,
    walk_m_s: float = 0,
    average_trip_km: float = 0,
    stop_loss_s: float = 0,
) -> dict:
    length = 1000 * number(length_km, "Longitud", positive=True)
    number(walk_m_s, "Velocidad peatonal")
    number(average_trip_km, "Viaje medio")
    number(stop_loss_s, "Penalización por parada")
    if not 2 <= stations or int(stations) != stations:
        raise ValueError("Se necesitan dos o más estaciones.")
    interval = length / (stations - 1)
    walk = interval / (4 * walk_m_s) / 60 if walk_m_s > 0 else None
    optimum = (
        min(length, sqrt(2000 * average_trip_km * walk_m_s * stop_loss_s))
        if min(walk_m_s, average_trip_km, stop_loss_s) > 0
        else None
    )
    return {
        "spacing_m": interval,
        "access_min": walk,
        "optimum_m": optimum,
        "stations": round(length / optimum) + 1 if optimum else None,
    }
