from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

from hcnet.domain.models import LaneGroupInput
from hcnet.ui.dialogs import LaneGroupDialog
from hcnet.ui.main_window import MainWindow
from hcnet.ui.styles import APP_STYLESHEET


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance() or QApplication([])
    return instance


def test_main_window_calculates_demo_and_populates_views(app: QApplication) -> None:
    window = MainWindow()
    assert not window.project.lane_groups
    assert window.last_result is None
    assert window.transit_tab.line_name.text() == ""
    assert not window.transit_tab.route_length.value()
    assert not window.roundabout_tab.parameters["diameter_m"].value()
    window.load_demo()
    assert window.calculate(switch_tab=False)
    app.processEvents()

    assert window.last_result is not None
    assert window.results_table.rowCount() == 8
    assert window.trace_selector.count() == 8
    assert "LOS" in window.los_card.value.text()
    assert "Flujo de demanda" in window.trace_browser.toPlainText()
    assert window.tabs.widget(0) is window.scope_tab
    assert window.tabs.tabText(0) == "Inicio y alcance"
    assert window.tabs.tabText(4) == "↔  Semaforización"
    assert window.tabs.tabText(6) == "↔  Reporte técnico"
    assert window.tabs.tabText(7) == "◇  Transporte público"
    assert window.tabs.tabText(8) == "◇  Rotondas"
    assert "3.2.0" in window.windowTitle()
    assert window.last_transit_result is not None
    assert window.transit_tab.congestion_table.rowCount() == 4
    assert window.roundabout_tab.operations.rowCount() == 4

    window.transit_tab.headway.setValue(6.0)
    assert window.calculate_transit()
    assert window.last_transit_result.service_frequency_bus_h == pytest.approx(10.0)
    assert "10.00 bus/h" in window.transit_tab.service_metric.value.text()

    window.optimize_signal_plan()
    assert window.last_optimization is not None
    assert "Webster" in window.optimization_summary.text()
    assert window.cycle_spin.value() == window.last_optimization.cycle_length_s

    window.dirty = False
    window.close()


def test_lane_group_dialog_preserves_all_values(app: QApplication) -> None:
    del app
    source = LaneGroupInput(
        approach="Poniente",
        movement="Izquierda",
        volume_veh_h=725,
        lanes=2,
        effective_green_s=41,
        parking_maneuvers_h=7,
        notes="Aforo de prueba",
    )
    dialog = LaneGroupDialog(source, cycle_length_s=100)
    restored = dialog.lane_group()

    assert restored == source
    dialog.close()


def test_main_window_exports_latex_report(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    window = MainWindow()
    window.load_demo()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Analista de prueba", True))
    destination = tmp_path / "reporte_desde_interfaz"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Documento LaTeX (*.tex)"),
    )

    window.export_tex()

    report_path = destination.with_suffix(".tex")
    assert report_path.exists()
    assert "Analista de prueba" in report_path.read_text(encoding="utf-8")
    window.dirty = False
    window.close()


def test_readable_fields_in_small_window(app: QApplication) -> None:
    window = MainWindow()
    window.setStyleSheet(APP_STYLESHEET)
    window.resize(640, 400)
    window.tabs.setCurrentWidget(window.project_tab)
    window.show()
    app.processEvents()
    for field in (window.name_edit, window.location_edit, window.analyst_edit, window.date_edit):
        assert field.height() >= field.fontMetrics().height() + 8
    assert window.project_tab.verticalScrollBar().maximum() > 0
    window.close()


def test_hcnet_restores_modules_and_optimized_plan(
    app: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    window = MainWindow()
    window.load_demo()
    window.optimize_signal_plan()
    plan = window.last_optimization
    window.transit_tab.headway.setValue(6)
    assert window.calculate_transit()
    window.roundabout_tab.arms.item(0, 1).setText("15")
    assert window.calculate_roundabout()
    destination = tmp_path / "estudio"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destination), ""))
    assert window.save()
    saved = destination.with_suffix(".hcnet")
    assert saved.exists()

    window.new_project()
    assert window.last_result is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(saved), ""))
    window.open_project()
    assert window.last_optimization == plan
    assert window.results_table.rowCount() == 8
    assert window.transit_tab.headway.value() == pytest.approx(6)
    assert window.transit_tab.congestion_table.rowCount() == 4
    assert window.roundabout_tab.operations.rowCount() == 4
    assert window.roundabout_tab.arms.item(0, 1).text() == "15.0"
    assert not window.dirty
    window.close()
