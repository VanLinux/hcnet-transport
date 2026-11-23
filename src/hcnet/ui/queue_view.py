"""Esquema y reproducción de las colas observadas por SUMO."""

from collections import defaultdict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.models import IntersectionProject
from hcnet.domain.signals import prepare_project
from hcnet.simulation.results import unpack
from hcnet.ui.charts import IntersectionSketch


class QueueView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.record: dict | None = None
        self.project: IntersectionProject | None = None
        self.queue: list = []
        self.stopped: list = []
        self.signals: list = []
        self.enqueued: list = []
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.run = QComboBox()
        self.run.currentIndexChanged.connect(self._load_run)
        self.by_lane = QCheckBox("Por carril")
        self.by_lane.toggled.connect(self._draw_frame)
        self.clock = QSpinBox()
        self.clock.setSuffix(" s")
        self.clock.valueChanged.connect(self._draw_frame)
        self.play = QPushButton("Reproducir")
        self.play.clicked.connect(self._play_pause)
        self.reset = QPushButton("Reiniciar")
        self.reset.clicked.connect(self._reset)
        for widget in (self.run, self.by_lane, self.clock, self.play, self.reset):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.source = QLabel()
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.sketch = IntersectionSketch()
        layout.addWidget(self.sketch, 1)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._step)

    def stop(self) -> None:
        self.timer.stop()
        self.play.setText("Reproducir")

    def set_study(self, project: IntersectionProject, record: dict | None) -> None:
        self.stop()
        self.project, self.record = project, record
        self.sketch.set_project(project)
        self.run.blockSignals(True)
        self.run.clear()
        if record:
            self.run.addItems(
                [f"Corrida {i + 1} · semilla {r['seed']}" for i, r in enumerate(record["runs"])]
            )
        self.run.blockSignals(False)
        for item in (self.clock, self.run, self.by_lane, self.play, self.reset):
            item.setEnabled(record is not None)
        self._load_run()

    def _load_run(self, *_args) -> None:
        self.stop()
        if self.record and self.run.currentIndex() >= 0:
            run = self.record["runs"][self.run.currentIndex()]
            self.queue = unpack(run["queue_series"])
            self.stopped = unpack(run["stopped_series"])
            self.signals = unpack(run["signal_series"])
            self.enqueued = unpack(run["in_queue_series"])
            start = self.record["options"]["warmup"]
            self.clock.setRange(start, start + len(self.queue) - 1)
            self.clock.setValue(start)
        else:
            self.queue, self.stopped = [], []
        self._draw_frame()

    def _reset(self) -> None:
        self.stop()
        self.clock.setValue(self.clock.minimum())

    def _step(self) -> None:
        if self.clock.value() < self.clock.maximum():
            self.clock.stepUp()
        else:
            self.stop()

    def _play_pause(self) -> None:
        if self.timer.isActive():
            self.stop()
        else:
            if self.clock.value() == self.clock.maximum():
                self.clock.setValue(self.clock.minimum())
            self.play.setText("Pausar")
            self.timer.start()

    def _draw_frame(self, *_args) -> None:
        self.sketch.active_phase = None
        self.sketch.queue_bands = {}
        if self.queue and self.record:
            self._draw_simulated()
        elif self.project:
            self._draw_static()
        self.sketch.update()

    def _draw_simulated(self) -> None:
        record = self.record
        assert record is not None
        time = self.clock.value()
        index = time - record["options"]["warmup"]
        if not 0 <= index < len(self.queue):
            return
        phase, states = self.signals[index]
        self.sketch.active_phase = -1
        state = "Todo rojo"
        if "g" in states.lower():
            self.sketch.active_phase = phase
            state = f"Fase {phase} · verde"
        elif "y" in states.lower():
            state = f"Fase {phase} · amarillo"
        self.source.setText(
            f"SUMO · t = {time} s · {state} · Detenidos en accesos: "
            f"{sum(self.stopped[index])} (velocidad < 0.1 m/s)"
        )
        per_branch = defaultdict(list)
        warnings = []
        for (branch, lane, storage), value, count in zip(
            record["lanes"],
            self.queue[index],
            self.enqueued[index],
            strict=True,
        ):
            per_branch[branch].append((lane, value, storage, count))
            if value >= storage - 1:
                warnings.append(f"{branch}, carril {lane}: cola cerca del extremo del acceso.")
            if self.by_lane.isChecked():
                self.sketch.queue_bands[branch, lane] = value / storage
        run = record["runs"][self.run.currentIndex()]
        lines = []
        for branch, values in per_branch.items():
            instant = max(q for _, q, _, _ in values)
            if not self.by_lane.isChecked():
                self.sketch.queue_bands[branch, None] = max(
                    q / length for _, q, length, _ in values
                )
            stat = run["branches"][branch]
            lane_text = (
                " · " + ", ".join(f"c{lane}: {value:.1f} m" for lane, value, _, _ in values)
                if self.by_lane.isChecked()
                else ""
            )
            enqueued = sum(count for _, _, _, count in values)
            lines.append(
                f"{branch}: {instant:.1f} m · {enqueued} veh detenidos en la cola · "
                f"media {stat['mean']:.1f} · "
                f"máx. {stat['max']:.1f} · P95 {stat['p95']:.1f} m{lane_text}"
            )
        self.summary.setText("\n".join(lines + warnings))

    def _draw_static(self) -> None:
        assert self.project
        self.source.setText("HCNet · Cola P95 aproximada por ramal (estimación estática)")
        try:
            prepared = prepare_project(self.project)
            result = calculate_intersection(prepared)
        except ValueError as exc:
            self.summary.setText(str(exc))
            return
        lengths = defaultdict(float)
        notes = []
        for group, row in zip(prepared.lane_groups, result.lane_groups, strict=True):
            branch = group.origin_branch
            lengths[branch] = max(lengths[branch], row.queue_95_m)
            fraction = row.queue_95_m / group.approach_length_m
            key = (branch, None)
            self.sketch.queue_bands[key] = max(self.sketch.queue_bands.get(key, 0), fraction)
            if fraction > 1:
                notes.append(f"{group.label}: P95 supera el almacenamiento.")
        self.summary.setText(
            "\n".join(
                [f"Ramal {branch}: {value:.1f} m" for branch, value in lengths.items()] + notes
            )
        )
