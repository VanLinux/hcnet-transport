from dataclasses import replace
from itertools import permutations

import pytest

from hcnet.domain.calculations import CalculationError, calculate_intersection
from hcnet.domain.models import IntersectionProject, LaneGroupInput, MovementInput, PhaseInput
from hcnet.domain.reporting import general_latex
from hcnet.domain.sample import demonstration_project
from hcnet.domain.scenarios import (
    METHODS,
    SearchSettings,
    baseline_key,
    evaluate_scenario,
    optimize,
    score,
)
from hcnet.domain.signals import aggregate_demand, timeline
from hcnet.io.project import load_project, save_project


def test_aggregates_only_enabled_movements_with_their_own_peak_factors():
    group = LaneGroupInput(movements=(
        MovementInput("C", 150, 0.75, 5),
        MovementInput("D", 160, 0.80, 15),
        MovementInput("B", 900, enabled=False),
    ))
    combined = aggregate_demand(group)
    assert combined.destination_branches == ("C", "D")
    assert combined.volume_veh_h == 310
    assert combined.volume_veh_h / combined.peak_hour_factor == pytest.approx(400)
    assert combined.heavy_vehicles_percent == pytest.approx(10)
    assert len(group.movements) == 3


def test_phase_closure_crossing_and_calibrated_permissive_movement():
    project = IntersectionProject(cycle_length_s=60, phases=[PhaseInput(1, 56, 3, 1)])
    project.lane_groups = [
        LaneGroupInput(origin_branch="A", movements=(MovementInput("C", 320),)),
        LaneGroupInput(origin_branch="B", movements=(MovementInput("D", 260),)),
    ]
    with pytest.raises(CalculationError, match="conflicto"):
        calculate_intersection(project)
    group = project.lane_groups[1]
    group.movements = (replace(group.movements[0], operation="Permisivo"),)
    with pytest.raises(CalculationError, match="calibrado"):
        calculate_intersection(project)
    group.turn_factor = 0.8
    assert calculate_intersection(project).total_entering_volume_veh_h == 580
    assert timeline(project).phases[-1].end_s == pytest.approx(60)
    project.phases[0] = replace(project.phases[0], green=55)
    with pytest.raises(CalculationError, match="coincidir con el ciclo"):
        calculate_intersection(project)


@pytest.mark.parametrize("method", METHODS)
def test_methods_respect_cycle_green_and_preserve_original(method):
    project = demonstration_project()
    before = project.to_dict()
    settings = SearchSettings(method=method, min_cycle=80, max_cycle=100, fixed_cycle=True,
                              population=8, generations=5)
    original = calculate_intersection(project)
    alternatives = optimize(project, settings)
    assert alternatives
    for scenario in alternatives:
        assert scenario.plan.cycle_length_s == 100
        assert scenario.baseline_key == baseline_key(project)
        assert scenario.plan.phases[-1].end_s == pytest.approx(100)
        for new, current in zip(scenario.plan.phases, project.phases, strict=True):
            assert new.green_s >= project.minimum_green_s - 1e-9
            assert new.yellow_s == current.yellow
            assert new.all_red_s == current.all_red
        assert evaluate_scenario(scenario).total_entering_volume_veh_h == (
            original.total_entering_volume_veh_h
        )
    assert project.to_dict() == before
    assert calculate_intersection(project) == original
    with pytest.raises(ValueError, match="fuera de los límites"):
        optimize(project, replace(settings, max_cycle=90))


def test_reassignment_lock_seed_roundtrip_and_pareto(tmp_path):
    project = IntersectionProject(branch_count=2, cycle_length_s=80,
                                  phases=[PhaseInput(1, 36, 3, 1), PhaseInput(2, 36, 3, 1)])
    for index, demand in enumerate((680, 90, 680), 1):
        project.lane_groups.append(LaneGroupInput(
            identifier=str(index), origin_branch="A", destination_branches=("B",),
            lane_indices=(index,), signal_phase=1 if index < 3 else 2,
            movements=(MovementInput("B", demand),),
        ))
    settings = SearchSettings(method=METHODS[2], regroup=True, locked_groups=("1",), max_cycle=120,
                              seed=42, population=12, generations=15)
    scenarios = optimize(project, settings)
    assert scenarios == optimize(project, settings)
    assert scenarios[0].settings["assignment"] == {"1": 1, "2": 2, "3": 1}
    fixed = optimize(project, replace(settings, regroup=False))[0]
    assert score(evaluate_scenario(scenarios[0]))[0] < score(evaluate_scenario(fixed))[0]
    front = optimize(project, replace(settings, method=METHODS[3]))
    assert len(front) > 1
    for a, b in permutations([score(evaluate_scenario(s)) for s in front], 2):
        assert any(x > y for x, y in zip(a, b, strict=True))
    project.scenarios = [*scenarios, *front]
    project.calculated_modules = ("intersection",)
    restored = load_project(save_project(project, tmp_path / "escenarios.hcnet"))
    assert restored == project
    assert baseline_key(restored) == baseline_key(project) == scenarios[0].baseline_key
    baseline_result = evaluate_scenario(restored.scenarios[0])
    report = general_latex(restored)
    assert "letterpaper" in report
    assert "Optimización y comparación" in report
    assert "Trayectorias activas por fase" in report
    assert r"\color{yellow!80!orange}" in report
    assert r"\section{Transporte público}" not in report
    restored.lane_groups[0].movements = (MovementInput("B", 650),)
    assert baseline_key(restored) != scenarios[0].baseline_key
    assert evaluate_scenario(restored.scenarios[0]) == baseline_result
