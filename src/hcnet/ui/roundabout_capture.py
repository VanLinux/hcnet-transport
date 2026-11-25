"""Captura gráfica y edición de la misma demanda en matriz y movimientos."""

import csv
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QMessageBox,
    QSplitter,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.roundabout_engineering import Arm, Movement, blank_arms
from hcnet.ui.roundabout_canvas import RoundCanvas
from hcnet.ui.transit_forms import Form, button, fill_table, label, numeric, row, scroll, table

ARM_SPECS = [
    ("name", "Nombre", "", ""),
    ("azimuth", "Azimut (°)", "0", "0 norte, 90 oriente."),
    ("inbound", "Carriles de entrada", "1", "Cero para excluir este acceso."),
    ("outbound", "Carriles de salida", "1", "Cero para excluir esta salida."),
    ("entry", "Ancho total de entrada (m)", "", ""),
    ("exit", "Ancho total de salida (m)", "", ""),
    ("length", "Longitud de aproximación (m)", "", ""),
    ("speed", "Velocidad de aproximación (km/h)", "", ""),
    ("storage", "Almacenamiento (m)", "", ""),
    ("splitter", "Ancho de isla separadora (m)", "", ""),
    ("approach", "Semiancho de aproximación Kimber (m)", "", ""),
    ("flare", "Abocinamiento efectivo Kimber (m)", "", ""),
    ("entry_angle", "Ángulo de entrada Kimber (°)", "", ""),
    ("curb_radius", "Radio de bordillo de entrada Kimber (m)", "", ""),
    ("entry_path", "Radio medido de trayectoria de entrada (m)", "", ""),
    ("entry_chord", "Cuerda de trayectoria de entrada (m)", "", ""),
    ("entry_sagitta", "Flecha de trayectoria de entrada (m)", "", ""),
    ("exit_path", "Radio medido de trayectoria de salida (m)", "", ""),
    ("sight", "Visibilidad medida (m)", "", ""),
    ("grade", "Pendiente longitudinal (%)", "", "Positiva ascendiendo en el sentido de viaje."),
    ("available_width", "Ancho disponible del corredor (m)", "", ""),
    ("bypass_width", "Giro segregado, ancho (m)", "", "Se registra en el esquema."),
    ("pedestrians", "Peatones (peatones/h)", "", ""),
    ("cycles", "Ciclistas (bicicletas/h)", "", ""),
    ("crossing", "Retiro del cruce (m)", "", ""),
    ("pedestrian_factor", "Factor peatonal", "1", "Factor externo documentado."),
    ("local_factor", "Factor de ajuste local", "1", "Debidamente documentado."),
    ("factor_source", "Fuente de factores, criterios y procedencia", "", ""),
    ("lock_lanes", "Fijar carriles de este ramal", False, ""),
    ("lock_azimuth", "Fijar orientación de este ramal", False, ""),
    ("outer_queue", "Cola inicial exterior (veh)", "", ""),
    ("inner_queue", "Cola inicial interior (veh)", "", ""),
    ("outer_conflicts", "Flujo conflictivo exterior", ("Todos", "Exterior", "Interior"), ""),
    ("inner_conflicts", "Flujo conflictivo interior", ("Todos", "Exterior", "Interior"), ""),
]
MOVE_HEADERS = (
    "Origen",
    "Destino",
    "Volumen (veh/h)",
    "FHMD",
    "Pesados (%)",
    "Autobuses (%)",
    "Motocicletas (%)",
    "Interior (%)",
    "Habilitado",
    "Fuente",
)
MODEL_HEADERS = (
    "origen",
    "destino",
    "volumen",
    "fhmd",
    "pesados",
    "autobuses",
    "motocicletas",
    "interior",
    "habilitado",
    "fuente",
)


