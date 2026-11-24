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
    assert window.workspaces.currentWidget() is window.scope_tab
    assert window.workspace_nav.tabData(window.workspace_nav.currentIndex()) == "help"
    assert not window.calculate_action.isEnabled()
    assert not window.dirty
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
    assert [window.workspace_nav.tabText(i) for i in range(window.workspace_nav.count())] == [
        "Inicio y alcance", "Intersección semaforizada", "Rotonda", "Transporte público",
    ]
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
    window._select_workspace("signal")
    window.tabs.setCurrentWidget(window.project_tab)
    window.show()
    app.processEvents()
    for field in (window.name_edit, window.location_edit, window.analyst_edit, window.date_edit):
        assert field.isVisible()
        assert field.height() >= field.fontMetrics().height() + 8
    assert window.project_tab.viewport().height() > 140
    assert window.project_tab.verticalScrollBar().maximum() > 0
    window.close()


def test_selected_tab_expands_its_panel_and_keeps_other_tabs_reachable(app: QApplication) -> None:
    window = MainWindow()
    window.resize(1240, 780)
    window._select_workspace("signal")
    window.show()
    app.processEvents()
    upper_bar = window.tabs.tabBar()
    lower_bar = window.detail_tabs.tabBar()

    assert window.project_tab.isVisible()
    assert window.live_sketch.isVisible()
    assert not window.results_tab.isVisible()
    assert window.detail_tabs.height() == lower_bar.height()
    assert lower_bar.isVisible()

    for _ in range(2):
        QTest.mouseClick(lower_bar, Qt.MouseButton.LeftButton, pos=lower_bar.tabRect(0).center())
        app.processEvents()
        assert upper_bar.isVisible()
        assert not window.project_tab.isVisible()
        assert not window.live_sketch.isVisible()
        assert not window.side_panel.isVisible()
        assert window.analysis_split.height() == upper_bar.height()
        assert window.results_tab.isVisible()
        assert window.detail_tabs.geometry().bottom() == window.signal_workspace.rect().bottom()

        QTest.mouseClick(upper_bar, Qt.MouseButton.LeftButton, pos=upper_bar.tabRect(0).center())
        app.processEvents()
        assert lower_bar.isVisible()
        assert not window.results_tab.isVisible()
        assert window.project_tab.isVisible()
        assert window.analysis_split.height() > upper_bar.height()

    window.resize(640, 400)
    app.processEvents()
    assert window.compact_view.isVisible()
    window.compact_view.setCurrentIndex(1)
    assert window.live_sketch.isVisible()
    window.compact_view.setCurrentIndex(2)
    assert window.results_tab.isVisible()
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
    window._select_workspace("transit")
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

    picker = window.workspace_nav
    picker.setFocus()
    index = picker.currentIndex()
    scroll_over(picker)
    assert picker.currentIndex() == index
    QTest.keyClick(picker, Qt.Key.Key_Right)
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


def test_transport_engineering_modes_demos_and_reopen(app, tmp_path):
    from hcnet.domain.transit_reporting import report
    from hcnet.io.project import load_project, save_project

    window = MainWindow()
    window.resize(1010, 720)
    window._select_workspace("transit")
    window.show()
    module = window.transit_tab.engineering
    assert module.line.line.value("length_km") == ""
    assert not module.run_current()
    form = module.specific.forms["Frecuencia"]
    form.set_values({"h": 4})
    window._calculate_active()
    record = module.records["specific/0"]
    assert record["metrics"]["Frecuencia (unid/h)"] == 15
    form.set_values({"h": 6})
    assert record["stale"]
    assert module.export_tex.isHidden()
    for case in range(7):
        module.load_demonstration(case)
        assert module.run_current(), module.status.text()
        app.processEvents()
        assert module.records
    project = window._project_from_ui()
    reopened = load_project(save_project(project, tmp_path / "transporte.hcnet"))
    window._load_project_into_ui(reopened)
    assert module.records.keys() == reopened.transit_engineering["records"].keys()
    document = report(reopened, module.records["advanced/0"])
    assert "letterpaper" in document and "inputenc" not in document
    assert "\\begin{picture}" in document
    assert window.workspaces.currentWidget() is window.transit_tab
    window.dirty = False
    window.close()


