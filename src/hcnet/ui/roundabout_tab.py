"""Captura y presentación del análisis de rotondas."""

from __future__ import annotations

from dataclasses import fields
from math import cos, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.roundabout import ARM_LIMIT, RoundaboutArm, RoundaboutInput, RoundaboutResult

ARM_FIELDS = (
    ("name", "Nombre"), ("azimuth_deg", "Azimut (°)"), ("entry_width_m", "Entrada (m)"),
    ("exit_width_m", "Salida (m)"), ("entry_radius_m", "Radio tray. entrada (m)"),
    ("exit_radius_m", "Radio tray. salida (m)"), ("storage_m", "Almacenamiento (m)"),
    ("heavy_percent", "Pesados (%)"), ("pedestrian_factor", "Factor peatonal"),
    ("entry_chord_m", "Cuerda ent. (m)"), ("entry_sagitta_m", "Flecha ent. (m)"),
    ("exit_chord_m", "Cuerda sal. (m)"), ("exit_sagitta_m", "Flecha sal. (m)"),
)
PARAMETERS = (
    ("diameter_m", "Diámetro inscrito (m)", 0, 300, 2),
    ("circulating_width_m", "Ancho anular de circulación (m)", 0, 20, 2),
    ("apron_width_m", "Corona montable (m)", 0, 20, 2),
    ("design_speed_kmh", "Velocidad de comprobación (km/h)", 0, 100, 1),
    ("cross_slope_percent", "Pendiente transversal con signo (%)", -12, 12, 2),
    ("side_friction", "Fricción lateral", 0, 1, 3),
    ("braking_deceleration_m_s2", "Desaceleración para visibilidad (m/s²)", 0.1, 10, 2),
    ("reaction_time_s", "Tiempo de percepción-reacción (s)", 0, 10, 2),
    ("peak_hour_factor", "Factor de hora de máxima demanda (FHMD)", 0.01, 1, 3),
    ("period_h", "Periodo de análisis (h)", 0.01, 4, 2),
    ("heavy_equivalency", "Equivalencia de vehículos pesados", 1, 10, 2),
    ("vehicle_spacing_m", "Separación media en cola (m/veh)", 1, 30, 2),
    ("capacity_a", "Capacidad sin conflictos, A (eq/h)", 1, 5000, 1),
    ("capacity_b", "Coeficiente de congestión, B (h/eq)", 0, 0.02, 6),
)


