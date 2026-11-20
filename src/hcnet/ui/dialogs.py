"""Diálogos de edición y metadatos."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.models import IntersectionProject, LaneGroupInput, SignalHeadInput


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
        project: IntersectionProject | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = group or LaneGroupInput(volume_veh_h=0)
        self._cycle_length_s = cycle_length_s
        self._project = project or IntersectionProject(cycle_length_s=cycle_length_s)
        self.setWindowTitle("Grupo de carriles")
        self.setModal(True)
        available = self.screen().availableGeometry()
        self.resize(min(690, available.width() - 24), min(650, available.height() - 50))
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

        identity = QGroupBox("Origen, destino y carriles")
        identity_form = QFormLayout(identity)
        self.origin = QComboBox()
        for branch in self._project.active_branches:
            self.origin.addItem(branch.label, branch.code)
        self.destinations = QListWidget()
        self.destinations.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.destinations.setMaximumHeight(92)
        self.lane_indices = QListWidget()
        self.lane_indices.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.lane_indices.setMaximumHeight(92)
        self.phase = QSpinBox()
        self.phase.setRange(1, 16)
        identity_form.addRow("Ramal de origen:", self.origin)
        identity_form.addRow("Ramal(es) de destino:", self.destinations)
        identity_form.addRow("Carril(es) de entrada:", self.lane_indices)
        identity_form.addRow("Fase semafórica:", self.phase)
        self.origin.currentIndexChanged.connect(self._refresh_route_options)
        layout.addWidget(identity)

        demand_box = QGroupBox("Demanda y señal")
        demand_form = QFormLayout(demand_box)
        self.volume = _double_spin(0, 20000, 1, 10, " veh/h")
        self.green = _double_spin(0.1, 600, 1, 1, " s")
        self.green.setToolTip(
            f"Debe ser menor que la longitud de ciclo actual ({self._cycle_length_s:.1f} s)."
        )
        self.phf = _double_spin(0.01, 1.0, 3, 0.01)
        demand_form.addRow("Volumen observado, V:", self.volume)
        demand_form.addRow("Verde efectivo, g:", self.green)
        demand_form.addRow("FHMD / PHF:", self.phf)
        layout.addWidget(demand_box)

        operation_box = QGroupBox("Recorrido y cola")
        operation_form = QFormLayout(operation_box)
        self.free_speed = _double_spin(1, 180, 1, 5, " km/h")
        self.approach_length = _double_spin(1, 10000, 1, 10, " m")
        self.vehicle_spacing = _double_spin(3, 20, 2, 0.5, " m/veh")
        operation_form.addRow("Velocidad de flujo libre:", self.free_speed)
        operation_form.addRow("Longitud de aproximación:", self.approach_length)
        operation_form.addRow("Espaciamiento medio en cola:", self.vehicle_spacing)
        layout.addWidget(operation_box)

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
            "HCNet calcula fw, fHV, fg, fp y fbb. Los factores fLU, fa y fturn "
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
        origin_index = self.origin.findData(group.origin_branch)
        self.origin.setCurrentIndex(max(0, origin_index))
        self._refresh_route_options()
        _select_list_data(self.destinations, set(group.destination_branches))
        _select_list_data(self.lane_indices, set(group.lane_indices))
        self.phase.setValue(group.signal_phase)
        self.volume.setValue(group.volume_veh_h)
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
        self.free_speed.setValue(group.free_flow_speed_kmh)
        self.approach_length.setValue(group.approach_length_m)
        self.vehicle_spacing.setValue(group.average_vehicle_spacing_m)
        self.notes.setPlainText(group.notes)

    def _refresh_route_options(self) -> None:
        origin = self.origin.currentData()
        selected_destinations = set(_selected_list_data(self.destinations))
        selected_lanes = set(_selected_list_data(self.lane_indices))

        self.destinations.clear()
        for branch in self._project.active_branches:
            if branch.code != origin:
                item = QListWidgetItem(branch.label)
                item.setData(Qt.ItemDataRole.UserRole, branch.code)
                self.destinations.addItem(item)
        _select_list_data(self.destinations, selected_destinations)

        self.lane_indices.clear()
        branch = self._project.branch(str(origin))
        lane_count = branch.inbound_lanes if branch is not None else 1
        for lane in range(1, lane_count + 1):
            item = QListWidgetItem(f"Carril {lane}")
            item.setData(Qt.ItemDataRole.UserRole, lane)
            self.lane_indices.addItem(item)
        _select_list_data(self.lane_indices, selected_lanes)

    def lane_group(self) -> LaneGroupInput:
        origin = str(self.origin.currentData())
        destinations = tuple(str(value) for value in _selected_list_data(self.destinations))
        lanes = tuple(int(value) for value in _selected_list_data(self.lane_indices))
        branch = self._project.branch(origin)
        approach = (
            self._source.approach
            if origin == self._source.origin_branch
            else branch.name if branch is not None else origin
        )
        movement = (
            self._source.movement
            if destinations == self._source.destination_branches
            else f"{origin} → {'/'.join(destinations)}"
        )
        return replace(
            self._source,
            origin_branch=origin,
            destination_branches=destinations,
            lane_indices=lanes,
            signal_phase=self.phase.value(),
            approach=approach,
            movement=movement,
            volume_veh_h=self.volume.value(),
            lanes=len(lanes),
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
            free_flow_speed_kmh=self.free_speed.value(),
            approach_length_m=self.approach_length.value(),
            average_vehicle_spacing_m=self.vehicle_spacing.value(),
            notes=self.notes.toPlainText().strip(),
        )

    def _accept_if_valid(self) -> None:
        problems = []
        if not _selected_list_data(self.destinations):
            problems.append("Selecciona al menos un ramal de destino.")
        if not _selected_list_data(self.lane_indices):
            problems.append("Selecciona al menos un carril de entrada.")
        if self.green.value() >= self._cycle_length_s:
            problems.append(
                f"El verde efectivo debe ser menor que el ciclo ({self._cycle_length_s:.1f} s)."
            )
        if problems:
            QMessageBox.warning(self, "Datos incompletos", "\n".join(problems))
            return
        self.accept()


class SignalHeadDialog(QDialog):
    """Configura ubicación, tipo, fase y movimientos de un semáforo."""

    SIGNAL_TYPES = (
        "Vehicular circular",
        "Flecha direccional",
        "Peatonal",
        "Ciclista",
        "Intermitente",
    )

    def __init__(
        self,
        project: IntersectionProject,
        head: SignalHeadInput | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._source = head or SignalHeadInput(name=f"Semáforo {len(project.signal_heads) + 1}")
        self.setWindowTitle("Configuración del semáforo")
        available = self.screen().availableGeometry()
        self.resize(min(560, available.width() - 24), min(520, available.height() - 50))

        root = QVBoxLayout(self)
        title = QLabel("Cabeza o grupo semafórico")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        description = QLabel(
            "Indica dónde está instalado, qué indicación muestra y cuáles movimientos controla."
        )
        description.setObjectName("pageSubtitle")
        description.setWordWrap(True)
        root.addWidget(description)

        box = QGroupBox("Datos del semáforo")
        form = QFormLayout(box)
        self.name = QLineEdit()
        self.branch = QComboBox()
        for branch in project.active_branches:
            self.branch.addItem(branch.label, branch.code)
        self.signal_type = QComboBox()
        self.signal_type.addItems(self.SIGNAL_TYPES)
        self.phase = QSpinBox()
        self.phase.setRange(1, 16)
        form.addRow("Nombre:", self.name)
        form.addRow("Ubicación (ramal):", self.branch)
        form.addRow("Tipo:", self.signal_type)
        form.addRow("Fase:", self.phase)
        root.addWidget(box)

        movements_box = QGroupBox("Movimientos controlados")
        movements_layout = QVBoxLayout(movements_box)
        self.movements = QListWidget()
        self.movements.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for group in project.lane_groups:
            item = QListWidgetItem(group.label)
            item.setData(Qt.ItemDataRole.UserRole, group.identifier)
            self.movements.addItem(item)
        movements_layout.addWidget(self.movements)
        root.addWidget(movements_box, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar semáforo")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.name.setText(self._source.name)
        self.branch.setCurrentIndex(max(0, self.branch.findData(self._source.branch_code)))
        self.signal_type.setCurrentText(self._source.signal_type)
        self.phase.setValue(self._source.signal_phase)
        _select_list_data(self.movements, set(self._source.controlled_group_ids))

    def signal_head(self) -> SignalHeadInput:
        return replace(
            self._source,
            name=self.name.text().strip(),
            branch_code=str(self.branch.currentData()),
            signal_type=self.signal_type.currentText(),
            signal_phase=self.phase.value(),
            controlled_group_ids=tuple(str(value) for value in _selected_list_data(self.movements)),
        )

    def _accept_if_valid(self) -> None:
        problems = []
        if not self.name.text().strip():
            problems.append("Escribe un nombre para el semáforo.")
        if not _selected_list_data(self.movements):
            problems.append("Selecciona al menos un movimiento controlado.")
        if problems:
            QMessageBox.warning(self, "Datos incompletos", "\n".join(problems))
            return
        self.accept()


def _selected_list_data(widget: QListWidget) -> list[object]:
    return [item.data(Qt.ItemDataRole.UserRole) for item in widget.selectedItems()]


def _select_list_data(widget: QListWidget, values: set[object]) -> None:
    for index in range(widget.count()):
        item = widget.item(index)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in values)


def _scrollable(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    return area
