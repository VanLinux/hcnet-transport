import json
from dataclasses import replace
from threading import Event

import pytest

from hcnet.domain.models import IntersectionProject
from hcnet.domain.scenarios import baseline_key
from hcnet.domain.transit_catalog import catalog
from hcnet.domain.transit_engineering import (
    Door,
    Service,
    Station,
    dwell,
    evaluate,
    service_quality,
    spacing,
)
from hcnet.domain.transit_planning import economics, fit, optimize, recommend, road_time, specific
from hcnet.io.project import load_project, save_project
from hcnet.simulation.options import locate_sumo
from hcnet.simulation.runner import SimulationCancelled, _command
from hcnet.simulation.transit import simulate_corridor


def example_line(**settings):
    args = dict(
        name="Línea",
        technology="road",
        length_km=10,
        speed_kmh=30,
        headway_min=5,
        demand=500,
        nominal=75,
        load_factor=0.8,
        min_headway_s=90,
        doors=(Door(),),
        intermediate=5,
        board=4,
        alight=2,
        terminal_min=5,
    )
    return Service(**(args | settings))


def test_doors_and_stop_spacing():
    doors = (Door(role="Ascenso", channels=2), Door(role="Descenso"))
    simultaneous = dwell(10, 5, doors, "Simultáneo")
    assert simultaneous["seconds"] == pytest.approx(16.5)
    assert dwell(10, 5, doors, "Secuencial")["seconds"] == pytest.approx(25.5)
    assert dwell(10, 5, (Door(interference=1.25),), "Compartida")["seconds"] == pytest.approx(46.5)
    with pytest.raises(ValueError, match="separados"):
        dwell(10, 5, (Door(),), "Simultáneo")
    assert spacing(5, 11, 1.25, 3, 15)["spacing_m"] == 500
    assert spacing(5, 11, 1.25, 3, 15)["access_min"] == pytest.approx(5 / 3)


def test_inverse_dimensioning_and_quality():
    assert specific("Tamaño mínimo de unidad", {"d": 800, "f": 15, "l": 0.8}) == {
        "Capacidad mínima (pax/unidad)": 67
    }
    assert specific("Frecuencia con flota disponible", {"n": 8, "t": 24}) == {
        "Frecuencia (unid/h)": 20,
        "Intervalo (min)": 3,
    }
    assert service_quality(5, (4, 6), True, False)["wait"] == pytest.approx(2.6)
    assert service_quality(5, (), True, False)["wait"] is None
    assert service_quality(5, (), True, True)["wait"] == 2.5


def test_station_profile_conserves_load_and_tracks_constraint():
    stations = (
        Station("A", 0, 480, 0, dwell_s=10),
        Station("B", 4, 240, 60, dwell_s=150),
        Station("C", 10, 0, 660, dwell_s=10),
    )
    line = example_line(
        stations=stations,
        passenger_units="Por hora",
        terminal_positions=1,
        reverse=(Station("C", 0, dwell_s=10), Station("A", 10, dwell_s=10)),
    )
    result = evaluate(line)
    assert [r["load"] for r in result["profiles"][0]] == [40, 55, 0]
    assert result["critical_station"] == "Bahías de regulación"
    assert result["station_limit"] == 12
    assert result["critical_section"] == "B"
    assert result["demand"] == 660
    assert result["profiles"][0][-1]["accumulated_board"] == 60
    broken = replace(stations[-1], alight=700)
    with pytest.raises(ValueError, match="exceden"):
        evaluate(replace(line, stations=(*stations[:-1], broken)))


def test_cable_uses_cabin_spacing_and_boarding_limit():
    cable = example_line(
        technology="cable",
        length_km=5,
        speed_kmh=18,
        nominal=10,
        cable_spacing_m=60,
        cable_min_spacing_m=50,
        cable_circuit_km=10.2,
        cable_station_s=10,
        cable_station_limit=2500,
        doors=(),
        intermediate=2,
        min_headway_s=10,
        terminal_min=0,
    )
    result = evaluate(cable)
    assert result["headway"] == pytest.approx(0.2)
    assert result["frequency"] == 300
    assert result["max_frequency"] == 250
    assert result["achievable"] == 2000
    with pytest.raises(ValueError, match="separación"):
        evaluate(replace(cable, cable_spacing_m=35))


def test_congestion_fit_holds_capacity_and_separates_validation():
    aperture = 1800
    t0 = 9
    points = [
        (flow, road_time("BPR", flow / aperture, t0, 0.2, 4)) for flow in range(200, 1900, 150)
    ]
    model = fit("BPR", points[:-2], aperture, {"t0": t0}, points[-2:])
    assert model["parameters"]["alpha"] == pytest.approx(0.2, abs=0.002)
    assert model["parameters"]["beta"] == pytest.approx(4, abs=0.01)
    assert model["calibration"]["rmse"] < 0.01
    assert model["validation"]["r2"] > 0.98
    with pytest.raises(ValueError, match="Davidson"):
        fit("Davidson", points[:-2], aperture, {"t0": t0}, [(aperture, 20)])
    with pytest.raises(ValueError, match="distintos"):
        fit("BPR", [points[0], points[0]], aperture)


