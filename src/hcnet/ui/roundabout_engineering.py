"""Área de ingeniería de rotondas, captura común y resultados por modalidad."""

import csv
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.models import IntersectionProject
from hcnet.domain.roundabout_engineering import (
    KINDS,
    METHODS,
    MODES,
    Site,
    design_geometry,
    evaluate,
    from_legacy,
    safety,
)
from hcnet.domain.roundabout_planning import (
    compare_designs,
    design,
    import_intersection,
    intersection_metrics,
    same_demand,
)
from hcnet.domain.roundabout_reporting import (
    comparison_record,
    geometry_record,
    operational_record,
    simulation_record,
)
from hcnet.io.project import load_project
from hcnet.simulation.results import unpack
from hcnet.ui.roundabout_canvas import RoundCanvas
from hcnet.ui.roundabout_capture import (
    DemandEditor,
    GeometryEditor,
    arm_form,
    initial_arms,
    movement_rows,
)
from hcnet.ui.roundabout_studies import CalibrationPane, RoundReplay, SimulationPane
from hcnet.ui.transit_forms import Form, ResultPanel, button, label, numeric, row, scroll
from hcnet.ui.transit_layout import AdaptiveColumns, TransitPages, TransitPanels

SITE_SPECS = [
    ("name", "Nombre del estudio", "", ""),
    ("kind", "Tipo de rotonda", ("Un carril", *[k for k in KINDS if k != "Un carril"]), ""),
    ("lanes", "Carriles circulantes", "1", "Los modelos analíticos se limitan a su ámbito."),
    (
        "direction",
        "Sentido y lado de conducción",
        ("Antihorario", "Horario"),
        "Horario: izquierda.",
    ),
    ("method", "Método principal", METHODS, ""),
    ("diameter", "Diámetro inscrito (m)", "", ""),
    ("island", "Diámetro de isla, incluida la corona (m)", "", ""),
    ("width", "Ancho de calzada circulante (m)", "", ""),
    ("apron", "Ancho de corona transitable (m)", "", ""),
    ("speed", "Velocidad objetivo o del anillo (km/h)", "", ""),
    ("period", "Duración del periodo (h)", ".25", ""),
    ("spacing", "Longitud más separación en cola (m)", "7.5", "Supuesto de conversión de P95."),
    ("available_diameter", "Diámetro máximo disponible (m)", "", ""),
    ("available_area", "Superficie disponible (m²)", "", ""),
    ("space_width", "Ancho rectangular disponible (m)", "", ""),
    ("space_length", "Largo rectangular disponible (m)", "", ""),
    ("critical_gap", "Brecha crítica (s)", "", ""),
    ("followup", "Seguimiento entre entradas (s)", "", ""),
    ("linear_a", "Intercepto lineal (eq/h)", "", ""),
    ("linear_b", "Pendiente lineal", "", ""),
    ("linear_min", "Límite inferior lineal (eq/h)", "", ""),
    ("linear_max", "Límite superior lineal (eq/h)", "", ""),
    ("model_source", "Fuente del modelo local y brechas", "", ""),
    ("hybrid", "Calcular demora híbrida para capacidades alternativas", False, ""),
    ("heavy_eq", "Equivalencia de pesados", "2", ""),
    ("bus_eq", "Equivalencia de autobuses", "2", ""),
    ("motorcycle_eq", "Equivalencia de motos", "1", ""),
    ("crossfall", "Pendiente transversal (%)", "-2", ""),
    ("friction", "Coeficiente de fricción lateral", ".2", ""),
    (
        "vehicle_name",
        "Vehículo de diseño",
        (
            "Sin estudio",
            "Automóvil",
            "Comercial ligero",
            "Autobús urbano",
            "Autobús articulado",
            "Camión rígido",
            "Tractocamión",
            "Personalizado",
        ),
        "",
    ),
    ("vehicle_width", "Ancho de vehículo (m)", "", ""),
    ("vehicle_length", "Longitud total de vehículo (m)", "", ""),
    ("wheelbase", "Distancia entre ejes (m)", "", ""),
    ("minimum_turn", "Radio mínimo comprobado (m)", "", ""),
]
LOCKS = [
    ("diameter", "Fijar diámetro inscrito"),
    ("width", "Fijar ancho circulante"),
    ("island", "Fijar isla"),
    ("lanes", "Fijar carriles circulantes"),
    ("kind", "Fijar tipo"),
]
SCENARIOS = [
    ("objective", "Objetivo de comparación", "Demora", ""),
    ("weights", "Pesos demora; cola; saturación; área", "4;2;2;1", "Sólo multicriterio."),
    (
        "control",
        "Control de original manual",
        ("Prioridad sin semáforo", "Alto", "Semaforizado", "Observación de campo"),
        "",
    ),
    ("observed_delay", "Demora de control observada (s/veh)", "", ""),
    ("observed_queue", "Cola P95 observada (m)", "", ""),
    ("observed_source", "Fuente y fecha de observaciones", "", ""),
]
OBJECTIVES = ("Demora", "Cola", "Saturación", "Capacidad", "Superficie", "Multicriterio")


