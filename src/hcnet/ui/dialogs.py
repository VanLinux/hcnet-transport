"""Diálogos de edición y metadatos."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.models import LaneGroupInput


def _double_spin(
    minimum: float,
    maximum: float,
    decimals: int,
    step: float,
    suffix: str = "",
) -> QDoubleSpinBox:
    field = QDoubleSpinBox()
    field.setRange(minimum, maximum)
    field.setDecimals(decimals)
    field.setSingleStep(step)
    field.setSuffix(suffix)
    field.setKeyboardTracking(False)
    return field


class LaneGroupDialog(QDialog):
    """Formulario completo para un grupo de carriles."""

    def __init__(
        self,
        group: LaneGroupInput | None = None,
        cycle_length_s: float = 90.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = group or LaneGroupInput()
        self._cycle_length_s = cycle_length_s
        self.setWindowTitle("Grupo de carriles")
        self.setModal(True)
        self.resize(690, 650)
        self._build_ui()
        self._set_values(self._source)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Datos del grupo de carriles")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Define la demanda, geometría y ajustes operacionales. "
            "Los factores avanzados son adimensionales."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._basic_tab(), "Datos básicos")
        self.tabs.addTab(self._adjustments_tab(), "Ajustes")
        self.tabs.addTab(self._notes_tab(), "Notas")
        root.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar grupo")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _basic_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        identity = QGroupBox("Identificación")
        identity_form = QFormLayout(identity)
        self.approach = QComboBox()
        self.approach.setEditable(True)
        self.approach.addItems(["Norte", "Sur", "Oriente", "Poniente"])
        self.movement = QComboBox()
        self.movement.setEditable(True)
        self.movement.addItems(
            ["Izquierda", "Directo", "Derecha", "Directo + derecha", "Compartido"]
        )
        identity_form.addRow("Acceso:", self.approach)
        identity_form.addRow("Movimiento:", self.movement)
        layout.addWidget(identity)

        demand_box = QGroupBox("Demanda y señal")
        demand_form = QFormLayout(demand_box)
        self.volume = _double_spin(0, 20000, 1, 10, " veh/h")
        self.lanes = QSpinBox()
        self.lanes.setRange(1, 12)
        self.green = _double_spin(0.1, 600, 1, 1, " s")
        self.green.setToolTip(
            f"Debe ser menor que la longitud de ciclo actual ({self._cycle_length_s:.1f} s)."
        )
        self.phf = _double_spin(0.01, 1.0, 3, 0.01)
        demand_form.addRow("Volumen observado, V:", self.volume)
        demand_form.addRow("Número de carriles, N:", self.lanes)
        demand_form.addRow("Verde efectivo, g:", self.green)
        demand_form.addRow("FHMD / PHF:", self.phf)
        layout.addWidget(demand_box)

        base_box = QGroupBox("Condiciones base")
        base_form = QFormLayout(base_box)
        self.s0 = _double_spin(500, 3000, 0, 50, " pc/h/carril")
        self.heavy = _double_spin(0, 100, 1, 1, " %")
        self.heavy_equivalency = _double_spin(1, 5, 2, 0.1)
        self.width = _double_spin(2.4, 4.8, 2, 0.1, " m")
        self.grade = _double_spin(-10, 10, 2, 0.5, " %")
        base_form.addRow("Flujo de saturación base, s₀:", self.s0)
        base_form.addRow("Vehículos pesados:", self.heavy)
        base_form.addRow("Equivalencia de pesados, Eₜ:", self.heavy_equivalency)
        base_form.addRow("Ancho de carril:", self.width)
        base_form.addRow("Pendiente (+ ascenso):", self.grade)
        layout.addWidget(base_box)
        layout.addStretch()
        return _scrollable(page)

    def _adjustments_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        saturation = QGroupBox("Ajustes del flujo de saturación")
        form = QFormLayout(saturation)
        self.f_lu = _double_spin(0.05, 1.5, 3, 0.01)
        self.parking = _double_spin(0, 1000, 1, 1, " maniobras/h")
        self.buses = _double_spin(0, 1000, 1, 1, " bloqueos/h")
        self.f_area = _double_spin(0.05, 1.5, 3, 0.01)
        self.f_turn = _double_spin(0.05, 1.5, 3, 0.01)
        form.addRow("Utilización de carriles, fLU:", self.f_lu)
        form.addRow("Estacionamiento, Nm:", self.parking)
        form.addRow("Paradas/bloqueos de autobús, Nb:", self.buses)
        form.addRow("Tipo de área, fa:", self.f_area)
        form.addRow("Ajuste por giro, fturn:", self.f_turn)
        layout.addWidget(saturation)

        delay = QGroupBox("Ajustes de demora")
        delay_form = QFormLayout(delay)
        self.progression = _double_spin(0.05, 1.5, 3, 0.05)
        self.k_factor = _double_spin(0.01, 1.5, 3, 0.05)
        self.i_factor = _double_spin(0.01, 1.5, 3, 0.05)
        self.d3 = _double_spin(0, 3600, 2, 1, " s/veh")
        delay_form.addRow("Progresión, PF:", self.progression)
        delay_form.addRow("Demora incremental, k:", self.k_factor)
        delay_form.addRow("Filtrado aguas arriba, I:", self.i_factor)
        delay_form.addRow("Demora por cola inicial, d₃:", self.d3)
        layout.addWidget(delay)

        note = QLabel(
            "HCNet 1.0 calcula fw, fHV, fg, fp y fbb. Los factores fLU, fa y fturn "
            "deben obtenerse del estudio y de la metodología aplicable. d₃ se introduce "
            "directamente; esta versión no la estima."
        )
        note.setObjectName("infoBanner")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return _scrollable(page)

    def _notes_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel("Supuestos, fuente de los datos o decisiones de agrupamiento:")
        label.setWordWrap(True)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(
            "Ejemplo: volumen obtenido mediante aforo de 15 min; giro derecho compartido…"
        )
        layout.addWidget(label)
        layout.addWidget(self.notes, 1)
        return page

    def _set_values(self, group: LaneGroupInput) -> None:
        self.approach.setCurrentText(group.approach)
        self.movement.setCurrentText(group.movement)
        self.volume.setValue(group.volume_veh_h)
        self.lanes.setValue(group.lanes)
        self.green.setValue(group.effective_green_s)
        self.phf.setValue(group.peak_hour_factor)
        self.s0.setValue(group.base_saturation_flow_pc_h_ln)
        self.heavy.setValue(group.heavy_vehicles_percent)
        self.heavy_equivalency.setValue(group.heavy_vehicle_equivalency)
        self.width.setValue(group.lane_width_m)
        self.grade.setValue(group.grade_percent)
        self.f_lu.setValue(group.lane_utilization_factor)
        self.parking.setValue(group.parking_maneuvers_h)
        self.buses.setValue(group.bus_blockages_h)
        self.f_area.setValue(group.area_type_factor)
        self.f_turn.setValue(group.turn_factor)
        self.progression.setValue(group.progression_factor)
        self.k_factor.setValue(group.incremental_delay_factor)
        self.i_factor.setValue(group.upstream_filtering_factor)
        self.d3.setValue(group.initial_queue_delay_s_veh)
        self.notes.setPlainText(group.notes)

    def lane_group(self) -> LaneGroupInput:
        return replace(
            self._source,
            approach=self.approach.currentText().strip(),
            movement=self.movement.currentText().strip(),
            volume_veh_h=self.volume.value(),
            lanes=self.lanes.value(),
            effective_green_s=self.green.value(),
            peak_hour_factor=self.phf.value(),
            base_saturation_flow_pc_h_ln=self.s0.value(),
            heavy_vehicles_percent=self.heavy.value(),
            heavy_vehicle_equivalency=self.heavy_equivalency.value(),
            lane_width_m=self.width.value(),
            grade_percent=self.grade.value(),
            lane_utilization_factor=self.f_lu.value(),
            parking_maneuvers_h=self.parking.value(),
            bus_blockages_h=self.buses.value(),
            area_type_factor=self.f_area.value(),
            turn_factor=self.f_turn.value(),
            progression_factor=self.progression.value(),
            incremental_delay_factor=self.k_factor.value(),
            upstream_filtering_factor=self.i_factor.value(),
            initial_queue_delay_s_veh=self.d3.value(),
            notes=self.notes.toPlainText().strip(),
        )

    def _accept_if_valid(self) -> None:
        problems = []
        if not self.approach.currentText().strip():
            problems.append("Escribe el nombre del acceso.")
        if not self.movement.currentText().strip():
            problems.append("Escribe el movimiento.")
        if self.green.value() >= self._cycle_length_s:
            problems.append(
                f"El verde efectivo debe ser menor que el ciclo ({self._cycle_length_s:.1f} s)."
            )
        if problems:
            QMessageBox.warning(self, "Datos incompletos", "\n".join(problems))
            return
        self.accept()


def _scrollable(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area
