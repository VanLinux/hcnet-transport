"""Herramientas de análisis avanzado de HCNet."""

import csv
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from threading import Event

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QTabWidget, QVBoxLayout, QWidget

from hcnet.domain.transit_catalog import catalog
from hcnet.domain.transit_engineering import evaluate
from hcnet.domain.transit_planning import MODELS, economics, fit, optimize, recommend, road_time
from hcnet.simulation.options import locate_sumo
from hcnet.simulation.runner import SimulationCancelled
from hcnet.simulation.transit import simulate_corridor
from hcnet.ui.transit_forms import (
    Form,
    button,
    fill_table,
    label,
    numeric,
    read_table,
    row,
    scroll,
    table,
)

INFRASTRUCTURE = tuple(dict.fromkeys(s["infrastructure"] for s in catalog()))
ROAD_FIELDS = [
    ("model", "Función", tuple(MODELS), ""),
    ("flow", "Flujo de vehículos (veh/h)", "", ""),
    ("capacity", "Capacidad vial (veh/h)", "", ""),
    ("t0", "Tiempo en flujo libre (min)", "", ""),
    ("alpha", "Alfa / j", "", ""),
    ("beta", "Beta · BPR", "", ""),
    ("fixed_t0", "Fijar el tiempo libre durante ajuste", False, ""),
    ("fixed_alpha", "Fijar alfa/j durante ajuste", False, ""),
    ("fixed_beta", "Fijar beta durante ajuste BPR", False, ""),
    (
        "compare",
        "Ajustar y comparar las cuatro funciones",
        False,
        "Usa los parámetros fijos comunes.",
    ),
]
ECON_FIELDS = [
    ("currency", "Moneda (por ejemplo MXN)", "", ""),
    ("hours", "Horas equivalentes al día", "", ""),
    ("days", "Días de operación al año", "", ""),
    ("paid", "Ascensos de pago por día", "", "No usar carga crítica por hora."),
    ("fare", "Tarifa media efectiva", "", ""),
    ("kilometer", "Costo por unidad-km", "", ""),
    ("fixed", "Costo fijo anual", "", ""),
    ("investment", "Inversión inicial", "", ""),
    ("years", "Horizonte (años)", "", ""),
    ("discount", "Tasa de descuento (0–1)", "", ""),
]
OPT_FIELDS = [
    ("minimum", "Intervalo mínimo (s)", "", ""),
    ("maximum", "Intervalo máximo (s)", "", ""),
    ("step", "Paso de búsqueda (s)", "", ""),
    ("fleet", "Límite de flota total (unid)", "", ""),
    ("cost", "Costo por unidad operativa-hora", "", ""),
    ("budget", "Presupuesto horario", "", ""),
    ("objective", "Objetivo", ("Espera", "Flota", "Costo", "Viaje", "Ocupación", "Pareto"), ""),
]
REC_FIELDS = [
    ("demand", "Demanda actual crítica (pax/h/sentido)", "", ""),
    ("growth", "Aumento para el escenario futuro (%)", "", ""),
    ("infra", "Infraestructura disponible o viable", "", "Nombres separados por punto y coma."),
    ("grade", "Pendiente máxima del corredor (%)", "", ""),
    ("radius", "Radio mínimo disponible (m)", "", ""),
    ("width", "Ancho disponible (m)", "", ""),
    ("budget", "Presupuesto comparable", "", ""),
    ("method", "Regla de ponderación", ("Ponderado", "TOPSIS"), ""),
    ("w1", "Peso de capacidad", "", ""),
    ("w2", "Peso de costo", "", ""),
    ("w3", "Peso de velocidad", "", ""),
    ("w4", "Peso de calidad", "", ""),
]
REC_HEADERS = (
    "Sistema",
    "Capacidad (pax/h/sentido)",
    "Costo comparable",
    "Vel. comercial (km/h)",
    "Calidad (escala común)",
    "Máx. pendiente (%)",
    "Mín. radio (m)",
    "Mín. ancho (m)",
    "Infraestructura",
    "Fuente / supuestos",
)
SUMO_FIELDS = [
    ("configuration", "Configuración de corredor (.sumocfg)", "", ""),
    ("prefix", "Prefijo de vehículos del servicio", "", ""),
    ("stop", "Parada común para intervalos", "", "ID de la parada SUMO."),
    ("lanes", "Carriles para colas (ID separados por ;)", "", ""),
    ("seed", "Semilla", "", ""),
]


