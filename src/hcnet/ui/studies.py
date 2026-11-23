"""Estudios opcionales de una intersección y control de la ejecución en segundo plano."""

from dataclasses import asdict, replace
from threading import Event
from xml.etree.ElementTree import ParseError

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.emissions import IDLE_POLLUTANTS, emission_difference, estimate_idle
from hcnet.domain.models import IntersectionProject
from hcnet.domain.scenarios import baseline_snapshot
from hcnet.domain.signals import prepare_project, timeline
from hcnet.simulation.options import (
    DEFAULT_FLEET,
    POLLUTANTS,
    FleetType,
    SimulationOptions,
    locate_sumo,
    scenario_choices,
    validate_fleet,
)
from hcnet.simulation.results import unpack
from hcnet.simulation.runner import SimulationCancelled, simulate
from hcnet.ui.queue_view import QueueView
from hcnet.ui.study_charts import StudyChart


def button(label, action):  # noqa: ANN001, ANN201
    widget = QPushButton(label)
    widget.clicked.connect(action)
    return widget


def spin(low, high, value):  # noqa: ANN001, ANN201
    widget = QSpinBox() if isinstance(low, int) else QDoubleSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


def note(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def table(headers: list[str], *, editable: bool = False) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.verticalHeader().hide()
    widget.setAlternatingRowColors(True)
    if not editable:
        widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    return widget


def fill(widget: QTableWidget, rows: list) -> None:
    widget.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            widget.setItem(i, j, QTableWidgetItem(str(value)))


def show_number(value) -> str:  # noqa: ANN001
    return "—" if value is None else f"{value:.4g}"


class SimulationWorker(QThread):
    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project, options, fleet, binaries, parent) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.arguments = project, options, fleet, binaries
        self.cancel = Event()

    def run(self) -> None:
        try:
            result = simulate(*self.arguments, self.cancel, self.progress.emit)
        except SimulationCancelled:
            self.cancelled.emit()
        except (ValueError, OSError, RuntimeError, KeyError, ArithmeticError, ParseError) as exc:
            self.failed.emit(str(exc))
        else:
            self.completed.emit(result)


