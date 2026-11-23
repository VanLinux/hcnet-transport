"""Opciones reproducibles y detección del motor de línea de comandos."""

import os
from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from pathlib import Path
from shutil import which

from hcnet.domain.models import IntersectionProject
from hcnet.domain.scenarios import baseline_key, scenario_project

POLLUTANTS = {"CO2": "kg", "CO": "g", "NOx": "g", "PMx": "g", "fuel": "g", "electricity": "Wh"}


@dataclass(frozen=True, slots=True)
class FleetType:
    label: str
    category: str
    percent: float
    emission_class: str
    vclass: str


DEFAULT_FLEET = (
    FleetType("Ligero gasolina", "ligero", 100, "HBEFA3/PC_G_EU4", "passenger"),
    FleetType("Ligero diésel", "ligero", 0, "HBEFA3/PC_D_EU4", "passenger"),
    FleetType("Ligero híbrido", "ligero", 0, "", "passenger"),
    FleetType("Ligero eléctrico", "ligero", 0, "Energy/unknown", "passenger"),
    FleetType("Pesado diésel", "pesado", 100, "HBEFA3/HDV_D_EU4", "truck"),
    FleetType("Pesado gas natural", "pesado", 0, "", "truck"),
    FleetType("Pesado eléctrico", "pesado", 0, "Energy/unknown", "truck"),
    FleetType("Autobús", "pesado", 0, "HBEFA3/Bus", "bus"),
    FleetType("Pesado otra motorización", "pesado", 0, "", "truck"),
)


@dataclass(frozen=True, slots=True)
class SimulationOptions:
    duration: int = 900
    warmup: int = 180
    runs: int = 3
    seed: int | None = None
    tau: float = 1.0
    min_gap: float = 2.5
    accel: float = 2.6
    decel: float = 4.5
    strategic: float = 1.0

    def validate(self) -> None:
        if not (60 <= self.duration <= 7200 and 0 <= self.warmup <= 1800):
            raise ValueError("Duración: 60–7200 s de medición; calentamiento: 0–1800 s.")
        if not 1 <= self.runs <= 12:
            raise ValueError("Selecciona entre 1 y 12 corridas.")
        if self.seed is not None and not 0 <= self.seed <= 2_147_483_647 - self.runs:
            raise ValueError("Semilla fuera de rango.")
        values = (self.tau, self.min_gap, self.accel, self.decel, self.strategic)
        if not all(isfinite(v) for v in values) or not (
            self.tau >= 1
            and self.min_gap >= 0
            and self.accel > 0
            and self.decel > 0
            and self.strategic >= 0
        ):
            raise ValueError("Revisa los parámetros de seguimiento y cambio de carril.")


def locate_sumo(executable: str = "") -> tuple[Path, Path] | None:
    home = os.environ.get("SUMO_HOME")
    package = find_spec("sumo") if not executable else None
    packaged = (
        str(Path(package.origin).with_name("bin") / "sumo")
        if package is not None and package.origin
        else ""
    )
    candidates = (
        [executable]
        if executable
        else [
            str(Path(home) / "bin" / "sumo") if home else "",
            packaged,
            "sumo",
        ]
    )
    for candidate in candidates:
        found = which(os.path.expanduser(candidate)) if candidate else None
        if found and Path(found).name == "sumo":
            sumo = Path(found).absolute()
            companion = which(str(sumo.with_name("netconvert")))
            if companion:
                return sumo, Path(companion).absolute()
    return None


def scenario_choices(
    project: IntersectionProject,
    *,
    include_archived: bool = False,
) -> list[tuple[str, str, IntersectionProject]]:
    choices = [("Condiciones actuales", baseline_key(project), project)]
    for index, scenario in enumerate(project.scenarios, 1):
        plan = scenario_project(scenario)
        choices.append((f"Escenario {index} · {scenario.name}", baseline_key(plan), plan))
    if include_archived:
        keys = {key for _, key, _ in choices}
        for key, record in project.studies.items():
            if key not in keys and isinstance(record, dict) and "snapshot" in record:
                label = record.get("scenario_label", "Escenario")
                choices.append(
                    (
                        f"Histórico · {label} · {key[:6]}",
                        key,
                        IntersectionProject.from_dict(record["snapshot"]),
                    )
                )
    return choices


def validate_fleet(fleet: tuple[FleetType, ...], *, simulated: bool) -> None:
    for category in ("ligero", "pesado"):
        selected = [item for item in fleet if item.category == category]
        if (
            any(not 0 <= item.percent <= 100 for item in selected)
            or abs(sum(item.percent for item in selected) - 100) > 0.001
        ):
            raise ValueError(f"La composición de vehículos del grupo {category} debe sumar 100 %.")
    if simulated and any(item.percent and not item.emission_class.strip() for item in fleet):
        raise ValueError("Captura una clase SUMO compatible para cada motorización utilizada.")