class DemandEditor(QWidget):
    changed = Signal()
    selected = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.codes = []
        self.movements = {}
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                "Escribe aforos en la matriz. Usa un guion para restringir "
                "el movimiento y un número para habilitarlo. La diagonal admite retornos."
            )
        )
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.matrix = table(())
        self.matrix.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.matrix.cellChanged.connect(self._matrix_edit)
        self.matrix.cellClicked.connect(self._matrix_click)
        self.tabs.addTab(self.matrix, "Matriz OD")
        self.details = table(MOVE_HEADERS)
        self.details.cellChanged.connect(self._detail_edit)
        self.details.cellClicked.connect(self._detail_click)
        self.tabs.addTab(self.details, "Movimientos y composición")
        layout.addWidget(self.tabs, 1)
        layout.addWidget(
            row(
                button("Importar OD .csv…", self._import),
                button("Exportar OD .csv…", self._export),
                button("Exportar matriz…", self._export_matrix),
            )
        )
        self.status = label("")
        layout.addWidget(self.status)

    def _record(self, origin, dest):
        return self.movements.get(
            (origin, dest), [origin, dest, "", "1", "0", "0", "0", "0", "No", ""]
        )

    def refresh(self, codes=None):
        if codes is not None:
            self.codes = list(codes)
        active = self.codes
        with QSignalBlocker(self.matrix):
            self.matrix.setColumnCount(len(active))
            self.matrix.setRowCount(len(active))
            self.matrix.setHorizontalHeaderLabels(active)
            self.matrix.setVerticalHeaderLabels(active)
            for i, a in enumerate(active):
                for j, b in enumerate(active):
                    record = self._record(a, b)
                    text = (
                        record[2]
                        if record[8].casefold() == "sí"
                        else ("—" if (a, b) in self.movements else "")
                    )
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.matrix.setItem(i, j, item)
        fill_table(self.details, [self._record(a, b) for a in active for b in active])
        for i in range(self.details.rowCount()):
            for j in (0, 1):
                cell = self.details.item(i, j)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def set_data(self, codes, movements):
        self.movements = {(r[0], r[1]): list(map(str, r)) for r in movements}
        self.refresh(codes)

    def toggle_route(self, start, end):
        record = self._record(start, end).copy()
        record[8] = "No" if record[8].casefold() == "sí" else "Sí"
        self.movements[start, end] = record
        self.refresh()
        self.selected.emit(start, end)
        self.changed.emit()

    def _matrix_click(self, i, j):
        self.selected.emit(self.codes[i], self.codes[j])

    def _detail_click(self, i, _col):
        self.selected.emit(self.details.item(i, 0).text(), self.details.item(i, 1).text())

    def _matrix_edit(self, i, j):
        origin, dest = self.codes[i], self.codes[j]
        item = self.matrix.item(i, j).text().strip()
        previous = self._record(origin, dest).copy()
        if item in ("", "-", "—"):
            previous[8] = "No"
        else:
            previous[2] = item
            previous[8] = "Sí"
        self.movements[origin, dest] = previous
        idx = i * len(self.codes) + j
        with QSignalBlocker(self.details):
            for column in (2, 8):
                self.details.item(idx, column).setText(previous[column])
        self.changed.emit()

    def _detail_edit(self, i, j):
        if j < 2:
            return
        values = [self.details.item(i, k).text().strip() for k in range(len(MOVE_HEADERS))]
        key = (values[0], values[1])
        self.movements[key] = values
        with QSignalBlocker(self.matrix):
            cell = self.matrix.item(self.codes.index(key[0]), self.codes.index(key[1]))
            cell.setText(values[2] if values[8].casefold() in {"sí", "si", "1"} else "—")
        self.changed.emit()

    def values(self):
        return [list(row) for row in self.movements.values()]

    def parsed(self):
        result = []
        for start, end, vol, phf, heavy, bus, moto, lane, enabled, source in self.values():
            status = enabled.casefold()
            if status not in {"sí", "si", "no", "1", "0", ""}:
                raise ValueError(f"{start} a {end}. Habilitado admite Sí o No.")
            if status not in {"sí", "si", "1"}:
                continue
            result.append(
                Movement(
                    start,
                    end,
                    numeric(vol, "Aforo", default=0),
                    numeric(heavy, "Pesados", default=0),
                    numeric(bus, "Autobuses", default=0),
                    numeric(moto, "Motocicletas", default=0),
                    numeric(phf, "FHMD", default=1),
                    numeric(lane, "Carril interior", default=0),
                    True,
                    source,
                )
            )
        return tuple(result)

    def _export(self):
        self._write(MODEL_HEADERS, self.values(), "demanda_rotonda.csv")

    def _export_matrix(self):
        rows = [
            [a, *[self.matrix.item(i, j).text() for j in range(len(self.codes))]]
            for i, a in enumerate(self.codes)
        ]
        self._write(["origen", *self.codes], rows, "matriz_rotonda.csv")

    def _write(self, headers, rows, name):
        filename, _ = QFileDialog.getSaveFileName(self, "Guardar demanda", name, "CSV (*.csv)")
        if filename:
            try:
                path = Path(filename)
                if path.suffix.lower() != ".csv":
                    path = path.with_suffix(".csv")
                with path.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(headers)
                    writer.writerows(rows)
            except OSError as exc:
                self.status.setText(str(exc))

    def _import(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir demanda", "", "CSV (*.csv)")
        if not filename:
            return
        try:
            with Path(filename).open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                header = reader.fieldnames or []
                if not {"origen", "destino", "volumen"} <= set(header):
                    if set(header) != {"origen", *self.codes}:
                        raise ValueError(
                            "CSV: origen,destino,volumen o matriz de los ramales activos."
                        )
                    movements = [
                        [r["origen"], b, r[b], "1", "0", "0", "0", "0", "Sí", "Matriz CSV"]
                        for r in reader
                        for b in self.codes
                        if r[b] not in ("", "-", "—")
                    ]
                else:
                    defaults = ("", "", "", "1", "0", "0", "0", "0", "Sí", "CSV")
                    movements = [
                        [
                            r.get(k, default) or default
                            for k, default in zip(MODEL_HEADERS, defaults, strict=True)
                        ]
                        for r in reader
                    ]
            seen = set()
            for values in movements:
                key = tuple(values[:2])
                if key in seen or any(code not in self.codes for code in key):
                    raise ValueError("El CSV contiene códigos inactivos o pares OD duplicados.")
                numeric(values[2], "Aforo", default=0)
                seen.add(key)
            self.set_data(self.codes, movements)
            self.status.setText("Demanda importada.")
            self.changed.emit()
        except (OSError, ValueError, csv.Error) as exc:
            self.status.setText(str(exc))


def movement_rows(movements):
    return [
        [
            m.origin,
            m.destination,
            m.volume,
            m.phf,
            m.heavy,
            m.bus,
            m.motorcycle,
            m.lane2,
            "Sí" if m.enabled else "No",
            m.source,
        ]
        for m in movements
    ]


class GeometryEditor(QWidget):
    changed = Signal()
    notice_requested = Signal(str)
    axes_changed = Signal(list)
    connected = Signal(str, str)

    def __init__(self, demand):
        super().__init__()
        self.demand = demand
        self.raw = {}
        self.editing = ""
        self._loading = False
        layout = QVBoxLayout(self)
        tools = QWidget()
        left = QVBoxLayout(tools)
        left.setContentsMargins(0, 0, 0, 0)
        action = QCheckBox("Vincular origen y destino")
        layout.addWidget(
            row(button("Añadir ramal", self._add), button("Quitar ramal…", self._remove), action)
        )
        self.canvas = RoundCanvas(editable=True)
        self.canvas.selected.connect(self.select)
        self.canvas.moved.connect(self._rotate)
        self.canvas.connected.connect(self.connected)
        action.toggled.connect(self.canvas.set_link_mode)
        left.addWidget(
            row(
                button("−", lambda: self.canvas.magnify(0.8)),
                button("+", lambda: self.canvas.magnify(1.25)),
                button("Ajustar vista", self.canvas.reset_view),
                button("SVG…", self._svg),
            )
        )
        left.addWidget(self.canvas, 1)
        self.pick = QComboBox()
        self.pick.setAccessibleName("Ramal activo")
        self.pick.currentTextChanged.connect(self.select)
        self.arm = Form(ARM_SPECS, self._edit)
        self.arm_controls = QWidget()
        controls = QVBoxLayout(self.arm_controls)
        controls.addWidget(self.pick)
        controls.addWidget(
            row(
                button("Entrada +", lambda: self._bump("inbound")),
                button("Entrada −", lambda: self._bump("inbound", -1)),
                button("Salida +", lambda: self._bump("outbound")),
                button("Salida −", lambda: self._bump("outbound", -1)),
            )
        )
        controls.addWidget(self.arm)
        controls.addStretch()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(tools)
        splitter.addWidget(scroll(self.arm_controls))
        splitter.setSizes([520, 340])
        layout.addWidget(splitter, 1)
        layout.addWidget(
            label(
                "Arrastra una letra para rotar su eje. Desplaza con el botón central. "
                "Para añadir o restringir un giro, vincula origen con destino."
            )
        )

    def set_advanced(self, on):
        self.arm.visible(tuple(f[0] for f in ARM_SPECS[10:]), on)

    def _svg(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Guardar esquema", "rotonda.svg", "SVG (*.svg)"
        )
        if filename:
            try:
                path = Path(filename)
                self.canvas.render_vector(
                    path if path.suffix.lower() == ".svg" else path.with_suffix(".svg")
                )
            except OSError as exc:
                self.notice_requested.emit(str(exc))

    def set_data(self, rows):
        self.raw = {code: dict(values) for code, values in rows.items()}
        with QSignalBlocker(self.pick):
            self.pick.clear()
            self.pick.addItems(list(self.raw))
        self.editing = ""
        self.select(next(iter(self.raw), ""))
        self.axes_changed.emit(list(self.raw))

    def select(self, code):
        if code not in self.raw:
            return
        self._loading = True
        self.editing = code
        with QSignalBlocker(self.pick):
            self.pick.setCurrentText(code)
        defaults = {k: (v[0] if isinstance(v, tuple) else v) for k, _, v, _ in ARM_SPECS}
        self.arm.set_values(defaults | self.raw[code])
        self.canvas.active = code
        self.canvas.update()
        self.arm.controls["azimuth"].setEnabled(not self.arm.value("lock_azimuth"))
        self._loading = False

    def _edit(self):
        if not self._loading and self.editing:
            self.arm.controls["azimuth"].setEnabled(not self.arm.value("lock_azimuth"))
            self.raw[self.editing] = self.arm.values()
            self.changed.emit()

    def _bump(self, key, delta=1):
        try:
            value = self.arm.whole(key, 0) + delta
            other = "outbound" if key == "inbound" else "inbound"
            if 0 <= value <= 4 and (value or self.arm.whole(other, 0)):
                self.arm.set_values({key: value})
        except ValueError as exc:
            self.notice_requested.emit(str(exc))

    def _rotate(self, code, angle):
        if self.editing == code and not self.arm.value("lock_azimuth"):
            self.arm.set_values({"azimuth": angle})

    def _add(self):
        if len(self.raw) >= 8:
            self.notice_requested.emit("Se admiten hasta ocho ramales.")
            return
        used = {
            float(r.get("azimuth", 0))
            for r in self.raw.values()
            if str(r.get("azimuth", "")).replace(".", "", 1).isdigit()
        }
        code = next(c for c in "ABCDEFGH" if c not in self.raw)
        angles = [i * 45 for i in range(8)]
        angle = max(
            angles, key=lambda a: min((abs((a - b + 180) % 360 - 180) for b in used), default=180)
        )
        self.set_data(self.raw | {code: arm_form(Arm(code, angle))})
        self.select(code)
        self.changed.emit()

    def _remove(self):
        code = self.editing
        if not code or len(self.raw) <= 2:
            self.notice_requested.emit("Conserva al menos dos ramales.")
            return
        affected = [key for key in self.demand.movements if code in key]
        if (
            affected
            and QMessageBox.question(
                self,
                "Quitar ramal",
                f"¿Eliminar {code} y sus registros de demanda?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for key in affected:
            del self.demand.movements[key]
        del self.raw[code]
        self.set_data(self.raw)
        self.changed.emit()

    def arms(self):
        return tuple(parse_arm(code, data) for code, data in self.raw.items())


def parse_arm(code, data):
    arm = Arm(code, 0)
    values = {}
    for key, title, _, _ in ARM_SPECS:
        default = getattr(arm, key)
        entered = data.get(key, "")
        if isinstance(default, bool):
            values[key] = bool(entered)
        elif isinstance(default, str):
            values[key] = str(entered or default)
        else:
            value = numeric(entered, title, default=default)
            if type(default) is int and value != int(value):
                raise ValueError(f"{code}. {title} requiere un entero.")
            values[key] = int(value) if type(default) is int else value
    return replace(arm, **values)


def arm_form(arm):
    values = asdict(arm)
    values.pop("code")
    return values


def initial_arms(count=4):
    return {arm.code: arm_form(arm) for arm in blank_arms(count)}