def _notes_for_fit(result):
    notes = []
    if not result["converged"]:
        notes.append("El ajuste agotó las iteraciones. Revisa los parámetros y los residuos.")
    if result["boundary"]:
        notes.append("Parámetros en el límite de la búsqueda: " + ", ".join(result["boundary"]))
    return notes


class RoadTool(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(label("Congestión vial: trabaja con flujos y tiempos de un mismo tramo."))
        self.form = Form(ROAD_FIELDS, self.changed.emit)
        layout.addWidget(self.form)
        self.observations = table(("Flujo (veh/h)", "Tiempo (min)", "Muestra: ajuste o validación"))
        self.observations.cellChanged.connect(lambda *_: self.changed.emit())
        layout.addWidget(self.observations)
        layout.addWidget(
            row(
                button("Agregar observación", self._add),
                button("Eliminar observación", self._remove),
                button("Importar CSV…", self._import),
            )
        )
        layout.addWidget(
            label(
                "CSV con columnas flujo,tiempo,muestra. Usa punto decimal. "
                "Para evaluar directamente, deja vacía la tabla. "
                "Davidson sólo aplica cuando v/c < 1."
            )
        )
        self.notice = label("", "warningBanner")
        layout.addWidget(self.notice)

    def _add(self):
        self.observations.insertRow(self.observations.rowCount())

    def _remove(self):
        if self.observations.currentRow() >= 0:
            self.observations.removeRow(self.observations.currentRow())
            self.changed.emit()

    def _import(self):
        name, _ = QFileDialog.getOpenFileName(self, "Importar observaciones", "", "CSV (*.csv)")
        if not name:
            return
        try:
            with Path(name).open(encoding="utf-8-sig", newline="") as stream:
                data = csv.DictReader(stream)
                fields = [field.strip().casefold() for field in data.fieldnames or []]
                if len(fields) != len(set(fields)) or not {"flujo", "tiempo"} <= set(fields):
                    raise ValueError("El CSV requiere encabezados flujo,tiempo y opcional muestra.")
                data.fieldnames = fields
                values = [[r["flujo"], r["tiempo"], r.get("muestra", "ajuste")] for r in data]
                for q, t, phase in values:
                    numeric(q, "Flujo")
                    numeric(t, "Tiempo")
                    if phase not in {"", "ajuste", "validación", "validacion"}:
                        raise ValueError("Usa ajuste o validación en la columna muestra.")
            fill_table(self.observations, values)
            self.notice.clear()
            self.changed.emit()
        except (OSError, ValueError, csv.Error) as exc:
            self.notice.setText(str(exc))

    def state(self):
        return {"form": self.form.values(), "observations": read_table(self.observations)}

    def restore(self, state):
        self.form.set_values(state.get("form", {}))
        fill_table(self.observations, state.get("observations", []))

    def calculate(self):
        f = self.form
        model = f.value("model")
        capacity = f.number("capacity")
        if capacity <= 0:
            raise ValueError("La capacidad vial debe ser mayor que cero.")
        observed = read_table(self.observations)
        record = {
            "title": f"Congestión vial · {model}",
            "formulas": [MODELS[model]],
            "inputs": self.state(),
            "notes": [],
            "tables": [],
            "charts": [],
        }
        if not observed:
            flow, t0, alpha, beta = (
                f.number("flow"),
                f.number("t0"),
                f.number("alpha"),
                f.number("beta", 4),
            )
            if model == "BPR" and beta <= 0:
                raise ValueError("Beta debe ser positivo.")
            x = flow / capacity
            time = road_time(model, x, t0, alpha, beta)
            record["metrics"] = {
                "Grado de saturación": x,
                "Tiempo de viaje (min)": time,
                "Demora (min)": time - t0 if time is not None else None,
            }
            if time is None:
                record["notes"].append("La función no tiene un tiempo finito para este flujo.")
            maximum = max(1.15, x)
            series = [
                [xv, est]
                for i in range(81)
                if (est := road_time(model, xv := maximum * i / 80, t0, alpha, beta)) is not None
            ]
            graph = {model: series}
            if time is not None:
                graph["Flujo evaluado"] = [[x, time]]
            record["charts"].append(
                {"title": "Tiempo estimado por saturación", "x": "v/c", "y": "min", "series": graph}
            )
            return record
        samples, validation = [], []
        for flow, travel, role in observed:
            role = role.strip().casefold()
            if role not in {"", "ajuste", "validación", "validacion"}:
                raise ValueError("Usa ajuste o validación en la columna muestra.")
            dataset = validation if role.startswith("valida") else samples
            dataset.append((numeric(flow, "Flujo"), numeric(travel, "Tiempo")))
        models = tuple(MODELS) if f.value("compare") else (model,)
        record["formulas"] = [MODELS[name] for name in models]
        rows = []
        for name in models:
            fixed = {
                k: f.number(k)
                for k in ("t0", "alpha", "beta")
                if f.value(f"fixed_{k}") and (k != "beta" or name == "BPR")
            }
            try:
                result = fit(name, samples, capacity, fixed, validation)
            except ValueError as exc:
                if len(models) == 1:
                    raise
                record["notes"].append(f"{name}: {exc}")
                continue
            p, c, v = (result[key] for key in ("parameters", "calibration", "validation"))
            rows.append(
                [
                    name,
                    p["t0"],
                    p["alpha"],
                    p.get("beta"),
                    c["r2"],
                    c["rmse"],
                    c["mae"],
                    v.get("r2"),
                    v.get("rmse"),
                    v.get("mae"),
                ]
            )
            record["notes"].extend(f"{name}: {note}" for note in _notes_for_fit(result))
            points = [*c["points"], *v.get("points", [])]
            record["tables"].append(
                (
                    f"Residuos · {name}",
                    ["v/c", "Observado (min)", "Estimado (min)", "Residuo (min)"],
                    points,
                )
            )
            graph = {
                "Ajuste observado": [[x, t] for x, t, *_ in c["points"]],
                "Estimado": sorted([[x, y] for x, _, y, _ in points]),
            }
            if v:
                graph["Validación observada"] = [[x, t] for x, t, *_ in v["points"]]
            record["charts"].append(
                {
                    "title": f"Tiempos observados y estimados · {name}",
                    "x": "v/c",
                    "y": "min",
                    "series": graph,
                    "markers": ["Ajuste observado", "Validación observada"],
                }
            )
        if not rows:
            raise ValueError("Ningún ajuste fue válido. " + " ".join(record["notes"]))
        record["tables"].insert(
            0,
            (
                "Comparación estadística",
                [
                    "Modelo",
                    "t₀",
                    "Alfa/j",
                    "Beta",
                    "R² ajuste",
                    "RMSE ajuste",
                    "MAE ajuste",
                    "R² validación",
                    "RMSE validación",
                    "MAE validación",
                ],
                rows,
            ),
        )
        return record


class TechnologyTool(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.form = Form(REC_FIELDS, self.changed.emit)
        layout.addWidget(label("Infraestructura de referencia: " + ", ".join(INFRASTRUCTURE) + "."))
        layout.addWidget(self.form)
        self.candidates = table(REC_HEADERS)
        self.candidates.cellChanged.connect(lambda *_: self.changed.emit())
        layout.addWidget(self.candidates)
        layout.addWidget(
            row(
                button("Agregar los ocho sistemas", self._add),
                button("Agregar alternativa", self._blank),
            )
        )
        layout.addWidget(
            label(
                "Introduce capacidad, costo y calidad comparables para cada candidato. "
                "Indica cero si una restricción de geometría no aplica. "
                "Los casos con datos faltantes aparecen como pendientes."
            )
        )

    def _add(self):
        existing = read_table(self.candidates)
        included = {r[0] for r in existing}
        for system in catalog():
            if system["name"] not in included:
                existing.append(
                    [system["name"], "", "", "", "", "", "", "", system["infrastructure"]]
                )
        fill_table(self.candidates, existing)
        self.changed.emit()

    def _blank(self):
        self.candidates.insertRow(self.candidates.rowCount())

    def state(self):
        return {"form": self.form.values(), "candidates": read_table(self.candidates)}

    def restore(self, state):
        self.form.set_values(state.get("form", {}))
        fill_table(self.candidates, state.get("candidates", []))

    def calculate(self):
        f = self.form
        candidates = []
        for name, *values, infra, source in read_table(self.candidates):
            if not name:
                raise ValueError("Identifica cada tecnología candidata.")
            keys = ("capacity", "cost", "speed", "quality", "grade", "radius", "width")
            candidate = {
                key: numeric(value, key) if value else None
                for key, value in zip(keys, values, strict=True)
            }
            candidates.append(candidate | {"name": name, "infra": infra, "source": source})
        if not candidates:
            raise ValueError("Agrega al menos una tecnología candidata.")
        growth = f.number("growth", 0)
        if growth < 0:
            raise ValueError("El crecimiento futuro debe ser no negativo.")
        demand = f.number("demand", 0)
        future = demand * (1 + growth / 100)
        result = recommend(
            candidates,
            future,
            {s.strip() for s in f.value("infra").split(";") if s.strip()},
            f.number("grade"),
            budget=f.number("budget", 0),
            radius=f.number("radius", 0),
            width=f.number("width", 0),
            weights=tuple(f.number(f"w{i}", 1) for i in range(1, 5)),
            method=f.value("method"),
        )
        ranking = result["ranking"]
        winner = ranking[0]["name"] if ranking else "Sin alternativa verificable"
        return {
            "title": "Selección preliminar de tecnología",
            "metrics": {
                "Primera alternativa elegible": winner,
                "Demanda actual (pax/h)": demand,
                "Demanda futura de diseño (pax/h)": future,
                "Método de ordenación": f.value("method"),
            },
            "inputs": self.state(),
            "notes": [
                "Los resultados dependen de las condiciones físicas y costos capturados. "
                "Verifica la factibilidad antes de definir la inversión."
            ],
            "tables": [
                (
                    "Alternativas elegibles",
                    [
                        "Sistema",
                        "Puntaje",
                        "Oferta (pax/h)",
                        "Costo",
                        "Vel. (km/h)",
                        "Calidad",
                        "Fuente",
                    ],
                    [
                        [
                            r["name"],
                            r["score"],
                            r["capacity"],
                            r["cost"],
                            r["speed"],
                            r["quality"],
                            r["source"],
                        ]
                        for r in ranking
                    ],
                ),
                (
                    "Alternativas excluidas o pendientes",
                    ["Sistema", "Restricciones", "Pendiente"],
                    [
                        [r["name"], ", ".join(r["reasons"]), ", ".join(r["pending"])]
                        for r in result["excluded"]
                    ],
                ),
                (
                    "Sensibilidad de pesos",
                    ["Criterio", "Multiplicador", "Primera alternativa"],
                    result["sensitivity"],
                ),
            ],
        }


class SumoTool(QWidget):
    changed = Signal()
    complete = Signal(dict)

    def __init__(self, line):
        super().__init__()
        self.line = line
        self.future = None
        self.cancel = Event()
        self.discard = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hcnet-transit")
        self.timer = QTimer(self, interval=150)
        self.timer.timeout.connect(self._poll)
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                "Simula un corredor vial propio. La configuración debe incluir red y rutas. "
                "Usa un prefijo exclusivo del servicio; la parada común permite medir intervalos."
            )
        )
        self.form = Form(SUMO_FIELDS, self.changed.emit)
        layout.addWidget(self.form)
        self.stop = button("Cancelar corrida", self.cancel.set)
        self.stop.setEnabled(False)
        layout.addWidget(row(button("Elegir configuración…", self._choose), self.stop))
        self.status = label("")
        layout.addWidget(self.status)

    def _choose(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Configuración SUMO", "", "Configuración SUMO (*.sumocfg)"
        )
        if filename:
            self.form.set_values({"configuration": filename})

    def start(self):
        if self.line.system()["technology"] != "road":
            raise ValueError("SUMO de corredor se habilita para sistemas viales.")
        if self.future is not None:
            raise ValueError("Ya hay una corrida en curso.")
        found = locate_sumo()
        if not found:
            raise ValueError("Instala SUMO y netconvert en PATH para simular el corredor.")
        f = self.form
        if not f.value("configuration") or not f.value("prefix"):
            raise ValueError("Selecciona el archivo SUMO y un prefijo de servicio.")
        self.cancel.clear()
        self.discard = False
        self.started_values = self.form.values()
        self.future = self.pool.submit(
            simulate_corridor,
            f.value("configuration"),
            found[0],
            f.value("prefix"),
            f.value("stop"),
            tuple(s.strip() for s in f.value("lanes").split(";") if s.strip()),
            f.whole("seed", 42),
            self.cancel,
        )
        self.status.setText("SUMO está calculando el corredor…")
        self.stop.setEnabled(True)
        self.form.setEnabled(False)
        self.timer.start()

    def reset(self):
        if self.future is not None:
            self.discard = True
            self.cancel.set()

    def _poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.timer.stop()
        self.stop.setEnabled(False)
        self.form.setEnabled(True)
        if self.discard:
            self.status.clear()
            return
        try:
            result = future.result()
        except SimulationCancelled:
            self.status.setText("Corrida cancelada.")
            return
        except Exception as exc:
            self.status.setText(f"SUMO: {exc}")
            return
        self.status.setText("Corrida terminada.")
        self.complete.emit(
            {
                "title": "Microsimulación del corredor vial",
                "inputs": self.started_values
                | {k: result[k] for k in ("seed", "version", "source_hash", "configuration")},
                "metrics": {
                    "Viajes completos": len(result["trips"]),
                    "Viaje medio (s)": result["travel_mean_s"],
                    "Tiempo perdido medio (s)": result["delay_mean_s"],
                    "Velocidad global (km/h)": result["speed_kmh"],
                    "Permanencia media (s)": result["dwell_mean_s"],
                    "Intervalo medio observado (min)": result["quality"]["observed_mean"],
                    "Coeficiente de variación": result["quality"]["cv"],
                    "Salidas simultáneas, excluidas del CV": result["same_time_departures"],
                },
                "notes": [
                    "Colas de tránsito por carril. Ascensos y descensos requieren pasajeros "
                    "explícitos en el modelo SUMO."
                ],
                "tables": [
                    (
                        "Viajes completos",
                        [
                            "Vehículo",
                            "Duración (s)",
                            "Distancia (m)",
                            "Pérdida (s)",
                            "En espera (s)",
                            "Retraso al salir (s)",
                            "Salida (s)",
                            "Llegada (s)",
                        ],
                        [list(r.values()) for r in result["trips"]],
                    ),
                    (
                        "Paradas registradas",
                        [
                            "Vehículo",
                            "Parada",
                            "Detención (s)",
                            "Salida (s)",
                            "Ascensos registrados",
                            "Descensos registrados",
                        ],
                        [list(r.values()) for r in result["stops"]],
                    ),
                    (
                        "Cola máxima vial",
                        ["Carril", "Longitud (m)"],
                        list(result["queues"].items()),
                    ),
                ],
                "charts": [
                    {
                        "title": "Intervalos observados en la parada",
                        "x": "Observación",
                        "y": "min",
                        "series": {"Intervalo": list(enumerate(result["headways_min"], 1))},
                    }
                ]
                if result["headways_min"]
                else [],
            }
        )


