from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPalette, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QWidget

from hcnet import __version__
from hcnet.domain.models import LaneGroupInput
from hcnet.ui.dialogs import LaneGroupDialog
from hcnet.ui.main_window import MainWindow
from hcnet.ui.styles import APP_STYLESHEET
from hcnet.ui.wheel import WheelScrollFilter


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance() or QApplication([])
    instance.installEventFilter(WheelScrollFilter(instance))
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
    assert window.tabs.widget(0) is window.project_tab
    assert window.tabs.tabText(3) == "↔ Semaforización"
    assert window.detail_tabs.tabText(2) == "Reporte técnico"
    assert window.workspace_choice.itemText(1) == "◇ Rotonda de un carril"
    assert window.workspace_choice.itemText(2) == "◇ Transporte público"
    assert __version__ in window.windowTitle()
    assert window.last_transit_result is not None
    assert window.transit_tab.congestion_table.rowCount() == 4
    assert window.roundabout_tab.operations.rowCount() == 4

    window.transit_tab.headway.setValue(6.0)
    assert window.calculate_transit()
    assert window.last_transit_result.service_frequency_bus_h == pytest.approx(10.0)
    assert "10.00 bus/h" in window.transit_tab.service_metric.value.text()

    original_cycle = window.cycle_spin.value()
    assert window.optimize_signal_plan()
    assert window.last_optimization is not None
    assert window.project.scenarios[-1].name == "Webster"
    assert window.cycle_spin.value() == original_cycle

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
        assert field.isVisible()
        assert field.height() >= field.fontMetrics().height() + 8
    assert window.project_tab.viewport().height() > 140
    assert window.project_tab.verticalScrollBar().maximum() > 0
    window.close()


def test_hcnet_restores_modules_and_optimized_plan(
    app: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    window = MainWindow()
    window.load_demo()
    assert window.optimize_signal_plan()
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


def test_phase_edit_marks_baseline_stale_and_keeps_archived_comparison(app: QApplication) -> None:
    window = MainWindow()
    window.load_demo()
    assert window.optimize_signal_plan()
    assert window.phase_editor.cards.count() == 4
    assert window.optimize_button.isEnabled()
    assert window.scenario_panel.table.columnCount() == 4
    initial = list(window.project.phases)
    window.phase_editor._move(0, 1)
    assert window.project.phases[:2] == initial[1::-1]
    assert window.last_result is None
    assert not window.optimize_button.isEnabled()
    assert "histórico" in window.scenario_panel.list.item(0).text()
    window.scenario_panel.list.item(0).setSelected(True)
    assert window.scenario_panel.table.horizontalHeaderItem(1).text() == "Original archivado"
    assert window.calculate(switch_tab=False)
    window._advance_cycle()
    assert window.live_sketch.active_phase == initial[1].number
    window._set_theme(True)
    window.workspace_choice.setCurrentIndex(2)
    assert window.workspaces.currentWidget() is window.transit_tab
    window._set_theme(False)
    window.dirty = False
    window.close()


def test_wheel_scrolls_form_and_leaves_focused_controls_unchanged(app: QApplication) -> None:
    def scroll_over(widget: QWidget) -> None:
        position = widget.rect().center()
        event = QWheelEvent(
            QPointF(position), QPointF(widget.mapToGlobal(position)), QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        QApplication.sendEvent(widget, event)

    window = MainWindow()
    window.resize(640, 400)
    window.show()
    window.load_demo()
    app.processEvents()

    field = window.cycle_spin
    field.setFocus()
    original_cycle = field.value()
    scrollbar = window.project_tab.verticalScrollBar()
    scrollbar.setValue(0)
    scroll_over(field.lineEdit())
    assert scrollbar.value() > 0
    assert field.value() == original_cycle
    QTest.keyClick(field, Qt.Key.Key_Up)
    assert field.value() == pytest.approx(original_cycle + field.singleStep())

    picker = window.workspace_choice
    picker.setFocus()
    index = picker.currentIndex()
    scroll_over(picker)
    assert picker.currentIndex() == index
    QTest.keyClick(picker, Qt.Key.Key_Down)
    assert picker.currentIndex() == index + 1
    scroll_over(window.roundabout_tab.circulation)
    assert window.roundabout_tab.circulation.currentIndex() == 0

    window.dirty = False
    window.close()


def test_side_panel_layout_theme_and_context(app: QApplication) -> None:
    window = MainWindow()
    window.resize(1240, 780)
    window.show()
    window.load_demo()
    app.processEvents()

    data, diagram, summary = window.analysis_split.sizes()
    assert data > diagram > summary
    assert "veh/h" in window.summary.text()
    assert "Grupo crítico" in window.summary.text()
    window.detail_tabs.setCurrentWidget(window.scenario_panel)
    assert window.guide_title.text() == "Comparar escenarios"
    window.tabs.tabBarClicked.emit(window.tabs.indexOf(window.project_tab))
    assert window.guide_title.text() == "Proyecto"
    window.cycle_spin.stepUp()
    assert window.summary_status.property("stale") is True
    assert "recalcular" in window.summary_status.text()
    assert not window.summary.text()

    result_page = window.results_tab.widget()
    window._set_theme(True)
    assert result_page.palette().color(QPalette.ColorRole.Window).lightness() < 80
    window._set_theme(False)
    assert result_page.palette().color(QPalette.ColorRole.Window).lightness() > 225
    assert window.result_timestamp.palette().color(QPalette.ColorRole.WindowText).lightness() < 120

    window.dirty = False
    window.close()
