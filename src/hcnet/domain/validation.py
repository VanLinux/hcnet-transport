"""Validación de datos antes de ejecutar el procedimiento analítico."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from hcnet.domain.calibration import empirical_multiplier
from hcnet.domain.models import IntersectionProject, LaneGroupInput

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    field: str
    message: str
    group_index: int | None = None

    def display(self, project: IntersectionProject) -> str:
        if self.group_index is None:
            return self.message
        group = project.lane_groups[self.group_index]
        return f"{group.label}: {self.message}"


def validate_project(project: IntersectionProject) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not project.name.strip():
        issues.append(ValidationIssue("warning", "name", "El proyecto no tiene nombre."))
    if not isfinite(project.cycle_length_s):
        issues.append(
            ValidationIssue("error", "cycle_length_s", "La longitud de ciclo no es finita.")
        )
    elif project.cycle_length_s <= 0:
        issues.append(
            ValidationIssue(
                "error",
                "cycle_length_s",
                "La longitud de ciclo debe ser mayor que cero.",
            )
        )
    elif not 30 <= project.cycle_length_s <= 240:
        issues.append(
            ValidationIssue(
                "warning",
                "cycle_length_s",
                "La longitud de ciclo está fuera del intervalo habitual de 30 a 240 s.",
            )
        )

    if not isfinite(project.analysis_period_h):
        issues.append(
            ValidationIssue("error", "analysis_period_h", "El periodo de análisis no es finito.")
        )
    elif project.analysis_period_h <= 0:
        issues.append(
            ValidationIssue(
                "error",
                "analysis_period_h",
                "El periodo de análisis debe ser positivo.",
            )
        )
    elif project.analysis_period_h > 1:
        issues.append(
            ValidationIssue(
                "warning",
                "analysis_period_h",
                "El periodo de análisis excede una hora; revisa la estacionariedad de la demanda.",
            )
        )

    if project.branch_count not in {2, 3, 4}:
        issues.append(
            ValidationIssue(
                "error", "branch_count", "La intersección debe tener dos, tres o cuatro ramales."
            )
        )
    if len(project.branches) < project.branch_count:
        issues.append(
            ValidationIssue(
                "error", "branches", "No existen suficientes ramales para la geometría elegida."
            )
        )
    active_codes = [branch.code for branch in project.active_branches]
    if len(set(active_codes)) != len(active_codes):
        issues.append(ValidationIssue("error", "branches", "Las letras de ramal deben ser únicas."))
    azimuths = [branch.azimuth for branch in project.active_branches]
    if any(not 0 <= angle < 360 for angle in azimuths) or len(set(azimuths)) != len(azimuths):
        issues.append(ValidationIssue(
            "error", "branches", "Asigna azimuts distintos entre 0° y menos de 360°."
        ))
    for branch in project.active_branches:
        if not branch.code.strip():
            issues.append(
                ValidationIssue("error", "branches", "Cada ramal debe tener una letra.")
            )
        if branch.inbound_lanes < 1 or branch.outbound_lanes < 1:
            issues.append(
                ValidationIssue(
                    "error",
                    "branches",
                    f"Ramal {branch.code}: debe tener carriles de entrada y salida.",
                )
            )

    for field_name, value, label in (
        ("signal_lost_time_s", project.signal_lost_time_s, "tiempo perdido"),
        ("minimum_green_s", project.minimum_green_s, "verde mínimo"),
        ("yellow_time_s", project.yellow_time_s, "amarillo"),
        ("all_red_time_s", project.all_red_time_s, "todo rojo"),
    ):
        if not isfinite(value) or value < 0:
            issues.append(
                ValidationIssue(
                    "error",
                    field_name,
                    f"El tiempo de {label} debe ser finito y no negativo.",
                )
            )
    if project.signal_lost_time_s <= 0:
        issues.append(
            ValidationIssue("error", "signal_lost_time_s", "El tiempo perdido debe ser positivo.")
        )
    default_clearance = project.yellow_time_s + project.all_red_time_s
    if not project.phases and default_clearance > project.signal_lost_time_s:
        issues.append(
            ValidationIssue(
                "error",
                "signal_lost_time_s",
                "Amarillo + todo rojo no puede exceder el tiempo perdido por fase.",
            )
        )

    if not project.lane_groups:
        issues.append(
            ValidationIssue("error", "lane_groups", "Agrega al menos un grupo de carriles.")
        )

    for index, group in enumerate(project.lane_groups):
        issues.extend(_validate_lane_group(group, project, index))

    lane_usage: dict[tuple[str, int], list[str]] = {}
    for group in project.lane_groups:
        for lane in group.lane_indices:
            lane_usage.setdefault((group.origin_branch, lane), []).append(group.label)
    for (branch_code, lane), labels in lane_usage.items():
        if len(labels) > 1:
            issues.append(
                ValidationIssue(
                    "warning",
                    "lane_groups",
                    f"Ramal {branch_code}, carril {lane}: aparece en varios grupos "
                    f"({'; '.join(labels)}). Agrupa los destinos que comparten carril "
                    "para evitar duplicar capacidad.",
                )
            )

    group_ids = {group.identifier for group in project.lane_groups}
    groups_by_id = {group.identifier: group for group in project.lane_groups}
    for head in project.signal_heads:
        if not head.name.strip():
            issues.append(
                ValidationIssue("error", "signal_heads", "Cada semáforo debe tener nombre.")
            )
        if head.branch_code not in active_codes:
            issues.append(
                ValidationIssue(
                    "error",
                    "signal_heads",
                    f"{head.name}: el ramal {head.branch_code} no está activo.",
                )
            )
        if head.signal_phase < 1:
            issues.append(
                ValidationIssue("error", "signal_heads", f"{head.name}: la fase debe ser positiva.")
            )
        unknown = set(head.controlled_group_ids) - group_ids
        if unknown:
            issues.append(
                ValidationIssue(
                    "error",
                    "signal_heads",
                    f"{head.name}: contiene movimientos que ya no existen.",
                )
            )
        if not head.controlled_group_ids:
            issues.append(
                ValidationIssue(
                    "warning", "signal_heads", f"{head.name}: no tiene movimientos asignados."
                )
            )
        wrong_phase = [
            groups_by_id[identifier].label
            for identifier in head.controlled_group_ids
            if identifier in groups_by_id
            and groups_by_id[identifier].signal_phase != head.signal_phase
        ]
        if wrong_phase:
            issues.append(
                ValidationIssue(
                    "error",
                    "signal_heads",
                    f"{head.name}: la fase no coincide con {', '.join(wrong_phase)}.",
                )
            )

    if not project.signal_heads:
        issues.append(
            ValidationIssue(
                "warning", "signal_heads", "No se han configurado semáforos en el proyecto."
            )
        )
    else:
        movement_phases = {group.signal_phase for group in project.lane_groups}
        head_phases = {head.signal_phase for head in project.signal_heads}
        missing_phases = movement_phases - head_phases
        if missing_phases:
            issues.append(
                ValidationIssue(
                    "warning",
                    "signal_heads",
                    "No hay semáforos configurados para las fases: "
                    + ", ".join(str(item) for item in sorted(missing_phases))
                    + ".",
                )
            )

    return issues


def _validate_lane_group(
    group: LaneGroupInput,
    project: IntersectionProject,
    index: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def error(field: str, message: str) -> None:
        issues.append(ValidationIssue("error", field, message, index))

    def warning(field: str, message: str) -> None:
        issues.append(ValidationIssue("warning", field, message, index))

    try:
        empirical_multiplier(group.lane_indices, group.empirical_factors, group.field_calibration)
    except (ValueError, TypeError, OverflowError) as exc:
        error("empirical_factors", str(exc))

    numeric_values = (
        ("volume_veh_h", group.volume_veh_h),
        ("effective_green_s", group.effective_green_s),
        ("peak_hour_factor", group.peak_hour_factor),
        ("base_saturation_flow_pc_h_ln", group.base_saturation_flow_pc_h_ln),
        ("heavy_vehicles_percent", group.heavy_vehicles_percent),
        ("heavy_vehicle_equivalency", group.heavy_vehicle_equivalency),
        ("lane_width_m", group.lane_width_m),
        ("grade_percent", group.grade_percent),
        ("lane_utilization_factor", group.lane_utilization_factor),
        ("parking_maneuvers_h", group.parking_maneuvers_h),
        ("bus_blockages_h", group.bus_blockages_h),
        ("area_type_factor", group.area_type_factor),
        ("turn_factor", group.turn_factor),
        ("progression_factor", group.progression_factor),
        ("incremental_delay_factor", group.incremental_delay_factor),
        ("upstream_filtering_factor", group.upstream_filtering_factor),
        ("initial_queue_delay_s_veh", group.initial_queue_delay_s_veh),
        ("free_flow_speed_kmh", group.free_flow_speed_kmh),
        ("approach_length_m", group.approach_length_m),
        ("average_vehicle_spacing_m", group.average_vehicle_spacing_m),
    )
    non_finite = [field for field, value in numeric_values if not isfinite(value)]
    for field in non_finite:
        error(field, "el valor debe ser un número finito.")
    if non_finite:
        return issues

    if not group.approach.strip():
        error("approach", "el acceso no puede estar vacío.")
    if not group.movement.strip():
        error("movement", "el movimiento no puede estar vacío.")
    if group.volume_veh_h < 0:
        error("volume_veh_h", "el volumen no puede ser negativo.")
    if group.lanes < 1:
        error("lanes", "debe existir al menos un carril.")
    active_codes = {branch.code for branch in project.active_branches}
    origin = project.branch(group.origin_branch)
    if origin is None:
        error("origin_branch", f"el ramal de origen {group.origin_branch} no está activo.")
    if not group.destination_branches:
        error("destination_branches", "selecciona al menos un ramal de destino.")
    for destination in group.destination_branches:
        if destination not in active_codes:
            error("destination_branches", f"el ramal de destino {destination} no está activo.")
        elif destination == group.origin_branch:
            error("destination_branches", "el origen y el destino no pueden ser el mismo ramal.")
    if not group.lane_indices:
        error("lane_indices", "selecciona al menos un carril.")
    if len(set(group.lane_indices)) != len(group.lane_indices):
        error("lane_indices", "la asignación contiene carriles repetidos.")
    if group.lanes != len(group.lane_indices):
        error("lanes", "el número de carriles debe coincidir con los carriles seleccionados.")
    if origin is not None and any(
        lane < 1 or lane > origin.inbound_lanes for lane in group.lane_indices
    ):
        error(
            "lane_indices",
            f"los carriles deben estar entre 1 y {origin.inbound_lanes} para el ramal de origen.",
        )
    if group.signal_phase < 1:
        error("signal_phase", "la fase semafórica debe ser mayor o igual que 1.")
    if group.effective_green_s <= 0:
        error("effective_green_s", "el verde efectivo debe ser positivo.")
    elif project.cycle_length_s > 0 and group.effective_green_s >= project.cycle_length_s:
        error("effective_green_s", "el verde efectivo debe ser menor que el ciclo.")
    if not 0 < group.peak_hour_factor <= 1:
        error("peak_hour_factor", "el FHMD/PHF debe estar en (0, 1].")
    if group.base_saturation_flow_pc_h_ln <= 0:
        error("base_saturation_flow_pc_h_ln", "el flujo de saturación base debe ser positivo.")
    elif not 1500 <= group.base_saturation_flow_pc_h_ln <= 2200:
        warning(
            "base_saturation_flow_pc_h_ln",
            "el flujo de saturación base está fuera del intervalo habitual "
            "de 1500 a 2200 pc/h/carril.",
        )
    if not 0 <= group.heavy_vehicles_percent <= 100:
        error(
            "heavy_vehicles_percent",
            "el porcentaje de vehículos pesados debe estar entre 0 y 100.",
        )
    if group.heavy_vehicle_equivalency < 1:
        error("heavy_vehicle_equivalency", "la equivalencia de pesados debe ser al menos 1.0.")
    if not 2.4 <= group.lane_width_m <= 4.8:
        error("lane_width_m", "el ancho de carril debe estar entre 2.4 y 4.8 m.")
    if not -10 <= group.grade_percent <= 10:
        error("grade_percent", "la pendiente debe estar entre -10 % y 10 %.")
    for field_name, value, label in (
        ("lane_utilization_factor", group.lane_utilization_factor, "utilización de carriles"),
        ("area_type_factor", group.area_type_factor, "tipo de área"),
        ("turn_factor", group.turn_factor, "giro"),
        ("progression_factor", group.progression_factor, "progresión"),
        ("incremental_delay_factor", group.incremental_delay_factor, "demora incremental"),
        ("upstream_filtering_factor", group.upstream_filtering_factor, "filtrado aguas arriba"),
    ):
        if value <= 0:
            error(field_name, f"el factor de {label} debe ser positivo.")
        elif value > 1.5:
            warning(field_name, f"el factor de {label} es mayor que 1.5; verifica el dato.")
    if group.parking_maneuvers_h < 0:
        error("parking_maneuvers_h", "las maniobras de estacionamiento no pueden ser negativas.")
    if group.bus_blockages_h < 0:
        error("bus_blockages_h", "los bloqueos de autobús no pueden ser negativos.")
    if group.initial_queue_delay_s_veh < 0:
        error("initial_queue_delay_s_veh", "la demora por cola inicial no puede ser negativa.")
    if group.free_flow_speed_kmh <= 0:
        error("free_flow_speed_kmh", "la velocidad de flujo libre debe ser positiva.")
    elif not 10 <= group.free_flow_speed_kmh <= 120:
        warning(
            "free_flow_speed_kmh",
            "la velocidad de flujo libre está fuera del intervalo habitual de 10 a 120 km/h.",
        )
    if group.approach_length_m <= 0:
        error("approach_length_m", "la longitud de aproximación debe ser positiva.")
    if not 3 <= group.average_vehicle_spacing_m <= 20:
        error(
            "average_vehicle_spacing_m",
            "el espaciamiento medio por vehículo debe estar entre 3 y 20 m.",
        )

    return issues