class RoundaboutSketch(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(240)
        self.data: RoundaboutInput | None = None

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        if self.data is None:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Esquema de la rotonda")
            return
        center = QPointF(self.width() / 2, self.height() / 2)
        outer = min(self.width(), self.height()) * 0.26
        data = self.data
        scale = outer / (data.diameter_m / 2)
        painter.setPen(QPen(QColor("#43545D"), 2))
        for index, arm in enumerate(data.arms[:data.arm_count]):
            angle = radians(arm.azimuth_deg)
            dx, dy = sin(angle), -cos(angle)
            end = center + QPointF(dx * outer * 1.48, dy * outer * 1.48)
            painter.setPen(QPen(QColor("#43545D"), max(
                3, (arm.entry_width_m + arm.exit_width_m) * scale,
            )))
            painter.drawLine(center, end)
            label_center = center + QPointF(dx * outer * 1.78, dy * outer * 1.78)
            painter.setPen(QColor("#202124"))
            painter.drawText(
                QRectF(label_center.x()-18, label_center.y()-10, 36, 20),
                Qt.AlignmentFlag.AlignCenter, chr(65 + index),
            )
        painter.setPen(Qt.PenStyle.NoPen)
        for radius, color in (
            (outer, "#43545D"),
            (outer - data.circulating_width_m * scale, "#AEB4B7"),
            (outer - (data.circulating_width_m + data.apron_width_m) * scale, "#DAE7D9"),
        ):
            painter.setBrush(QColor(color))
            painter.drawEllipse(center, radius, radius)
        painter.setPen(QColor("#202124"))
        painter.drawText(
            QRectF(center.x()-20, center.y()-12, 40, 24),
            Qt.AlignmentFlag.AlignCenter, "↻" if data.circulation == "Horario" else "↺",
        )


class RoundaboutTab(QScrollArea):
    input_changed = Signal()
    calculate_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        title = QLabel("Rotondas de un carril · operación y predimensionamiento")
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        for label, signal in (
            ("Calcular rotonda", self.calculate_requested),
            ("Exportar reporte .tex", self.export_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(signal.emit)
            header.addWidget(button)
        layout.addLayout(header)

        configuration = QGroupBox("Geometría general y parámetros de análisis")
        form = QFormLayout(configuration)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name = QLineEdit()
        self.count = QSpinBox()
        self.count.setRange(2, ARM_LIMIT)
        self.circulation = QComboBox()
        self.circulation.addItems(["Antihorario", "Horario"])
        form.addRow("Nombre:", self.name)
        form.addRow("Cantidad de ramales:", self.count)
        form.addRow("Sentido de circulación:", self.circulation)
        self.parameters = {}
        for key, label, low, high, precision in PARAMETERS:
            control = QDoubleSpinBox()
            control.setDecimals(precision)
            control.setRange(low, high)
            control.setKeyboardTracking(False)
            if low == 0 and key in {"diameter_m", "circulating_width_m", "design_speed_kmh"}:
                control.setSpecialValueText("Por capturar")
            control.valueChanged.connect(self._input_edited)
            self.parameters[key] = control
            form.addRow(label + ":", control)
        self.count.valueChanged.connect(self._update_count)
        self.name.textChanged.connect(self._input_edited)
        self.circulation.currentIndexChanged.connect(self._input_edited)
        layout.addWidget(configuration)

        note = QLabel(
            "Azimut desde el norte en sentido horario. Los radios se miden en la trayectoria "
            "vehicular. Para calcular un radio, deja vacía su celda y captura cuerda y flecha. "
            "Desplaza la tabla a la derecha para ver esas columnas. "
            "Deja vacío un ancho o almacenamiento si no lo has medido. "
            "El factor peatonal vale 1 cuando no se aplica reducción de capacidad."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.arms = QTableWidget(ARM_LIMIT, len(ARM_FIELDS))
        self.arms.setHorizontalHeaderLabels([label for _, label in ARM_FIELDS])
        self.arms.setVerticalHeaderLabels(list("ABCDEFGH"))
        self.arms.setColumnWidth(0, 130)
        self.arms.resizeColumnsToContents()
        self.arms.setMinimumHeight(220)
        self.arms.itemChanged.connect(self._input_edited)
        layout.addWidget(self.arms)
        instructions = QLabel(
            "Aforos OD (veh/h). Filas de origen y columnas de destino. "
            "Usa la diagonal para vueltas en U. Las celdas vacías equivalen a cero."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.od = QTableWidget(ARM_LIMIT, ARM_LIMIT)
        self.od.setHorizontalHeaderLabels(list("ABCDEFGH"))
        self.od.setVerticalHeaderLabels(list("ABCDEFGH"))
        self.od.horizontalHeader().setDefaultSectionSize(65)
        self.od.setMinimumHeight(220)
        self.od.itemChanged.connect(self._input_edited)
        layout.addWidget(self.od)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.sketch = RoundaboutSketch()
        layout.addWidget(self.sketch)
        self.operations = self._result_table(layout, [
            "Ramal", "Entrada", "Salida", "Conflicto", "Conflicto (eq/h)", "Capacidad",
            "v/c", "Demora (s/veh)", "LOS", "P95 (veh)", "P95 (m)",
        ])
        self.geometry = self._result_table(layout, [
            "Ramal", "Azimut (°)", "Ancho ent. (m)", "Ancho sal. (m)", "Radio ent. (m)",
            "Radio sal. (m)", "Vel. ent. (km/h)", "Vel. sal. (km/h)", "Ángulo sig. (°)",
            "Arco sig. (m)",
        ])
        self.diagnosis = QLabel()
        self.diagnosis.setWordWrap(True)
        layout.addWidget(self.diagnosis)
        self.setWidget(page)
        self.clear_result()

    @staticmethod
    def _result_table(layout: QVBoxLayout, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setMinimumHeight(240)
        table.verticalHeader().hide()
        layout.addWidget(table)
        return table

    def _update_count(self, count: int) -> None:
        for i in range(ARM_LIMIT):
            self.arms.setRowHidden(i, i >= count)
            self.od.setRowHidden(i, i >= count)
            self.od.setColumnHidden(i, i >= count)
        self.input_changed.emit()

    def _input_edited(self, *_args) -> None:
        self.input_changed.emit()

    def set_input(self, data: RoundaboutInput) -> None:
        self.name.setText(data.name)
        self.circulation.setCurrentText(data.circulation)
        self.count.setValue(data.arm_count)
        for key, control in self.parameters.items():
            control.setValue(getattr(data, key))
        for i in range(ARM_LIMIT):
            for j, (key, _) in enumerate(ARM_FIELDS):
                value = getattr(data.arms[i], key)
                shown = str(value) if value or key in {"azimuth_deg", "pedestrian_factor"} else ""
                self.arms.setItem(i, j, QTableWidgetItem(shown))
            for j in range(ARM_LIMIT):
                value = data.flows[i][j]
                self.od.setItem(i, j, QTableWidgetItem(str(value) if value else ""))
        self._update_count(self.count.value())

    def input_data(self) -> RoundaboutInput:
        data = RoundaboutInput(
            name=self.name.text().strip(), arm_count=self.count.value(),
            circulation=self.circulation.currentText(),
            **{key: control.value() for key, control in self.parameters.items()},
        )
        defaults = {field.name: field.default for field in fields(RoundaboutArm)}
        for i in range(ARM_LIMIT):
            for j, (key, label) in enumerate(ARM_FIELDS):
                value = self.arms.item(i, j).text().strip()
                if key == "name":
                    data.arms[i].name = value
                else:
                    setattr(data.arms[i], key, self._number(value, label, defaults[key]))
            for j in range(ARM_LIMIT):
                data.flows[i][j] = self._number(
                    self.od.item(i, j).text().strip(), f"OD {chr(65+i)} → {chr(65+j)}", 0,
                )
        return data

    @staticmethod
    def _number(value: str, label: str, default: float) -> float:
        try:
            number = float(value.replace(",", ".")) if value else default
            if not -1e7 <= number <= 1e7:
                raise ValueError
            return number
        except ValueError as exc:
            raise ValueError(f"Revisa el valor de {label}. Usa un número finito.") from exc

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple]) -> None:
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                label = f"{value:.2f}" if isinstance(value, float) else str(value)
                cell = QTableWidgetItem("—" if value is None else label)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, j, cell)
        table.resizeColumnsToContents()

    def set_result(self, data: RoundaboutInput, result: RoundaboutResult) -> None:
        self.summary.setText(
            f"{data.name or 'Rotonda'} · {data.circulation}\n"
            f"Demanda ajustada {result.total_entry:.1f} veh/h · "
            f"Demora ponderada {result.delay:.1f} s/veh · LOS {result.los}\n"
            f"Radio de isla total {result.island_radius:.2f} m · "
            f"Isla no montable {result.hard_island_radius:.2f} m · "
            f"Eje anular {result.centerline_radius:.2f} m\n"
            f"Radio mínimo para la velocidad capturada {result.design_min_radius:.2f} m · "
            f"Velocidad teórica en el eje {result.centerline_speed:.1f} km/h · "
            f"Visibilidad de parada {result.stopping_distance:.1f} m"
        )
        self._fill(self.operations, [
            (a.code, a.entry, a.exiting, a.conflicting, a.conflicting_equivalent, a.capacity,
             a.saturation, a.delay, a.los, a.queue_95, a.queue_95_m)
            for a in result.arms
        ])
        self._fill(self.geometry, [
            (r.code + (f" · {a.name}" if a.name else ""), a.azimuth_deg,
             a.entry_width_m or None, a.exit_width_m or None, r.entry_radius,
             r.exit_radius, r.entry_speed, r.exit_speed, r.next_angle, r.arc_length)
            for a, r in zip(data.arms, result.arms, strict=False)
        ])
        self.sketch.data = data
        self.sketch.update()
        self.diagnosis.setText(
            "\n".join(result.warnings) or "Sin alertas para los datos capturados."
        )

    def clear_result(self) -> None:
        self.summary.setText("Calcula la rotonda para ver los resultados de operación y geometría.")
        self.operations.setRowCount(0)
        self.geometry.setRowCount(0)
        self.sketch.data = None
        self.sketch.update()
        self.diagnosis.clear()
