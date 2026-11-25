from dataclasses import replace
from math import exp
from threading import Event

import pytest

from hcnet.domain.models import IntersectionProject
from hcnet.domain.roundabout_engineering import (
    Movement,
    Site,
    blank_arms,
    capacity,
    control,
    design_geometry,
    evaluate,
    flows,
    kimber,
    network,
    safety,
)
from hcnet.domain.roundabout_examples import example
from hcnet.domain.roundabout_planning import (
    accepted_gap,
    calibrate,
    compare_designs,
    design,
    import_intersection,
    intersection_metrics,
    same_demand,
)
from hcnet.domain.roundabout_reporting import geometry_record
from hcnet.domain.scenarios import baseline_key
from hcnet.io.project import export_general_tex, load_project, save_project
from hcnet.simulation.options import SimulationOptions, locate_sumo
from hcnet.simulation.results import unpack
from hcnet.simulation.roundabout import simulate_roundabouts
from hcnet.simulation.runner import SimulationCancelled


def test_movement_tracing_exit_conflicts_and_return():
    site = Site(
        arms=blank_arms(), movements=(Movement("A", "C", 90, 10, phf=0.9), Movement("C", "C", 100))
    )
    values = flows(site, network(site))
    assert values["A"]["entry"] == [100]
    assert values["C"]["exit"] == 200
    assert values["D"]["conflict"] == [210]
    assert values["C"]["conflict"] == [0]
    assert sum(row["exit"] for row in values.values()) == sum(
        sum(row["entry"]) for row in values.values()
    )
    clockwise = replace(site, direction="Horario", driving="Izquierda")
    assert flows(clockwise, network(clockwise))["B"]["conflict"] == [210]
    with pytest.raises(ValueError, match="lado"):
        network(replace(clockwise, driving="Derecha"))


def test_independent_lanes_and_movements():
    site, _ = example(1)
    result = evaluate(site)
    assert len(result["lanes"]) == 8
    arm = next(a for a in site.arms if a.code == "A")
    assert capacity(site, arm, 1, 450, "HCM") == pytest.approx(1420 * exp(-0.00085 * 450))
    assert capacity(site, arm, 2, 450, "HCM") == pytest.approx(1350 * exp(-0.00092 * 450))
    arm = replace(arm, outbound=0)
    with pytest.raises(ValueError, match="conexión"):
        network(replace(site, arms=(arm, *site.arms[1:])))
    with pytest.raises(ValueError, match="composición"):
        network(replace(site, movements=(Movement("A", "B", 25, heavy=70, bus=40),)))
    unsupported = evaluate(replace(site, lanes=3, kind="Multicarril"))
    assert all(row["capacity"] is None for row in unsupported["lanes"])


def test_capacity_domains_and_hybrid_results():
    site, _ = example(4)
    arm = site.arms[0]
    assert capacity(site, arm, 1, 0, "Brechas") == pytest.approx(3600 / 2.7)
    assert capacity(site, arm, 1, 1000, "Lineal") == 770
    with pytest.raises(ValueError, match="dominio"):
        capacity(site, arm, 1, 2000, "Lineal")
    assert kimber(arm, 40, 0) == pytest.approx(1309.0973, rel=0.01)
    with pytest.raises(ValueError, match="dominio"):
        kimber(replace(arm, flare=0), 40, 0)
    result = evaluate(replace(site, method="Lineal", hybrid=False))
    assert result["overall"]["delay"] is None
    assert result["overall"]["capacity"] is not None
    assert evaluate(replace(site, method="Lineal", hybrid=True))["overall"]["delay"] > 0


def test_control_los_queue_and_delay_units():
    result = control(601, 600, 0.25)
    assert result["los"] == "F"
    assert result["q95"] > 0 and result["qmean"] is None
    assert control(589, 600, 0.25, initial=12)["q95"] is None
    assert control(100, 0, 0.25)["delay"] is None
    site, _ = example(0)
    metrics = evaluate(site)["overall"]
    assert metrics["delay_total"] == pytest.approx(
        metrics["demand"] * metrics["delay"] * site.period / 3600
    )


def test_geometry_state_locks_and_no_feasible_conversion():
    site, _ = example(3)
    proposed, geo = design(site)
    assert geo["diameter"] == 42
    assert geo["diameter"] == pytest.approx(geo["island"] + 2 * geo["width"])
    assert geo["statuses"] == {"diameter": "Fijado", "island": "Calculado", "width": "Propuesto"}
    assert len(safety(proposed, geo)["checks"]) == 4
    with pytest.raises(ValueError, match="incompatible"):
        design_geometry(replace(proposed, island=41))
    badly_fit, _ = example(8)
    assert compare_designs(badly_fit, conversion=True)["recommendation"] is None


