"""Apartado autónomo de planeación de transporte público."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.transit import TransitLineInput, TransitLineResult
from hcnet.ui.charts import TransitCongestionChart
from hcnet.ui.styles import COLORS
from hcnet.ui.transit_engineering import TransitEngineering


class _TransitMetric(QFrame):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        self.label = QLabel(label)
        self.label.setObjectName("metricLabel")
        self.value = QLabel("—")
        self.value.setObjectName("metricValue")
        self.detail = QLabel("")
        self.detail.setObjectName("pageSubtitle")
        self.detail.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_metric(self, value: str, detail: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.value.setStyleSheet(f"color: {color};" if color else "")


class PublicTransportTab(QWidget):
    """Formulario, resultados y comparador de congestión de una línea."""

    input_changed = Signal()
    calculate_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._build_ui()
        self._connect_inputs()

    @staticmethod
    def _double(
        minimum: float,
        maximum: float,
        decimals: int = 2,
        suffix: str = "",
        step: float = 1.0,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(0 if minimum > 0 else minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(step)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        if minimum > 0:
            widget.setSpecialValueText("Por capturar")
        return widget

    @staticmethod
    def _integer(minimum: int, maximum: int, suffix: str = "") -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(0, maximum)
        if minimum > 0:
            widget.setSpecialValueText("Por capturar")
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        return widget

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace = QComboBox()
        self.workspace.setAccessibleName("Herramienta de transporte público")
        self.workspace.addItems(("Herramientas de transporte público", "Cálculo de línea vial 3.4"))
        outer_layout.addWidget(self.workspace)
        self.pages = QStackedWidget()
        outer_layout.addWidget(self.pages)
        self.engineering = TransitEngineering()
        self.pages.addWidget(self.engineering)
        self.workspace.currentIndexChanged.connect(self.pages.setCurrentIndex)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 14)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Planeación de transporte público")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Dimensiona operación, flota y paradas; después compara la respuesta vial "
            "de cuatro funciones de congestión."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch()
        calculate_button = QPushButton("Calcular línea")
        calculate_button.setObjectName("primaryButton")
        calculate_button.clicked.connect(self.calculate_requested.emit)
        heading.addWidget(calculate_button)
        export_button = QPushButton("Exportar reporte .tex")
        export_button.clicked.connect(self.export_requested.emit)
        heading.addWidget(export_button)
        layout.addLayout(heading)

        banner = QLabel(
            "La velocidad de operación representa el recorrido entre paradas. La velocidad "
            "comercial incorpora detenciones; el tiempo de ciclo agrega la regulación en "
            "ambas terminales. Demanda y capacidad se expresan por hora y por sentido."
        )
        banner.setObjectName("infoBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        inputs = QGridLayout()
        inputs.setHorizontalSpacing(10)
        inputs.addWidget(self._build_service_box(), 0, 0)
        inputs.addWidget(self._build_stops_box(), 0, 1)
        inputs.addWidget(self._build_congestion_box(), 1, 0, 1, 2)
        inputs.setColumnStretch(0, 1)
        inputs.setColumnStretch(1, 1)
        layout.addLayout(inputs)

        results_box = QGroupBox("Resultados operacionales")
        results_layout = QVBoxLayout(results_box)
        cards = QGridLayout()
        self.speed_metric = _TransitMetric("VELOCIDAD COMERCIAL")
        self.cycle_metric = _TransitMetric("TIEMPO DE CICLO")
        self.fleet_metric = _TransitMetric("FLOTA MÍNIMA + RESERVA")
        self.capacity_metric = _TransitMetric("CAPACIDAD DE LÍNEA")
        self.service_metric = _TransitMetric("FRECUENCIA E INTERVALO")
        self.stop_metric = _TransitMetric("PARADAS Y ACCESO")
        self.dwell_metric = _TransitMetric("ASCENSO, DESCENSO Y PERMANENCIA")
        self.balance_metric = _TransitMetric("BALANCE OFERTA / DEMANDA")
        for index, metric in enumerate(
            (
                self.speed_metric,
                self.cycle_metric,
                self.fleet_metric,
                self.capacity_metric,
                self.service_metric,
                self.stop_metric,
                self.dwell_metric,
                self.balance_metric,
            )
        ):
            cards.addWidget(metric, index // 2, index % 2)
        results_layout.addLayout(cards)
        layout.addWidget(results_box)

        comparison_box = QGroupBox("Análisis oferta–demanda y congestión")
        comparison_layout = QVBoxLayout(comparison_box)
        self.congestion_summary = QLabel("Sin cálculo.")
        self.congestion_summary.setObjectName("pageSubtitle")
        self.congestion_summary.setWordWrap(True)
        comparison_layout.addWidget(self.congestion_summary)
        self.congestion_chart = TransitCongestionChart()
        comparison_layout.addWidget(self.congestion_chart)
        self.congestion_table = QTableWidget(0, 5)
        self.congestion_table.setHorizontalHeaderLabels(
            ["Modelo", "t₀ (min)", "t actual (min)", "Demora (min)", "Velocidad (km/h)"]
        )
        self.congestion_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.congestion_table.verticalHeader().setVisible(False)
        self.congestion_table.setMinimumHeight(170)
        self.congestion_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        comparison_layout.addWidget(self.congestion_table)
        self.diagnosis = QLabel("Calcula la línea para generar el diagnóstico.")
        self.diagnosis.setObjectName("warningBanner")
        self.diagnosis.setWordWrap(True)
        comparison_layout.addWidget(self.diagnosis)
        layout.addWidget(comparison_box)

        note = QLabel(
            "El espaciamiento óptimo equilibra acceso peatonal y penalización por parada. "
            "Es una aproximación de planeación; no sustituye un estudio de cobertura, "
            "seguridad vial, accesibilidad universal ni demanda espacial."
        )
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        scroll.setWidget(page)
        self.pages.addWidget(scroll)

    def _build_service_box(self) -> QGroupBox:
        box = QGroupBox("Servicio, demanda y flota")
        form = QFormLayout(box)
        self.line_name = QLineEdit()
        self.route_length = self._double(0.1, 1000, 2, " km", 0.5)
        self.stop_count = self._integer(2, 1000, " / sentido")
        self.operating_speed = self._double(1, 200, 1, " km/h", 1)
        self.layover = self._double(0, 240, 1, " min/terminal", 1)
        self.headway = self._double(0.1, 240, 1, " min", 0.5)
        self.vehicle_capacity = self._double(1, 1000, 0, " pasajeros", 5)
        self.load_factor = self._double(0.01, 2.0, 2, "", 0.05)
        self.peak_demand = self._double(0, 100000, 0, " pax/h/sentido", 50)
        self.reserve = self._double(0, 100, 1, " %", 1)
        form.addRow("Nombre de la línea:", self.line_name)
        form.addRow("Longitud por sentido:", self.route_length)
        form.addRow("Paradas:", self.stop_count)
        form.addRow("Velocidad de operación:", self.operating_speed)
        form.addRow("Regulación terminal:", self.layover)
        form.addRow("Intervalo programado:", self.headway)
        form.addRow("Capacidad vehicular:", self.vehicle_capacity)
        form.addRow("Ocupación objetivo:", self.load_factor)
        form.addRow("Demanda pico:", self.peak_demand)
        form.addRow("Reserva de flota:", self.reserve)
        return box

    def _build_stops_box(self) -> QGroupBox:
        box = QGroupBox("Paradas, acceso e intercambio")
        form = QFormLayout(box)
        self.walking_speed = self._double(0.1, 3, 2, " m/s", 0.05)
        self.average_trip = self._double(0.1, 1000, 2, " km", 0.5)
        self.boardings = self._double(0, 1000, 1, " pax/parada", 1)
        self.alightings = self._double(0, 1000, 1, " pax/parada", 1)
        self.boarding_time = self._double(0, 60, 2, " s/pax", 0.1)
        self.alighting_time = self._double(0, 60, 2, " s/pax", 0.1)
        self.door_time = self._double(0, 120, 1, " s", 0.5)
        self.door_count = self._integer(1, 20)
        self.exchange_mode = QComboBox()
        self.exchange_mode.addItems(["Simultáneo", "Secuencial"])
        self.stop_penalty = self._double(0, 300, 1, " s/parada", 1)
        self.clearance = self._double(0, 300, 1, " s", 1)
        self.berths = self._integer(1, 20)
        form.addRow("Velocidad peatonal:", self.walking_speed)
        form.addRow("Longitud media de viaje:", self.average_trip)
        form.addRow("Ascensos medios:", self.boardings)
        form.addRow("Descensos medios:", self.alightings)
        form.addRow("Tiempo de ascenso:", self.boarding_time)
        form.addRow("Tiempo de descenso:", self.alighting_time)
        form.addRow("Abrir/cerrar puertas:", self.door_time)
        form.addRow("Puertas útiles:", self.door_count)
        form.addRow("Intercambio:", self.exchange_mode)
        form.addRow("Acelerar/desacelerar:", self.stop_penalty)
        form.addRow("Despeje de parada:", self.clearance)
        form.addRow("Posiciones de atención:", self.berths)
        return box

    def _build_congestion_box(self) -> QGroupBox:
        box = QGroupBox("Oferta vial y funciones de congestión")
        grid = QGridLayout(box)
        self.background_flow = self._double(0, 100000, 0, " veh/h", 50)
        self.road_capacity = self._double(1, 100000, 0, " veh/h", 50)
        self.bus_pce = self._double(0.1, 20, 2, " veh eq/bus", 0.1)
        self.linear_alpha = self._double(0, 10, 3, "", 0.01)
        self.bpr_alpha = self._double(0, 10, 3, "", 0.01)
        self.bpr_beta = self._double(0.1, 20, 2, "", 0.1)
        self.davidson_j = self._double(0, 20, 3, "", 0.05)
        self.exponential_alpha = self._double(0, 10, 3, "", 0.01)
        widgets = (
            ("Flujo de fondo:", self.background_flow),
            ("Capacidad vial:", self.road_capacity),
            ("Equivalencia del autobús:", self.bus_pce),
            ("Lineal, α:", self.linear_alpha),
            ("BPR, α:", self.bpr_alpha),
            ("BPR, β:", self.bpr_beta),
            ("Davidson, J:", self.davidson_j),
            ("Exponencial, α:", self.exponential_alpha),
        )
        for index, (label, widget) in enumerate(widgets):
            pair = index % 2
            row = index // 2
            grid.addWidget(QLabel(label), row, pair * 2)
            grid.addWidget(widget, row, pair * 2 + 1)
        return box

    def _all_inputs(self) -> tuple[QWidget, ...]:
        return (
            self.line_name,
            self.route_length,
            self.stop_count,
            self.operating_speed,
            self.layover,
            self.headway,
            self.vehicle_capacity,
            self.load_factor,
            self.peak_demand,
            self.reserve,
            self.walking_speed,
            self.average_trip,
            self.boardings,
            self.alightings,
            self.boarding_time,
            self.alighting_time,
            self.door_time,
            self.door_count,
            self.exchange_mode,
            self.stop_penalty,
            self.clearance,
            self.berths,
            self.background_flow,
            self.road_capacity,
            self.bus_pce,
            self.linear_alpha,
            self.bpr_alpha,
            self.bpr_beta,
            self.davidson_j,
            self.exponential_alpha,
        )

    def _connect_inputs(self) -> None:
        for widget in self._all_inputs():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._input_edited)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._input_edited)
            else:
                widget.valueChanged.connect(self._input_edited)

    def _input_edited(self, *_args) -> None:
        if not self._loading:
            self.input_changed.emit()

    def input_data(self) -> TransitLineInput:
        return TransitLineInput(
            name=self.line_name.text().strip(),
            route_length_km=self.route_length.value(),
            stop_count_per_direction=self.stop_count.value(),
            operating_speed_kmh=self.operating_speed.value(),
            terminal_layover_min=self.layover.value(),
            scheduled_headway_min=self.headway.value(),
            vehicle_capacity_pax=self.vehicle_capacity.value(),
            target_load_factor=self.load_factor.value(),
            peak_demand_pax_h_direction=self.peak_demand.value(),
            reserve_fleet_percent=self.reserve.value(),
            walking_speed_m_s=self.walking_speed.value(),
            average_trip_length_km=self.average_trip.value(),
            boardings_per_stop=self.boardings.value(),
            alightings_per_stop=self.alightings.value(),
            boarding_time_s_pax=self.boarding_time.value(),
            alighting_time_s_pax=self.alighting_time.value(),
            door_open_close_s=self.door_time.value(),
            door_count=self.door_count.value(),
            exchange_mode=self.exchange_mode.currentText(),
            stop_accel_decel_penalty_s=self.stop_penalty.value(),
            stop_clearance_s=self.clearance.value(),
            stop_berths=self.berths.value(),
            background_flow_veh_h=self.background_flow.value(),
            road_capacity_veh_h=self.road_capacity.value(),
            bus_pce=self.bus_pce.value(),
            linear_alpha=self.linear_alpha.value(),
            bpr_alpha=self.bpr_alpha.value(),
            bpr_beta=self.bpr_beta.value(),
            davidson_j=self.davidson_j.value(),
            exponential_alpha=self.exponential_alpha.value(),
        )

    def set_input(self, data: TransitLineInput) -> None:
        self._loading = True
        self.line_name.setText(data.name)
        values = (
            (self.route_length, data.route_length_km),
            (self.stop_count, data.stop_count_per_direction),
            (self.operating_speed, data.operating_speed_kmh),
            (self.layover, data.terminal_layover_min),
            (self.headway, data.scheduled_headway_min),
            (self.vehicle_capacity, data.vehicle_capacity_pax),
            (self.load_factor, data.target_load_factor),
            (self.peak_demand, data.peak_demand_pax_h_direction),
            (self.reserve, data.reserve_fleet_percent),
            (self.walking_speed, data.walking_speed_m_s),
            (self.average_trip, data.average_trip_length_km),
            (self.boardings, data.boardings_per_stop),
            (self.alightings, data.alightings_per_stop),
            (self.boarding_time, data.boarding_time_s_pax),
            (self.alighting_time, data.alighting_time_s_pax),
            (self.door_time, data.door_open_close_s),
            (self.door_count, data.door_count),
            (self.stop_penalty, data.stop_accel_decel_penalty_s),
            (self.clearance, data.stop_clearance_s),
            (self.berths, data.stop_berths),
            (self.background_flow, data.background_flow_veh_h),
            (self.road_capacity, data.road_capacity_veh_h),
            (self.bus_pce, data.bus_pce),
            (self.linear_alpha, data.linear_alpha),
            (self.bpr_alpha, data.bpr_alpha),
            (self.bpr_beta, data.bpr_beta),
            (self.davidson_j, data.davidson_j),
            (self.exponential_alpha, data.exponential_alpha),
        )
        for widget, value in values:
            widget.setValue(value)
        self.exchange_mode.setCurrentText(data.exchange_mode)
        self._loading = False

    def set_result(self, data: TransitLineInput, result: TransitLineResult) -> None:
        color = COLORS["green"] if result.capacity_margin_pax_h_direction >= 0 else COLORS["red"]
        self.speed_metric.set_metric(
            f"{result.commercial_speed_kmh:.1f} km/h",
            f"Operación entre paradas: {result.operating_speed_kmh:.1f} km/h",
        )
        self.cycle_metric.set_metric(
            f"{result.cycle_time_min:.1f} min",
            f"Ida: {result.commercial_time_one_way_min:.1f} min + regulación terminal",
        )
        self.fleet_metric.set_metric(
            f"{result.minimum_fleet_veh} + {result.reserve_fleet_veh} = {result.total_fleet_veh}",
            "vehículos en servicio + reserva",
        )
        self.capacity_metric.set_metric(
            f"{result.line_capacity_pax_h_direction:,.0f}", "pax/h/sentido", color
        )
        self.service_metric.set_metric(
            f"{result.service_frequency_bus_h:.2f} bus/h",
            f"Intervalo {data.scheduled_headway_min:.1f} min · "
            f"espera media {result.average_wait_min:.1f} min",
        )
        self.stop_metric.set_metric(
            f"{result.actual_stop_spacing_m:.0f} m",
            f"Óptimo aprox. {result.optimal_stop_spacing_m:.0f} m · "
            f"{result.recommended_stop_count} paradas · "
            f"acceso {result.average_access_time_min:.1f} min",
        )
        self.dwell_metric.set_metric(
            f"{result.dwell_time_s:.1f} s/parada",
            f"Ascenso {result.boarding_service_time_s:.1f} s · "
            f"descenso {result.alighting_service_time_s:.1f} s · "
            f"capacidad crítica {result.critical_stop_capacity_bus_h:.1f} bus/h",
        )
        ratio_text = (
            "∞"
            if result.supply_demand_ratio == float("inf")
            else f"{result.supply_demand_ratio:.2f}"
        )
        self.balance_metric.set_metric(
            ratio_text,
            f"Oferta/demanda · margen {result.capacity_margin_pax_h_direction:+,.0f} pax/h/sentido",
            color,
        )

        self.congestion_summary.setText(
            f"Flujo equivalente = {result.equivalent_road_flow_veh_h:,.1f} veh/h · "
            f"capacidad = {data.road_capacity_veh_h:,.1f} veh/h · "
            f"x = {result.road_degree_of_saturation:.3f}. La frecuencia requerida por "
            f"demanda es {result.required_frequency_bus_h:.2f} bus/h "
            + (
                f"(intervalo {result.required_headway_min:.2f} min)."
                if result.required_frequency_bus_h > 0
                else "(sin demanda capturada)."
            )
        )
        self.congestion_table.setRowCount(len(result.congestion))
        for row, item in enumerate(result.congestion):
            values = (
                item.model,
                f"{result.free_flow_time_min:.2f}",
                "No finito" if item.travel_time_min is None else f"{item.travel_time_min:.2f}",
                "—" if item.delay_min is None else f"{item.delay_min:.2f}",
                "—" if item.commercial_speed_kmh is None else f"{item.commercial_speed_kmh:.2f}",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.congestion_table.setItem(row, column, cell)
        self.congestion_chart.set_data(data, result)
        if result.warnings:
            self.diagnosis.setText("Diagnóstico:\n• " + "\n• ".join(result.warnings))
        else:
            self.diagnosis.setText(
                "Diagnóstico: la configuración no genera advertencias automáticas."
            )

    def clear_result(self) -> None:
        for metric in (
            self.speed_metric,
            self.cycle_metric,
            self.fleet_metric,
            self.capacity_metric,
            self.service_metric,
            self.stop_metric,
            self.dwell_metric,
            self.balance_metric,
        ):
            metric.set_metric("—")
        self.congestion_summary.setText("Sin cálculo.")
        self.congestion_table.setRowCount(0)
        self.congestion_chart.set_data(None, None)
        self.diagnosis.setText("Calcula la línea para generar el diagnóstico.")
