import sys
from dataclasses import replace
from pathlib import Path
from threading import Event, Timer

import pytest

from hcnet.domain.calculations import (
    CalculationError,
    adjustment_factors,
    calculate_intersection,
)
from hcnet.domain.calibration import EmpiricalFactor, FieldCalibration
from hcnet.domain.emissions import emission_difference, estimate_idle
from hcnet.domain.reporting import latex_report
from hcnet.domain.sample import demonstration_project
from hcnet.domain.scenarios import SearchSettings, baseline_key, optimize, scenario_project
from hcnet.io.project import load_project, save_project
from hcnet.simulation.options import DEFAULT_FLEET, SimulationOptions, locate_sumo
from hcnet.simulation.results import queue_stats, stats, unpack
from hcnet.simulation.runner import SimulationCancelled, _command, simulate


def test_calibration_aggregates_lane_products_and_keeps_original(tmp_path):
    project = demonstration_project()
    group = next(g for g in project.lane_groups if len(g.lane_indices) == 2)
    base = adjustment_factors(group).product
    lane_a, lane_b = group.lane_indices
    first = EmpiricalFactor(
        "Obstáculo", "fOL", 0.8, "Obstáculo fijo", "Inspección", "Obstrucción lateral", lane_a
    )
    second = EmpiricalFactor(
        "Uso", "fUE", 0.9, "Acceso especial", "Inspección", "Uso especial", lane_a
    )
    third = replace(second, value=0.5, lane=lane_b)
    group.empirical_factors = (first, second, third)
    assert adjustment_factors(group).product == pytest.approx(base * (0.8 * 0.9 + 0.5) / 2)
    group.field_calibration = FieldCalibration(1300, 1000, "Aforo")
    assert adjustment_factors(group).product == pytest.approx(base * 0.61 * 1.3)
    doc = save_project(project, tmp_path / "calibrado.hcnet")
    assert load_project(doc).lane_groups == project.lane_groups
    assert "Coeficiente 1.3000" in latex_report(project, calculate_intersection(project))
    group.empirical_factors += (replace(first, symbol="fOtro"),)
    with pytest.raises(CalculationError, match="Factor repetido"):
        calculate_intersection(project)


def test_idle_requires_documented_wait_and_rates():
    project = demonstration_project()
    expected_vehicles = sum(g.volume_veh_h for g in project.lane_groups)
    assert expected_vehicles > 0
    rates = {"Ligero gasolina": {"CO2": 900}, "Pesado diésel": {"CO2": 1800}}
    with pytest.raises(ValueError, match="fuente"):
        estimate_idle(project, DEFAULT_FLEET, 900, 25, rates, "")
    value = estimate_idle(project, DEFAULT_FLEET, 900, 25, rates, "Medición de ralentí")
    light = value["demand"]["ligero"]
    heavy = value["demand"]["pesado"]
    assert value["totals"] == {"CO2": pytest.approx((light * 0.9 + heavy * 1.8) * 25 / 3600)}
    alternative = estimate_idle(project, DEFAULT_FLEET, 900, 20, rates, "Medición de ralentí")
    assert emission_difference(value, alternative, "idle", "CO2")[-1] == pytest.approx(-20.0)


def test_sumo_is_optional_and_statistics_are_defined():
    assert locate_sumo("/inexistente/sumo") is None
    assert stats([3.0]) == {"n": 1, "mean": 3.0, "sd": None, "ci95": None}
    assert stats([2.0, 4.0])["ci95"] == pytest.approx([3 - 12.706, 3 + 12.706])
    assert queue_stats(list(range(1, 21))) == {"mean": 10.5, "max": 20, "p95": 19}


def test_real_sumo_original_optimized_round_trip(tmp_path):
    binaries = locate_sumo()
    if not binaries:
        pytest.skip("requiere sumo y netconvert en PATH o SUMO_HOME")
    project = demonstration_project()
    options = SimulationOptions(duration=250, warmup=40, runs=2, seed=204)
    cancel = Event()
    original = simulate(project, options, DEFAULT_FLEET, binaries, cancel)
    repeated = simulate(project, options, DEFAULT_FLEET, binaries, cancel)
    assert original["metrics"] == repeated["metrics"]
    expected = sum(r["rate"] for r in original["demand"]) * 290 / 3600
    assert {r["planned"] for r in original["runs"]} == {round(expected)}
    run, sample_again = original["runs"][0], repeated["runs"][0]
    assert run["seed"] == 204 and original["runs"][1]["seed"] == 205
    assert 0 < run["completed"] <= run["cohort"] <= run["departed"] <= run["planned"]
    assert run["emissions"]["CO2"] > 0
    assert run["queue_series"] == sample_again["queue_series"]
    frames = unpack(run["queue_series"])
    signals = unpack(run["signal_series"])
    assert len(frames) == len(signals) == 250
    assert len({state for _, state in signals}) > 2
    assert (
        0
        <= max(max(frame) for frame in frames)
        == pytest.approx(run["metrics"]["Cola máxima · extensión máxima instantánea, m"])
    )
    scenario = optimize(project, SearchSettings())[0]
    project.scenarios.append(scenario)
    optimized = simulate(scenario_project(scenario), options, DEFAULT_FLEET, binaries, cancel)
    assert emission_difference(original, optimized, "simulation", "CO2") is not None
    project.studies[baseline_key(project)] = {"simulation": original}
    project.studies[optimized["scenario_key"]] = {"simulation": optimized}
    path = save_project(project, tmp_path / "estudio.hcnet")
    restored = load_project(path)
    assert restored.studies == project.studies
    report = latex_report(restored, calculate_intersection(restored))
    assert "Resultados de microsimulación SUMO" in report
    assert "Comparación ambiental" in report


def test_cancelled_study_stops_before_invoking_engine():
    cancel = Event()
    cancel.set()
    with pytest.raises(SimulationCancelled):
        simulate(
            demonstration_project(),
            SimulationOptions(),
            DEFAULT_FLEET,
            (Path("unused/sumo"), Path("unused/netconvert")),
            cancel,
        )



def test_cancellation_terminates_a_running_process(tmp_path):
    cancel = Event()
    timer = Timer(0.2, cancel.set)
    timer.start()
    try:
        with pytest.raises(SimulationCancelled):
            _command([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, cancel)
    finally:
        timer.cancel()
