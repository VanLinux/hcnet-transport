"""Programas de tiempo fijo y demanda por movimiento."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from math import isclose, isfinite

from hcnet.domain.models import (
    IntersectionProject,
    LaneGroupInput,
    PhaseInput,
    SignalOptimizationResult,
    SignalPhaseResult,
)


def aggregate_demand(group: LaneGroupInput) -> LaneGroupInput | None:
    if not group.movements:
        return group
    active = [m for m in group.movements if m.enabled]
    if not active:
        return None
    for m in active:
        if (
            not isfinite(m.volume)
            or m.volume < 0
            or not 0 < m.phf <= 1
            or not 0 <= m.heavy_percent <= 100
            or m.operation not in {"Protegido", "Permisivo"}
        ):
            raise ValueError(f"{group.origin_branch} → {m.destination}: demanda inválida.")
        if m.operation == "Permisivo" and not 0 < group.turn_factor < 1:
            raise ValueError(
                f"{group.origin_branch} → {m.destination}: captura un factor de giro calibrado "
                "para evaluar el movimiento permisivo."
            )
    if len({m.destination for m in active}) != len(active):
        raise ValueError(f"{group.label}: destinos duplicados.")
    observed = sum(m.volume for m in active)
    adjusted = sum(m.volume / m.phf for m in active)
    if not isfinite(adjusted):
        raise ValueError(f"{group.label}: demanda ajustada fuera de rango.")
    heavy = sum(m.volume / m.phf * m.heavy_percent for m in active) / adjusted if adjusted else 0
    return replace(
        group,
        destination_branches=tuple(m.destination for m in active),
        volume_veh_h=observed,
        peak_hour_factor=observed / adjusted if adjusted else 1,
        heavy_vehicles_percent=heavy,
    )


def _crosses(one: tuple[float, float], other: tuple[float, float]) -> bool:
    start, end = one
    a, b = other
    span = (end - start) % 360
    return (0 < (a - start) % 360 < span) != (0 < (b - start) % 360 < span)


def incompatible_groups(project: IntersectionProject) -> set[frozenset[str]]:
    """Conflictos esquemáticos de cruce y convergencia; tránsito por la derecha."""

    result = set()
    for first, second in combinations(project.lane_groups, 2):
        if first.origin_branch == second.origin_branch:
            if set(first.lane_indices) & set(second.lane_indices):
                result.add(frozenset((first.identifier, second.identifier)))
            continue
        for a in first.destination_branches:
            for b in second.destination_branches:
                origin_a, origin_b = (
                    project.branch(first.origin_branch),
                    project.branch(second.origin_branch),
                )
                exit_a, exit_b = project.branch(a), project.branch(b)
                if not (origin_a and origin_b and exit_a and exit_b):
                    continue
                a_permissive = any(
                    m.destination == a and m.enabled and m.operation == "Permisivo"
                    for m in first.movements
                )
                b_permissive = any(
                    m.destination == b and m.enabled and m.operation == "Permisivo"
                    for m in second.movements
                )
                converge = a == b
                crosses = _crosses(
                    ((origin_a.azimuth - 0.05) % 360, (exit_a.azimuth + 0.05) % 360),
                    ((origin_b.azimuth - 0.05) % 360, (exit_b.azimuth + 0.05) % 360),
                )
                # Una única corriente permisiva cede a la protegida; dos permisivas no.
                if (converge or crosses) and a_permissive == b_permissive:
                    result.add(frozenset((first.identifier, second.identifier)))
    return result


def compatible_assignment(groups: list[LaneGroupInput], conflicts: set[frozenset[str]]) -> bool:
    return not any(
        a.signal_phase == b.signal_phase and frozenset((a.identifier, b.identifier)) in conflicts
        for a, b in combinations(groups, 2)
    )


def prepare_project(project: IntersectionProject) -> IntersectionProject:
    groups = [
        group for source in project.lane_groups if (group := aggregate_demand(source)) is not None
    ]
    disabled_ids = {g.identifier for g in project.lane_groups} - {g.identifier for g in groups}
    phases = {phase.number: phase for phase in project.phases}
    heads = (
        [
            replace(
                head,
                controlled_group_ids=tuple(
                    group_id for group_id in head.controlled_group_ids
                    if group_id not in disabled_ids
                ),
            )
            for head in project.signal_heads
        ]
        if disabled_ids
        else project.signal_heads
    )
    normalized = replace(project, lane_groups=groups, signal_heads=heads)
    if not project.phases:
        return normalized
    if len(phases) != len(project.phases) or any(
        p.number < 1
        or not all(isfinite(t) for t in (p.green, p.yellow, p.all_red))
        or p.green < project.minimum_green_s
        or p.yellow <= 0
        or p.all_red < 0
        for p in project.phases
    ):
        raise ValueError("Revisa identificadores, verdes mínimos, amarillos y todo rojo.")
    if not isclose(
        sum(p.green + p.yellow + p.all_red for p in project.phases),
        project.cycle_length_s,
        abs_tol=0.011,
        rel_tol=0,
    ):
        raise ValueError("La suma de verde, amarillo y todo rojo debe coincidir con el ciclo.")
    missing = [g.label for g in groups if g.signal_phase not in phases]
    if missing:
        raise ValueError("Asigna una fase definida a: " + ", ".join(missing))
    missing_heads = [h.name for h in heads if h.signal_phase not in phases]
    if missing_heads:
        raise ValueError("Asigna una fase definida a los grupos: " + ", ".join(missing_heads))
    control_phases: dict[str, int] = {}
    for head in heads:
        if (
            head.control_group
            and control_phases.setdefault(
                head.control_group,
                head.signal_phase,
            )
            != head.signal_phase
        ):
            raise ValueError(f"{head.control_group}: sus cabezas deben compartir la fase.")
    conflicts = incompatible_groups(normalized)
    for a, b in combinations(groups, 2):
        if (
            a.signal_phase == b.signal_phase
            and frozenset((a.identifier, b.identifier)) in conflicts
        ):
            raise ValueError(f"Fase {a.signal_phase}: conflicto entre {a.label} y {b.label}.")
    return replace(
        normalized,
        lane_groups=[replace(g, effective_green_s=phases[g.signal_phase].green) for g in groups],
    )


def timeline(project: IntersectionProject) -> SignalOptimizationResult | None:
    if not project.phases:
        # Solo se infiere la secuencia si los datos previos describen íntegramente el ciclo.
        greens: dict[int, set[float]] = {}
        for group in project.lane_groups:
            greens.setdefault(group.signal_phase, set()).add(group.effective_green_s)
        if not greens or any(len(values) != 1 for values in greens.values()):
            return None
        yellow = project.yellow_time_s
        red = project.all_red_time_s
        phases = [
            PhaseInput(number, next(iter(values)), yellow, red)
            for number, values in sorted(greens.items())
        ]
        if red < 0 or not isclose(
            sum(p.green + yellow + red for p in phases), project.cycle_length_s, abs_tol=0.011
        ):
            return None
    else:
        phases = project.phases
    if not project.cycle_length_s > 0:
        return None
    rows = []
    start = 0.0
    for phase in phases:
        end = start + phase.green + phase.yellow + phase.all_red
        rows.append(
            SignalPhaseResult(
                phase.number,
                0,
                phase.green,
                phase.yellow,
                phase.all_red,
                start,
                end,
            )
        )
        start = end
    return SignalOptimizationResult("Condiciones actuales", project.cycle_length_s, 0, tuple(rows))


def signal_rows(
    project: IntersectionProject,
    program: SignalOptimizationResult,
) -> list[tuple[str, int]]:
    rows = dict.fromkeys(
        (head.control_group or head.name, head.signal_phase) for head in project.signal_heads
    )
    return list(rows) or [(f"Fase {p.phase_number}", p.phase_number) for p in program.phases]