class AdvancedTools(QWidget):
    changed = Signal()

    def __init__(self, line):
        super().__init__()
        self.line = line
        self.alternative = None
        self.baseline = None
        self.original_line = None
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.road = RoadTool()
        self.road.changed.connect(self.changed)
        self.tabs.addTab(scroll(self.road), "Congestión y calibración")
        self.econ = Form(ECON_FIELDS, self.changed.emit)
        self.tabs.addTab(scroll(self.econ), "Economía")
        search = QWidget()
        box = QVBoxLayout(search)
        self.options = Form(OPT_FIELDS, self.changed.emit)
        box.addWidget(self.options)
        box.addWidget(
            row(
                button("Fijar configuración original", self._baseline),
                button("Capturar configuración alternativa", self._alternative),
            )
        )
        self.compare_status = label(
            "Fijar el original es opcional. Cambia puertas o estaciones en Servicio para "
            "capturar una segunda configuración. La búsqueda conserva el original."
        )
        box.addWidget(self.compare_status)
        self.tabs.addTab(scroll(search), "Optimización")
        self.sumo = SumoTool(line)
        self.sumo.changed.connect(self.changed)
        self.tabs.addTab(scroll(self.sumo), "Microsimulación SUMO")

    def _baseline(self):
        self.baseline = self.line.state()
        self.compare_status.setText("Configuración original capturada.")
        self.changed.emit()

    def _alternative(self):
        self.alternative = self.line.state()
        self.compare_status.setText("Configuración alternativa capturada.")
        self.changed.emit()

    def state(self):
        return {
            "road": self.road.state(),
            "econ": self.econ.values(),
            "opt": self.options.values(),
            "sumo": self.sumo.form.values(),
            "baseline": self.baseline,
            "alternative": self.alternative,
            "tab": self.tabs.currentIndex(),
        }

    def restore(self, state):
        self.sumo.reset()
        for form, specs, key in (
            (self.econ, ECON_FIELDS, "econ"),
            (self.options, OPT_FIELDS, "opt"),
            (self.sumo.form, SUMO_FIELDS, "sumo"),
            (self.road.form, ROAD_FIELDS, "road"),
        ):
            form.set_values(
                {
                    k: default[0] if isinstance(default, tuple) else default
                    for k, _, default, _ in specs
                }
            )
            if key != "road":
                form.set_values(state.get(key, {}))
        self.road.restore(state.get("road", {}))
        self.baseline = state.get("baseline")
        self.alternative = state.get("alternative")
        self.tabs.setCurrentIndex(max(0, min(3, state.get("tab", 0))))
        self.compare_status.setText(
            f"Original: {'capturado' if self.baseline else 'captura actual'}. "
            f"Alternativa: {'capturada' if self.alternative else 'sin captura'}."
        )

    def calculate(self):
        index = self.tabs.currentIndex()
        if index == 0:
            if self.line.system()["technology"] != "road":
                raise ValueError(
                    "Las funciones volumen–demora viales se aplican a un sistema vial."
                )
            return self.road.calculate()
        if index == 3:
            self.sumo.start()
            return None
        if index == 1:
            line = self.line.service()
            service = evaluate(line)
            f = self.econ
            data = economics(
                service["frequency"],
                line.length_km,
                f.number("hours"),
                f.number("days"),
                f.number("paid"),
                f.number("fare"),
                f.number("kilometer"),
                f.number("fixed", 0),
                investment=f.number("investment", 0),
                years=f.whole("years", 0),
                discount=f.number("discount", 0),
                currency=f.value("currency") or "MXN",
            )
            money = data["currency"]
            return {
                "title": "Evaluación económica de operación",
                "inputs": {"line": asdict(line), "financial": f.values()},
                "formulas": [
                    r"K_{a}=2LfH\,D,\quad I_a=P_d\,D\,\tau",
                    r"C_a=K_a c_{km}+C_f,\quad S_a=\max(0,C_a-I_a)",
                ],
                "notes": [
                    "Costos e ingresos constantes para el horizonte indicado. "
                    "No incluye externalidades ni ampliaciones de demanda."
                ],
                "metrics": {
                    "Vehículo-km/año": data["annual_km"],
                    f"Ingreso anual ({money})": data["revenue"],
                    f"Costo anual ({money})": data["cost"],
                    f"Saldo anual ({money})": data["balance"],
                    f"Subsidio requerido ({money})": data["subsidy"],
                    f"Costo por ascenso ({money})": data["cost_per_boarding"],
                    "Cobertura de costos": data["coverage"],
                    f"Valor presente neto ({money})": data["npv"],
                },
            }
        from dataclasses import replace

        current = self.line.state()
        try:
            if self.baseline is not None:
                self.line.set_state(self.baseline)
            original = self.line.service()
            candidates = ()
            if self.alternative is not None:
                self.line.set_state(self.alternative)
                candidate = self.line.service()
                if original.technology != candidate.technology:
                    raise ValueError("La comparación operacional requiere la misma tecnología.")
                if original.demand != candidate.demand:
                    raise ValueError("Usa la misma demanda crítica en la comparación.")
                candidates = (replace(candidate, name=candidate.name + " · alternativa"),)
        finally:
            self.line.set_state(current)
        f = self.options
        result = optimize(
            original,
            f.number("minimum"),
            f.number("maximum"),
            f.number("step"),
            f.whole("fleet"),
            f.number("cost", 0),
            f.number("budget", 0),
            f.value("objective"),
            candidates,
        )
        base = result["original"]
        rows = result["alternatives"]
        summary = []
        if rows:
            best = rows[0]
            for title, before, after in (
                ("Frecuencia (unid/h)", base["frequency"], 3600 / best["headway_s"]),
                ("Flota total", base["fleet_total"], best["fleet"]),
                ("Oferta alcanzable (pax/h)", base["achievable"], best["offer"]),
                ("Espera regular equivalente (min)", base["headway"] / 2, best["wait"]),
                (
                    "Velocidad comercial ida (km/h)",
                    base["commercial_kmh"][0],
                    60 * original.length_km / best["travel_min"][0],
                ),
                ("Costo horario", base["fleet"] * f.number("cost", 0), best["cost"]),
                ("Permanencia total, ida + regreso (s)", sum(base["dwell_total_s"]), best["dwell"]),
                ("Frecuencia máxima (unid/h)", base["max_frequency"], best["station_limit"]),
            ):
                summary.append([title, before, after, after - before])
        return {
            "title": "Optimización operacional",
            "metrics": {"Objetivo": result["objective"], "Candidatos tabulados": len(rows)},
            "notes": [
                "Espera equivalente bajo servicio regular y llegadas uniformes. "
                "El original se conserva."
            ]
            + ([] if rows else ["No hay alternativa factible."]),
            "inputs": {
                "original": asdict(original),
                "alternatives": [asdict(c) for c in candidates],
                "search": f.values(),
            },
            "tables": [
                (
                    "Cambio frente al original",
                    ["Indicador", "Original", "Alternativa", "Diferencia"],
                    summary,
                ),
                (
                    "Alternativas factibles",
                    [
                        "Configuración",
                        "Intervalo (s)",
                        "Espera (min)",
                        "Flota",
                        "Costo/h",
                        "Oferta",
                        "Margen",
                        "Ciclo",
                    ],
                    [
                        [
                            r[k]
                            for k in (
                                "name",
                                "headway_s",
                                "wait",
                                "fleet",
                                "cost",
                                "offer",
                                "margin",
                                "cycle",
                            )
                        ]
                        for r in rows
                    ],
                ),
            ],
            "charts": [
                {
                    "title": "Compromiso entre espera y flota",
                    "x": "Espera (min)",
                    "y": "Flota (unid)",
                    "series": {"Factibles": [[r["wait"], r["fleet"]] for r in rows]},
                    "markers": ["Factibles"],
                }
            ]
            if rows
            else [],
        }