def initial_form(specs):
    return {k: (v[0] if isinstance(v, tuple) else v) for k, _, v, _ in specs}


class RoundaboutEngineering(QWidget):
    changed = Signal()
    export_requested = Signal(dict)
    ANALYSIS, DESIGN, OPTIMIZE, CONVERT = range(4)

    def __init__(self, current_project, legacy):
        super().__init__()
        self.setObjectName("publicTransport")
        self.project_reader = current_project
        self.legacy_reader = legacy
        self._loading = True
        self.records = {}
        self.displayed = None
        self.report_key = ""
        self.original = None
        self.candidates = []
        self.original_site = None
        self.optimization_baseline = None
        self.fitted = {}
        self.demo = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.mode.setAccessibleName("Modalidad de rotonda")
        self.advanced = QCheckBox("Modo avanzado")
        run = button("Calcular", self.run_current)
        run.setObjectName("primaryButton")
        layout.addWidget(
            AdaptiveColumns(
                self.mode,
                row(run, button("Caso demostrativo…", self._demo), wrap=False),
                self.advanced,
                stretches=(3, 2, 1),
            )
        )
        self.status = label("Configura los accesos y la demanda del estudio.", "infoBanner")
        layout.addWidget(self.status)
        capture = QWidget()
        box = QVBoxLayout(capture)
        box.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        box.addWidget(self.tabs, 1)
        self.demand = DemandEditor()
        self.geometry = GeometryEditor(self.demand)
        self.geometry.axes_changed.connect(self.demand.refresh)
        self.geometry.connected.connect(self.demand.toggle_route)
        self.geometry.notice_requested.connect(self.status.setText)
        self.demand.selected.connect(self._highlight)
        self.geometry.changed.connect(self._changed)
        self.demand.changed.connect(self._changed)
        self.tabs.addTab(scroll(self.geometry), "Constructor")
        self.tabs.addTab(scroll(self.demand), "Demanda OD")
        self.settings = Form(
            SITE_SPECS,
            self._parameters,
            second_column={
                "available_diameter",
                "available_area",
                "space_width",
                "space_length",
                "critical_gap",
                "followup",
                "linear_a",
                "linear_b",
                "linear_min",
                "linear_max",
                "model_source",
                "hybrid",
                "heavy_eq",
                "bus_eq",
                "motorcycle_eq",
                "crossfall",
                "friction",
                "vehicle_name",
                "vehicle_width",
                "vehicle_length",
                "wheelbase",
                "minimum_turn",
            },
        )
        values = QWidget()
        vb = QVBoxLayout(values)
        vb.addWidget(self.settings)
        self.locks = {key: QCheckBox(title) for key, title in LOCKS}
        for check in self.locks.values():
            check.toggled.connect(self._changed)
        vb.addWidget(AdaptiveColumns(*self.locks.values()))
        vb.addWidget(
            row(
                button("Importar geometría .json…", self._import_site),
                button("Exportar geometría .json…", self._export_site),
                button("Usar captura clásica", self._import_legacy),
                button("Aplicar dimensiones calculadas", self._apply_dimensions),
            )
        )
        vb.addStretch()
        self.tabs.addTab(scroll(values), "Modelo y dimensiones")
        scen = QWidget()
        sb = QVBoxLayout(scen)
        self.scenario = Form(
            [(k, t, OBJECTIVES if k == "objective" else v, tip) for k, t, v, tip in SCENARIOS],
            self._changed,
        )
        self.original_notice = label("Original: sin captura archivada.")
        sb.addWidget(self.original_notice)
        sb.addWidget(
            row(
                button("Importar intersección de este proyecto", self._import_current),
                button("Importar de un .hcnet…", self._import_project),
            )
        )
        self.picker = QComboBox()
        self.picker.setAccessibleName("Alternativa de rotonda")
        self.picker.currentIndexChanged.connect(self._compare_view)
        sb.addWidget(self.picker)
        sb.addWidget(
            row(
                button("Cargar alternativa para edición", self._use_candidate),
                button("Fijar original manual", self._manual),
            )
        )
        self.compare_sketch = QSplitter(Qt.Orientation.Horizontal)
        self.compare_buttons = row(
            button("Ampliar original", lambda: self._show_sketches(True, False)),
            button("Ver ambos", lambda: self._show_sketches(True, True)),
            button("Ampliar propuesta", lambda: self._show_sketches(False, True)),
        )
        sb.addWidget(self.compare_buttons)
        self.original_canvas = RoundCanvas()
        self.candidate_canvas = RoundCanvas()
        self.compare_sketch.addWidget(self.original_canvas)
        self.compare_sketch.addWidget(self.candidate_canvas)
        sb.addWidget(self.compare_sketch, 1)
        sb.addWidget(self.scenario)
        self.scenario_tab = self.tabs.addTab(scroll(scen), "Original y alternativas")
        self.calibration = CalibrationPane()
        self.calibration.changed.connect(self._calibration_changed)
        self.calibration.applied.connect(self._apply_fit)
        self.cal_tab = self.tabs.addTab(scroll(self.calibration), "Calibración")
        self.simulation = SimulationPane()
        self.simulation.changed.connect(self._sim_changed)
        self.simulation.complete.connect(self._simulation_complete)
        self.sim_tab = self.tabs.addTab(scroll(self.simulation), "SUMO")
        results = QWidget()
        rb = QVBoxLayout(results)
        rb.setContentsMargins(0, 0, 0, 0)
        self.report_selector = QComboBox()
        self.report_selector.currentIndexChanged.connect(self._display)
        self.tex = button("Exportar .tex…", self._export)
        self.csv = button("CSV…", self._csv)
        rb.addWidget(AdaptiveColumns(self.report_selector, row(self.tex, self.csv, wrap=False)))
        self.present = QTabWidget()
        self.present.setDocumentMode(True)
        rb.addWidget(self.present, 1)
        self.result_panel = ResultPanel()
        self.result_scroll = scroll(self.result_panel)
        self.present.addTab(self.result_scroll, "Indicadores")
        self.result_canvas = RoundCanvas()
        self.present.addTab(scroll(self.result_canvas), "Esquema y cola P95")
        self.replay = RoundReplay()
        self.replay_tab = self.present.addTab(scroll(self.replay), "Colas de SUMO")
        self.panels = TransitPanels(capture, results)
        pages = TransitPages()
        pages.addWidget(self.panels)
        layout.addWidget(scroll(pages), 1)
        self.mode.currentIndexChanged.connect(self._mode)
        self.advanced.toggled.connect(self._mode)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.set_state({})

    def _mode(self, *_):
        advanced = self.advanced.isChecked()
        self.tabs.setTabVisible(self.cal_tab, advanced)
        self.tabs.setTabVisible(self.sim_tab, advanced)
        self.present.setTabVisible(self.replay_tab, advanced)
        self.geometry.set_advanced(advanced)
        self.scenario.visible(("weights",), advanced)
        manual = self.mode.currentIndex() == self.CONVERT and not self.original
        self.scenario.visible(
            ("control", "observed_delay", "observed_queue", "observed_source"), manual
        )
        self.settings.visible(
            (
                "crossfall",
                "friction",
                "vehicle_name",
                "vehicle_width",
                "vehicle_length",
                "wheelbase",
                "minimum_turn",
            ),
            advanced,
        )
        method = self.settings.controls["method"]
        has_kimber = method.findText("Kimber") >= 0
        if advanced and not has_kimber:
            method.addItem("Kimber")
        elif has_kimber and not advanced:
            method.removeItem(method.findText("Kimber"))
        self._refresh_reports()
        if not self._loading:
            self.changed.emit()

    def _tab_changed(self, *_):
        if self._loading:
            return
        key = (
            "calibration"
            if self.tabs.currentIndex() == self.cal_tab
            else ("simulation" if self.tabs.currentIndex() == self.sim_tab else "")
        )
        if key and self.report_selector.findData(key) >= 0:
            self.report_selector.setCurrentIndex(self.report_selector.findData(key))

    def _parameters(self):
        if self._loading:
            return
        kind = self.settings.value("kind")
        if kind != "Personalizada":
            count = {
                "Minirotonda": 1,
                "Compacta": 1,
                "Un carril": 1,
                "Dos carriles": 2,
                "Multicarril": 3,
                "Turborrotonda": 2,
            }.get(kind)
            if self.settings.value("lanes") == "" or (
                kind != getattr(self, "_last_kind", kind) and count is not None
            ):
                self._loading = True
                self.settings.set_values({"lanes": count})
                self._loading = False
        self._last_kind = kind
        self._changed()

    def site(self, *, render=False):
        defaults = Site()
        data = {}
        for key, _, _, _ in SITE_SPECS:
            default = getattr(defaults, key)
            if isinstance(default, bool) or isinstance(default, str):
                data[key] = self.settings.value(key)
            elif key == "lanes":
                data[key] = self.settings.whole(key, default)
            else:
                data[key] = self.settings.number(key, default)
        fitted = self.fitted
        if fitted and data["method"] == "HCM":
            data.update({f"fitted_{k}": v for k, v in fitted.items()})
        data["vehicle_name"] = "" if data["vehicle_name"] == "Sin estudio" else data["vehicle_name"]
        data["driving"] = "Derecha" if data["direction"] == "Antihorario" else "Izquierda"
        data["locks"] = tuple(key for key, box in self.locks.items() if box.isChecked())
        return Site(
            arms=self.geometry.arms(), movements=() if render else self.demand.parsed(), **data
        )

    def _changed(self, *_):
        if self._loading:
            return
        for key, record in self.records.items():
            if key != "calibration":
                record["stale"] = True
        self._redraw()
        self._refresh_reports()
        if any(r.get("stale") for r in self.records.values()):
            self.status.setText("Captura modificada. Calcula de nuevo para actualizar resultados.")
        self.changed.emit()

    def _calibration_changed(self):
        if not self._loading:
            if "calibration" in self.records:
                self.records["calibration"]["stale"] = True
            self._refresh_reports()
            self.changed.emit()

    def _sim_changed(self):
        if not self._loading:
            if "simulation" in self.records:
                self.records["simulation"]["stale"] = True
            self._refresh_reports()
            self.changed.emit()

    def _highlight(self, a, b):
        self.geometry.canvas.link = (a, b)
        self.geometry.canvas.update()

    def _redraw(self):
        try:
            s = self.site(render=True)
            g = None
            if sum(bool(v) for v in (s.diameter, s.island, s.width)) >= 2:
                try:
                    g = design_geometry(s)
                except ValueError:
                    pass
            self.geometry.canvas.set_site(s, g)
            try:
                routes = self.demand.parsed()
                self.geometry.canvas.traffic = (
                    {
                        arm.code: sum(r.volume for r in routes if r.origin == arm.code)
                        for arm in s.arms
                    }
                    if routes
                    else {}
                )
            except ValueError:
                self.geometry.canvas.traffic = {}
        except (ValueError, ArithmeticError):
            return

    def _apply_fit(self, fit):
        model = fit["model"]
        if model == "Lineal":
            self.settings.set_values({"linear_" + k: fit[k] for k in ("a", "b", "min", "max")})
            self.settings.set_values({"method": "Lineal"})
        elif model == "Brechas":
            self.settings.set_values(
                {"critical_gap": fit["critical"], "followup": fit["followup"], "method": "Brechas"}
            )
        else:
            self.fitted = {k: fit[k] for k in ("a", "b", "min", "max")}
            self.settings.set_values({"method": "HCM"})
        self.settings.set_values({"model_source": "Ajuste local con datos de capacidad saturada."})
        self.status.setText("Ajuste aplicado a la captura.")

    def _archive_original(self, project):
        site = import_intersection(project)
        self.original = json.loads(
            json.dumps(
                replace(
                    project, roundabout_engineering={}, transit_engineering={}, studies={}
                ).to_dict(),
                ensure_ascii=False,
            )
        )
        physical = {b.code: b for b in project.active_branches}
        self.original_site = replace(
            site,
            arms=tuple(
                replace(
                    a,
                    inbound=physical[a.code].inbound_lanes,
                    outbound=physical[a.code].outbound_lanes,
                )
                for a in site.arms
            ),
        ).to_dict()
        self._load_site(site)
        self.mode.setCurrentIndex(self.CONVERT)
        self.original_notice.setText(f"Original semaforizado archivado · {project.name}")
        self._mode()
        self._changed()

    def _import_current(self):
        try:
            self._archive_original(self.project_reader())
        except (ValueError, ArithmeticError) as exc:
            self.status.setText(str(exc))

    def _import_project(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Importar intersección", "", "HCNet (*.hcnet *.json)"
        )
        if filename:
            try:
                self._archive_original(load_project(filename))
            except (OSError, ValueError, TypeError, ArithmeticError) as exc:
                self.status.setText(str(exc))

    def _manual(self):
        try:
            site = self.site()
            from hcnet.domain.roundabout_engineering import network

            network(site)
            self.original_site = site.to_dict()
            if self.mode.currentIndex() == self.OPTIMIZE:
                self.optimization_baseline = self.original_site
            self.original = None
            self.original_notice.setText(
                "Original manual archivado. Se comparará con aforos iguales."
            )
            self._changed()
        except (ValueError, ArithmeticError) as exc:
            self.status.setText(str(exc))

    def _apply_dimensions(self):
        result = self.records.get("geometry")
        if not result or result.get("stale"):
            self.status.setText("Calcula el diseño antes de aplicar sus dimensiones.")
            return
        geometry = result["geometry"]
        self.settings.set_values(
            {
                key: geometry[key]
                for key in ("diameter", "width", "island")
                if not self.locks[key].isChecked()
            }
        )

    def _import_legacy(self):
        try:
            self._load_site(from_legacy(self.legacy_reader()))
            self._changed()
        except (ValueError, ArithmeticError) as exc:
            self.status.setText(str(exc))

    def _import_site(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir geometría", "", "JSON (*.json)")
        if filename:
            try:
                payload = json.loads(Path(filename).read_text(encoding="utf-8"))
                site = Site.from_dict(payload)
                from hcnet.domain.roundabout_engineering import network

                network(site)
                self._load_site(site)
                self._changed()
            except (OSError, ValueError, TypeError, ArithmeticError) as exc:
                self.status.setText(str(exc))

    def _save_file(self, title, suggestion, extension, writer):
        filename, _ = QFileDialog.getSaveFileName(
            self, title, suggestion, f"{extension.upper()} (*.{extension})"
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != f".{extension}":
            path = path.with_suffix(f".{extension}")
        try:
            writer(path)
            self.status.setText(f"Archivo guardado: {path.name}")
        except (OSError, ValueError, ArithmeticError) as exc:
            self.status.setText(str(exc))

    def _export_site(self):
        self._save_file(
            "Exportar configuración",
            "rotonda.json",
            "json",
            lambda p: p.write_text(
                json.dumps(self.site().to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            ),
        )

    def _load_site(self, site):
        was_loading = self._loading
        self._loading = True
        self._last_kind = site.kind
        if site.method == "Kimber":
            self.advanced.setChecked(True)
        self.settings.set_values(
            {k: v for k, v in site.to_dict().items() if k in self.settings.controls}
        )
        self.settings.set_values({"vehicle_name": site.vehicle_name or "Sin estudio"})
        self.fitted = (
            {k: getattr(site, f"fitted_{k}") for k in ("a", "b", "min", "max")}
            if site.fitted_a
            else {}
        )
        for k, box in self.locks.items():
            box.setChecked(k in site.locks)
        self.geometry.set_data({a.code: arm_form(a) for a in site.arms})
        self.demand.set_data([a.code for a in site.arms], movement_rows(site.movements))
        self._loading = was_loading
        self._redraw()

    def _show_sketches(self, base, candidate):
        self.original_canvas.setVisible(base)
        self.candidate_canvas.setVisible(candidate)

    def _compare_view(self, *_):
        i = self.picker.currentIndex()
        if i < 0 or i >= len(self.candidates):
            self.original_canvas.set_site(None)
            self.candidate_canvas.set_site(None)
            self.compare_sketch.hide()
            self.compare_buttons.hide()
            return
        self.compare_sketch.show()
        self.compare_buttons.show()
        candidate = self.candidates[i]
        original = (
            Site.from_dict(self.original_site) if self.original_site else self.site(render=True)
        )
        self.original_canvas.circular = self.mode.currentIndex() != self.CONVERT
        diameters = [
            s for s in [original.diameter, (candidate.get("geometry") or {}).get("diameter")] if s
        ]
        scale = max(diameters, default=40) / 2
        for canvas in (self.original_canvas, self.candidate_canvas):
            canvas.same_scale = scale
        self.original_canvas.set_site(original)
        self.candidate_canvas.set_site(Site.from_dict(candidate["site"]), candidate.get("geometry"))

    def _use_candidate(self):
        i = self.picker.currentIndex()
        if 0 <= i < len(self.candidates):
            self._load_site(Site.from_dict(self.candidates[i]["site"]))
            self.tabs.setCurrentIndex(0)
            self._changed()

    def _comparison(self, site):
        conversion = self.mode.currentIndex() == self.CONVERT
        weights = [numeric(s, "Peso") for s in self.scenario.value("weights").split(";")]
        baseline = (
            Site.from_dict(self.optimization_baseline)
            if self.optimization_baseline and not conversion
            else site
        )
        if not conversion and not same_demand(baseline, site):
            raise ValueError(
                "La nueva captura cambió el aforo. Fija un nuevo original para compararla."
            )
        record = compare_designs(
            site,
            conversion=conversion,
            advanced=self.advanced.isChecked(),
            weights=weights,
            objective=self.scenario.value("objective"),
        )
        if not conversion:
            if not self.optimization_baseline:
                self.optimization_baseline = site.to_dict()
            self.original_site = self.optimization_baseline
            original = evaluate(baseline, advanced=self.advanced.isChecked())["overall"]
        elif self.original:
            original = intersection_metrics(IntersectionProject.from_dict(self.original))
            if (
                abs(original["demand"] - sum(m.volume / m.phf for m in site.movements if m.enabled))
                > 0.01
            ):
                raise ValueError(
                    "La demanda de la propuesta debe coincidir con la intersección original."
                )
            if not same_demand(
                import_intersection(IntersectionProject.from_dict(self.original)), site
            ):
                raise ValueError(
                    "Conserva los pares OD, los factores pico y la composición originales."
                )
        elif self.original_site:
            manual = Site.from_dict(self.original_site)
            if not same_demand(manual, site):
                raise ValueError("Conserva la demanda OD y la composición del original manual.")
            original = {"demand": sum(m.volume / m.phf for m in manual.movements)}
            if self.scenario.value("observed_source"):
                original["delay"] = (
                    self.scenario.number("observed_delay", 0)
                    if self.scenario.value("observed_delay")
                    else None
                )
                original["queue_m"] = (
                    self.scenario.number("observed_queue", 0)
                    if self.scenario.value("observed_queue")
                    else None
                )
        else:
            raise ValueError("Importa una intersección o fija la captura manual como original.")
        self.candidates = record["alternatives"]
        self._fill_candidates()
        result = comparison_record(record, original, site)
        if conversion:
            controls = self.scenario.values()
            result["notes"].append(
                "Original semaforizado evaluado con el módulo de intersecciones."
                if self.original
                else "Original manual. Se incluyen sólo métricas de "
                "campo con fuente y el control registrado."
            )
            result["inputs"]["original_control"] = controls
            result["inputs"]["original"] = self.original_site
        return result

    def _fill_candidates(self):
        self.picker.blockSignals(True)
        self.picker.clear()
        self.picker.addItems([r["label"] for r in self.candidates])
        self.picker.setCurrentIndex(0 if self.candidates else -1)
        self.picker.blockSignals(False)
        self._compare_view()

    def run_current(self):
        try:
            if self.advanced.isChecked() and self.tabs.currentIndex() == self.cal_tab:
                self._record("calibration", self.calibration.calculate())
                return True
            site = self.site()
            if self.advanced.isChecked() and self.tabs.currentIndex() == self.sim_tab:
                candidates = [("Rotonda capturada", site)]
                if self.simulation.alternatives.isChecked():
                    candidates.extend(
                        (r["label"], Site.from_dict(r["site"]))
                        for r in [a for a in self.candidates if a["preliminary"]][:2]
                    )
                original = (
                    IntersectionProject.from_dict(self.original)
                    if (self.original and self.simulation.paired.isChecked())
                    else None
                )
                self.simulation.run(candidates, original)
                self._sim_fingerprint = (
                    self.settings.values(),
                    self.geometry.raw.copy(),
                    self.demand.values(),
                    self.simulation.form.values(),
                )
                self.status.setText("Corrida iniciada. Consulta el estado en SUMO.")
                return True
            mode = self.mode.currentIndex()
            if mode == self.DESIGN:
                proposed, geometry = design(site)
                record = geometry_record(proposed, geometry, safety(proposed, geometry))
                self._record("geometry", record)
            elif mode in (self.OPTIMIZE, self.CONVERT):
                self._record("comparison", self._comparison(site))
            else:
                result = evaluate(site, advanced=self.advanced.isChecked())
                self._record(
                    "operation",
                    operational_record(site, result)
                    | {
                        "geometry": result["geometry"],
                        "queue_bands": [
                            [r["arm"], r["lane"], r["queue_m"]]
                            for r in result["lanes"]
                            if r["queue_m"] is not None
                        ],
                    },
                )
                if self.advanced.isChecked() and result["geometry"]:
                    geometry = result["geometry"]
                    self._record(
                        "safety",
                        geometry_record(site, geometry, safety(site, geometry)),
                        focus=False,
                    )
            return True
        except (ValueError, ArithmeticError, OSError, TypeError) as exc:
            self.status.setText(str(exc))
            return False

    def _simulation_complete(self, data):
        current = (
            self.settings.values(),
            self.geometry.raw.copy(),
            self.demand.values(),
            self.simulation.form.values(),
        )
        self._record(
            "simulation",
            simulation_record(data)
            | {"stale": current != getattr(self, "_sim_fingerprint", current)},
        )
        self.replay.set_record(
            data, Site.from_dict(self.original_site) if self.original_site else None
        )

    def _record(self, key, record, *, focus=True):
        if self.demo:
            record.setdefault("notes", []).insert(
                0, f"Caso demostrativo: {self.demo}. Datos hipotéticos."
            )
        self.records[key] = record
        if focus:
            self.report_key = key
        self._refresh_reports()
        if focus and self.panels.tabs.currentIndex() == self.panels.CAPTURE:
            self.panels.tabs.setCurrentIndex(self.panels.RESULTS)
        self.status.setText("Análisis terminado. " + ("Caso demostrativo." if self.demo else ""))
        self.changed.emit()

    def _refresh_reports(self):
        self.report_selector.blockSignals(True)
        self.report_selector.clear()
        for key, record in self.records.items():
            if key in ("simulation", "calibration", "safety") and not self.advanced.isChecked():
                continue
            title = record["title"] + (" · Por actualizar" if record.get("stale") else "")
            self.report_selector.addItem(title, key)
        i = self.report_selector.findData(self.report_key)
        self.report_selector.setCurrentIndex(max(0, i))
        self.report_selector.blockSignals(False)
        self._display()

    def _display(self, *_):
        key = self.report_selector.currentData()
        record = self.records.get(key)
        if key:
            self.report_key = key
        if record is not self.displayed:
            self.result_panel.show_record(record)
            self.result_scroll.verticalScrollBar().setValue(0)
            self.displayed = record
        fresh = bool(record and not record.get("stale"))
        self.tex.setEnabled(fresh)
        self.csv.setEnabled(fresh)
        self.result_canvas.queue = {}
        self.result_canvas.conflicts = []
        raw = record.get("inputs", {}) if record else {}
        if "arms" in raw:
            self.result_canvas.queue = {(a, b): v for a, b, v in record.get("queue_bands", [])}
            self.result_canvas.conflicts = record.get("conflicts", [])
            self.result_canvas.set_site(
                Site.from_dict({k: v for k, v in raw.items() if k in Site.__dataclass_fields__}),
                record.get("geometry"),
            )
        else:
            self.result_canvas.set_site(None)
        self.present.setTabVisible(1, bool(self.result_canvas.site))

    def _export(self):
        record = self.records.get(self.report_key)
        if record and not record.get("stale"):
            self.export_requested.emit(record)

    def _csv(self):
        record = self.records.get(self.report_key)
        if not record or record.get("stale"):
            return

        def write(path):
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow((record["title"],))
                writer.writerows(record.get("metrics", {}).items())
                for title, headers, rows in record.get("tables", []):
                    writer.writerow((title,))
                    writer.writerow(headers)
                    writer.writerows(rows)
                data = self.simulation.record
                if self.report_key == "simulation" and data:
                    for scenario in data["scenarios"]:
                        for run in scenario["runs"]:
                            writer.writerow((scenario["name"], run["seed"], "Series de colas"))
                            writer.writerow(
                                ["t (s)", *[f"{a}/{j} (m)" for a, j, _ in scenario["lanes"]]]
                            )
                            start = data["options"]["warmup"]
                            writer.writerows(
                                [i, *vals]
                                for i, vals in enumerate(unpack(run["queue_series"]), start)
                            )

        self._save_file("Exportar resultados", "resultados_rotonda.csv", "csv", write)

    def _demo(self):
        from hcnet.domain.roundabout_examples import EXAMPLES

        chosen, ok = QInputDialog.getItem(
            self, "Cargar caso demostrativo", "Caso", EXAMPLES, editable=False
        )
        if ok:
            self.load_case(EXAMPLES.index(chosen))

    def load_case(self, index):
        from hcnet.domain.roundabout_examples import EXAMPLES, example

        site, state = example(index)
        self.set_state(state | {"demo": EXAMPLES[index]})
        self._load_site(site)
        self.status.setText(f"Caso demostrativo · {self.demo}. Datos hipotéticos.")
        self.changed.emit()

    def snapshot(self):
        return deepcopy(
            {
                "mode": self.mode.currentIndex(),
                "advanced": self.advanced.isChecked(),
                "tab": self.tabs.currentIndex(),
                "settings": self.settings.values(),
                "arms": self.geometry.raw,
                "movements": self.demand.values(),
                "locks": [k for k, b in self.locks.items() if b.isChecked()],
                "records": self.records,
                "panel": self.report_key,
                "scenario": self.scenario.values(),
                "candidates": self.candidates,
                "original": self.original,
                "original_site": self.original_site,
                "optimization_baseline": self.optimization_baseline,
                "calibration": self.calibration.state(),
                "simulation": self.simulation.state(),
                "fitted": self.fitted,
                "demo": self.demo,
            }
        )

    def set_state(self, state):
        self._loading = True
        self.mode.setCurrentIndex(state.get("mode", 0))
        self.advanced.setChecked(state.get("advanced", False))
        self._mode()
        self.settings.set_values(initial_form(SITE_SPECS) | state.get("settings", {}))
        self._last_kind = self.settings.value("kind")
        self.scenario.set_values(
            initial_form(SCENARIOS) | {"objective": "Demora"} | state.get("scenario", {})
        )
        for key, box in self.locks.items():
            box.setChecked(key in state.get("locks", []))
        self.geometry.set_data(state.get("arms", initial_arms()))
        self.demand.set_data(list(self.geometry.raw), state.get("movements", []))
        self.records = deepcopy(state.get("records", {}))
        self.report_key = state.get("panel", "")
        self.original = state.get("original")
        self._mode()
        self.original_site = state.get("original_site")
        self.optimization_baseline = state.get("optimization_baseline")
        self.candidates = state.get("candidates", [])
        self.fitted = state.get("fitted", {})
        self.demo = state.get("demo", "")
        self.original_notice.setText(
            "Original archivado." if self.original_site else "Original: sin captura."
        )
        self.calibration.restore(state.get("calibration", {}))
        self.simulation.restore(state.get("simulation", {}))
        self.replay.set_record(
            self.simulation.record,
            Site.from_dict(self.original_site) if self.original_site else None,
        )
        self._fill_candidates()
        self.tabs.setCurrentIndex(state.get("tab", 0))
        self._redraw()
        self._refresh_reports()
        self.status.setText("Configura los accesos y la demanda del estudio.")
        self._loading = False
