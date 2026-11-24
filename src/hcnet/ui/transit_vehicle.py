"""Editor vectorial esquemático del vehículo y sus puertas."""

from dataclasses import asdict, fields, replace

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMenu, QVBoxLayout, QWidget

from hcnet.domain.transit_engineering import DOOR_PRESETS, ROLES, Door, preset_doors
from hcnet.ui.transit_forms import Form, button, fill_table, integer, label, numeric, row, table

FIELD_NAMES = (
    "Uso",
    "Carro",
    "Ancho (m)",
    "Canales",
    "Ascenso (s/pax)",
    "Descenso (s/pax)",
    "Peso ascenso",
    "Peso descenso",
    "Interferencia",
    "Tiempo fijo (s)",
    "Accesibilidad (s)",
    "Acceso",
    "Cobro",
    "Notas",
)
COLORS = {
    "Ascenso": "#2f9c72",
    "Descenso": "#d88330",
    "Mixta": "#2e7eb5",
    "Deshabilitada": "#82909b",
}
DOOR_KEYS = [field.name for field in fields(Door)]


class VehicleSide(QWidget):
    changed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(176)
        self.body = "bus"
        self.cars = 1
        self.doors = []
        self.hits = []

    def set_vehicle(self, body, cars, doors):
        self.body, self.cars, self.doors = body, max(1, min(cars, 20)), doors
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        ink = palette.text().color()
        p.fillRect(self.rect(), palette.base())
        cable = self.body == "cable"
        rail = self.body in {"rail", "metro"}
        sections = (
            self.cars
            if rail
            else 3
            if self.body == "biarticulated"
            else (2 if "art" in self.body else 1)
        )
        width = max(85, self.width() - 48)
        if cable or self.body == "van":
            width *= 0.54 if cable else 0.77
        start = (self.width() - width) / 2
        unit = width / sections
        height = 63 if cable or rail else 53
        top = 52.0 if cable else 40.0
        self.hits = []
        if cable:
            p.setPen(QPen(ink, 2))
            p.drawLine(QPointF(start - 42, 22), QPointF(start + width + 44, 22))
            p.drawLine(QPointF(start + width / 2, 22), QPointF(start + width / 2, top))
        elif "trolley" in self.body:
            p.setPen(QPen(ink, 2))
            p.drawLine(QPointF(start + width * 0.35, top), QPointF(start + width * 0.59, 19))
            p.drawLine(QPointF(start + width * 0.45, top), QPointF(start + width * 0.72, 19))
        for i in range(sections):
            left = start + i * unit
            p.setPen(QPen(ink, 1.2))
            p.setBrush(QColor("#b7c9d5") if rail else QColor("#86b7bf"))
            p.drawRoundedRect(QRectF(left, top, unit - 3, height), 8 if cable else 5, 8)
            p.setBrush(QColor("#294758"))
            for j in range(3):
                p.drawRoundedRect(
                    QRectF(left + 6 + j * (unit - 10) / 3, top + 7, max(1, (unit - 14) / 3), 18),
                    3,
                    3,
                )
            if not cable:
                p.setBrush(ink)
                for position in (0.19, 0.79):
                    p.drawEllipse(QRectF(left + unit * position - 6, top + height - 5, 13, 13))
        for index, door in enumerate(self.doors):
            section = (
                min(max(1, door.car), sections) - 1
                if rail
                else index * sections // max(1, len(self.doors))
            )
            grouping = [
                d
                for k, d in enumerate(self.doors)
                if (min(max(1, d.car), sections) - 1 if rail else k * sections // len(self.doors))
                == section
            ]
            before = sum(
                1
                for k, d in enumerate(self.doors[:index])
                if (min(max(1, d.car), sections) - 1 if rail else k * sections // len(self.doors))
                == section
            )
            center = start + section * unit + (before + 1) * unit / (len(grouping) + 1)
            dw = min(27, unit / (len(grouping) + 1) * 0.8)
            rect = QRectF(center - dw / 2, top + 20, dw, height - 21)
            self.hits.append((index, rect.adjusted(-1, -6, 1, 23)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(COLORS.get(door.role, "#82909b")))
            p.drawRoundedRect(rect, 2, 2)
            p.setPen(QColor("#ffffff"))
            sign = {"Ascenso": "↑", "Descenso": "↓", "Mixta": "↕", "Deshabilitada": "×"}
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, sign.get(door.role, "?"))
            p.setPen(ink)
            p.drawText(
                QRectF(center - 9, top + height + 7, 18, 17),
                Qt.AlignmentFlag.AlignCenter,
                str(index + 1),
            )
        p.setPen(ink)
        p.drawText(
            QRectF(8, 132, max(10, self.width() - 16), 44),
            Qt.TextFlag.TextWordWrap,
            "Cabina · circulación continua"
            if cable
            else "↑ Ascenso   ↓ Descenso   ↕ Mixta   × Deshabilitada · clic en una puerta",
        )
        p.end()

    def mousePressEvent(self, event):  # noqa: N802
        for index, area in self.hits:
            if area.contains(event.position()):
                menu = QMenu(self)
                for role in ROLES:
                    action = menu.addAction(role)
                    action.triggered.connect(
                        lambda _, i=index, value=role: self.changed.emit(i, value)
                    )
                menu.exec(event.globalPosition().toPoint())
                break


class VehicleDoors(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.body, self.cars = "bus", 1
        layout = QVBoxLayout(self)
        self.side = VehicleSide()
        self.side.changed.connect(self._set_role)
        layout.addWidget(self.side)
        self.settings = Form(
            [
                ("count", "Número de puertas", "", "Captura de la unidad o formación completa."),
                ("preset", "Configuración rápida", DOOR_PRESETS, ""),
            ],
            lambda *_: None,
        )
        self.controls = row(
            button("Ajustar número de puertas", self._resize),
            button("Aplicar configuración", self._preset),
        )
        layout.addWidget(self.settings)
        layout.addWidget(self.controls)
        self.table = table(FIELD_NAMES)
        self.table.cellChanged.connect(self._edit)
        layout.addWidget(self.table)
        self.note = label(
            "Los tiempos de ascenso y descenso son supuestos editables por canal. "
            "Usa los pesos para repartir la demanda entre puertas habilitadas."
        )
        layout.addWidget(self.note)
        self.error = label("", "warningBanner")
        self.error.hide()
        layout.addWidget(self.error)

    def configure(self, body, cars):
        self.body, self.cars = body, cars
        for widget in (self.settings, self.controls, self.table, self.note):
            widget.setVisible(body != "cable")
        self._draw()

    def set_doors(self, doors):
        fill_table(self.table, doors)
        self.settings.set_values({"count": len(doors)})
        self._draw()

    def raw(self):
        return [
            [
                self.table.item(i, j).text() if self.table.item(i, j) else ""
                for j in range(self.table.columnCount())
            ]
            for i in range(self.table.rowCount())
        ]

    def doors(self):
        result = []
        for values in self.raw():
            data = dict(zip(DOOR_KEYS, values, strict=True))
            for key in ("car", "channels"):
                data[key] = integer(data[key], key)
            for key in DOOR_KEYS[2:-3]:
                if key != "channels":
                    data[key] = numeric(data[key], key, default=0)
            if data["car"] > self.cars or data["role"] not in ROLES:
                raise ValueError("Revisa el carro y el uso asignado a cada puerta.")
            result.append(Door(**data))
        return tuple(result)

    def _draw(self):
        try:
            self.side.set_vehicle(self.body, self.cars, self.doors())
            self.error.hide()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()

    def _edit(self, *_args):
        self._draw()
        self.changed.emit()

    def _resize(self):
        try:
            count = self.settings.whole("count")
            if not 0 <= count <= 80:
                raise ValueError("Selecciona de 0 a 80 puertas.")
            before = self.raw()
            doors = before[:count]
            for index in range(len(doors), count):
                default = Door(car=min(self.cars, index * self.cars // count + 1))
                doors.append(list(asdict(default).values()))
            self.set_doors(doors)
            self.changed.emit()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()

    def _preset(self):
        try:
            doors = preset_doors(self.doors(), self.settings.value("preset"))
            self.set_doors([list(asdict(door).values()) for door in doors])
            self.changed.emit()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()

    def _set_role(self, index, role):
        doors = list(self.doors())
        doors[index] = replace(doors[index], role=role)
        self.set_doors([list(asdict(door).values()) for door in doors])
        self.changed.emit()
