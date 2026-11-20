"""Planeación operacional de una línea de transporte público.

El módulo es deliberadamente independiente del cálculo de intersecciones. Representa
la relación entre oferta, demanda, paradas y desempeño vial de una línea sencilla.
Las ecuaciones y sus límites se documentan en ``docs/METHODOLOGY.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from math import ceil, exp, isfinite, sqrt
from typing import Any


@dataclass(slots=True)
class TransitLineInput:
    """Entradas operacionales de una línea bidireccional."""

    name: str = "Línea demostrativa"
    route_length_km: float = 12.0
    stop_count_per_direction: int = 25
    operating_speed_kmh: float = 28.0
    terminal_layover_min: float = 8.0
    scheduled_headway_min: float = 8.0
    vehicle_capacity_pax: float = 80.0
    target_load_factor: float = 0.85
    peak_demand_pax_h_direction: float = 500.0
    reserve_fleet_percent: float = 10.0

    walking_speed_m_s: float = 1.2
    average_trip_length_km: float = 5.0
    boardings_per_stop: float = 8.0
    alightings_per_stop: float = 7.0
    boarding_time_s_pax: float = 2.5
    alighting_time_s_pax: float = 1.8
    door_open_close_s: float = 4.0
    door_count: int = 2
    exchange_mode: str = "Simultáneo"
    stop_accel_decel_penalty_s: float = 12.0
    stop_clearance_s: float = 8.0
    stop_berths: int = 1

    background_flow_veh_h: float = 900.0
    road_capacity_veh_h: float = 1800.0
    bus_pce: float = 2.0
    linear_alpha: float = 0.15
    bpr_alpha: float = 0.15
    bpr_beta: float = 4.0
    davidson_j: float = 0.50
    exponential_alpha: float = 0.15

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> TransitLineInput:
        """Carga entradas tolerando campos futuros y números serializados como texto."""

        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise ValueError("'public_transport' debe ser un objeto.")
        allowed = {item.name: item for item in fields(cls)}
        clean: dict[str, Any] = {}
        key = ""
        try:
            for key, value in payload.items():
                if key not in allowed:
                    continue
                current_type = allowed[key].type
                if current_type == "str":
                    clean[key] = str(value)
                elif current_type == "int":
                    clean[key] = int(value)
                else:
                    clean[key] = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"El campo de transporte público '{key}' es inválido.") from exc
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class CongestionResult:
    """Resultado de una función volumen–demora para la condición capturada."""

    model: str
    travel_time_min: float | None
    delay_min: float | None
    commercial_speed_kmh: float | None


@dataclass(frozen=True, slots=True)
class TransitLineResult:
    """Indicadores de oferta, demanda, paradas y flota."""

    running_time_one_way_min: float
    commercial_time_one_way_min: float
    operating_speed_kmh: float
    commercial_speed_kmh: float
    cycle_time_min: float
    service_frequency_bus_h: float
    effective_vehicle_capacity_pax: float
    line_capacity_pax_h_direction: float
    required_frequency_bus_h: float
    required_headway_min: float
    minimum_fleet_veh: int
    reserve_fleet_veh: int
    total_fleet_veh: int
    supply_demand_ratio: float
    capacity_margin_pax_h_direction: float
    average_wait_min: float
    actual_stop_spacing_m: float
    optimal_stop_spacing_m: float
    recommended_stop_count: int
    average_access_time_min: float
    boarding_service_time_s: float
    alighting_service_time_s: float
    dwell_time_s: float
    critical_stop_capacity_bus_h: float
    critical_stop_capacity_pax_h_direction: float
    equivalent_road_flow_veh_h: float
    road_degree_of_saturation: float
    free_flow_time_min: float
    congestion: tuple[CongestionResult, ...]
    warnings: tuple[str, ...] = ()


class TransitCalculationError(ValueError):
    """Indica que la línea no puede calcularse con las entradas actuales."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("\n".join(messages))


