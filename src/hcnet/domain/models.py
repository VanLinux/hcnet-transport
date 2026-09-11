"""Entidades de dominio para una intersección semaforizada aislada."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from hcnet import __version__

SCHEMA_VERSION = 1


def _identifier() -> str:
    return uuid4().hex[:12]


@dataclass(slots=True)
class LaneGroupInput:
    """Datos de entrada de un grupo de carriles.

    Los volúmenes están expresados en veh/h, los tiempos en segundos y las
    longitudes en metros. Los factores sin dimensiones se introducen como
    fracciones, no como porcentajes.
    """

    identifier: str = field(default_factory=_identifier)
    approach: str = "Norte"
    movement: str = "Directo"
    volume_veh_h: float = 450.0
    lanes: int = 1
    effective_green_s: float = 35.0
    peak_hour_factor: float = 0.92
    base_saturation_flow_pc_h_ln: float = 1900.0
    heavy_vehicles_percent: float = 2.0
    heavy_vehicle_equivalency: float = 2.0
    lane_width_m: float = 3.6
    grade_percent: float = 0.0
    lane_utilization_factor: float = 1.0
    parking_maneuvers_h: float = 0.0
    bus_blockages_h: float = 0.0
    area_type_factor: float = 1.0
    turn_factor: float = 1.0
    progression_factor: float = 1.0
    incremental_delay_factor: float = 0.5
    upstream_filtering_factor: float = 1.0
    initial_queue_delay_s_veh: float = 0.0
    notes: str = ""

    @property
    def label(self) -> str:
        return f"{self.approach} · {self.movement}"


@dataclass(slots=True)
class IntersectionProject:
    """Proyecto de análisis de una intersección semaforizada."""

    name: str = "Intersección sin nombre"
    location: str = ""
    analyst: str = ""
    study_date: str = field(default_factory=lambda: date.today().isoformat())
    cycle_length_s: float = 90.0
    analysis_period_h: float = 0.25
    lane_groups: list[LaneGroupInput] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "application": "HCNet Transport",
            "application_version": __version__,
            "project": asdict(self),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IntersectionProject:
        schema_version = payload.get("schema_version", SCHEMA_VERSION)
        try:
            schema_version = int(schema_version)
        except (TypeError, ValueError) as exc:
            raise ValueError("'schema_version' debe ser un número entero.") from exc
        if schema_version > SCHEMA_VERSION:
            raise ValueError(
                "El proyecto fue creado con un esquema más reciente que esta versión "
                "de HCNet. Actualiza la aplicación antes de abrirlo."
            )

        project_data = payload.get("project", payload)
        if not isinstance(project_data, dict):
            raise ValueError("El archivo no contiene un objeto de proyecto válido.")

        data = dict(project_data)
        raw_groups = data.pop("lane_groups", [])
        if not isinstance(raw_groups, list):
            raise ValueError("'lane_groups' debe ser una lista.")

        allowed_project = set(cls.__dataclass_fields__)
        clean_project = {key: value for key, value in data.items() if key in allowed_project}
        _convert_values(
            clean_project,
            strings=("name", "location", "analyst", "study_date", "notes"),
            floats=("cycle_length_s", "analysis_period_h"),
        )
        allowed_group = set(LaneGroupInput.__dataclass_fields__)
        groups = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                raise ValueError("Cada grupo de carriles debe ser un objeto.")
            clean_group = {key: value for key, value in raw_group.items() if key in allowed_group}
            _convert_values(
                clean_group,
                strings=("identifier", "approach", "movement", "notes"),
                integers=("lanes",),
                floats=(
                    "volume_veh_h",
                    "effective_green_s",
                    "peak_hour_factor",
                    "base_saturation_flow_pc_h_ln",
                    "heavy_vehicles_percent",
                    "heavy_vehicle_equivalency",
                    "lane_width_m",
                    "grade_percent",
                    "lane_utilization_factor",
                    "parking_maneuvers_h",
                    "bus_blockages_h",
                    "area_type_factor",
                    "turn_factor",
                    "progression_factor",
                    "incremental_delay_factor",
                    "upstream_filtering_factor",
                    "initial_queue_delay_s_veh",
                ),
            )
            groups.append(LaneGroupInput(**clean_group))

        return cls(lane_groups=groups, **clean_project)


def _convert_values(
    data: dict[str, Any],
    *,
    strings: tuple[str, ...] = (),
    integers: tuple[str, ...] = (),
    floats: tuple[str, ...] = (),
) -> None:
    """Convierte datos JSON conocidos y produce errores comprensibles."""

    key = ""
    try:
        for key in strings:
            if key in data:
                if data[key] is None:
                    raise TypeError
                data[key] = str(data[key])
        for key in integers:
            if key in data:
                data[key] = int(data[key])
        for key in floats:
            if key in data:
                data[key] = float(data[key])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"El campo '{key}' tiene un tipo o valor inválido.") from exc


@dataclass(frozen=True, slots=True)
class AdjustmentFactors:
    lane_width: float
    heavy_vehicles: float
    grade: float
    parking: float
    bus_blockage: float
    lane_utilization: float
    area_type: float
    turn: float

    @property
    def product(self) -> float:
        return (
            self.lane_width
            * self.heavy_vehicles
            * self.grade
            * self.parking
            * self.bus_blockage
            * self.lane_utilization
            * self.area_type
            * self.turn
        )


@dataclass(frozen=True, slots=True)
class LaneGroupResult:
    identifier: str
    label: str
    demand_flow_rate_veh_h: float
    factors: AdjustmentFactors
    saturation_flow_veh_h: float
    capacity_veh_h: float
    degree_of_saturation: float
    uniform_delay_s_veh: float
    incremental_delay_s_veh: float
    initial_queue_delay_s_veh: float
    control_delay_s_veh: float
    level_of_service: str
    red_arrivals_veh_cycle: float
    residual_demand_veh: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntersectionResult:
    lane_groups: tuple[LaneGroupResult, ...]
    total_entering_volume_veh_h: float
    weighted_control_delay_s_veh: float
    level_of_service: str
    critical_degree_of_saturation: float
    critical_lane_group: str
    warnings: tuple[str, ...] = ()
