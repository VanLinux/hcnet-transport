from __future__ import annotations

import csv

import pytest

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.sample import demonstration_project
from hcnet.io.project import export_results_csv, load_project, save_project


def test_project_json_round_trip(tmp_path) -> None:
    project = demonstration_project()
    path = tmp_path / "demo.hcnet.json"

    save_project(project, path)
    restored = load_project(path)

    assert restored == project
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_csv_export_contains_results_and_factors(tmp_path) -> None:
    project = demonstration_project()
    result = calculate_intersection(project)
    path = tmp_path / "results.csv"

    export_results_csv(project, result, path)

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(project.lane_groups)
    assert rows[0]["proyecto"] == project.name
    assert rows[0]["nivel_servicio"] in set("ABCDEF")
    assert float(rows[0]["producto_factores"]) > 0


def test_loader_accepts_project_payload_without_envelope(tmp_path) -> None:
    path = tmp_path / "minimal.json"
    path.write_text(
        '{"name":"Mínimo","cycle_length_s":90,"analysis_period_h":0.25,"lane_groups":[]}',
        encoding="utf-8",
    )

    project = load_project(path)
    assert project.name == "Mínimo"


def test_loader_converts_numeric_strings(tmp_path) -> None:
    path = tmp_path / "numeric-strings.json"
    path.write_text(
        '{"cycle_length_s":"90","analysis_period_h":"0.25",'
        '"lane_groups":[{"lanes":"2","volume_veh_h":"500"}]}',
        encoding="utf-8",
    )

    project = load_project(path)
    assert project.cycle_length_s == 90.0
    assert project.lane_groups[0].lanes == 2
    assert project.lane_groups[0].volume_veh_h == 500.0


def test_loader_rejects_future_schema(tmp_path) -> None:
    path = tmp_path / "future.json"
    path.write_text('{"schema_version":99,"project":{}}', encoding="utf-8")

    with pytest.raises(ValueError, match="esquema más reciente"):
        load_project(path)
