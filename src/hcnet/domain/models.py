"""Entidades persistentes del proyecto HCNet Transport."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from hcnet import __version__
from hcnet.domain.roundabout import RoundaboutInput
from hcnet.domain.transit import TransitLineInput

SCHEMA_VERSION = 5
AZIMUTHS = dict(zip(
    ("Norte", "Noreste", "Oriente", "Sureste", "Sur", "Suroeste", "Poniente", "Noroeste"),
    range(0, 360, 45), strict=True,
))


def _identifier() -> str:
    return uuid4().hex[:12]


@dataclass(frozen=True, slots=True)
class MovementInput:
    destination: str
    volume: float = 0
    phf: float = 1
    heavy_percent: float = 0
    enabled: bool = True
    operation: str = "Protegido"


@dataclass(frozen=True, slots=True)
class PhaseInput:
    number: int
    green: float
    yellow: float
    all_red: float


@dataclass(slots=True)
class Scenario:
    name: str
    baseline_key: str
    settings: dict[str, Any]
    baseline: dict[str, Any]
    plan: SignalOptimizationResult


@dataclass(slots=True)
class LaneGroupInput:
    """Datos de entrada de un grupo de carriles.

    Los volúmenes están expresados en veh/h, los tiempos en segundos y las
    longitudes en metros. Los factores sin dimensiones se introducen como
    fracciones, no como porcentajes.
    """

    identifier: str = field(default_factory=_identifier)
    origin_branch: str = "A"
    destination_branches: tuple[str, ...] = ("C",)
    lane_indices: tuple[int, ...] = (1,)
    signal_phase: int = 1
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
    free_flow_speed_kmh: float = 40.0
    approach_length_m: float = 150.0
    average_vehicle_spacing_m: float = 7.5
    notes: str = ""
    movements: tuple[MovementInput, ...] = ()

    def __post_init__(self) -> None:
        if self.lanes > 1 and self.lane_indices == (1,):
            self.lane_indices = tuple(range(1, self.lanes + 1))

    @property
    def label(self) -> str:
        destinations = "/".join(self.destination_branches)
        route = f"{self.origin_branch} → {destinations}" if destinations else self.movement
        return f"{route} · carril{'es' if len(self.lane_indices) != 1 else ''} " + ", ".join(
            str(item) for item in self.lane_indices
        )


@dataclass(slots=True)
class BranchInput:
    """Geometría básica de un ramal de la intersección."""

    code: str
    name: str
    position: str
    inbound_lanes: int = 2
    outbound_lanes: int = 2
    azimuth_deg: float | None = None

    @property
    def azimuth(self) -> float:
        if self.azimuth_deg is not None:
            return self.azimuth_deg
        return AZIMUTHS.get(self.position, {"A": 0, "B": 90, "C": 180, "D": 270}.get(
            self.code, 0
        ))

    @property
    def label(self) -> str:
        return f"{self.code} · {self.name}" if self.name else self.code


def default_branches() -> list[BranchInput]:
    return [
        BranchInput("A", "Norte", "Norte", 3, 3),
        BranchInput("B", "Oriente", "Oriente", 3, 3),
        BranchInput("C", "Sur", "Sur", 3, 3),
        BranchInput("D", "Poniente", "Poniente", 3, 3),
    ]


@dataclass(slots=True)
class SignalHeadInput:
    """Cabeza o grupo semafórico instalado en un ramal."""

    identifier: str = field(default_factory=_identifier)
    name: str = "Semáforo 1"
    branch_code: str = "A"
    signal_type: str = "Vehicular circular"
    signal_phase: int = 1
    controlled_group_ids: tuple[str, ...] = ()
    control_group: str = ""


@dataclass(slots=True)
class IntersectionProject:
    """Proyecto de análisis de una intersección semaforizada."""

    name: str = "Intersección sin nombre"
    location: str = ""
    analyst: str = ""
    study_date: str = field(default_factory=lambda: date.today().isoformat())
    cycle_length_s: float = 90.0
    analysis_period_h: float = 0.25
    branch_count: int = 4
    branches: list[BranchInput] = field(default_factory=default_branches)
    lane_groups: list[LaneGroupInput] = field(default_factory=list)
    signal_heads: list[SignalHeadInput] = field(default_factory=list)
    optimization_method: str = "Webster"
    signal_lost_time_s: float = 4.0
    minimum_green_s: float = 10.0
    yellow_time_s: float = 3.0
    all_red_time_s: float = 1.0
    public_transport: TransitLineInput = field(default_factory=TransitLineInput)
    roundabout: RoundaboutInput = field(default_factory=RoundaboutInput)
    calculated_modules: tuple[str, ...] = ()
    signal_optimization: SignalOptimizationResult | None = None
    last_evaluated: dict[str, Any] | None = None
    phases: list[PhaseInput] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    workspace: str = "signal"
    notes: str = ""

    @property
    def active_branches(self) -> list[BranchInput]:
        return self.branches[: self.branch_count]

    def branch(self, code: str) -> BranchInput | None:
        return next((branch for branch in self.active_branches if branch.code == code), None)

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
        raw_branches = data.pop("branches", None)
        raw_heads = data.pop("signal_heads", [])
        raw_public_transport = data.pop("public_transport", None)
        raw_roundabout = data.pop("roundabout", None)
        raw_calculations = data.pop("calculated_modules", [])
        raw_optimization = data.pop("signal_optimization", None)
        raw_phases = data.pop("phases", [])
        raw_scenarios = data.pop("scenarios", [])
        if not isinstance(raw_phases, list) or not isinstance(raw_scenarios, list):
            raise ValueError("Las fases y escenarios deben ser listas.")
        scenarios = []
        for raw in raw_scenarios:
            if not isinstance(raw, dict):
                raise ValueError("Escenario inválido.")
            plan = SignalOptimizationResult.from_dict(raw.get("plan"))
            if (
                plan is None
                or not isinstance(raw.get("baseline"), dict)
                or not isinstance(raw.get("settings"), dict)
                or not isinstance(raw.get("baseline_key"), str)
            ):
                raise ValueError("Faltan datos del escenario.")
            scenarios.append(Scenario(
                str(raw.get("name", plan.method)), raw["baseline_key"], dict(raw["settings"]),
                dict(raw["baseline"]), plan,
            ))
        if not isinstance(raw_calculations, list):
            raise ValueError("Los módulos calculados deben ser una lista.")
        if not isinstance(raw_groups, list):
            raise ValueError("'lane_groups' debe ser una lista.")
        if raw_branches is not None and not isinstance(raw_branches, list):
            raise ValueError("'branches' debe ser una lista.")
        if not isinstance(raw_heads, list):
            raise ValueError("'signal_heads' debe ser una lista.")

        allowed_project = set(cls.__dataclass_fields__)
        clean_project = {key: value for key, value in data.items() if key in allowed_project}
        _convert_values(
            clean_project,
            strings=(
                "name",
                "location",
                "analyst",
                "study_date",
                "optimization_method",
                "workspace",
                "notes",
            ),
            integers=("branch_count",),
            floats=(
                "cycle_length_s",
                "analysis_period_h",
                "signal_lost_time_s",
                "minimum_green_s",
                "yellow_time_s",
                "all_red_time_s",
            ),
        )
        branches = _parse_branches(raw_branches)
        allowed_group = set(LaneGroupInput.__dataclass_fields__)
        groups = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                raise ValueError("Cada grupo de carriles debe ser un objeto.")
            clean_group = {key: value for key, value in raw_group.items() if key in allowed_group}
            _convert_values(
                clean_group,
                strings=("identifier", "origin_branch", "approach", "movement", "notes"),
                integers=("lanes", "signal_phase"),
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
                    "free_flow_speed_kmh",
                    "approach_length_m",
                    "average_vehicle_spacing_m",
                ),
            )
            lanes = int(clean_group.get("lanes", 1))
            origin = clean_group.get("origin_branch") or _legacy_origin(
                str(clean_group.get("approach", "")), branches
            )
            clean_group["origin_branch"] = origin
            if "destination_branches" in clean_group:
                clean_group["destination_branches"] = tuple(
                    str(value) for value in clean_group["destination_branches"]
                )
            else:
                clean_group["destination_branches"] = _legacy_destinations(
                    origin,
                    str(clean_group.get("movement", "Directo")),
                    [branch.code for branch in branches],
                )
            if "lane_indices" in clean_group:
                clean_group["lane_indices"] = tuple(
                    int(value) for value in clean_group["lane_indices"]
                )
            else:
                clean_group["lane_indices"] = tuple(range(1, lanes + 1))
            clean_group["movements"] = tuple(
                MovementInput(**movement) for movement in clean_group.get("movements", ())
            )
            groups.append(LaneGroupInput(**clean_group))

        heads = _parse_signal_heads(raw_heads)
        public_transport = (
            TransitLineInput.empty() if raw_public_transport is None
            else TransitLineInput.from_dict(raw_public_transport)
        )
        branch_count = int(clean_project.get("branch_count", 4))
        return cls(
            branches=branches,
            lane_groups=groups,
            signal_heads=heads,
            public_transport=public_transport,
            roundabout=RoundaboutInput.from_dict(raw_roundabout),
            calculated_modules=tuple(raw_calculations),
            signal_optimization=SignalOptimizationResult.from_dict(raw_optimization),
            phases=[PhaseInput(**phase) for phase in raw_phases],
            scenarios=scenarios,
            branch_count=branch_count,
            **{key: value for key, value in clean_project.items() if key != "branch_count"},
        )


def _parse_branches(raw: list[dict[str, Any]] | None) -> list[BranchInput]:
    if raw is None:
        return default_branches()
    branches: list[BranchInput] = []
    allowed = set(BranchInput.__dataclass_fields__)
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Cada ramal debe ser un objeto.")
        clean = {key: value for key, value in item.items() if key in allowed}
        _convert_values(
            clean,
            strings=("code", "name", "position"),
            integers=("inbound_lanes", "outbound_lanes"),
        )
        if clean.get("azimuth_deg") is not None:
            clean["azimuth_deg"] = float(clean["azimuth_deg"])
        branches.append(BranchInput(**clean))
    defaults = default_branches()
    for fallback in defaults:
        if not any(item.code == fallback.code for item in branches):
            branches.append(fallback)
    return sorted(branches, key=lambda item: item.code)[:4]


def _parse_signal_heads(raw: list[dict[str, Any]]) -> list[SignalHeadInput]:
    heads: list[SignalHeadInput] = []
    allowed = set(SignalHeadInput.__dataclass_fields__)
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Cada semáforo debe ser un objeto.")
        clean = {key: value for key, value in item.items() if key in allowed}
        _convert_values(
            clean,
            strings=("identifier", "name", "branch_code", "signal_type", "control_group"),
            integers=("signal_phase",),
        )
        if "controlled_group_ids" in clean:
            clean["controlled_group_ids"] = tuple(
                str(value) for value in clean["controlled_group_ids"]
            )
        heads.append(SignalHeadInput(**clean))
    return heads


def _legacy_origin(approach: str, branches: list[BranchInput]) -> str:
    normalized = approach.strip().lower()
    for branch in branches:
        if normalized in {branch.code.lower(), branch.name.lower(), branch.position.lower()}:
            return branch.code
    return "A"


def _legacy_destinations(origin: str, movement: str, codes: list[str]) -> tuple[str, ...]:
    if origin not in codes or len(codes) < 3:
        return tuple(code for code in codes if code != origin)[:1]
    index = codes.index(origin)
    left = codes[(index + 1) % len(codes)]
    straight = codes[(index + 2) % len(codes)]
    right = codes[(index - 1) % len(codes)]
    normalized = movement.lower()
    if "izquierda" in normalized:
        return (left,)
    if "directo" in normalized and "derecha" in normalized:
        return tuple(dict.fromkeys((straight, right)))
    if "directo" in normalized:
        return (straight,)
    if "derecha" in normalized:
        return (right,)
    return tuple(code for code in codes if code != origin)


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
    average_queue_veh: float
    queue_95_veh: float
    queue_95_m: float
    free_flow_travel_time_s: float
    travel_time_s: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntersectionResult:
    lane_groups: tuple[LaneGroupResult, ...]
    total_entering_volume_veh_h: float
    weighted_control_delay_s_veh: float
    level_of_service: str
    critical_degree_of_saturation: float
    critical_lane_group: str
    maximum_queue_95_m: float
    weighted_travel_time_s: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SignalPhaseResult:
    phase_number: int
    critical_flow_ratio: float
    green_s: float
    yellow_s: float
    all_red_s: float
    start_s: float
    end_s: float


@dataclass(frozen=True, slots=True)
class SignalOptimizationResult:
    method: str
    cycle_length_s: float
    total_critical_flow_ratio: float
    phases: tuple[SignalPhaseResult, ...]
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: Any) -> SignalOptimizationResult | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("El plan semafórico debe ser un objeto.")
        try:
            return cls(
                str(raw["method"]), float(raw["cycle_length_s"]),
                float(raw["total_critical_flow_ratio"]),
                tuple(SignalPhaseResult(**phase) for phase in raw["phases"]),
                tuple(raw.get("warnings", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("El plan semafórico guardado está incompleto.") from exc
