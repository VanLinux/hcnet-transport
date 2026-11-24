"""Captura de línea, fichas vehiculares y perfiles de pasajeros por sentido."""

import json
from dataclasses import asdict

from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QInputDialog, QTabWidget, QVBoxLayout, QWidget

from hcnet.domain.transit_catalog import catalog, system_for, vehicle_for
from hcnet.domain.transit_engineering import STRATEGIES, Service, Station, capacity_for, evaluate
from hcnet.ui.transit_forms import (
    Form,
    button,
    fill_table,
    integer,
    intervals,
    label,
    numeric,
    read_table,
    row,
    scroll,
    table,
)
from hcnet.ui.transit_vehicle import VehicleDoors

VEHICLE_FIELDS = [
    ("label", "Nombre de la ficha", "", ""),
    ("manufacturer", "Fabricante", "", ""),
    ("config", "Configuración / variante", "", ""),
    ("width", "Anchura del vehículo (m)", "", ""),
    ("standing", "Plazas nominales de pie", "", ""),
    ("maxspeed", "Velocidad máxima (km/h)", "", ""),
    ("acceleration", "Aceleración (m/s²)", "", ""),
    ("deceleration", "Desaceleración (m/s²)", "", ""),
    ("motor", "Motorización", "", ""),
    (
        "provenance",
        "Procedencia de los valores editados",
        (
            "Por capturar",
            "Documentada",
            "Observación de campo",
            "Referencial",
            "Supuesto de ingeniería",
            "Personalizado",
        ),
        "",
    ),
    ("nominal", "Capacidad nominal (pax/unidad)", "", ""),
    ("seats", "Asientos", "", "Sin dato, déjalo vacío."),
    ("area", "Área de pie (m²)", "", ""),
    ("density", "Densidad de pie (pax/m²)", "", ""),
    ("length_m", "Longitud de la unidad (m)", "", ""),
    ("cars", "Carros de la formación", "", "Uno para una unidad vial."),
    ("limits", "Límites y condiciones de operación", "", ""),
    ("accessibility", "Accesibilidad del vehículo", "", ""),
    ("payment", "Sistema de cobro", "", ""),
    ("source_note", "Fuente de las modificaciones", "", ""),
    ("method", "Capacidad utilizada", ("Nominal", "Por área"), ""),
]
LINE_FIELDS = [
    ("name", "Nombre de la línea", "", ""),
    ("length_km", "Longitud por sentido (km)", "", ""),
    ("speed_kmh", "Velocidad en marcha (km/h)", "", "Excluye permanencia en paradas."),
    (
        "demand",
        "Demanda crítica de diseño (pax/h/sentido)",
        "",
        "Si hay perfiles, se usa el máximo entre demanda capturada y demanda calculada.",
    ),
    ("headway_min", "Intervalo programado (min)", "", ""),
    (
        "min_headway_s",
        "Intervalo mínimo de la infraestructura (s)",
        "",
        "Incluye señalización o condiciones de separación.",
    ),
    ("load_factor", "Factor de ocupación objetivo (0–1)", "", ""),
    ("terminal_min", "Regulación por terminal (min)", "", "Captura 0 si no aplica."),
    ("terminal_positions", "Bahías efectivas de regulación por terminal", "", ""),
    (
        "homogeneous_dwell_s",
        "Permanencia homogénea observada (s)",
        "",
        "Si queda vacía, se estima según las puertas y los pasajeros.",
    ),
    ("walking_speed", "Velocidad peatonal (m/s)", "", "Opcional; estima acceso longitudinal."),
    ("reserve_percent", "Reserva de operación (%)", "", ""),
    ("availability", "Fracción de flota disponible (0–1)", "", ""),
    ("intermediate", "Paradas interiores en modelo homogéneo", "", ""),
    ("board", "Ascensos típicos por parada (pax/unidad)", "", ""),
    ("alight", "Descensos típicos por parada (pax/unidad)", "", ""),
    ("stop_positions", "Posiciones efectivas por estación", "", ""),
    ("stop_clearance_s", "Tiempo de despeje (s)", "", ""),
    (
        "movement_penalty_s",
        "Pérdida adicional por parada (s)",
        "",
        "Aceleración y frenado omitidos en la velocidad en marcha.",
    ),
    ("exchange", "Modelo de intercambio en puertas", STRATEGIES, ""),
    ("passenger_units", "Unidades de las tablas", ("Por unidad", "Por hora"), ""),
    ("initial_pax", "Carga inicial en ida (unidad de la tabla)", "", ""),
    ("initial_reverse_pax", "Carga inicial en regreso (unidad de la tabla)", "", ""),
    ("cable_spacing_m", "Separación programada entre cabinas (m)", "", ""),
    ("cable_min_spacing_m", "Separación mínima entre cabinas (m)", "", ""),
    ("cable_circuit_km", "Longitud de cable en el circuito completo (km)", "", ""),
    ("cable_station_s", "Tiempo adicional de cabina por estación (s)", "", ""),
    ("cable_station_limit", "Capacidad del área de embarque (pax/h/sentido)", "", ""),
    ("headways_observed", "Intervalos observados (min; separados por ;)", "", ""),
    ("random_arrivals", "Llegadas aleatorias de pasajeros", False, ""),
    ("regular_service", "Servicio regular si no hay observaciones", False, ""),
]
STATION_HEADERS = (
    "Estación",
    "km acumulados",
    "Ascensos",
    "Descensos",
    "Vel. tramo (km/h)",
    "Permanencia obs. (s)",
    "Posiciones",
    "Despeje (s)",
    "Andén (pax/h)",
    "Accesible",
)