def validate_transit_line(data: TransitLineInput) -> list[str]:
    """Devuelve errores de dominio, sin depender de la interfaz gráfica."""

    errors: list[str] = []
    positive = (
        ("Longitud de la línea", data.route_length_km),
        ("Velocidad de operación", data.operating_speed_kmh),
        ("Intervalo programado", data.scheduled_headway_min),
        ("Capacidad del vehículo", data.vehicle_capacity_pax),
        ("Factor de ocupación objetivo", data.target_load_factor),
        ("Velocidad peatonal", data.walking_speed_m_s),
        ("Longitud media de viaje", data.average_trip_length_km),
        ("Número de puertas", float(data.door_count)),
        ("Número de posiciones de parada", float(data.stop_berths)),
        ("Capacidad vial", data.road_capacity_veh_h),
        ("Equivalencia del autobús", data.bus_pce),
        ("Exponente BPR", data.bpr_beta),
    )
    nonnegative = (
        ("Tiempo de regulación terminal", data.terminal_layover_min),
        ("Demanda de pasajeros", data.peak_demand_pax_h_direction),
        ("Reserva de flota", data.reserve_fleet_percent),
        ("Ascensos por parada", data.boardings_per_stop),
        ("Descensos por parada", data.alightings_per_stop),
        ("Tiempo de ascenso", data.boarding_time_s_pax),
        ("Tiempo de descenso", data.alighting_time_s_pax),
        ("Apertura y cierre", data.door_open_close_s),
        ("Penalización por parada", data.stop_accel_decel_penalty_s),
        ("Despeje de parada", data.stop_clearance_s),
        ("Flujo vial de fondo", data.background_flow_veh_h),
        ("Parámetro lineal", data.linear_alpha),
        ("Parámetro alfa BPR", data.bpr_alpha),
        ("Parámetro Davidson", data.davidson_j),
        ("Parámetro exponencial", data.exponential_alpha),
    )
    for label, value in positive:
        if not isfinite(value) or value <= 0:
            errors.append(f"{label}: debe ser un número finito mayor que cero.")
    for label, value in nonnegative:
        if not isfinite(value) or value < 0:
            errors.append(f"{label}: debe ser un número finito no negativo.")
    if data.stop_count_per_direction < 2:
        errors.append("Número de paradas: debe haber al menos dos por sentido.")
    if data.exchange_mode not in {"Simultáneo", "Secuencial"}:
        errors.append("Intercambio de pasajeros: selecciona Simultáneo o Secuencial.")
    return errors


