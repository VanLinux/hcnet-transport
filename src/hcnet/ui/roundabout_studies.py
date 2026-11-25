"""Herramientas avanzadas de calibración y experimentos vehiculares."""

import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.roundabout_engineering import Site
from hcnet.domain.roundabout_planning import accepted_gap, calibrate
from hcnet.simulation.options import SimulationOptions, locate_sumo
from hcnet.simulation.results import unpack
from hcnet.simulation.roundabout import simulate_roundabouts
from hcnet.simulation.runner import SimulationCancelled
from hcnet.ui.roundabout_canvas import RoundCanvas
from hcnet.ui.transit_forms import (
    Form,
    button,
    fill_table,
    label,
    numeric,
    read_table,
    row,
    table,
)
from hcnet.ui.transit_layout import AdaptiveColumns

CALIBRATION = ("Exponencial", "Brechas", "Lineal", "Brechas aceptadas/rechazadas")
SETTINGS = [
    ("duration", "Medición (s)", "900", "Paso de salida de 1 s."),
    ("warmup", "Calentamiento (s)", "180", ""),
    ("runs", "Corridas", "3", "Entre 1 y 12."),
    ("seed", "Primera semilla", "42", "Se incrementa en cada corrida."),
    ("tau", "Tiempo de seguimiento SUMO (s)", "1", "Parámetro tau del modelo vehicular."),
    ("min_gap", "Separación mínima (m)", "2.5", ""),
    ("accel", "Aceleración (m/s²)", "2.6", ""),
    ("decel", "Desaceleración (m/s²)", "4.5", ""),
    ("strategic", "Cambio de carril estratégico", "1", ""),
    ("engine", "Ejecutable SUMO (opcional)", "", "También se detecta en PATH y SUMO_HOME."),
    ("light", "Clase de emisión ligeros", "", "Vacío: HBEFA3/PC_G_EU4."),
    ("heavy", "Clase de emisión pesados", "", "Vacío: HBEFA3/HDV_D_EU4."),
    ("bus", "Clase de emisión autobús", "", "Vacío: HBEFA3/Bus."),
    ("moto", "Clase de emisión motocicleta", "", "Vacío: aproximación HBEFA3/PC_G_EU4."),
]