def _stations(widget, default_clearance):
    result = []
    for (
        name,
        km,
        board,
        alight,
        speed,
        observed,
        berths,
        clearance,
        platform,
        accessible,
    ) in read_table(widget):
        access = accessible.casefold()
        if access not in {"", "si", "sí", "no"}:
            raise ValueError("En Accesible, captura sí, no o deja la celda vacía.")
        result.append(
            Station(
                name,
                numeric(km, "Distancia acumulada"),
                numeric(board, "Ascensos", default=0),
                numeric(alight, "Descensos", default=0),
                numeric(speed, "Velocidad del tramo", default=0),
                numeric(observed, "Permanencia") if observed else None,
                integer(berths, "Posiciones", default=1),
                numeric(clearance, "Despeje", default=default_clearance),
                numeric(platform, "Capacidad de andén", default=0),
                access != "no" if access else None,
            )
        )
    return tuple(result)


def line_record(line, result):
    frequency = result["frequency"]
    metrics = {
        "Frecuencia programada (unid/h)": frequency,
        "Frecuencia requerida teórica (unid/h)": result["required_frequency"],
        "Frecuencia requerida entera (unid/h)": result["operational_frequency"],
        "Frecuencia límite (unid/h)": result["max_frequency"],
        "Intervalo programado (min)": result["headway"],
        "Capacidad física por unidad (pax)": result["nominal_unit"],
        "Capacidad de diseño por unidad (pax)": result["design_unit"],
        "Oferta física programada (pax/h/sentido)": result["physical_offer"],
        "Oferta de diseño programada (pax/h/sentido)": result["offered"],
        "Oferta alcanzable (pax/h/sentido)": result["achievable"],
        "Demanda crítica (pax/h/sentido)": result["demand"],
        "Margen de capacidad (pax/h/sentido)": result["margin"],
        "Ocupación proyectada de la oferta física (%)": result["occupation"] * 100,
        "Flota operativa mínima (unid)": result["fleet"],
        "Flota de reserva (unid)": result["reserve"],
        "Flota total (unid)": result["fleet_total"],
        "Ciclo (min)": result["cycle"],
        "Estación limitante": result["critical_station"] or "Sin estación limitante",
        "Sección de máxima carga registrada": result["critical_section"],
        "Espera estimada (min)": result["quality"]["wait"],
        "Intervalo observado medio (min)": result["quality"]["observed_mean"],
        "Coeficiente de variación de intervalos": result["quality"]["cv"],
        "Intervalo observado máximo (min)": result["quality"]["max_headway"],
    }
    speed = [
        [
            name,
            result["running_min"][i],
            result["dwell_total_s"][i],
            result["travel_min"][i],
            result["commercial_kmh"][i],
            result["operating_kmh"][i],
        ]
        for i, name in enumerate(("Ida", "Regreso"))
    ]
    tables = [
        (
            "Operación por sentido",
            [
                "Sentido",
                "Marcha (min)",
                "Paradas (s)",
                "Viaje (min)",
                "Vel. comercial (km/h)",
                "Vel. operación (km/h)",
            ],
            speed,
        )
    ]
    loads, stays = {}, {}
    for name, values in zip(("Ida", "Regreso"), result["profiles"], strict=True):
        if not values:
            continue
        tables.append(
            (
                f"Perfil de carga · {name}",
                [
                    "Estación",
                    "km",
                    "Asc./unidad",
                    "Desc./unidad",
                    "Carga/unidad",
                    "Ocupación (%)",
                    "Déficit incremental/unidad",
                    "Permanencia (s)",
                    "Capacidad (unid/h)",
                    "Cap. diseño (pax/h)",
                    "Intercambio (pax/h)",
                    "Asientos libres",
                    "Densidad (pax/m²)",
                    "Accesible",
                    "Capacidad libre (pax/unidad)",
                    "Saturación estación (%)",
                    "Ascensos acumulados",
                    "Descensos acumulados",
                ],
                [
                    [
                        r["name"],
                        r["km"],
                        r["board"],
                        r["alight"],
                        r["load"],
                        100 * r["occupation"],
                        r["deficit"],
                        r["dwell"],
                        r["station_units"],
                        r["station_pax"],
                        r["platform_load"],
                        r["seats_available"],
                        r["density"],
                        r["accessible"],
                        r["available_after"],
                        100 * r["station_saturation"],
                        r["accumulated_board"],
                        r["accumulated_alight"],
                    ]
                    for r in values
                ],
            )
        )
        loads[name] = [[r["km"], r["load"]] for r in values]
        stays[name] = [[r["km"], r["dwell"]] for r in values]
    charts = [
        {
            "title": "Oferta y demanda por hora y sentido",
            "x": "Indicador",
            "bars": True,
            "y": "pax/h",
            "series": {"Demanda": [[1, result["demand"]]], "Oferta": [[2, result["achievable"]]]},
        }
    ]
    if loads:
        loads["Capacidad"] = [[0, line.nominal], [line.length_km, line.nominal]]
        charts.extend(
            [
                {
                    "title": "Perfil de carga después de cada estación",
                    "x": "km",
                    "y": "pax/unidad",
                    "series": loads,
                },
                {"title": "Permanencia", "x": "km", "y": "s", "series": stays},
            ]
        )
    return {
        "title": line.name or "Análisis integral",
        "metrics": metrics,
        "formulas": [
            r"h=s/v\quad\text{(cabinas, en segundos)}"
            if line.technology == "cable"
            else r"T_c=T_{ida}+T_{regreso}+2t_r",
            r"f=60/h,\qquad Q_d=fC\lambda,\qquad N_{op}=\lceil T_c/h\rceil",
            r"P_i=P_{i-1}+B_i-A_i",
        ],
        "notes": list(result["warnings"]),
        "tables": tables,
        "charts": charts,
        "inputs": asdict(line),
    }


