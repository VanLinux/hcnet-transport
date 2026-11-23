"""Motor matemático transparente para intersecciones semaforizadas.

El módulo implementa el flujo analítico base de capacidad y demora para
grupos de carriles con control de tiempo fijo. Las limitaciones metodológicas
se documentan en ``docs/METHODOLOGY.md``.
"""

from __future__ import annotations

from math import ceil, isfinite, sqrt

from hcnet.domain.models import (
    AdjustmentFactors,
    IntersectionProject,
    IntersectionResult,
    LaneGroupInput,
    LaneGroupResult,
    SignalOptimizationResult,
    SignalPhaseResult,
)
from hcnet.domain.signals import prepare_project
from hcnet.domain.validation import validate_project


class CalculationError(ValueError):
    """Indica que el proyecto no puede calcularse con datos inválidos."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("\n".join(messages))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def adjustment_factors(group: LaneGroupInput) -> AdjustmentFactors:
    """Calcula los factores de ajuste implementados por el módulo."""

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
    *,
    delay_model: str = "HCNet",
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
    if delay_model == "Akçelik":
        x0 = 0.67 + saturation_flow * group.effective_green_s / (3600 * 600)
        overflow = 0.0
        if degree > x0:
            overflow = capacity * period / 4 * (
                degree - 1 + sqrt((degree - 1)**2 + 12 * (degree - x0) / (capacity * period))
            )
        incremental_delay = 3600 * overflow / capacity
        uniform_delay /= group.progression_factor

    initial_queue_delay = group.initial_queue_delay_s_veh if delay_model == "HCNet" else 0
    control_delay = uniform_delay + incremental_delay + initial_queue_delay

    red_time = cycle - group.effective_green_s
    red_arrivals = demand * red_time / 3600.0
    residual_demand = max(0.0, (demand - capacity) * period)
    average_queue = residual_demand + 0.5 * red_arrivals
    queue_95 = residual_demand + red_arrivals + 1.645 * sqrt(max(0.0, red_arrivals))
    queue_95_m = queue_95 / group.lanes * group.average_vehicle_spacing_m
    free_flow_travel_time = group.approach_length_m / (group.free_flow_speed_kmh / 3.6)
    travel_time = free_flow_travel_time + control_delay

    warnings: list[str] = []
    if degree > 1.0:
        warnings.append("Demanda superior a la capacidad durante el periodo analizado.")
    elif degree >= 0.90:
        warnings.append("Operación cercana a la capacidad (X ≥ 0.90).")
    if group.initial_queue_delay_s_veh > 0:
        warnings.append("d₃ fue proporcionada por el usuario y no estimada por HCNet.")
    if group.progression_factor != 1.0:
        warnings.append("Se aplicó un factor de progresión definido por el usuario.")
    if queue_95_m > group.approach_length_m:
        warnings.append(
            "La cola percentil 95 aproximada excede la longitud de aproximación disponible."
        )

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
        average_queue_veh=average_queue,
        queue_95_veh=queue_95,
        queue_95_m=queue_95_m,
        free_flow_travel_time_s=free_flow_travel_time,
        travel_time_s=travel_time,
        warnings=tuple(warnings),
    )


def calculate_intersection(
    project: IntersectionProject, *, delay_model: str = "HCNet",
) -> IntersectionResult:
    """Valida y calcula todos los grupos y el agregado de la intersección."""

    try:
        project = prepare_project(project)
    except ValueError as exc:
        raise CalculationError([str(exc)]) from exc
    issues = validate_project(project)
    errors = [issue.display(project) for issue in issues if issue.severity == "error"]
    if errors:
        raise CalculationError(errors)

    results = tuple(
        calculate_lane_group(project, group, delay_model=delay_model)
        for group in project.lane_groups
    )
    total_volume = sum(group.volume_veh_h for group in project.lane_groups)
    total_demand = sum(result.demand_flow_rate_veh_h for result in results)
    if total_demand > 0:
        weighted_delay = (
            sum(result.control_delay_s_veh * result.demand_flow_rate_veh_h for result in results)
            / total_demand
        )
        weighted_travel_time = (
            sum(result.travel_time_s * result.demand_flow_rate_veh_h for result in results)
            / total_demand
        )
    else:
        weighted_delay = 0.0
        weighted_travel_time = 0.0

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
        maximum_queue_95_m=max(result.queue_95_m for result in results),
        weighted_travel_time_s=weighted_travel_time,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def optimize_signal_timing(project: IntersectionProject) -> SignalOptimizationResult:
    """Optimiza ciclo y reparto de verdes con el método clásico de Webster.

    Los grupos que comparten número de fase se consideran simultáneos; por ello se
    utiliza la relación de flujo crítica máxima de cada fase. El resultado es una
    propuesta inicial de tiempo fijo y debe revisarse frente a conflictos, peatones
    y mínimos normativos antes de implantarse.
    """

    if not project.lane_groups:
        raise CalculationError(["Agrega al menos un movimiento antes de optimizar."])
    if project.optimization_method != "Webster":
        raise CalculationError(
            [f"El método de optimización '{project.optimization_method}' no está implementado."]
        )
    if project.signal_lost_time_s <= 0:
        raise CalculationError(["El tiempo perdido por fase debe ser positivo."])
    if project.yellow_time_s < 0 or project.all_red_time_s < 0:
        raise CalculationError(["Los intervalos amarillo y todo rojo no pueden ser negativos."])
    if project.yellow_time_s + project.all_red_time_s > project.signal_lost_time_s:
        raise CalculationError(
            ["Amarillo + todo rojo no puede exceder el tiempo perdido por fase."]
        )

    phase_ratios: dict[int, list[float]] = {}
    for group in project.lane_groups:
        if group.signal_phase < 1:
            raise CalculationError([f"{group.label}: la fase debe ser mayor o igual que 1."])
        demand = group.volume_veh_h / group.peak_hour_factor
        saturation = (
            group.base_saturation_flow_pc_h_ln
            * group.lanes
            * adjustment_factors(group).product
        )
        if saturation <= 0:
            raise CalculationError([f"{group.label}: el flujo de saturación no es válido."])
        phase_ratios.setdefault(group.signal_phase, []).append(demand / saturation)

    critical = {phase: max(values) for phase, values in phase_ratios.items()}
    total_ratio = sum(critical.values())
    if total_ratio >= 1.0:
        raise CalculationError(
            [
                "La suma de relaciones críticas Y es mayor o igual que 1.00; "
                "Webster no produce un ciclo finito. Revisa demanda, fases o geometría."
            ]
        )

    phase_numbers = sorted(critical)
    phase_count = len(phase_numbers)
    total_lost = phase_count * project.signal_lost_time_s
    webster_cycle = (1.5 * total_lost + 5.0) / (1.0 - total_ratio)
    minimum_cycle = phase_count * (project.minimum_green_s + project.signal_lost_time_s)
    cycle = float(ceil(_clamp(max(webster_cycle, minimum_cycle), 40.0, 180.0)))
    effective_green = cycle - total_lost
    greens = _allocate_greens(
        [critical[phase] for phase in phase_numbers],
        effective_green,
        project.minimum_green_s,
    )

    phases: list[SignalPhaseResult] = []
    start = 0.0
    for phase_number, ratio, green in zip(
        phase_numbers, (critical[item] for item in phase_numbers), greens, strict=True
    ):
        end = start + green + project.signal_lost_time_s
        phases.append(
            SignalPhaseResult(
                phase_number=phase_number,
                critical_flow_ratio=ratio,
                green_s=green,
                yellow_s=project.yellow_time_s,
                all_red_s=project.all_red_time_s,
                start_s=start,
                end_s=end,
            )
        )
        start = end

    warnings: list[str] = []
    if webster_cycle > 180:
        warnings.append("El ciclo teórico superó 180 s y fue limitado a ese valor.")
    if total_ratio >= 0.90:
        warnings.append("La suma crítica Y es alta; conviene revisar la factibilidad de las fases.")
    warnings.append(
        "La propuesta no sustituye la revisión de conflictos, tiempos peatonales "
        "ni normativa local."
    )
    return SignalOptimizationResult(
        method="Webster",
        cycle_length_s=cycle,
        total_critical_flow_ratio=total_ratio,
        phases=tuple(phases),
        warnings=tuple(warnings),
    )


def _allocate_greens(weights: list[float], total: float, minimum: float) -> list[float]:
    """Distribuye verde proporcionalmente respetando un mínimo por fase."""

    if not weights:
        return []
    if total < len(weights) * minimum:
        return [total / len(weights)] * len(weights)

    allocations = [0.0] * len(weights)
    remaining = set(range(len(weights)))
    remaining_total = total
    while remaining:
        weight_sum = sum(weights[index] for index in remaining)
        shares = {
            index: (
                remaining_total * weights[index] / weight_sum
                if weight_sum > 0
                else remaining_total / len(remaining)
            )
            for index in remaining
        }
        below = {index for index, value in shares.items() if value < minimum}
        if not below:
            for index, value in shares.items():
                allocations[index] = value
            break
        for index in below:
            allocations[index] = minimum
        remaining_total -= minimum * len(below)
        remaining -= below
    return allocations