class IntersectionStudies(QDialog):
    changed = Signal()

    def __init__(self, project: IntersectionProject, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Microsimulación, colas y emisiones")
        self.project = project
        self.choices = [
            (label, key, IntersectionProject.from_dict(baseline_snapshot(config)))
            for label, key, config in scenario_choices(project, include_archived=True)
        ]
        self.worker: SimulationWorker | None = None
        self.cancel_close = False
        self.active_choice = 0
        self.options = SimulationOptions(**project.study_settings.get("options", {}))
        self.fleet = tuple(
            FleetType(**row)
            for row in project.study_settings.get(
                "fleet",
                [asdict(item) for item in DEFAULT_FLEET],
            )
        )
        self.idle = project.study_settings.get("idle", {})
        self.record: dict = {}
        self.settings = QSettings("VanLinux", "HCNet Transport")
        root = QVBoxLayout(self)
        self.scenario = QComboBox()
        self.scenario.addItems([label for label, _, _ in self.choices])
        form = QFormLayout()
        form.addRow("Escenario", self.scenario)
        root.addLayout(form)
        self.capture_note = note()
        self.capture_note.hide()
        root.addWidget(self.capture_note)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._simulation_tab(), "Microsimulación")
        self.queues = QueueView()
        self.tabs.addTab(self.queues, "Análisis de colas")
        self.tabs.addTab(self._environment_tab(), "Evaluación ambiental y emisiones")
        self.tabs.currentChanged.connect(lambda index: self.queues.stop() if index != 1 else None)
        root.addWidget(self.tabs, 1)
        root.addWidget(button("Cerrar", self.reject))
        self.scenario.currentIndexChanged.connect(self._refresh)
        self._refresh()
        screen = self.screen().availableGeometry()
        self.resize(min(screen.width() - 24, 1040), min(screen.height() - 50, 740))

    def _simulation_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.status = note()
        layout.addWidget(self.status)
        form = QFormLayout()
        self.executable = QLineEdit(self.settings.value("sumo_executable", "", type=str))
        self.executable.setPlaceholderText("Detectar mediante PATH o SUMO_HOME")
        self.executable.textChanged.connect(self._update_availability)
        binary = QHBoxLayout()
        binary.addWidget(self.executable, 1)
        binary.addWidget(button("Buscar…", self._browse))
        form.addRow("Motor SUMO", binary)
        self.duration = spin(60, 7200, self.options.duration)
        self.warmup = spin(0, 1800, self.options.warmup)
        self.runs = spin(1, 12, self.options.runs)
        self.seed = spin(-1, 2_147_483_630, -1 if self.options.seed is None else self.options.seed)
        self.seed.setSpecialValueText("Automática")
        for label, value in (
            ("Medición (s)", self.duration),
            ("Calentamiento (s)", self.warmup),
            ("Corridas", self.runs),
            ("Semilla inicial", self.seed),
        ):
            form.addRow(label, value)
            value.valueChanged.connect(self._save_settings)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.run_button = button("Ejecutar microsimulación", self._execute)
        self.cancel_button = button("Cancelar ejecución", self._cancel)
        self.cancel_button.hide()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(button("Comportamiento vehicular…", self._behavior))
        layout.addLayout(buttons)
        self.operational = table(["Indicador", "HCNet", "SUMO · media", "DE", "IC 95 %"])
        layout.addWidget(self.operational, 1)
        self.run_table = table(
            [
                "Semilla",
                "Programados",
                "Insertados",
                "Arribos",
                "Viajes medidos",
                "Demora (s)",
                "Espera (s)",
                "Viaje (s)",
            ]
        )
        self.run_table.setMinimumHeight(110)
        layout.addWidget(self.run_table)
        self.run_note = note(
            "HCNet estima demora de control y cola P95. SUMO mide timeLoss y viajes completos "
            "en la red modelada, incluida la salida. La cola del cruce es la máxima extensión "
            "entre carriles en cada segundo. Los indicadores tienen definiciones distintas."
        )
        layout.addWidget(self.run_note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _environment_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        actions.addWidget(button("Composición y factores…", self._edit_fleet))
        actions.addWidget(button("Estimar ralentí", self._estimate))
        self.method = QComboBox()
        self.method.addItems(["SUMO", "Ralentí"])
        self.method.currentIndexChanged.connect(self._refresh_environment)
        actions.addWidget(self.method)
        self.pollutant = QComboBox()
        for key, unit in POLLUTANTS.items():
            self.pollutant.addItem(f"{key} ({unit})", key)
        self.pollutant.currentIndexChanged.connect(self._refresh_environment)
        actions.addWidget(self.pollutant)
        layout.addLayout(actions)
        self.environment_note = note()
        layout.addWidget(self.environment_note)
        self.category = StudyChart()
        self.evolution = StudyChart(line=True)
        self.comparison = StudyChart()
        for chart in (self.category, self.evolution, self.comparison):
            layout.addWidget(chart, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _save_settings(self, *_args) -> None:
        self.options = replace(
            self.options,
            duration=self.duration.value(),
            warmup=self.warmup.value(),
            runs=self.runs.value(),
            seed=None if self.seed.value() == -1 else self.seed.value(),
        )
        values = {
            "options": asdict(self.options),
            "fleet": [asdict(v) for v in self.fleet],
            "idle": self.idle,
        }
        if self.project.study_settings != values:
            self.project.study_settings.update(values)
            self.changed.emit()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar el binario sumo", self.executable.text()
        )
        if path:
            self.executable.setText(path)
            self.executable.editingFinished.emit()

    def _behavior(self) -> None:
        popup = QDialog(self)
        popup.setWindowTitle("Parámetros microscópicos")
        form = QFormLayout(popup)
        values = {}
        fields = (
            ("tau", "Tiempo de seguimiento (s)", 1.0, 5.0),
            ("min_gap", "Separación mínima (m)", 0.0, 15.0),
            ("accel", "Aceleración (m/s²)", 0.1, 10.0),
            ("decel", "Deceleración (m/s²)", 0.1, 12.0),
            ("strategic", "Cambio de carril estratégico", 0.0, 5.0),
        )
        for key, label, lower, upper in fields:
            values[key] = spin(lower, upper, getattr(self.options, key))
            form.addRow(label, values[key])
        form.addRow(self._dialog_buttons(popup))
        if popup.exec():
            self.options = replace(self.options, **{k: w.value() for k, w in values.items()})
            self._save_settings()

    @staticmethod
    def _dialog_buttons(popup: QDialog) -> QDialogButtonBox:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(popup.accept)
        buttons.rejected.connect(popup.reject)
        return buttons

    def _edit_fleet(self) -> None:
        popup = QDialog(self)
        popup.setWindowTitle("Composición y factores documentados")
        layout = QVBoxLayout(popup)
        layout.addWidget(
            note(
                "Cada grupo (ligeros y pesados) debe sumar 100 %. Para SUMO, indica una clase "
                "compatible con tu instalación (por ejemplo HBEFA3 o PHEMlight). Los factores son "
                "opcionalmente para ralentí, en g por vehículo-hora. Deja vacíos los desconocidos."
            )
        )
        entries = table(["Motorización", "%", "Clase SUMO", *IDLE_POLLUTANTS], editable=True)
        idle = self.idle.get("factors", {})
        fill(
            entries,
            [
                [
                    v.label,
                    v.percent,
                    v.emission_class,
                    *(idle.get(v.label, {}).get(k, "") for k in IDLE_POLLUTANTS),
                ]
                for v in self.fleet
            ],
        )
        for i in range(len(self.fleet)):
            item = entries.item(i, 0)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        layout.addWidget(entries)
        source = QLineEdit(self.idle.get("source", ""))
        source.setPlaceholderText("Fuente de los factores de ralentí")
        layout.addWidget(source)
        layout.addWidget(self._dialog_buttons(popup))
        popup.resize(820, 420)
        while popup.exec():
            try:
                fleet = tuple(
                    replace(
                        v,
                        percent=float(entries.item(i, 1).text()),
                        emission_class=entries.item(i, 2).text().strip(),
                    )
                    for i, v in enumerate(self.fleet)
                )
                validate_fleet(fleet, simulated=False)
                factors = {}
                for i, v in enumerate(fleet):
                    factors[v.label] = {
                        k: float(entries.item(i, j).text())
                        for j, k in enumerate(IDLE_POLLUTANTS, 3)
                        if entries.item(i, j).text().strip()
                    }
            except ValueError as exc:
                QMessageBox.warning(popup, "Revisa la composición", str(exc))
                continue
            self.fleet = fleet
            self.idle = {**self.idle, "source": source.text().strip(), "factors": factors}
            self._save_settings()
            return

    def _estimate(self) -> None:
        popup = QDialog(self)
        popup.setWindowTitle("Estimación de emisiones en ralentí")
        form = QFormLayout(popup)
        wait = spin(0.0, 3600.0, self.idle.get("waiting", 0))
        form.addRow("Espera observada en ralentí (s/veh)", wait)
        form.addRow(note(f"Periodo de medición: {self.duration.value()} s. Usa el aforo ajustado."))
        form.addRow(self._dialog_buttons(popup))
        if not popup.exec():
            return
        _, key, scenario = self.choices[self.scenario.currentIndex()]
        try:
            calculate_intersection(scenario)
            record = estimate_idle(
                scenario,
                self.fleet,
                self.duration.value(),
                wait.value(),
                self.idle.get("factors", {}),
                self.idle.get("source", ""),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Estimación pendiente", str(exc))
            return
        self.idle = {**self.idle, "waiting": wait.value()}
        self._save_settings()
        slot = self._study_slot(self.scenario.currentIndex(), key)
        slot["idle"] = record
        self.changed.emit()
        self._refresh()
        self.method.setCurrentIndex(1)

    def _update_availability(self, *_args) -> None:
        if not hasattr(self, "run_button") or self.worker is not None:
            return
        self.settings.setValue("sumo_executable", self.executable.text().strip())
        found = locate_sumo(self.executable.text().strip())
        _, _, scenario = self.choices[self.scenario.currentIndex()]
        try:
            calculate_intersection(scenario)
            ready = timeline(prepare_project(scenario)) is not None
        except ValueError:
            ready = False
        self.run_button.setEnabled(bool(found) and ready)
        if found:
            message = (
                f"Motor SUMO disponible · {found[0]}"
                if ready
                else ("Completa y evalúa la intersección para ejecutar SUMO.")
            )
        else:
            message = (
                "El motor SUMO no está disponible. El motor analítico de HCNet sigue disponible."
            )
        self.status.setText(message)

    def _execute(self) -> None:
        binaries = locate_sumo(self.executable.text().strip())
        if not binaries:
            self._update_availability()
            return
        self._save_settings()
        try:
            self.options.validate()
            validate_fleet(self.fleet, simulated=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Revisa la configuración", str(exc))
            return
        self.active_choice = self.scenario.currentIndex()
        _, _, scenario = self.choices[self.active_choice]
        self.worker = SimulationWorker(scenario, self.options, self.fleet, binaries, self)
        self.worker.progress.connect(self._progress)
        self.worker.completed.connect(self._completed)
        self.worker.cancelled.connect(self._cancelled)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.status.setText("Preparando red y demanda…")
        self.worker.start()

    def _progress(self, index: int, total: int) -> None:
        self.status.setText(f"SUMO · corrida {index} de {total}")

    def _study_slot(self, index: int, key: str) -> dict:
        label, _, scenario = self.choices[index]
        slot = self.project.studies.setdefault(key, {})
        slot.update({"snapshot": baseline_snapshot(scenario), "scenario_label": label})
        return slot

    def mark_capture_changed(self) -> None:
        self.capture_note.setText("La captura cambió. Abre de nuevo esta ventana para usarla.")
        self.capture_note.show()

    def _completed(self, record: dict) -> None:
        self._study_slot(self.active_choice, record["scenario_key"])["simulation"] = record
        self.changed.emit()
        self._refresh()
        self.status.setText(f"Experimento terminado · {len(record['runs'])} corridas.")

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Deteniendo SUMO…")

    def _cancelled(self) -> None:
        self.status.setText("Microsimulación cancelada.")

    def _failed(self, error: str) -> None:
        self.status.setText("La microsimulación terminó con un error.")
        if not self.cancel_close:
            QMessageBox.warning(self, "Error de microsimulación", error)

    def _finished(self) -> None:
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.cancel_button.hide()
        message = self.status.text()
        self._update_availability()
        self.status.setText(message)
        if self.cancel_close:
            self.cancel_close = False
            super().reject()

    def reject(self) -> None:
        self.queues.stop()
        if self.worker:
            self.cancel_close = True
            self._cancel()
        else:
            super().reject()

    def _refresh(self, *_args) -> None:
        _, key, scenario = self.choices[self.scenario.currentIndex()]
        self.record = self.project.studies.get(key, {})
        sim = self.record.get("simulation")
        self.queues.set_study(scenario, sim)
        self._show_metrics(scenario, sim)
        self._refresh_environment()
        self._update_availability()

    def _show_metrics(self, scenario: IntersectionProject, sim: dict | None) -> None:
        try:
            analytic = calculate_intersection(scenario)
            comparisons = {
                "Demora SUMO (timeLoss), s": analytic.weighted_control_delay_s_veh,
                "Duración de viaje, s": analytic.weighted_travel_time_s,
                "Cola P95 · extensión máxima instantánea, m": analytic.maximum_queue_95_m,
            }
        except ValueError:
            comparisons = {}
        stats = sim["metrics"] if sim else {}
        names = dict.fromkeys([*comparisons, *stats])
        rows = []
        for name in names:
            data = stats.get(name, {})
            ci = data.get("ci95")
            rows.append(
                [
                    name,
                    show_number(comparisons.get(name)),
                    show_number(data.get("mean")),
                    show_number(data.get("sd")),
                    f"[{ci[0]:.3g}, {ci[1]:.3g}]" if ci else "—",
                ]
            )
        fill(self.operational, rows)
        runs = sim["runs"] if sim else []
        fill(
            self.run_table,
            [
                [
                    r["seed"],
                    r["planned"],
                    r["departed"],
                    r["arrived"],
                    f"{r['completed']} de {r['cohort']}",
                    *(
                        show_number(r["metrics"].get(k))
                        for k in (
                            "Demora SUMO (timeLoss), s",
                            "Espera (<0.1 m/s), s",
                            "Duración de viaje, s",
                        )
                    ),
                ]
                for r in runs
            ],
        )

    def _refresh_environment(self, *_args) -> None:
        key = self.pollutant.currentData()
        unit = POLLUTANTS[key]
        sim = self.method.currentIndex() == 0
        engine = "simulation" if sim else "idle"
        result = self.record.get(engine)
        for chart in (self.category, self.evolution, self.comparison):
            chart.set_data([], [], unit)
        if not result:
            self.environment_note.setText(
                "Este escenario todavía no tiene resultados con este método."
            )
            return
        reference = self.project.studies.get(self.choices[0][1], {}).get(engine)
        if sim:
            self._show_simulated_emissions(result, key, unit)
        else:
            totals = result["by_type"]
            if key in result["totals"]:
                self.category.set_data(list(totals), [row[key] for row in totals.values()], unit)
            self.environment_note.setText(
                f"Escape en ralentí · {result['duration']} s · Fuente: {result['source']}."
            )
        comparison = emission_difference(reference, result, engine, key)
        if self.scenario.currentIndex() and comparison is not None:
            original, alternative, delta, percent = comparison
            suffix = f" ({percent:+.2f} %)" if percent is not None else ""
            self.comparison.set_data(["Actual", "Alternativa"], [original, alternative], unit)
            self.environment_note.setText(
                self.environment_note.text() + f" Cambio: {delta:+.4g} {unit}{suffix}."
            )

    def _show_simulated_emissions(self, result: dict, key: str, unit: str) -> None:
        runs, fleet = result["runs"], result["fleet"]
        labels = [v["label"] for v in fleet if v["percent"]]
        values = [
            sum(r["by_type"].get(f"v{i}", {}).get(key, 0) for r in runs) / len(runs)
            for i, v in enumerate(fleet)
            if v["percent"]
        ]
        self.category.set_data(labels, values, unit)
        series = unpack(runs[0]["emission_series"])
        start = result["options"]["warmup"]
        index = list(POLLUTANTS).index(key)
        self.evolution.set_data(
            [str(start), str(start + len(series) - 1)], [row[index] for row in series], f"{unit}/s"
        )
        self.environment_note.setText(
            f"{result['sumo']} · Totales medios por tipo · Serie de la corrida 1. "
            "Las emisiones son directas. La electricidad se expresa como energía."
        )