def test_navigation_and_transit_panels_use_available_width(app):
    from PySide6.QtWidgets import QPushButton, QToolBar

    window = MainWindow()
    window.resize(1240, 720)
    window.show()
    app.processEvents()
    nav = window.workspace_nav
    toolbar = window.findChild(QToolBar)
    assert nav.parentWidget() is toolbar
    assert window.save_action not in toolbar.actions()
    assert window.calculate_action not in toolbar.actions()

    def click_tab(bar, index):
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(index).center())
        app.processEvents()

    for key, page in (
        ("signal", window.signal_workspace), ("roundabout", window.roundabout_tab),
        ("help", window.scope_tab), ("transit", window.transit_tab),
    ):
        index = next(i for i in range(nav.count()) if nav.tabData(i) == key)
        click_tab(nav, index)
        assert window.workspaces.currentWidget() is page
        assert window.calculate_action.isEnabled() == (key != "help")

    transit = window.transit_tab
    for index, panels in ((0, transit.engineering.panels), (1, transit.line_panels)):
        transit.workspace.setCurrentIndex(index)
        app.processEvents()
        assert panels.tabs.currentIndex() == panels.PARALLEL
        assert panels.capture.width() > panels.results.width() > 0
        assert panels.capture.geometry().top() == panels.results.geometry().top()
        panels.splitter.setSizes([560, 600])
        panels.splitter.splitterMoved.emit(560, 1)
        remembered = panels.splitter.sizes()
        click_tab(panels.tabs, panels.RESULTS)
        assert panels.results.width() == panels.splitter.width()
        assert not panels.capture.isVisible() and panels.tabs.isVisible()
        click_tab(panels.tabs, panels.CAPTURE)
        assert panels.capture.width() == panels.splitter.width()
        assert not panels.results.isVisible() and panels.tabs.isVisible()
        click_tab(panels.tabs, panels.PARALLEL)
        assert panels.splitter.sizes() == remembered

        window.resize(640, 400)
        app.processEvents()
        assert not panels.tabs.isTabEnabled(panels.PARALLEL)
        assert panels.capture.width() == panels.splitter.width()
        assert not panels.results.isVisible()
        window.resize(1240, 720)
        app.processEvents()
        assert panels.tabs.currentIndex() == panels.PARALLEL
        assert panels.splitter.sizes() == remembered

    transit.workspace.setCurrentIndex(0)
    transit.engineering.modes.setCurrentIndex(1)
    window.resize(480, 330)
    app.processEvents()
    assert nav.tabRect(nav.count() - 1).right() < nav.width()
    assert transit.viewport.verticalScrollBar().maximum() > 0
    form_view = transit.engineering.line.sections.currentWidget()
    assert form_view.viewport().height() > 70
    for action in transit.engineering.toolbar.findChildren(QPushButton):
        assert action.height() >= action.sizeHint().height()

    window.dirty = False
    window.close()


@pytest.mark.parametrize("dark", [False, True])
def test_dropdown_shows_all_options_that_fit_on_screen(app, dark):
    window = MainWindow()
    window._set_theme(dark)
    window.resize(640, 430)
    window._select_workspace("transit")
    window.show()
    app.processEvents()
    transit = window.transit_tab

    for combo in (transit.workspace, transit.engineering.specific.methods):
        assert combo.isVisible()
        QTest.mouseClick(combo, Qt.MouseButton.LeftButton, pos=combo.rect().center())
        app.processEvents()
        view = combo.view()
        assert view.isVisible()
        assert view.verticalScrollBar().maximum() == 0
        last = combo.model().index(combo.count() - 1, combo.modelColumn())
        assert view.viewport().rect().contains(view.visualRect(last))
        combo.hidePopup()
        app.processEvents()
    assert transit.workspace.itemText(1) == "Cálculo de línea vial"

    window._set_theme(False)
    window.dirty = False
    window.close()
