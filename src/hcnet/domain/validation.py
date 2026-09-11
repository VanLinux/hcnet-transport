"""Validación de datos antes de ejecutar el procedimiento analítico."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

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

    if not project.lane_groups:
        issues.append(
            ValidationIssue("error", "lane_groups", "Agrega al menos un grupo de carriles.")
        )

    for index, group in enumerate(project.lane_groups):
        issues.extend(_validate_lane_group(group, project, index))

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

    return issues