def test_technology_filters_before_scoring_and_optimization_preserves_original():
    candidate = {
        "name": "BRT",
        "infra": "Carril",
        "capacity": 4000,
        "cost": 70,
        "grade": 7,
        "radius": 15,
        "width": 9,
        "quality": 7,
        "speed": 34,
    }
    other = candidate | {"name": "Metro", "infra": "Vía", "capacity": 40_000, "cost": 300}
    incomplete = candidate | {"name": "Vial", "capacity": None}
    result = recommend(
        [candidate, other, incomplete],
        2700,
        {"Carril"},
        5,
        width=10,
        radius=20,
        budget=100,
        method="TOPSIS",
    )
    assert [row["name"] for row in result["ranking"]] == ["BRT"]
    assert len(result["sensitivity"]) == 8
    assert result["excluded"][1]["pending"] == ["capacidad"]
    line = example_line()
    original = evaluate(line)
    options = optimize(line, 120, 300, 10, 30, 100, 0, "Pareto")
    assert options["original"] == original
    assert evaluate(line) == original
    assert options["alternatives"]
    assert all(row["fleet"] <= 30 and row["margin"] >= 0 for row in options["alternatives"])
    econ = economics(10, 10, 8, 250, 100, 8, 2, 200)
    assert econ["annual_km"] == 400_000
    assert econ["subsidy"] == 600_200


def test_transit_data_roundtrip_and_exclusion_from_intersection_baseline(tmp_path):
    assert len(catalog()) == 8
    assert all(len(system["vehicles"]) == 2 for system in catalog())
    assert all(
        vehicle["source"].startswith("https://")
        for system in catalog()
        for vehicle in system["vehicles"]
    )
    project = IntersectionProject()
    modern = replace(project, transit_engineering={"line": {"system": "brt"}})
    assert baseline_key(project) == baseline_key(modern)
    assert load_project(save_project(modern, tmp_path / "transporte.hcnet")) == modern
    data = json.loads(json.dumps(project.to_dict()))
    data["schema_version"] = 6
    data["project"].pop("transit_engineering")
    assert IntersectionProject.from_dict(data).transit_engineering == {}


def test_real_sumo_corridor_uses_shared_engine_and_keeps_inputs(tmp_path):
    engine = locate_sumo()
    if engine is None:
        pytest.skip("SUMO externo no disponible")
    (tmp_path / "nodes.xml").write_text(
        '<nodes><node id="A" x="0" y="0"/><node id="B" x="400" y="0"/></nodes>'
    )
    (tmp_path / "edges.xml").write_text('<edges><edge id="E" from="A" to="B" speed="10"/></edges>')
    _command(
        [
            str(engine[1]),
            "--node-files",
            "nodes.xml",
            "--edge-files",
            "edges.xml",
            "-o",
            "network.xml",
        ],
        tmp_path,
        Event(),
    )
    (tmp_path / "routes.xml").write_text(
        '<routes><vType id="bus" vClass="bus"/><route id="r" edges="E"/>'
        '<vehicle id="bus.0" type="bus" route="r" depart="0"><stop busStop="S" duration="5"/>'
        '</vehicle><vehicle id="bus.1" type="bus" route="r" depart="80">'
        '<stop busStop="S" duration="8"/></vehicle></routes>'
    )
    (tmp_path / "stops.xml").write_text(
        '<additional><busStop id="S" lane="E_0" startPos="140" endPos="160"/></additional>'
    )
    config = tmp_path / "corridor.sumocfg"
    config.write_text(
        '<configuration><input><net-file value="network.xml"/><route-files value="routes.xml"/>'
        '<additional-files value="stops.xml"/></input><time><end value="180"/></time>'
        '<output><tripinfo-output value="must-not-write.xml"/></output></configuration>'
    )
    before = {path.name for path in tmp_path.iterdir()}
    result = simulate_corridor(config, engine[0], "bus.", "S", ("E_0",), 42, Event())
    assert len(result["trips"]) == len(result["stops"]) == 2
    assert result["dwell_mean_s"] >= 6.5
    assert result["headways_min"][0] > 1
    assert result["seed"] == 42 and result["reference_stop"] == "S"
    assert set(result["queues"]) == {"E_0"}
    assert {path.name for path in tmp_path.iterdir()} == before
    canceled = Event()
    canceled.set()
    with pytest.raises(SimulationCancelled):
        simulate_corridor(config, engine[0], "bus.", "S", (), 42, canceled)
