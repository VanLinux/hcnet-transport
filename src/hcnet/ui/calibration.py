"""Biblioteca de factores por grupo y asistente de calibración."""

from dataclasses import replace

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from hcnet.domain.calculations import adjustment_factors
from hcnet.domain.calibration import (
    EFFECTS,
    EmpiricalFactor,
    FieldCalibration,
    empirical_multiplier,
)
from hcnet.domain.models import LaneGroupInput
from hcnet.domain.signals import aggregate_demand

STANDARD = (
    ("fw", "Ancho", "Ancho de carril"),
    ("fHV", "Pesados", "Composición y equivalencia"),
    ("fg", "Pendiente", "Pendiente del acceso"),
    ("fp", "Estacionamiento", "Maniobras por hora"),
    ("fbb", "Bloqueo de autobuses", "Bloqueos por hora"),
    ("fLU", "Utilización", "Captura del analista"),
    ("fa", "Tipo de área", "Captura del analista"),
    ("fturn", "Giros", "Captura del analista"),
)


class CalibrationDialog(QDialog):
    def __init__(self, group: LaneGroupInput, parent=None) -> None:
        super().__init__(parent)
        self.group = group
        self.setWindowTitle("Factores de ajuste y calibración")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(group.label))
        standard_group = replace(group, empirical_factors=(), field_calibration=None)
        values = adjustment_factors(aggregate_demand(standard_group) or standard_group)
        form = QFormLayout()
        factors = (
            values.lane_width,
            values.heavy_vehicles,
            values.grade,
            values.parking,
            values.bus_blockage,
            values.lane_utilization,
            values.area_type,
            values.turn,
        )
        for (symbol, name, method), value in zip(STANDARD, factors, strict=True):
            form.addRow(f"{symbol} · {name}", QLabel(f"{value:.4f} · {method}"))
        layout.addLayout(form)
        self.table = QComboBox()
        layout.addWidget(self.table)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.table.currentIndexChanged.connect(self._preview)
        layout.addWidget(self.preview)
        for label, action in (
            ("Agregar factor personalizado", self._add),
            ("Editar factor", self._edit),
            ("Quitar factor", self._remove),
            ("Calibrar con flujo observado", self._calibrate),
            ("Quitar calibración de campo", self._clear),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            layout.addWidget(button)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()
        self.resize(560, 520)

    def _refresh(self) -> None:
        self.table.clear()
        for factor in self.group.empirical_factors:
            lane = f"carril {factor.lane}" if factor.lane else "todo el grupo"
            self.table.addItem(f"{factor.symbol} · {factor.name} · {factor.value:.2f} · {lane}")
        self._preview()

    def _preview(self) -> None:
        group = self.group
        effective = aggregate_demand(group) or group
        flow = effective.base_saturation_flow_pc_h_ln * effective.lanes
        try:
            flow *= adjustment_factors(effective).product
            messages = [f"Flujo ajustado del grupo: {flow:.1f} veh/h"]
        except ValueError as exc:
            messages = [str(exc)]
        field = group.field_calibration
        if field:
            messages.append(f"Campo: {field.observed:.1f} veh/h · k = {field.coefficient:.4f}")
        i = self.table.currentIndex()
        if i >= 0:
            factor = group.empirical_factors[i]
            messages.append(f"{factor.effect} · {factor.description}\nOrigen: {factor.source}")
        self.preview.setText("\n".join(messages))

    def _add(self) -> None:
        self._edit_factor(None)

    def _edit(self) -> None:
        if self.table.currentIndex() >= 0:
            self._edit_factor(self.table.currentIndex())

    def _edit_factor(self, index: int | None) -> None:
        factors = list(self.group.empirical_factors)
        current = factors[index] if index is not None else None
        popup = QDialog(self)
        popup.setWindowTitle("Factor empírico")
        form = QFormLayout(popup)
        name, symbol, description, source = (
            QLineEdit(getattr(current, field, ""))
            for field in ("name", "symbol", "description", "source")
        )
        effect, lane = QComboBox(), QComboBox()
        effect.addItems(EFFECTS)
        lane.addItem("Todo el grupo", None)
        for number in self.group.lane_indices:
            lane.addItem(f"Carril {number}", number)
        value = QDoubleSpinBox()
        value.setRange(0.10, 1.0)
        value.setSingleStep(0.05)
        value.setValue(current.value if current else 0.85)
        if current:
            effect.setCurrentText(current.effect)
            lane.setCurrentIndex(lane.findData(current.lane))
        for label, widget in (
            ("Nombre", name),
            ("Símbolo", symbol),
            ("Tipo de efecto", effect),
            ("Carril", lane),
            ("Valor", value),
            ("Descripción", description),
            ("Origen o justificación", source),
        ):
            form.addRow(label, widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(popup.accept)
        buttons.rejected.connect(popup.reject)
        form.addRow(buttons)
        while popup.exec():
            factor = EmpiricalFactor(
                name.text(),
                symbol.text(),
                value.value(),
                description.text(),
                source.text(),
                effect.currentText(),
                lane.currentData(),
            )
            revised = (
                factors + [factor]
                if index is None
                else [factor if i == index else old for i, old in enumerate(factors)]
            )
            try:
                empirical_multiplier(self.group.lane_indices, tuple(revised), None)
            except ValueError as exc:
                QMessageBox.warning(self, "Revisa el factor", str(exc))
                continue
            self.group = replace(self.group, empirical_factors=tuple(revised))
            self._refresh()
            return

    def _remove(self) -> None:
        index = self.table.currentIndex()
        if index >= 0:
            factors = self.group.empirical_factors
            self.group = replace(
                self.group, empirical_factors=factors[:index] + factors[index + 1 :]
            )
            self._refresh()

    def _clear(self) -> None:
        self.group = replace(self.group, field_calibration=None)
        self._refresh()

    def _calibrate(self) -> None:
        base = replace(aggregate_demand(self.group) or self.group, field_calibration=None)
        reference = (
            base.base_saturation_flow_pc_h_ln * base.lanes * adjustment_factors(base).product
        )
        if reference <= 0:
            QMessageBox.warning(
                self, "Flujo inválido", "Captura primero una base de flujo positiva."
            )
            return
        observed, accepted = QInputDialog.getDouble(
            self,
            "Flujo observado",
            "Flujo de saturación del grupo (veh/h)",
            reference,
            0.01,
            100_000,
            2,
        )
        if not accepted:
            return
        source, accepted = QInputDialog.getText(
            self, "Calibración de campo", "Fuente o justificación"
        )
        if not accepted or not source.strip():
            return
        field = FieldCalibration(observed, reference, source.strip())
        delta = observed - reference
        answer = QMessageBox.question(
            self,
            "Aplicar coeficiente empírico",
            f"Observado: {observed:.2f} veh/h. Calculado: {reference:.2f} veh/h.\n"
            f"Diferencia: {delta:+.2f} veh/h ({100 * delta / reference:+.2f} %).\n"
            f"¿Aplicar k = {field.coefficient:.4f}?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.group = replace(self.group, field_calibration=field)
            self._refresh()