def calculate_transit_line(data: TransitLineInput) -> TransitLineResult:
    """Calcula el plan operacional y el balance oferta–demanda de la línea."""

    errors = validate_transit_line(data)
    if errors:
        raise TransitCalculationError(errors)

    boarding = data.boardings_per_stop * data.boarding_time_s_pax / data.door_count
    alighting = data.alightings_per_stop * data.alighting_time_s_pax / data.door_count
    passenger_exchange = max(boarding, alighting)
    if data.exchange_mode == "Secuencial":
        passenger_exchange = boarding + alighting
    dwell = data.door_open_close_s + passenger_exchange

    running_time = 60.0 * data.route_length_km / data.operating_speed_kmh
    intermediate_stops = max(0, data.stop_count_per_direction - 2)
    stop_time = dwell + data.stop_accel_decel_penalty_s
    commercial_time = running_time + intermediate_stops * stop_time / 60.0
    commercial_speed = 60.0 * data.route_length_km / commercial_time
    cycle_time = 2.0 * commercial_time + 2.0 * data.terminal_layover_min

    frequency = 60.0 / data.scheduled_headway_min
    effective_capacity = data.vehicle_capacity_pax * data.target_load_factor
    line_capacity = frequency * effective_capacity
    required_frequency = data.peak_demand_pax_h_direction / effective_capacity
    required_headway = 60.0 / required_frequency if required_frequency > 0 else float("inf")
    minimum_fleet = ceil(cycle_time / data.scheduled_headway_min)
    reserve_fleet = ceil(minimum_fleet * data.reserve_fleet_percent / 100.0)
    total_fleet = minimum_fleet + reserve_fleet
    supply_demand_ratio = (
        line_capacity / data.peak_demand_pax_h_direction
        if data.peak_demand_pax_h_direction > 0
        else float("inf")
    )

    route_m = data.route_length_km * 1000.0
    actual_spacing = route_m / (data.stop_count_per_direction - 1)
    average_access_time = actual_spacing / (4.0 * data.walking_speed_m_s) / 60.0
    optimal_spacing = sqrt(
        4.0
        * data.walking_speed_m_s
        * data.average_trip_length_km
        * 1000.0
        * stop_time
    )
    recommended_stops = max(2, round(route_m / optimal_spacing) + 1)

    stop_service_time = dwell + data.stop_clearance_s
    critical_stop_capacity = data.stop_berths * 3600.0 / stop_service_time
    critical_stop_pax_capacity = critical_stop_capacity * effective_capacity

    equivalent_flow = data.background_flow_veh_h + frequency * data.bus_pce
    degree = equivalent_flow / data.road_capacity_veh_h
    free_flow_time = running_time
    congestion = tuple(
        _current_congestion_result(model, data, degree, free_flow_time)
        for model in ("Lineal", "BPR", "Davidson", "Exponencial")
    )

    warnings: list[str] = []
    if line_capacity < data.peak_demand_pax_h_direction:
        warnings.append(
            "La oferta programada no cubre la demanda pico; reduce el intervalo o aumenta "
            "la capacidad vehicular."
        )
    if frequency > critical_stop_capacity:
        warnings.append(
            "La frecuencia programada supera la capacidad teórica de la parada crítica."
        )
    if degree >= 1.0:
        warnings.append(
            "La demanda vial equivalente alcanza o supera la capacidad; Davidson no es "
            "finita en esta condición."
        )
    elif degree >= 0.90:
        warnings.append("La vía opera cerca de su capacidad después de incorporar los autobuses.")
    if data.average_trip_length_km > data.route_length_km:
        warnings.append("La longitud media de viaje excede la longitud de la línea capturada.")
    if actual_spacing < 200 or actual_spacing > 1000:
        warnings.append(
            "El espaciamiento actual está fuera del intervalo exploratorio de 200 a 1 000 m; "
            "revisa accesibilidad y velocidad comercial."
        )

    return TransitLineResult(
        running_time_one_way_min=running_time,
        commercial_time_one_way_min=commercial_time,
        operating_speed_kmh=data.operating_speed_kmh,
        commercial_speed_kmh=commercial_speed,
        cycle_time_min=cycle_time,
        service_frequency_bus_h=frequency,
        effective_vehicle_capacity_pax=effective_capacity,
        line_capacity_pax_h_direction=line_capacity,
        required_frequency_bus_h=required_frequency,
        required_headway_min=required_headway,
        minimum_fleet_veh=minimum_fleet,
        reserve_fleet_veh=reserve_fleet,
        total_fleet_veh=total_fleet,
        supply_demand_ratio=supply_demand_ratio,
        capacity_margin_pax_h_direction=line_capacity - data.peak_demand_pax_h_direction,
        average_wait_min=data.scheduled_headway_min / 2.0,
        actual_stop_spacing_m=actual_spacing,
        optimal_stop_spacing_m=optimal_spacing,
        recommended_stop_count=recommended_stops,
        average_access_time_min=average_access_time,
        boarding_service_time_s=boarding,
        alighting_service_time_s=alighting,
        dwell_time_s=dwell,
        critical_stop_capacity_bus_h=critical_stop_capacity,
        critical_stop_capacity_pax_h_direction=critical_stop_pax_capacity,
        equivalent_road_flow_veh_h=equivalent_flow,
        road_degree_of_saturation=degree,
        free_flow_time_min=free_flow_time,
        congestion=congestion,
        warnings=tuple(warnings),
    )


def congestion_time(
    model: str,
    free_flow_time_min: float,
    degree_of_saturation: float,
    data: TransitLineInput,
) -> float | None:
    """Evalúa una función volumen–demora para un valor de ``v/c``."""

    x = max(0.0, degree_of_saturation)
    if model == "Lineal":
        return free_flow_time_min * (1.0 + data.linear_alpha * x)
    if model == "BPR":
        return free_flow_time_min * (1.0 + data.bpr_alpha * x**data.bpr_beta)
    if model == "Davidson":
        if x >= 1.0:
            return None
        return free_flow_time_min * (1.0 + data.davidson_j * x / (1.0 - x))
    if model == "Exponencial":
        return free_flow_time_min * exp(data.exponential_alpha * x)
    raise ValueError(f"Modelo de congestión desconocido: {model}")


def _current_congestion_result(
    model: str,
    data: TransitLineInput,
    degree: float,
    free_flow_time: float,
) -> CongestionResult:
    travel_time = congestion_time(model, free_flow_time, degree, data)
    if travel_time is None:
        return CongestionResult(model, None, None, None)
    speed = 60.0 * data.route_length_km / travel_time
    return CongestionResult(model, travel_time, travel_time - free_flow_time, speed)
