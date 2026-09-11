"""Motor matemático transparente para intersecciones semaforizadas.

La versión 1.0 implementa el flujo analítico base de capacidad y demora para
grupos de carriles con control de tiempo fijo. Las limitaciones metodológicas
se documentan en ``docs/METHODOLOGY.md``.
"""

from __future__ import annotations

from math import isfinite, sqrt

from hcnet.domain.models import (
    AdjustmentFactors,
    IntersectionProject,
    IntersectionResult,
    LaneGroupInput,
    LaneGroupResult,
)
from hcnet.domain.validation import validate_project


class CalculationError(ValueError):
    """Indica que el proyecto no puede calcularse con datos inválidos."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("\n".join(messages))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def adjustment_factors(group: LaneGroupInput) -> AdjustmentFactors:
    """Calcula los factores de ajuste implementados en la versión 1.0."""

    lane_width = _clamp(1.0 + (group.lane_width_m - 3.6) / 9.0, 0.80, 1.20)
    heavy_share = group.heavy_vehicles_percent / 100.0
    heavy_vehicles = 1.0 / (1.0 + heavy_share * (group.heavy_vehicle_equivalency - 1.0))
    grade = _clamp(1.0 - group.grade_percent / 200.0, 0.80, 1.20)

    if group.parking_maneuvers_h == 0:
        parking = 1.0
    else:
        parking = (group.lanes - 0.1 - (18.0 * group.parking_maneuvers_h / 3600.0)) / group.lanes
        parking = _clamp(parking, 0.05, 1.0)

    bus_blockage = (group.lanes - (14.4 * group.bus_blockages_h / 3600.0)) / group.lanes
    bus_blockage = _clamp(bus_blockage, 0.05, 1.0)

    return AdjustmentFactors(
        lane_width=lane_width,
        heavy_vehicles=heavy_vehicles,
        grade=grade,
        parking=parking,
        bus_blockage=bus_blockage,
        lane_utilization=group.lane_utilization_factor,
        area_type=group.area_type_factor,
        turn=group.turn_factor,
    )


def level_of_service(control_delay_s_veh: float, degree_of_saturation: float | None = None) -> str:
    """Asigna LOS A–F a partir de demora de control.

    En grupos de carriles, una demanda superior a la capacidad (X > 1) se
    identifica como LOS F aun cuando el periodo corto produzca una demora
    calculada menor que 80 s/veh. Para el agregado de la intersección se usa
    exclusivamente la demora ponderada.
    """

    if degree_of_saturation is not None and degree_of_saturation > 1.0:
        return "F"
    if control_delay_s_veh <= 10.0:
        return "A"
    if control_delay_s_veh <= 20.0:
        return "B"
    if control_delay_s_veh <= 35.0:
        return "C"
    if control_delay_s_veh <= 55.0:
        return "D"
    if control_delay_s_veh <= 80.0:
        return "E"
    return "F"


def calculate_lane_group(
    project: IntersectionProject,
    group: LaneGroupInput,
) -> LaneGroupResult:
    """Calcula capacidad, grado de saturación y demora de un grupo."""

    cycle = project.cycle_length_s
    period = project.analysis_period_h
    green_ratio = group.effective_green_s / cycle
    demand = group.volume_veh_h / group.peak_hour_factor
    factors = adjustment_factors(group)

    saturation_flow = group.base_saturation_flow_pc_h_ln * group.lanes * factors.product
    capacity = saturation_flow * green_ratio
    if capacity <= 0 or not isfinite(capacity):
        raise CalculationError([f"{group.label}: la capacidad calculada no es válida."])

    degree = demand / capacity

    uniform_denominator = 1.0 - min(1.0, degree) * green_ratio
    uniform_delay = (
        0.5 * cycle * (1.0 - green_ratio) ** 2 / uniform_denominator * group.progression_factor
    )

    radical = (degree - 1.0) ** 2 + (
        8.0
        * group.incremental_delay_factor
        * group.upstream_filtering_factor
        * degree
        / (capacity * period)
    )
    incremental_delay = 900.0 * period * ((degree - 1.0) + sqrt(radical))
    incremental_delay = max(0.0, incremental_delay)

    initial_queue_delay = group.initial_queue_delay_s_veh
    control_delay = uniform_delay + incremental_delay + initial_queue_delay

    red_time = cycle - group.effective_green_s
    red_arrivals = demand * red_time / 3600.0
    residual_demand = max(0.0, (demand - capacity) * period)

    warnings: list[str] = []
    if degree > 1.0:
        warnings.append("Demanda superior a la capacidad durante el periodo analizado.")
    elif degree >= 0.90:
        warnings.append("Operación cercana a la capacidad (X ≥ 0.90).")
    if group.initial_queue_delay_s_veh > 0:
        warnings.append("d₃ fue proporcionada por el usuario y no estimada por HCNet.")
    if group.progression_factor != 1.0:
        warnings.append("Se aplicó un factor de progresión definido por el usuario.")

    return LaneGroupResult(
        identifier=group.identifier,
        label=group.label,
        demand_flow_rate_veh_h=demand,
        factors=factors,
        saturation_flow_veh_h=saturation_flow,
        capacity_veh_h=capacity,
        degree_of_saturation=degree,
        uniform_delay_s_veh=uniform_delay,
        incremental_delay_s_veh=incremental_delay,
        initial_queue_delay_s_veh=initial_queue_delay,
        control_delay_s_veh=control_delay,
        level_of_service=level_of_service(control_delay, degree),
        red_arrivals_veh_cycle=red_arrivals,
        residual_demand_veh=residual_demand,
        warnings=tuple(warnings),
    )


def calculate_intersection(project: IntersectionProject) -> IntersectionResult:
    """Valida y calcula todos los grupos y el agregado de la intersección."""

    issues = validate_project(project)
    errors = [issue.display(project) for issue in issues if issue.severity == "error"]
    if errors:
        raise CalculationError(errors)

    results = tuple(calculate_lane_group(project, group) for group in project.lane_groups)
    total_volume = sum(group.volume_veh_h for group in project.lane_groups)
    total_demand = sum(result.demand_flow_rate_veh_h for result in results)
    if total_demand > 0:
        weighted_delay = (
            sum(result.control_delay_s_veh * result.demand_flow_rate_veh_h for result in results)
            / total_demand
        )
    else:
        weighted_delay = 0.0

    critical = max(results, key=lambda result: result.degree_of_saturation)
    warnings = [issue.display(project) for issue in issues if issue.severity == "warning"]
    for result in results:
        warnings.extend(f"{result.label}: {message}" for message in result.warnings)

    return IntersectionResult(
        lane_groups=results,
        total_entering_volume_veh_h=total_volume,
        weighted_control_delay_s_veh=weighted_delay,
        level_of_service=level_of_service(weighted_delay),
        critical_degree_of_saturation=critical.degree_of_saturation,
        critical_lane_group=critical.label,
        warnings=tuple(dict.fromkeys(warnings)),
    )
