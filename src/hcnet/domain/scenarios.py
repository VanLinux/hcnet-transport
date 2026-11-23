"""Evaluación de alternativas sin modificar el escenario original."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from random import Random

from hcnet.domain.calculations import _allocate_greens, adjustment_factors, calculate_intersection
from hcnet.domain.models import (
    IntersectionProject,
    IntersectionResult,
    PhaseInput,
    Scenario,
    SignalOptimizationResult,
    SignalPhaseResult,
)
from hcnet.domain.signals import (
    compatible_assignment,
    incompatible_groups,
    prepare_project,
    timeline,
)

METHODS = ("Webster", "Akçelik · búsqueda directa", "Genético", "Multiobjetivo · Pareto")
OBJECTIVES = ("Demora", "Cola P95", "Saturación")
Metrics = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class SearchSettings:
    method: str = "Webster"
    objective: str = "Demora"
    min_cycle: float = 40
    max_cycle: float = 180
    fixed_cycle: bool = False
    regroup: bool = False
    locked_groups: tuple[str, ...] = ()
    population: int = 24
    generations: int = 25
    patience: int = 8
    seed: int = 42


def baseline_snapshot(project: IntersectionProject) -> dict:
    snapshot = replace(project, scenarios=[], last_evaluated=None).to_dict()["project"]
    for key in (
        "scenarios",
        "public_transport",
        "roundabout",
        "calculated_modules",
        "signal_optimization",
        "last_evaluated",
        "workspace",
        "name",
        "location",
        "analyst",
        "study_date",
        "notes",
        "optimization_method",
    ):
        del snapshot[key]
    return json.loads(json.dumps(snapshot, allow_nan=False))


def baseline_key(project: IntersectionProject) -> str:
    def canonical(value):  # noqa: ANN001, ANN202
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, list):
            return [canonical(item) for item in value]
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        return value

    serialized = json.dumps(canonical(baseline_snapshot(project)), sort_keys=True)
    return sha256(serialized.encode()).hexdigest()


def score(result: IntersectionResult) -> Metrics:
    return (
        result.weighted_control_delay_s_veh,
        result.maximum_queue_95_m,
        result.critical_degree_of_saturation,
    )


def scenario_project(scenario: Scenario) -> IntersectionProject:
    base = IntersectionProject.from_dict(scenario.baseline)
    return apply_plan(base, scenario.plan, scenario.settings.get("assignment", {}))


def evaluate_scenario(scenario: Scenario) -> IntersectionResult:
    return calculate_intersection(scenario_project(scenario))


def apply_plan(
    base: IntersectionProject,
    plan: SignalOptimizationResult,
    assignment: dict[str, int],
) -> IntersectionProject:
    base = prepare_project(base)
    phases = [PhaseInput(p.phase_number, p.green_s, p.yellow_s, p.all_red_s) for p in plan.phases]
    green = {p.number: p.green for p in phases}
    groups = [
        replace(g, signal_phase=assignment.get(g.identifier, g.signal_phase))
        for g in base.lane_groups
    ]
    phases_by_group = {g.identifier: g.signal_phase for g in groups}
    heads = []
    for head in base.signal_heads:
        mapped = {phases_by_group[i] for i in head.controlled_group_ids if i in phases_by_group}
        if len(mapped) > 1:
            raise ValueError(f"{head.name}: sus movimientos deben permanecer en una misma fase.")
        heads.append(replace(head, signal_phase=next(iter(mapped), head.signal_phase)))
    return replace(
        base,
        cycle_length_s=plan.cycle_length_s,
        phases=phases,
        signal_heads=heads,
        lane_groups=[replace(g, effective_green_s=green[g.signal_phase]) for g in groups],
    )


@dataclass(frozen=True, slots=True)
class _Candidate:
    cycle: float
    greens: tuple[float, ...]
    assignment: tuple[int, ...]


def _dominates(a: Metrics, b: Metrics) -> bool:
    return all(x <= y for x, y in zip(a, b, strict=True)) and a != b


def _front(values: dict[_Candidate, Metrics]) -> list[_Candidate]:
    front: list[_Candidate] = []
    for candidate, value in values.items():
        if any(values[p] == value or _dominates(values[p], value) for p in front):
            continue
        front = [p for p in front if not _dominates(value, values[p])]
        front.append(candidate)
    return front


def _spread(front: list[_Candidate], values: dict[_Candidate, Metrics]) -> list[_Candidate]:
    # Prioriza extremos y distancia a vecinos normalizada sobre cada objetivo.
    distances = dict.fromkeys(front, 0.0)
    for index in range(3):
        ordered = sorted(front, key=lambda c: values[c][index])
        distances[ordered[0]] = distances[ordered[-1]] = float("inf")
        width = values[ordered[-1]][index] - values[ordered[0]][index]
        if width:
            for left, center in pairwise(range(len(ordered) - 1)):
                distances[ordered[center]] += (
                    values[ordered[center + 1]][index] - values[ordered[left]][index]
                ) / width
    return sorted(front, key=distances.__getitem__, reverse=True)


def optimize(project: IntersectionProject, settings: SearchSettings) -> list[Scenario]:
    calculate_intersection(project)  # La optimización requiere entradas originales válidas.
    base = prepare_project(project)
    program = timeline(base)
    if program is None:
        raise ValueError("Define las fases y los intervalos del ciclo antes de optimizar.")
    if settings.method not in METHODS or settings.objective not in OBJECTIVES:
        raise ValueError("Selecciona un método y un objetivo disponibles.")
    if not all(isfinite(v) for v in (settings.min_cycle, settings.max_cycle)):
        raise ValueError("Los límites de ciclo deben ser finitos.")
    if not 1 <= settings.min_cycle <= settings.max_cycle <= 600:
        raise ValueError("Revisa los límites de ciclo (1–600 s).")
    if settings.regroup and settings.method not in METHODS[2:]:
        raise ValueError("La reasignación está disponible para Genético y Pareto.")
    if not (
        4 <= settings.population <= 64
        and 1 <= settings.generations <= 100
        and 1 <= settings.patience <= 100
    ):
        raise ValueError("Revisa tamaño de población, generaciones y criterio de parada.")
    phases = program.phases
    numbers = tuple(p.phase_number for p in phases)
    clearance = sum(p.yellow_s + p.all_red_s for p in phases)
    minimum = base.minimum_green_s
    if minimum <= 0 or len(phases) < 2 or not all(p.yellow_s > 0 for p in phases):
        raise ValueError("Se necesitan al menos dos fases, verde mínimo y amarillos positivos.")
    lower = max(settings.min_cycle, clearance + minimum * len(phases))
    upper = settings.max_cycle
    if settings.fixed_cycle:
        if not lower <= base.cycle_length_s <= upper:
            raise ValueError("El ciclo original queda fuera de los límites factibles.")
        lower = upper = base.cycle_length_s
    if lower > upper:
        raise ValueError("No cabe el verde mínimo y el despeje en el ciclo máximo.")
    assignment = tuple(g.signal_phase for g in base.lane_groups)
    if set(assignment) != set(numbers):
        raise ValueError("Para optimizar, cada fase necesita al menos un grupo de carriles activo.")
    conflicts = incompatible_groups(base)
    ratios = [
        g.volume_veh_h
        / g.peak_hour_factor
        / (g.base_saturation_flow_pc_h_ln * g.lanes * adjustment_factors(g).product)
        for g in base.lane_groups
    ]
    if not any(ratios):
        raise ValueError("Captura demanda mayor que cero antes de optimizar.")

    def phase_ratios(mapping: tuple[int, ...]) -> list[float]:
        return [
            max((v for v, phase in zip(ratios, mapping, strict=True) if phase == n), default=0)
            for n in numbers
        ]

    def candidate(cycle: float, weights: list[float], mapping: tuple[int, ...]) -> _Candidate:
        cycle = min(upper, max(lower, round(cycle, 3)))
        greens = tuple(_allocate_greens(weights, cycle - clearance, minimum))
        return _Candidate(cycle, greens, mapping)

    criticals = phase_ratios(assignment)
    total_critical = sum(criticals)
    if settings.method == "Webster" and total_critical >= 1:
        raise ValueError("Webster no produce ciclo teórico finito si la suma crítica es ≥ 1.")
    lost_time = base.signal_lost_time_s * len(phases)
    cycle = (1.5 * lost_time + 5) / (1 - total_critical) if total_critical < 1 else upper
    webster = candidate(cycle, criticals, assignment)
    original = candidate(base.cycle_length_s, [p.green_s for p in phases], assignment)
    cache: dict[_Candidate, Metrics] = {}

    def plan(c: _Candidate) -> SignalOptimizationResult:
        start = 0.0
        intervals = []
        criticals = phase_ratios(c.assignment)
        for old, green, y in zip(phases, c.greens, criticals, strict=True):
            end = start + green + old.yellow_s + old.all_red_s
            intervals.append(
                SignalPhaseResult(
                    old.phase_number,
                    y,
                    green,
                    old.yellow_s,
                    old.all_red_s,
                    start,
                    end,
                )
            )
            start = end
        return SignalOptimizationResult(settings.method, c.cycle, sum(criticals), tuple(intervals))

    def mapping(c: _Candidate) -> dict[str, int]:
        return {
            g.identifier: phase for g, phase in zip(base.lane_groups, c.assignment, strict=True)
        }

    def assess(c: _Candidate) -> bool:
        if c in cache:
            return True
        if set(c.assignment) != set(numbers):
            return False
        groups = [
            replace(g, signal_phase=p) for g, p in zip(base.lane_groups, c.assignment, strict=True)
        ]
        if not compatible_assignment(groups, conflicts):
            return False
        try:
            alternative = apply_plan(base, plan(c), mapping(c))
            result = calculate_intersection(
                alternative,
                delay_model="Akçelik" if settings.method == METHODS[1] else "HCNet",
            )
        except ValueError:
            return False
        cache[c] = score(result)
        return True

    evaluated = [c for c in (webster, original) if assess(c)]
    if not evaluated or (settings.method == "Webster" and webster not in evaluated):
        raise ValueError("No se encontró un programa factible. Revisa el plan y los conflictos.")
    goal = OBJECTIVES.index(settings.objective)
    stop_reason = "Cálculo analítico"
    iterations = 0
    if settings.method == "Webster":
        selected = [webster]
    elif settings.method == METHODS[1]:
        best = min(evaluated, key=lambda c: cache[c][goal])
        step = 5.0
        for _ in range(settings.generations):
            iterations += 1
            neighbors = [
                candidate(best.cycle + sign * step, list(best.greens), best.assignment)
                for sign in (-1, 1)
            ]
            for i, green in enumerate(best.greens):
                for j, other in enumerate(best.greens):
                    if i == j or other - step < minimum:
                        continue
                    weights = list(best.greens)
                    weights[i], weights[j] = green + step, other - step
                    neighbors.append(candidate(best.cycle, weights, best.assignment))
            improvement = min(
                (n for n in [best, *neighbors] if assess(n)),
                key=lambda c: cache[c][goal],
            )
            if cache[improvement][goal] < cache[best][goal] - 1e-8:
                best = improvement
            else:
                step /= 2
                if step < 0.1:
                    break
        stop_reason = "Paso de búsqueda menor de 0.1 s" if step < 0.1 else "Límite de iteraciones"
        selected = [best]
    else:
        rng = Random(settings.seed)
        pareto = settings.method == METHODS[3]
        unlocked = [
            i for i, g in enumerate(base.lane_groups) if g.identifier not in settings.locked_groups
        ]
        pool = list(dict.fromkeys(evaluated))
        for _ in range(settings.population * 2):
            random_plan = candidate(
                rng.uniform(lower, upper),
                [rng.random() for _ in numbers],
                assignment,
            )
            if assess(random_plan):
                pool.append(random_plan)
            if len(pool) >= settings.population:
                break
        best_signature = None
        stale = 0
        for _ in range(settings.generations):
            iterations += 1
            if pareto:
                archive = _front({c: cache[c] for c in pool})
                ranked = _spread(archive, cache)
                signature = frozenset(cache[c] for c in archive)
                parents = ranked[: settings.population]
            else:
                parents = sorted(set(pool), key=lambda c: cache[c][goal])[
                    : settings.population // 2
                ]
                signature = cache[parents[0]][goal]
            stale = stale + 1 if signature == best_signature else 0
            best_signature = signature
            if stale >= settings.patience:
                break
            children = []
            for _ in range(settings.population):
                a, b = rng.choice(parents), rng.choice(parents)
                weights = [
                    max(0.01, (x + y) / 2 * rng.uniform(0.8, 1.2))
                    for x, y in zip(a.greens, b.greens, strict=True)
                ]
                genes = list(a.assignment)
                if settings.regroup and unlocked and rng.random() < 0.6:
                    i = rng.choice(unlocked)
                    if len(unlocked) > 1 and rng.random() < 0.5:
                        j = rng.choice([j for j in unlocked if i != j])
                        genes[i], genes[j] = genes[j], genes[i]
                    else:
                        genes[i] = rng.choice(numbers)
                child = candidate((a.cycle + b.cycle) / 2 + rng.gauss(0, 6), weights, tuple(genes))
                if assess(child):
                    children.append(child)
            pool = list(dict.fromkeys([*parents, *children]))
        stop_reason = (
            "Sin cambios durante el número de generaciones indicado"
            if stale >= settings.patience
            else "Límite de generaciones"
        )
        selected = (
            _spread(_front(cache), cache)[:12]
            if pareto
            else [min(cache, key=lambda c: cache[c][goal])]
        )

    snapshot = baseline_snapshot(project)
    key = baseline_key(project)
    return [
        Scenario(
            settings.method,
            key,
            {
                **asdict(settings),
                "locked_groups": list(settings.locked_groups),
                "assignment": mapping(c),
                "iterations": iterations,
                "evaluations": len(cache),
                "termination": stop_reason,
                "search_delay": cache[c][0],
            },
            snapshot,
            plan(c),
        )
        for c in selected
    ]
