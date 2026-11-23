"""Ajustes empíricos sobre el flujo de saturación por carril."""

from dataclasses import dataclass
from math import isfinite, prod
from statistics import mean

EFFECTS = ("Obstrucción lateral", "Uso especial", "Fricción residual")
STANDARD_SYMBOLS = {"fw", "fhv", "fg", "fp", "fbb", "flu", "fa", "fturn", "kcal"}


@dataclass(frozen=True, slots=True)
class EmpiricalFactor:
    name: str
    symbol: str
    value: float
    description: str
    source: str
    effect: str
    lane: int | None = None


@dataclass(frozen=True, slots=True)
class FieldCalibration:
    observed: float
    reference: float
    source: str

    @property
    def coefficient(self) -> float:
        return self.observed / self.reference


def empirical_multiplier(
    lanes: tuple[int, ...],
    factors: tuple[EmpiricalFactor, ...],
    field: FieldCalibration | None,
) -> float:
    """Promedia los productos individuales para una base uniforme por carril."""
    if not factors and field is None:
        return 1.0
    if not lanes:
        raise ValueError("Selecciona los carriles antes de aplicar una calibración.")
    by_lane: dict[int, list[float]] = {lane: [] for lane in lanes}
    applied: set[tuple[int, str]] = set()
    for factor in factors:
        symbol = "".join(c for c in factor.symbol.casefold() if c.isalnum())
        if (
            not factor.name.strip()
            or not symbol
            or symbol in STANDARD_SYMBOLS
            or not factor.description.strip()
            or not factor.source.strip()
            or factor.effect not in EFFECTS
        ):
            raise ValueError(
                "Identifica y justifica un efecto residual y usa un símbolo distinto de los HCM."
            )
        if not (0.1 <= factor.value <= 0.9 or factor.value == 1):
            raise ValueError("El factor reductor debe estar entre 0.10 y 0.90 o ser 1.00.")
        targets = lanes if factor.lane is None else (factor.lane,)
        for lane in targets:
            keys = {(lane, factor.effect.casefold()), (lane, symbol)}
            if lane not in by_lane or applied & keys:
                raise ValueError("Factor repetido o asignado a un carril ajeno al grupo.")
            applied.update(keys)
            by_lane[lane].append(factor.value)
    multiplier = mean(prod(values) for values in by_lane.values())
    if field is not None:
        if (
            not all(isfinite(v) and v > 0 for v in (field.observed, field.reference))
            or not field.source.strip()
            or not isfinite(field.coefficient)
        ):
            raise ValueError("Registra flujos positivos y la fuente de la calibración de campo.")
        multiplier *= field.coefficient
    return multiplier