class LineEditor(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._loading = False
        self.reference = {}
        self.settings = QSettings()
        self.custom = self._load_library()
        layout = QVBoxLayout(self)
        self.sections = QTabWidget()
        layout.addWidget(self.sections)
        self.line = Form(LINE_FIELDS, self._edit)
        service_panel = QWidget()
        service_layout = QVBoxLayout(service_panel)
        self.systems = QComboBox()
        self.systems.setAccessibleName("Sistema de transporte")
        for system in catalog():
            self.systems.addItem(system["name"], system["id"])
        self.systems.currentIndexChanged.connect(self._system_changed)
        service_layout.addWidget(label("Sistema de transporte", "sectionTitle"))
        service_layout.addWidget(self.systems)
        self.system_info = label("")
        service_layout.addWidget(self.system_info)
        self.details = QCheckBox("Mostrar captura avanzada")
        self.details.toggled.connect(self._visibility)
        service_layout.addWidget(self.details)
        service_layout.addWidget(self.line)
        self.sections.addTab(scroll(service_panel), "Servicio")
        vehicle_panel = QWidget()
        vehicle_layout = QVBoxLayout(vehicle_panel)
        self.vehicles = QComboBox()
        self.vehicles.setAccessibleName("Vehículo de referencia")
        self.vehicles.activated.connect(self._apply)
        vehicle_layout.addWidget(self.vehicles)
        vehicle_layout.addWidget(
            row(
                button("Aplicar ficha seleccionada", self._apply),
                button("Guardar vehículo de usuario…", self._save_vehicle),
            )
        )
        self.vehicle_source = label("")
        vehicle_layout.addWidget(self.vehicle_source)
        self.source_button = button("Consultar fuente", self._open_source)
        vehicle_layout.addWidget(self.source_button)
        self.vehicle = Form(VEHICLE_FIELDS, self._edit)
        vehicle_layout.addWidget(self.vehicle)
        self.doors = VehicleDoors()
        self.doors.changed.connect(self._edit)
        vehicle_layout.addWidget(self.doors)
        self.sections.addTab(scroll(vehicle_panel), "Vehículo y puertas")
        self.station_tables = []
        station_panel = QWidget()
        station_layout = QVBoxLayout(station_panel)
        station_layout.addWidget(
            label(
                "Cada sentido empieza en km 0 y termina en la longitud de la línea. "
                "La permanencia observada tiene prioridad sobre el modelo de puertas. "
                "Una tabla vacía emplea el modelo homogéneo."
            )
        )
        for name in ("Ida", "Regreso"):
            station_layout.addWidget(label(name, "sectionTitle"))
            widget = table(STATION_HEADERS)
            widget.cellChanged.connect(self._edit)
            self.station_tables.append(widget)
            station_layout.addWidget(widget)
            station_layout.addWidget(
                row(
                    button("Agregar estación", lambda _, w=widget: self._station_row(w, False)),
                    button("Eliminar estación", lambda _, w=widget: self._station_row(w, True)),
                    button("Ordenar por km", lambda _, w=widget: self._sort_stations(w)),
                )
            )
        self.sections.addTab(scroll(station_panel), "Estaciones")
        self.set_state({})

    def _load_library(self):
        try:
            return json.loads(self.settings.value("transit35/custom_vehicles", "{}"))
        except (TypeError, ValueError):
            return {}

    def _visibility(self, *_):
        cable = self.system()["technology"] == "cable"
        detailed = self.details.isChecked()
        self.line.visible(
            ("headway_min", "board", "alight", "exchange", "homogeneous_dwell_s"), not cable
        )
        self.line.visible(
            tuple(key for key in self.line.controls if key.startswith("cable")), cable
        )
        self.line.visible(
            (
                "reserve_percent",
                "availability",
                "stop_positions",
                "stop_clearance_s",
                "movement_penalty_s",
                "passenger_units",
                "initial_pax",
                "initial_reverse_pax",
                "headways_observed",
                "regular_service",
                "random_arrivals",
                "walking_speed",
            ),
            detailed,
        )
        self.line.visible(("terminal_positions",), detailed and not cable)
        self.vehicle.visible(
            (
                "width",
                "standing",
                "maxspeed",
                "acceleration",
                "deceleration",
                "area",
                "density",
                "limits",
                "payment",
                "accessibility",
                "method",
            ),
            detailed,
        )

    def _sort_stations(self, widget):
        rows = read_table(widget)
        try:
            rows.sort(key=lambda values: numeric(values[1], "Distancia"))
        except ValueError:
            return
        fill_table(widget, rows)
        self._edit()

    def _station_row(self, widget, remove):
        if remove and widget.currentRow() >= 0:
            widget.removeRow(widget.currentRow())
        elif not remove:
            widget.insertRow(widget.rowCount())
            widget.setCurrentCell(widget.rowCount() - 1, 0)
        self._edit()

    def system(self):
        return system_for(self.systems.currentData())

    def _system_changed(self, *_):
        old = self._loading
        self._loading = True
        system = self.system()
        self.system_info.setText(f"{system['infrastructure']}. {system['description']}")
        self._visibility()
        self.vehicles.clear()
        self.vehicles.addItem("Selecciona un modelo o captura un vehículo propio", "")
        for vehicle in system["vehicles"]:
            self.vehicles.addItem(vehicle["name"], vehicle["id"])
        for name, entry in self.custom.items():
            if entry.get("system") == system["id"]:
                self.vehicles.addItem(name, f"user:{name}")
        self._loading = old
        if not old:
            self.reference = {}
            self._refresh_reference()
            self._edit()

    def _apply(self, *_):
        key = self.vehicles.currentData()
        self._loading = True
        if key and key.startswith("user:"):
            entry = self.custom[key.removeprefix("user:")]
            self.reference = entry["reference"]
            self.vehicle.set_values(entry["vehicle"])
            self.doors.set_doors(entry["doors"])
        else:
            ref = vehicle_for(self.system()["id"], key)
            self.reference = ref or {}
            self.vehicle.set_values(
                {
                    name: default[0] if isinstance(default, tuple) else default
                    for name, _, default, _ in VEHICLE_FIELDS
                }
            )
            if ref:
                self.vehicle.set_values(
                    ref["values"]
                    | {
                        "label": ref["name"],
                        "manufacturer": ref["manufacturer"],
                        "provenance": "Documentada",
                    }
                )
            self.doors.set_doors([])
        self._loading = False
        self._refresh_reference()
        self._edit()

    def _save_vehicle(self):
        name, ok = QInputDialog.getText(
            self, "Vehículo de usuario", "Nombre de la ficha", text=self.vehicle.value("label")
        )
        name = name.strip()
        if ok and name:
            self.custom[name] = {
                "detailed": self.details.isChecked(),
                "system": self.system()["id"],
                "reference": self.reference,
                "vehicle": self.vehicle.values(),
                "doors": self.doors.raw(),
            }
            self.settings.setValue(
                "transit35/custom_vehicles", json.dumps(self.custom, ensure_ascii=False)
            )
            self._loading = True
            self._system_changed()
            self.vehicles.setCurrentIndex(self.vehicles.findData(f"user:{name}"))
            self._loading = False
            self._edit()

    def _open_source(self):
        if self.reference.get("source"):
            QDesktopServices.openUrl(QUrl(self.reference["source"]))

    def _refresh_reference(self):
        ref = self.reference
        if ref:
            values = ", ".join(f"{key} = {value}" for key, value in ref["values"].items())
            self.vehicle_source.setText(
                (f"{ref['manufacturer']}. " if ref["manufacturer"] else "")
                + ref["note"]
                + (f"Valores de la ficha original: {values}." if values else "")
            )
        else:
            self.vehicle_source.setText(
                "Captura la configuración de la unidad. Los campos vacíos no tienen fuente."
            )
        self.source_button.setEnabled(bool(ref.get("source")))

    def _edit(self, *_):
        if not self._loading:
            body = self.reference.get("body", self.system()["id"])
            try:
                cars = self.vehicle.whole("cars", 1)
            except ValueError:
                cars = 1
            self.doors.configure(body, max(1, cars))
            self.changed.emit()

    def state(self):
        return {
            "detailed": self.details.isChecked(),
            "system": self.system()["id"],
            "selection": self.vehicles.currentData(),
            "reference": self.reference,
            "vehicle": self.vehicle.values(),
            "line": self.line.values(),
            "doors": self.doors.raw(),
            "stations": [read_table(widget) for widget in self.station_tables],
        }

    def set_state(self, state):
        self._loading = True
        system = self.systems.findData(state.get("system", "rtp"))
        self.systems.setCurrentIndex(max(0, system))
        self._system_changed()
        self.vehicles.setCurrentIndex(max(0, self.vehicles.findData(state.get("selection", ""))))
        self.details.setChecked(state.get("detailed", False))
        self.reference = state.get("reference", {})
        for form, specs, key in (
            (self.line, LINE_FIELDS, "line"),
            (self.vehicle, VEHICLE_FIELDS, "vehicle"),
        ):
            form.set_values(
                {
                    field: default[0] if isinstance(default, tuple) else default
                    for field, _, default, _ in specs
                }
                | state.get(key, {})
            )
        self.doors.set_doors(state.get("doors", []))
        stations = state.get("stations", [[], []])
        for i, widget in enumerate(self.station_tables):
            fill_table(widget, stations[i] if i < len(stations) else [])
        self._refresh_reference()
        cars = self.vehicle.value("cars")
        try:
            count = integer(cars, "Carros", default=1)
        except ValueError:
            count = 1
        self.doors.configure(self.reference.get("body", self.system()["id"]), max(1, count))
        self._loading = False

    def service(self):
        form = self.line
        v = self.vehicle
        tech = self.system()["technology"]
        cable = tech == "cable"
        number = form.number
        seats = v.number("seats") if v.value("seats") else None
        area = v.number("area") if v.value("area") else None
        nominal = capacity_for(
            v.number("nominal", 0), seats or 0, area or 0, v.number("density", 0), v.value("method")
        )
        if seats is not None and not 0 <= seats <= nominal:
            raise ValueError("Los asientos deben estar entre cero y la capacidad nominal.")
        if area is not None and area < 0:
            raise ValueError("El área debe ser no negativa.")
        clear = number("stop_clearance_s", 8)
        return Service(
            form.value("name"),
            tech,
            number("length_km"),
            number("speed_kmh"),
            number("headway_min", 0) if cable else number("headway_min"),
            number("demand", 0),
            nominal,
            number("load_factor"),
            number("min_headway_s"),
            number("reserve_percent", 0),
            number("availability", 1),
            number("terminal_min", 0),
            form.whole("intermediate", 0),
            number("board", 0),
            number("alight", 0),
            form.whole("stop_positions", 1),
            clear,
            number("movement_penalty_s", 0),
            form.value("exchange"),
            self.doors.doors() if not cable else (),
            _stations(self.station_tables[0], clear),
            _stations(self.station_tables[1], clear),
            form.value("passenger_units"),
            number("initial_pax", 0),
            number("initial_reverse_pax", 0),
            number("cable_spacing_m", 0),
            number("cable_min_spacing_m", 0),
            number("cable_circuit_km", 0),
            number("cable_station_s", 0),
            number("cable_station_limit", 0),
            intervals(form.value("headways_observed")),
            form.value("random_arrivals"),
            form.value("regular_service"),
            seats,
            area,
            number("homogeneous_dwell_s")
            if form.value("homogeneous_dwell_s") and not cable
            else None,
            form.whole("terminal_positions", 0),
        )

    def calculate(self):
        service = self.service()
        result = evaluate(service)
        record = line_record(service, result)
        walk_speed = self.line.number("walking_speed", 0)
        if walk_speed < 0:
            raise ValueError("Captura una velocidad peatonal no negativa.")
        record["inputs"]["walking_speed"] = walk_speed
        record["inputs"]["vehicle"] = self.vehicle.values()
        record["inputs"]["system"] = self.system()["name"]
        for i, direction in enumerate(("Ida", "Regreso")):
            space = service.length_km * 1000 / (result["station_count"][i] - 1)
            record["metrics"][f"{direction} · Espaciamiento medio (m)"] = space
            if walk_speed:
                record["metrics"][f"{direction} · Acceso longitudinal medio (min)"] = space / (
                    240 * walk_speed
                )
        if walk_speed:
            record["notes"].append(
                "El acceso longitudinal supone orígenes uniformes y uso de la estación más cercana."
            )
        if self.reference.get("source"):
            record["sources"] = [self.reference["source"]]
            record["notes"].append(self.reference["note"])
        return record
