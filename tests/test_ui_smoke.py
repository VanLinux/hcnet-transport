from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from hcnet.domain.models import LaneGroupInput
from hcnet.ui.dialogs import LaneGroupDialog
from hcnet.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance() or QApplication([])
    return instance


def test_main_window_calculates_demo_and_populates_views(app: QApplication) -> None:
    window = MainWindow()
    assert window.calculate(switch_tab=False)
    app.processEvents()

    assert window.last_result is not None
    assert window.results_table.rowCount() == 8
    assert window.trace_selector.count() == 8
    assert "LOS" in window.los_card.value.text()
    assert "Flujo de demanda" in window.trace_browser.toPlainText()

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