class CalibrationPane(QWidget):
    changed = Signal()
    applied = Signal(dict)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.method = QComboBox()
        self.method.addItems(CALIBRATION)
        layout.addWidget(self.method)
        self.method.currentIndexChanged.connect(self._switch)
        self.notice = label("Usa aforos de descarga en saturación. CSV: flujo,capacidad,muestra.")
        layout.addWidget(self.notice)
        self.data = table(("Flujo conflictivo (eq/h)", "Capacidad (eq/h)", "Muestra"))
        self.data.cellChanged.connect(self._changed)
        layout.addWidget(self.data, 1)
        layout.addWidget(
            row(
                button("Agregar fila", self._add),
                button("Eliminar fila", self._remove),
                button("Importar CSV…", self._import),
                button("Aplicar el ajuste", self._apply),
            )
        )
        self.cached = {}
        self.gaps = []
        self.counts = []
        self._previous = 0
        self._loading = False

    def _add(self):
        self.data.insertRow(self.data.rowCount())

    def _remove(self):
        if self.data.currentRow() >= 0:
            self.data.removeRow(self.data.currentRow())
            self._changed()

    def _changed(self, *_):
        self.cached = {}
        if not self._loading:
            self.changed.emit()

    def _switch(self, index):
        if not self._loading:
            if self._previous == 3:
                self.gaps = read_table(self.data)
            else:
                self.counts = read_table(self.data)
        gaps = index == 3
        self.data.setHorizontalHeaderLabels(
            ["Rechazo máximo (s)", "Aceptación (s)", "Nota"]
            if gaps
            else ["Flujo conflictivo (eq/h)", "Capacidad (eq/h)", "Muestra"]
        )
        self.notice.setText(
            "Captura pares por conductor. CSV: rechazo,aceptacion."
            if gaps
            else "Usa aforos de descarga en saturación. "
            "CSV: flujo,capacidad,muestra. Muestras: ajuste y validación."
        )
        fill_table(self.data, self.gaps if gaps else self.counts)
        self._previous = index
        self._changed()

    def _import(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir observaciones", "", "CSV (*.csv)")
        if not filename:
            return
        try:
            with Path(filename).open(encoding="utf-8-sig", newline="") as stream:
                fields = (
                    ("rechazo", "aceptacion")
                    if self.method.currentIndex() == 3
                    else ("flujo", "capacidad", "muestra")
                )
                reader = csv.DictReader(stream)
                if not set(fields[:2]) <= set(reader.fieldnames or []):
                    raise ValueError("Encabezados esperados: " + ", ".join(fields))
                rows = [[r.get(k, "") or "" for k in fields] for r in reader]
                for values in rows:
                    numeric(values[0], fields[0])
                    numeric(values[1], fields[1])
            fill_table(self.data, rows)
            self._changed()
        except (OSError, ValueError, csv.Error) as exc:
            self.notice.setText(str(exc))

    def calculate(self):
        raw = read_table(self.data)
        if self.method.currentIndex() == 3:
            data = [(numeric(a, "rechazo"), numeric(b, "aceptación")) for a, b, _ in raw]
            result = accepted_gap(data)
            record = {
                "title": "Brechas individuales · lognormal censurada por intervalo",
                "metrics": {
                    "Brecha crítica mediana (s)": result["median"],
                    "Brecha crítica media (s)": result["mean"],
                    "N": result["n"],
                    "Desv. estándar logarítmica": result["sigma_log"],
                },
                "notes": ["Revisa identificabilidad; parámetro en el límite."]
                if result["at_bound"]
                else [],
                "inputs": {"pares": raw},
            }
            return record
        from hcnet.domain.roundabout_reporting import calibration_record

        rows = []
        for x, y, p in raw:
            phase = p.lower() or "ajuste"
            if phase not in ("ajuste", "validación", "validacion"):
                raise ValueError("Selecciona ajuste o validación en cada observación.")
            rows.append(
                (
                    numeric(x, "Flujo"),
                    numeric(y, "Capacidad"),
                    "validación" if phase.startswith("valid") else phase,
                )
            )
        result = calibrate(rows, self.method.currentText())
        self.cached = result
        return calibration_record(result, rows)

    def _apply(self):
        if self.cached:
            self.applied.emit(self.cached)
        else:
            self.notice.setText("Ejecuta primero la calibración por flujos.")

    def state(self):
        current = read_table(self.data)
        gaps = self.method.currentIndex() == 3
        return {
            "index": self.method.currentIndex(),
            "gaps": current if gaps else self.gaps,
            "counts": self.counts if gaps else current,
            "fit": self.cached,
        }

    def restore(self, state):
        self._loading = True
        self.gaps = state.get("gaps", [])
        self.counts = state.get("counts", [])
        index = state.get("index", 0)
        self.method.setCurrentIndex(index)
        self._switch(index)
        self.cached = state.get("fit", {})
        self._loading = False


class RoundReplay(QWidget):
    def __init__(self):
        super().__init__()
        self.record = None
        self.original = None
        self.loaded = []
        layout = QVBoxLayout(self)
        self.scene = QComboBox()
        self.run = QComboBox()
        self.scene.currentIndexChanged.connect(self._load)
        self.run.currentIndexChanged.connect(self._load)
        self.speed = QComboBox()
        self.speed.addItems(("1×", "2×", "4×", "8×"))
        self.speed.currentIndexChanged.connect(self._pace)
        self.by_lane = QCheckBox("Por carril")
        self.by_lane.setChecked(True)
        self.by_lane.toggled.connect(self._draw)
        layout.addWidget(AdaptiveColumns(self.scene, self.run, self.speed, self.by_lane))
        self.clock = QSlider(Qt.Orientation.Horizontal)
        self.clock.valueChanged.connect(self._draw)
        layout.addWidget(self.clock)
        self.play = button("Reproducir", self._play)
        layout.addWidget(row(self.play, button("Reiniciar", self._reset)))
        self.heading = label("Ejecuta el escenario para reproducir colas observadas.")
        layout.addWidget(self.heading)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.base = RoundCanvas()
        self.current = RoundCanvas()
        self.split.addWidget(self.base)
        self.split.addWidget(self.current)
        layout.addWidget(self.split, 1)
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self._step)

    def _pace(self, index):
        self.timer.setInterval(1000 // (2**index))

    def set_record(self, record, original):
        self._stop()
        self.record, self.original = record, original
        self.scene.blockSignals(True)
        self.run.blockSignals(True)
        self.scene.clear()
        self.run.clear()
        if record:
            self.scene.addItems([s["name"] for s in record["scenarios"]])
            self.scene.setCurrentIndex(len(record["scenarios"]) - 1)
            self.run.addItems([f"Semilla {i}" for i in record["seeds"]])
        self.scene.blockSignals(False)
        self.run.blockSignals(False)
        self._load()

    def _load(self, *_):
        self._stop()
        self.loaded = []
        if not self.record or self.scene.currentIndex() < 0 or self.run.currentIndex() < 0:
            self.base.hide()
            self.current.set_site(None)
            self._draw()
            return
        selected = self.record["scenarios"][self.scene.currentIndex()]
        baseline = self.record["scenarios"][0]
        self.base.setVisible(selected is not baseline)
        for canvas, item in ((self.base, baseline), (self.current, selected)):
            run = item["runs"][self.run.currentIndex()]
            canvas.circular = item["site"] is not None
            canvas.set_site(Site.from_dict(item["site"]) if canvas.circular else self.original)
            self.loaded.append((canvas, item, unpack(run["queue_series"])))
        start = self.record["options"]["warmup"]
        self.clock.setRange(start, start + len(self.loaded[-1][2]) - 1)
        self.clock.setValue(start)
        self._draw()

    def _draw(self, *_):
        if not self.loaded:
            self.heading.setText("Ejecuta el escenario para reproducir colas observadas.")
            return
        seconds = self.clock.value()
        frame = seconds - self.clock.minimum()
        labels = []
        for canvas, data, series in self.loaded:
            if canvas is self.base and canvas.isHidden():
                continue
            values = series[frame]
            queues = {(k, j): v for (k, j, _), v in zip(data["lanes"], values, strict=True)}
            if not self.by_lane.isChecked():
                maximum = {
                    k: max(value for (a, _), value in queues.items() if a == k) for k, _ in queues
                }
                queues = {(k, j): maximum[k] for k, j in queues}
            canvas.queue = queues
            canvas.update()
            labels.append(f"{data['name']}: máxima instantánea {max(values, default=0):.1f} m")
        self.heading.setText(f"SUMO · t = {seconds} s · " + " · ".join(labels))

    def _stop(self):
        self.timer.stop()
        self.play.setText("Reproducir")

    def _reset(self):
        self._stop()
        self.clock.setValue(self.clock.minimum())

    def _play(self):
        if self.timer.isActive():
            self._stop()
        elif self.loaded:
            if self.clock.value() == self.clock.maximum():
                self.clock.setValue(self.clock.minimum())
            self.play.setText("Pausar")
            self.timer.start()

    def _step(self):
        if self.clock.value() == self.clock.maximum():
            self._stop()
        else:
            self.clock.setValue(self.clock.value() + 1)


class SimulationPane(QWidget):
    changed = Signal()
    complete = Signal(dict)
    progress = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hcnet-rotonda")
        self.future = None
        self.cancel = Event()
        self.discard = False
        self.archive = None
        self.record = None
        self.timer = QTimer(self, interval=150)
        self.timer.timeout.connect(self._poll)
        layout = QVBoxLayout(self)
        self.form = Form(
            SETTINGS,
            self.changed.emit,
            second_column={
                "engine",
                "tau",
                "min_gap",
                "accel",
                "decel",
                "strategic",
                "light",
                "heavy",
                "bus",
                "moto",
            },
        )
        layout.addWidget(self.form)
        self.paired = QCheckBox("Incluir el original semaforizado, si está importado")
        self.paired.toggled.connect(lambda _: self.changed.emit())
        self.alternatives = QCheckBox("Incluir las primeras dos alternativas editables")
        self.alternatives.toggled.connect(lambda _: self.changed.emit())
        layout.addWidget(self.paired)
        layout.addWidget(self.alternatives)
        self.stop = button("Cancelar corrida", self.cancel.set)
        self.stop.setEnabled(False)
        layout.addWidget(
            row(
                button("Elegir binario…", self._choose_engine),
                button("Exportar insumos y salidas al simular…", self._archive),
                self.stop,
            )
        )
        self.status = label(
            "Usa el motor central de SUMO. Se simulan vehículos con el mismo calendario OD."
        )
        layout.addWidget(self.status)
        layout.addStretch()
        self.progress.connect(self._progress)

    def _choose_engine(self):
        name, _ = QFileDialog.getOpenFileName(self, "Elegir ejecutable sumo")
        if name:
            self.form.set_values({"engine": name})

    def _archive(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para nuevos archivos de corrida")
        if folder:
            self.archive = Path(folder)
            self.status.setText(
                "La próxima corrida guardará insumos y salidas en la carpeta elegida."
            )

    def _progress(self, current, total):
        if self.future is not None:
            self.status.setText(f"SUMO · corrida {current} de {total}")

    def run(self, scenarios, original=None):
        if self.future is not None:
            raise ValueError("Ya hay una simulación en curso.")
        f = self.form
        binary = locate_sumo(f.value("engine"))
        if not binary:
            raise ValueError("SUMO y netconvert del mismo paquete deben estar disponibles.")
        options = SimulationOptions(
            duration=f.whole("duration"),
            warmup=f.whole("warmup"),
            runs=f.whole("runs"),
            seed=f.whole("seed") if f.value("seed") else None,
            tau=f.number("tau"),
            min_gap=f.number("min_gap"),
            accel=f.number("accel"),
            decel=f.number("decel"),
            strategic=f.number("strategic"),
        )
        options.validate()
        self.cancel.clear()
        self.discard = False
        self.future = self.pool.submit(
            simulate_roundabouts,
            scenarios,
            options,
            binary,
            self.cancel,
            progress=self.progress.emit,
            original=original,
            archive=self.archive,
            classes={k: f.value(k) for k in ("light", "heavy", "bus", "moto")},
        )
        self.archive = None
        self.stop.setEnabled(True)
        self.form.setEnabled(False)
        self.timer.start()

    def _poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.timer.stop()
        self.stop.setEnabled(False)
        self.form.setEnabled(True)
        if self.discard:
            return
        try:
            self.record = future.result()
        except SimulationCancelled:
            self.status.setText("Corrida cancelada.")
        except Exception as exc:
            self.status.setText(str(exc))
        else:
            self.status.setText("Experimento terminado. Consulta Resultados y Colas de SUMO.")
            self.complete.emit(self.record)

    def reset(self):
        self.cancel.set()
        self.discard = True

    def state(self):
        return {
            "form": self.form.values(),
            "paired": self.paired.isChecked(),
            "alternatives": self.alternatives.isChecked(),
            "record": self.record,
        }

    def restore(self, state):
        self.reset()
        self.record = state.get("record")
        self.form.set_values({key: value for key, _, value, _ in SETTINGS} | state.get("form", {}))
        self.paired.setChecked(state.get("paired", False))
        self.alternatives.setChecked(state.get("alternatives", False))
