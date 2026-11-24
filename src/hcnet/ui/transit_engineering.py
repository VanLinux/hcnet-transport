"""Espacio de trabajo con cálculos independientes, integrales y selección tecnológica."""

import csv
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QInputDialog,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.transit_examples import DEMONSTRATIONS, demonstration
from hcnet.domain.transit_planning import SPECIFIC, specific
from hcnet.ui.transit_advanced import AdvancedTools, RoadTool, TechnologyTool
from hcnet.ui.transit_forms import Form, ResultPanel, button, intervals, label, row, scroll
from hcnet.ui.transit_layout import AdaptiveColumns, TransitPanels
from hcnet.ui.transit_line import LineEditor


class SpecificTool(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.methods = QComboBox()
        self.methods.setAccessibleName("Tipo de cálculo")
        self.methods.addItems([*SPECIFIC, "Congestión y calibración vial"])
        layout.addWidget(self.methods)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.forms = {}
        for name, (_, fields) in SPECIFIC.items():
            specs = [(key, title, "", "") for key, title in fields]
            if name == "Calidad y espera":
                specs.extend(
                    [
                        ("observed", "Intervalos observados (min; separados por ;)", "", ""),
                        ("random", "Llegadas aleatorias de pasajeros", False, ""),
                        ("regular", "Servicio regular supuesto", False, ""),
                    ]
                )
            form = Form(specs, self.changed.emit)
            self.forms[name] = form
            self.stack.addWidget(scroll(form))
        self.road = RoadTool()
        self.road.changed.connect(self.changed)
        self.stack.addWidget(scroll(self.road))
        self.methods.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.methods.currentIndexChanged.connect(lambda *_: self.changed.emit())

    def state(self):
        return {
            "method": self.methods.currentText(),
            "forms": {key: form.values() for key, form in self.forms.items()},
            "road": self.road.state(),
        }

    def restore(self, state):
        self.methods.setCurrentText(state.get("method", next(iter(SPECIFIC))))
        for key, form in self.forms.items():
            defaults = {
                key: False if isinstance(value, bool) else ""
                for key, value in form.values().items()
            }
            form.set_values(defaults | state.get("forms", {}).get(key, {}))
        self.road.form.set_values(
            {
                key: False if isinstance(value, bool) else ""
                for key, value in self.road.form.values().items()
            }
        )
        self.road.form.set_values({"model": "Lineal"})
        self.road.restore(state.get("road", {}))

    def calculate(self):
        method = self.methods.currentText()
        if method not in SPECIFIC:
            return self.road.calculate()
        form = self.forms[method]
        formula, fields = SPECIFIC[method]
        inputs = {
            key: form.number(
                key,
                0
                if key in {"x", "p", "r", "a", "b", "d", "tf"} or method == "Calidad y espera"
                else None,
            )
            for key, _ in fields
        }
        observed = ()
        random = regular = False
        if method == "Calidad y espera":
            observed = intervals(form.value("observed"))
            random, regular = form.value("random"), form.value("regular")
        result = specific(method, inputs, observed, random, regular)
        return {"title": method, "formulas": [formula], "inputs": form.values(), "metrics": result}


class TransitEngineering(QWidget):
    changed = Signal()
    export_requested = Signal(dict)
    MODES = ("Cálculo específico", "Análisis integral", "Recomendación de sistema")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self.records = {}
        self.demo_name = ""
        self.results_key = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.modes = QComboBox()
        self.modes.setAccessibleName("Modalidad de transporte público")
        self.modes.addItems(self.MODES)
        calculate = button("Calcular", self.run_current)
        calculate.setObjectName("primaryButton")
        self.toolbar = AdaptiveColumns(
            self.modes,
            row(calculate, button("Cargar caso demostrativo…", self._choose_demo), wrap=False),
            stretches=(2, 3),
        )
        self.status = label("", "infoBanner")
        self.status.hide()
        layout.addWidget(self.status)
        self.inputs = QStackedWidget()
        self.specific = SpecificTool()
        self.inputs.addWidget(self.specific)
        self.specific.changed.connect(self._specific_edited)
        self.integral = QTabWidget()
        self.integral.setDocumentMode(True)
        self.line = LineEditor()
        self.integral.addTab(self.line, "Configuración y operación")
        self.line.changed.connect(self._line_edited)
        self.advanced = AdvancedTools(self.line)
        self.integral.addTab(self.advanced, "Análisis avanzado")
        self.advanced.changed.connect(self._advanced_edited)
        self.advanced.sumo.complete.connect(lambda record: self._complete("advanced/3", record))
        self.inputs.addWidget(self.integral)
        self.technology = TechnologyTool()
        self.technology.changed.connect(lambda: self._edited("technology"))
        self.inputs.addWidget(scroll(self.technology))
        results_page = QWidget()
        footer = QVBoxLayout(results_page)
        footer.setContentsMargins(0, 0, 0, 0)
        self.export_tex = button("Exportar reporte .tex…", self._tex)
        self.export_csv = button("Exportar resultados .csv…", self._csv)
        footer.addWidget(row(self.export_tex, self.export_csv))
        self.results = ResultPanel()
        footer.addWidget(scroll(self.results), 1)
        self.panels = TransitPanels(self.inputs, results_page)
        layout.addWidget(self.panels, 1)
        self.modes.currentIndexChanged.connect(self._switch)
        self.integral.currentChanged.connect(self._switch)
        self.advanced.tabs.currentChanged.connect(self._switch)
        self._show()

    def _key(self):
        index = self.modes.currentIndex()
        if index == 0:
            return f"specific/{self.specific.methods.currentIndex()}"
        if index == 2:
            return "technology"
        if self.integral.currentIndex() == 1:
            return f"advanced/{self.advanced.tabs.currentIndex()}"
        return "line"

    def _switch(self, *_):
        self.inputs.setCurrentIndex(self.modes.currentIndex())
        if not self._loading:
            self._show()

    def _specific_edited(self):
        key = f"specific/{self.specific.methods.currentIndex()}"
        if self.results_key and self.results_key != key and self._key() == key:
            self._show()
            return
        self._edited(key)

    def _line_edited(self):
        self._edited("line", "advanced/0", "advanced/1", "advanced/2", "advanced/3")

    def _advanced_edited(self):
        self._edited(f"advanced/{self.advanced.tabs.currentIndex()}")

    def _edited(self, *keys):
        if self._loading:
            return
        for key in keys:
            if key in self.records:
                self.records[key]["stale"] = True
        self._show()
        self.changed.emit()

    def _show(self):
        key = self._key()
        self.results_key = key
        record = self.records.get(key)
        self.results.show_record(record)
        exportable = bool(record and not record.get("stale"))
        self.export_tex.setVisible(exportable and not key.startswith("advanced/"))
        self.export_csv.setVisible(exportable)
        if record and record.get("stale"):
            self.status.setText("Datos modificados. Calcula de nuevo para actualizar el reporte.")
            self.status.show()
        elif self.demo_name:
            self.status.setText(f"Caso demostrativo · {self.demo_name}. Datos didácticos.")
            self.status.show()
        else:
            self.status.hide()

    def run_current(self):
        key = self._key()
        try:
            if key.startswith("specific"):
                record = self.specific.calculate()
            elif key == "line":
                record = self.line.calculate()
            elif key == "technology":
                record = self.technology.calculate()
            else:
                record = self.advanced.calculate()
            if record is not None:
                self._complete(key, record)
            else:
                self.status.setText("Corrida iniciada. Consulta el estado en Microsimulación SUMO.")
                self.status.show()
            return True
        except (ValueError, OSError, OverflowError) as exc:
            self.status.setText(str(exc))
            self.status.show()
            return False

    def _complete(self, key, record):
        if self.demo_name:
            record.setdefault("notes", []).insert(
                0, f"Caso demostrativo {self.demo_name}. Los parámetros del estudio son didácticos."
            )
        self.records[key] = record
        self._show()
        self.changed.emit()

    def _tex(self):
        record = self.records.get(self._key())
        if not record or record.get("stale"):
            return
        if self._key() == "line":
            advanced = [
                dict(value)
                for key, value in self.records.items()
                if key.startswith("advanced/") and not value.get("stale")
            ]
            record = record | {"included": advanced}
        self.export_requested.emit(record)

    def _csv(self):
        record = self.records.get(self._key())
        if not record or record.get("stale"):
            return
        name, _ = QFileDialog.getSaveFileName(
            self, "Guardar resultados", "transporte.csv", "CSV (*.csv)"
        )
        if not name:
            return
        try:
            path = Path(name)
            if path.suffix.lower() != ".csv":
                path = path.with_suffix(".csv")
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow([record["title"]])
                writer.writerows(record.get("metrics", {}).items())
                for title, headers, rows in record.get("tables", []):
                    writer.writerow([])
                    writer.writerow([title])
                    writer.writerow(headers)
                    writer.writerows(rows)
        except OSError as exc:
            self.status.setText(str(exc))
            self.status.show()

    def _choose_demo(self):
        name, ok = QInputDialog.getItem(
            self, "Cargar caso demostrativo", "Selecciona el caso", DEMONSTRATIONS, editable=False
        )
        if ok:
            self.load_demonstration(DEMONSTRATIONS.index(name))

    def load_demonstration(self, index):
        self.set_state(demonstration(index) | {"demo": DEMONSTRATIONS[index]})
        self.changed.emit()

    def snapshot(self):
        return deepcopy(
            {
                "mode": self.modes.currentIndex(),
                "integral_tab": self.integral.currentIndex(),
                "line_tab": self.line.sections.currentIndex(),
                "specific": self.specific.state(),
                "line": self.line.state(),
                "advanced": self.advanced.state(),
                "recommend": self.technology.state(),
                "records": self.records,
                "demo": self.demo_name,
            }
        )

    def set_state(self, state):
        self._loading = True
        self.demo_name = state.get("demo", "")
        self.specific.restore(state.get("specific", {}))
        self.line.set_state(state.get("line", {}))
        self.advanced.restore(state.get("advanced", {}))
        for reference in self.technology.form.controls:
            self.technology.form.set_values(
                {reference: "Ponderado" if reference == "method" else ""}
            )
        self.technology.restore(state.get("recommend", {}))
        self.records = deepcopy(state.get("records", {}))
        self.modes.setCurrentIndex(max(0, min(2, state.get("mode", 0))))
        self.integral.setCurrentIndex(max(0, min(1, state.get("integral_tab", 0))))
        self.line.sections.setCurrentIndex(max(0, min(2, state.get("line_tab", 0))))
        self.inputs.setCurrentIndex(self.modes.currentIndex())
        self._loading = False
        self._show()
