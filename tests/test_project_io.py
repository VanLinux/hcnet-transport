from __future__ import annotations

import csv

import pytest

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.sample import demonstration_project
from hcnet.io.project import export_report_tex, export_results_csv, load_project, save_project


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


def test_latex_report_contains_analyst_results_and_escaped_text(tmp_path) -> None:
    project = demonstration_project()
    project.name = "Cruce Norte & Sur_1"
    project.analyst = "Dra. Ana López & equipo"
    result = calculate_intersection(project)
    path = tmp_path / "reporte.tex"

    export_report_tex(project, result, path)

    report = path.read_text(encoding="utf-8")
    assert report.startswith(r"\documentclass")
    assert "HCNet Transport 2.0.0" in report
    assert r"Cruce Norte \& Sur\_1" in report
    assert r"Dra. Ana López \& equipo" in report
    assert r"\section{Resultados por grupo de carriles}" in report
    assert rf"\textbf{{Nivel de servicio}} & {result.level_of_service}" in report
    assert report.count(r"\subsection{") >= len(project.lane_groups)


def test_saved_project_records_current_application_version(tmp_path) -> None:
    project = demonstration_project()
    path = tmp_path / "version.hcnet.json"

    save_project(project, path)

    assert '"application_version": "2.0.0"' in path.read_text(encoding="utf-8")


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