def test_calibration_independent_validation_and_gap_pairs():
    rows = [(x, 1520 - 0.8 * x, "ajuste") for x in (200, 400, 650, 900)]
    rows.append((1000, 730, "validación"))
    result = calibrate(rows, "Lineal")
    assert result["a"] == pytest.approx(1520)
    assert result["b"] == pytest.approx(0.8)
    assert result["validation"]["mae"] == pytest.approx(10)
    with pytest.raises(ValueError, match="tres"):
        calibrate(rows[:2], "Lineal")
    with pytest.raises(ValueError, match="decreciente"):
        calibrate([(x, x * 2, "ajuste") for x in (1, 2, 3)], "Exponencial")
    gaps = accepted_gap([(3.1, 4.1), (3.9, 5.2), (4.4, 5.5), (3.5, 4.5), (4.6, 5.8), (3.6, 4.7)])
    assert 4.1 < gaps["median"] < 5.2
    assert gaps["n"] == 6


def test_import_conversion_and_roundtrip(tmp_path):
    site, state = example(6)
    original = IntersectionProject.from_dict(state["original"])
    before = original.to_dict()
    imported = import_intersection(original)
    assert same_demand(site, imported)
    proposal = compare_designs(site, conversion=True)
    assert proposal["recommendation"]
    for row in proposal["alternatives"]:
        assert same_demand(site, Site.from_dict(row["site"]))
    assert intersection_metrics(original)["demand"] == pytest.approx(
        sum(m.volume / m.phf for m in imported.movements)
    )
    assert original.to_dict() == before
    geometry, report = design(replace(site, diameter=40, width=5))
    record = geometry_record(geometry, report, safety(geometry, report))
    state["records"] = {"geometry": record}
    project = replace(original, roundabout_engineering=state, calculated_modules=())
    assert baseline_key(original) == baseline_key(project)
    path = save_project(project, tmp_path / "rotonda.hcnet")
    restored = load_project(path)
    assert restored.roundabout_engineering["records"]["geometry"]["geometry"]["diameter"] == 40
    document = export_general_tex(restored, tmp_path / "informe.tex").read_text()
    assert "Predimensionamiento" in document and r"\begin{picture}" in document


def test_sumo_roundabout_connectivity_matched_counts_and_cancel(tmp_path):
    engine = locate_sumo()
    if not engine:
        pytest.skip("SUMO externo ausente")
    site, state = example(6)
    original = IntersectionProject.from_dict(state["original"])
    site, _ = design(site)
    options = SimulationOptions(duration=120, warmup=30, runs=2, seed=14)
    directory = tmp_path / "export"
    directory.mkdir()
    record = simulate_roundabouts(
        [("Propuesta", site)],
        options,
        engine,
        Event(),
        original=original,
        archive=directory,
    )
    a, b = record["scenarios"]
    assert record["seeds"] == [14, 15]
    assert [r["planned"] for r in a["runs"]] == [r["planned"] for r in b["runs"]]
    for run in b["runs"]:
        assert run["planned"] >= run["departed"] >= run["arrived"]
        assert len(unpack(run["queue_series"])) == 120
        assert "HC" in run["emissions"]
        assert len(run["duration_positive_s"]) == len(b["lanes"])
    config = directory / "escenario-2" / "network.net.xml"
    assert config.is_file() and "<roundabout" in config.read_text()
    for seed in record["seeds"]:
        paths = [directory / f"escenario-{case}" / f"{seed}-demand.rou.xml" for case in (1, 2)]
        from xml.etree import ElementTree as ET

        common = [
            [
                (v.attrib["id"], v.attrib["depart"], v.attrib["type"])
                for v in ET.parse(p).findall("vehicle")
            ]
            for p in paths
        ]
        assert common[0] == common[1]
    clockwise = simulate_roundabouts(
        [("Izquierda", replace(site, direction="Horario", driving="Izquierda"))],
        replace(options, runs=1),
        engine,
        Event(),
    )
    assert clockwise["scenarios"][0]["runs"][0]["completed"] > 0
    canceled = Event()
    canceled.set()
    with pytest.raises(SimulationCancelled):
        simulate_roundabouts([("Cancelada", site)], options, engine, canceled)
