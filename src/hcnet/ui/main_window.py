"""Ventana principal de HCNet Transport."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from PySide6.QtCore import QDate, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from hcnet import __version__
from hcnet.domain.calculations import (
    CalculationError,
    calculate_intersection,
)
from hcnet.domain.models import (
    BranchInput,
    IntersectionProject,
    IntersectionResult,
    SignalOptimizationResult,
)
from hcnet.domain.reporting import calculation_trace_html
from hcnet.domain.roundabout import calculate_roundabout
from hcnet.domain.sample import demonstration_project
from hcnet.domain.scenarios import SearchSettings, baseline_snapshot, optimize
from hcnet.domain.signals import aggregate_demand, prepare_project, timeline
from hcnet.domain.transit import (
    TransitCalculationError,
    TransitLineInput,
    TransitLineResult,
    calculate_transit_line,
)
from hcnet.io.project import (
    export_general_tex,
    export_report_tex,
    export_results_csv,
    export_roundabout_tex,
    export_transit_tex,
    load_project,
    save_project,
)
from hcnet.ui.charts import IntersectionSketch, SaturationChart, SignalTimingDiagram
from hcnet.ui.dialogs import LaneGroupDialog, SignalHeadDialog
from hcnet.ui.roundabout_tab import RoundaboutTab
from hcnet.ui.signal_workspace import OptimizationDialog, PhaseEditor, ScenarioPanel
from hcnet.ui.styles import COLORS, LOS_COLORS, dark_active, set_theme, themed_text
from hcnet.ui.transit_widget import PublicTransportTab


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(3)
        self.label = QLabel(label)
        self.label.setObjectName("metricLabel")
        self.value = QLabel(value)
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
        if color and not dark_active():
            self.value.setStyleSheet(f"color: {color};")
        else:
            self.value.setStyleSheet("")


class MainWindow(QMainWindow):
    PROJECT_FILTER = "Proyecto HCNet (*.hcnet)"
    OPEN_FILTER = PROJECT_FILTER + ";;Proyectos anteriores (*.hcnet.json *.json)"
    PANEL_WIDTHS = (520, 320, 160)

    def __init__(self) -> None:
        super().__init__()
        self.project = self._blank_project()
        self.current_path: Path | None = None
        self.last_result: IntersectionResult | None = None
        self.last_optimization: SignalOptimizationResult | None = None
        self.last_transit_result: TransitLineResult | None = None
        self.dirty = False
        self._loading = False
        self._compact = None

        self.setWindowTitle(f"HCNet Transport {__version__}")
        self.setMinimumSize(480, 330)
        screen = self.screen().availableGeometry()
        self.resize(min(1250, screen.width() - 40), min(840, screen.height() - 55))
        self._set_icon()
        self._create_actions()
        self._create_menu_and_toolbar()
        self._build_ui()
        self._load_project_into_ui(self.project)
        self._set_theme(QSettings("VanLinux", "HCNet Transport").value("dark", False, type=bool))

    @staticmethod
    def _blank_project() -> IntersectionProject:
        branches = [
            BranchInput(chr(65 + index), "", position, 1, 1)
            for index, position in enumerate(("Norte", "Oriente", "Sur", "Poniente"))
        ]
        return IntersectionProject(
            name="", cycle_length_s=0, branches=branches,
            public_transport=TransitLineInput.empty(),
        )

    def _set_icon(self) -> None:
        icon_path = Path(__file__).parents[1] / "resources" / "hcnet.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _resource_icon(self, filename: str) -> QIcon:
        path = Path(__file__).parents[1] / "resources" / filename
        return QIcon(str(path)) if path.exists() else QIcon()

    def _create_actions(self) -> None:
        self.new_action = QAction(self._resource_icon("new.svg"), "Nuevo", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self.new_project)

        self.open_action = QAction(self._resource_icon("open.svg"), "Abrir…", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_project)

        self.save_action = QAction(self._resource_icon("save.svg"), "Guardar", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self.save)

        self.save_as_action = QAction("Guardar como…", self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.save_as_action.triggered.connect(self.save_as)

        self.export_action = QAction("Exportar resultados CSV…", self)
        self.export_action.setIcon(self._resource_icon("export_csv.svg"))
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.triggered.connect(self.export_csv)

        self.demo_action = QAction("Cargar caso demostrativo", self)
        self.demo_action.triggered.connect(self.load_demo)

        self.calculate_action = QAction(
            self._resource_icon("calculate.svg"), "Calcular situación actual", self,
        )
        self.calculate_action.setShortcut("F5")
        self.calculate_action.triggered.connect(self._calculate_active)

        self.quit_action = QAction("Salir", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

        self.about_action = QAction("Acerca de HCNet", self)
        self.about_action.triggered.connect(self.show_about)

    def _create_menu_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        file_menu.addActions([self.new_action, self.open_action])
        file_menu.addSeparator()
        file_menu.addActions([self.save_action, self.save_as_action])
        export_menu = file_menu.addMenu("Exportar")
        export_menu.addAction(self.export_action)
        export_menu.addAction("Informe general .tex…", self._export_general)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        project_menu = self.menuBar().addMenu("Proyecto")
        project_menu.addAction(self.demo_action)
        project_menu.addAction(self.calculate_action)

        view_menu = self.menuBar().addMenu("Vista")
        self.dark_action = view_menu.addAction("Modo oscuro")
        self.dark_action.setCheckable(True)
        self.dark_action.toggled.connect(self._set_theme)

        help_menu = self.menuBar().addMenu("Ayuda")
        help_menu.addAction(self.about_action)

        toolbar = QToolBar("Herramientas principales")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addAction(self.calculate_action)
        toolbar.addSeparator()
        toolbar.addAction(self.export_action)
        self.addToolBar(toolbar)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 12)
        root.setSpacing(12)

        self.page_title = QLabel("HCNet Transport")
        self.page_title.setObjectName("pageTitle")
        root.addWidget(self.page_title)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.scope_tab = self._build_scope_tab()
        self.project_tab = self._build_project_tab()
        self.geometry_tab = self._build_geometry_tab()
        self.groups_tab = self._build_groups_tab()
        self.signals_tab = self._build_signals_tab()
        self.transit_tab = PublicTransportTab()
        self.transit_tab.input_changed.connect(self._transit_changed)
        self.transit_tab.calculate_requested.connect(self.calculate_transit)
        self.transit_tab.export_requested.connect(self._export_transit)
        self.roundabout_tab = RoundaboutTab()
        self.roundabout_tab.input_changed.connect(self._roundabout_changed)
        self.roundabout_tab.calculate_requested.connect(self.calculate_roundabout)
        self.roundabout_tab.export_requested.connect(self._export_roundabout)
        self.results_tab = self._build_results_tab()
        self.trace_tab = self._build_trace_tab()
        self.workspace_choice = QComboBox()
        self.workspace_choice.addItem("↔ Intersección semaforizada", "signal")
        self.workspace_choice.addItem("◇ Rotonda de un carril", "roundabout")
        self.workspace_choice.addItem("◇ Transporte público", "transit")
        self.workspace_choice.addItem("Inicio y alcance", "help")
        self.workspace_choice.setAccessibleName("Tipo de análisis")
        self.workspace_choice.currentIndexChanged.connect(self._workspace_changed)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.workspace_choice, 1)
        self.compact_view = QComboBox()
        self.compact_view.addItems(["Captura", "Esquema y resumen", "Resultados y reporte"])
        self.compact_view.setAccessibleName("Panel visible de intersección")
        self.compact_view.currentIndexChanged.connect(self._update_display)
        toolbar.addWidget(self.compact_view)
        root.addLayout(toolbar)

        for widget, label in (
            (self.project_tab, "Proyecto"), (self.geometry_tab, "Geometría"),
            (self.groups_tab, "Movimientos"), (self.signals_tab, "Semaforización"),
        ):
            i = self.tabs.addTab(widget, f"↔ {label}")
            self.tabs.setTabToolTip(i, "Compartido por el análisis de intersección")

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setDocumentMode(True)
        self.scenario_panel = ScenarioPanel()
        for widget, label in (
            (self.results_tab, "Resultados actuales"), (self.scenario_panel, "Comparar escenarios"),
            (self.trace_tab, "Reporte técnico"),
        ):
            self.detail_tabs.addTab(widget, label)
        self.live_sketch = IntersectionSketch()
        self.live_sketch.interactive = True
        self.live_sketch.setToolTip("Selecciona un acceso en el esquema para agregar un grupo.")
        self.live_sketch.branch_clicked.connect(self._add_at_branch)
        self.live_sketch.setAccessibleName("Geometría y movimientos")
        self.side_panel = self._build_side_panel()
        self.analysis_split = QSplitter(Qt.Orientation.Horizontal)
        self.analysis_split.addWidget(self.tabs)
        self.analysis_split.addWidget(self.live_sketch)
        self.analysis_split.addWidget(self.side_panel)
        self.signal_workspace = QSplitter(Qt.Orientation.Vertical)
        self.signal_workspace.addWidget(self.analysis_split)
        self.signal_workspace.addWidget(self.detail_tabs)
        self.signal_workspace.setSizes([480, 230])
        self.workspaces = QStackedWidget()
        for widget in (
            self.signal_workspace, self.roundabout_tab, self.transit_tab, self.scope_tab,
        ):
            self.workspaces.addWidget(widget)
        root.addWidget(self.workspaces, 1)

        self.setCentralWidget(central)
        self._update_display()
        self.statusBar().showMessage("HCNet Transport listo")

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        super().resizeEvent(event)
        if hasattr(self, "workspaces"):
            self._update_display()

    def _update_display(self, *_args) -> None:
        compact = self.width() < 900 or self.height() < 640
        changed = self._compact != compact
        self._compact = compact
        view = self.compact_view.currentIndex()
        self.page_title.setVisible(not compact)
        self.compact_view.setVisible(compact and self.workspace_choice.currentData() == "signal")
        self.tabs.setVisible(not compact or view == 0)
        self.live_sketch.setVisible(not compact or view == 1)
        self.side_panel.setVisible(not compact or view == 1)
        self.analysis_split.setVisible(not compact or view != 2)
        self.detail_tabs.setVisible(not compact or view == 2)
        if changed and not compact:
            self.analysis_split.setSizes(list(self.PANEL_WIDTHS))
            self.signal_workspace.setSizes([480, 230])

    def _build_side_panel(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 10, 12)
        layout.setSpacing(8)

        title = QLabel("Situación actual")
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        self.summary_status = QLabel()
        self.summary_status.setObjectName("panelStatus")
        self.summary_status.setWordWrap(True)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.guide_title = QLabel()
        self.guide_title.setObjectName("sectionTitle")
        self.guide_title.setWordWrap(True)
        self.guide_detail = QLabel()
        self.guide_detail.setWordWrap(True)
        for widget in (
            title, self.summary_status, self.summary, self.guide_title, self.guide_detail,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)

        self._panel_guides = {
            self.project_tab: ("Proyecto", "Identifica el estudio y define el ciclo de análisis."),
            self.geometry_tab: ("Geometría", "Ajusta los ramales, su orientación y sus carriles."),
            self.groups_tab: ("Movimientos", "Asigna carriles y captura el aforo de cada giro."),
            self.signals_tab: (
                "Semaforización", "Edita las fases, reproduce el ciclo o genera alternativas."
            ),
            self.results_tab: (
                "Resultados actuales", "Consulta el desempeño. Abre un grupo para ver su cálculo."
            ),
            self.scenario_panel: (
                "Comparar escenarios", "Coteja las demoras y las colas de las alternativas."
            ),
            self.trace_tab: ("Reporte técnico", "Consulta las ecuaciones y exporta el informe."),
        }
        for tabs in (self.tabs, self.detail_tabs):
            tabs.currentChanged.connect(partial(self._show_panel_guide, tabs))
            tabs.tabBarClicked.connect(partial(self._show_panel_guide, tabs))
        self._show_panel_guide(self.tabs, self.tabs.currentIndex())
        self._set_summary_status("Calcula la situación actual.")
        scroll = self._scrollable(page)
        scroll.setMinimumWidth(140)
        return scroll

    def _show_panel_guide(self, tabs: QTabWidget, index: int) -> None:
        guide = self._panel_guides.get(tabs.widget(index))
        if guide is not None:
            title, detail = guide
            self.guide_title.setText(title)
            self.guide_detail.setText(detail)

    def _set_summary_status(self, message: str, *, stale: bool = False) -> None:
        self.summary_status.setText(message)
        self.summary_status.setProperty("stale", stale)
        style = self.summary_status.style()
        style.unpolish(self.summary_status)
        style.polish(self.summary_status)

    def _workspace_changed(self, index: int) -> None:
        self.workspaces.setCurrentIndex(index)
        self._update_display()
        self.calculate_action.setEnabled(self.workspace_choice.currentData() != "help")
        if self.workspace_choice.currentData() != "help":
            self._mark_document_dirty()

    def _set_theme(self, dark: bool) -> None:
        self.dark_action.blockSignals(True)
        self.dark_action.setChecked(dark)
        self.dark_action.blockSignals(False)
        set_theme(dark)
        self.scope_browser.setHtml(themed_text(self.scope_html))
        self.refresh_trace()
        QSettings("VanLinux", "HCNet Transport").setValue("dark", dark)

    def _build_project_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        banner = QLabel(
            "Identifica el estudio y configura el ciclo de la intersección."
        )
        banner.setObjectName("infoBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 10, 0)

        identification = QGroupBox("Identificación del estudio")
        form = QFormLayout(identification)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit()
        self.location_edit = QLineEdit()
        self.analyst_edit = QLineEdit()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Proyecto:", self.name_edit)
        form.addRow("Ubicación:", self.location_edit)
        form.addRow("Analista:", self.analyst_edit)
        form.addRow("Fecha del estudio:", self.date_edit)
        details_layout.addWidget(identification)

        parameters = QGroupBox("Parámetros generales")
        parameters_form = QFormLayout(parameters)
        parameters_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.cycle_spin = QDoubleSpinBox()
        self.cycle_spin.setRange(0, 600)
        self.cycle_spin.setSpecialValueText("Por capturar")
        self.cycle_spin.setDecimals(1)
        self.cycle_spin.setSingleStep(5)
        self.cycle_spin.setSuffix(" s")
        self.period_spin = QDoubleSpinBox()
        self.period_spin.setRange(0.05, 4)
        self.period_spin.setDecimals(2)
        self.period_spin.setSingleStep(0.25)
        self.period_spin.setSuffix(" h")
        parameters_form.addRow("Longitud de ciclo, C:", self.cycle_spin)
        parameters_form.addRow("Periodo de análisis, T:", self.period_spin)
        details_layout.addWidget(parameters)

        notes_box = QGroupBox("Notas del proyecto")
        notes_layout = QVBoxLayout(notes_box)
        self.project_notes = QPlainTextEdit()
        self.project_notes.setMinimumHeight(75)
        self.project_notes.setPlaceholderText("Origen de aforos, supuestos y observaciones…")
        notes_layout.addWidget(self.project_notes)
        details_layout.addWidget(notes_box)
        details_layout.addStretch()

        sketch_box = QGroupBox("Esquema y demanda por acceso")
        sketch_layout = QVBoxLayout(sketch_box)
        self.sketch = IntersectionSketch()
        sketch_layout.addWidget(self.sketch)
        sketch_note = QLabel(
            "Esquema orientativo. La geometría detallada se define mediante grupos de carriles."
        )
        sketch_note.setObjectName("pageSubtitle")
        sketch_note.setWordWrap(True)
        sketch_layout.addWidget(sketch_note)

        splitter.addWidget(details)
        splitter.addWidget(sketch_box)
        splitter.setSizes([610, 450])
        layout.addWidget(splitter, 1)

        for widget in (self.name_edit, self.location_edit, self.analyst_edit):
            widget.textChanged.connect(self._mark_document_dirty)
        self.date_edit.dateChanged.connect(self._mark_document_dirty)
        self.cycle_spin.valueChanged.connect(self._mark_dirty)
        self.period_spin.valueChanged.connect(self._mark_dirty)
        self.project_notes.textChanged.connect(self._mark_document_dirty)
        return _ProjectScrollArea(page, splitter)

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _build_geometry_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Geometría de la intersección")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Asigna una letra a cada ramal y define sus carriles de entrada y salida."
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.branch_count_combo = QComboBox()
        self.branch_count_combo.addItem("Dos ramales (A–B)", 2)
        self.branch_count_combo.addItem("Tres ramales (A–C)", 3)
        self.branch_count_combo.addItem("Cuatro ramales (A–D)", 4)
        self.branch_count_combo.currentIndexChanged.connect(self._geometry_changed)
        header.addWidget(QLabel("Tipo:"))
        header.addWidget(self.branch_count_combo)
        layout.addLayout(header)

        note = QLabel(
            "Convención: el usuario elige después los recorridos con pares origen–destino, "
            "por ejemplo A → C. El número de carril se cuenta desde el borde izquierdo "
            "del acceso en el sentido de circulación. Captura el azimut desde el norte "
            "en sentido horario (0° norte, 90° oriente)."
        )
        note.setObjectName("infoBanner")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.geometry_table = QTableWidget(4, 6)
        self.geometry_table.setHorizontalHeaderLabels(
            ["Letra", "Nombre del ramal", "Ubicación", "Carriles entrada", "Carriles salida",
             "Azimut (°)"]
        )
        self.geometry_table.verticalHeader().setVisible(False)
        self.geometry_table.setAlternatingRowColors(True)
        self.geometry_table.verticalHeader().setDefaultSectionSize(42)
        self.geometry_table.setMinimumHeight(215)
        self.geometry_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.geometry_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.geometry_table.itemChanged.connect(self._geometry_changed)
        layout.addWidget(self.geometry_table)

        summary = QLabel(
            "Los carriles de entrada delimitan las opciones disponibles al crear cada movimiento. "
            "Si cambia la geometría, revise que los movimientos existentes sigan siendo válidos."
        )
        summary.setObjectName("pageSubtitle")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addStretch()
        return self._scrollable(page)

    def _populate_geometry_table(self) -> None:
        self.geometry_table.blockSignals(True)
        positions = ("Norte", "Oriente", "Sur", "Poniente")
        for row, branch in enumerate(self.project.branches[:4]):
            code_item = QTableWidgetItem(branch.code)
            code_item.setFlags(code_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.geometry_table.setItem(row, 0, code_item)
            self.geometry_table.setItem(row, 1, QTableWidgetItem(branch.name))
            position_item = QTableWidgetItem(branch.position or positions[row])
            position_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.geometry_table.setItem(row, 2, position_item)
            inbound = QSpinBox()
            inbound.setRange(1, 12)
            inbound.setValue(branch.inbound_lanes)
            inbound.valueChanged.connect(self._geometry_changed)
            outbound = QSpinBox()
            outbound.setRange(1, 12)
            outbound.setValue(branch.outbound_lanes)
            outbound.valueChanged.connect(self._geometry_changed)
            self.geometry_table.setCellWidget(row, 3, inbound)
            self.geometry_table.setCellWidget(row, 4, outbound)
            angle = QDoubleSpinBox()
            angle.setRange(0, 359.99)
            angle.setDecimals(2)
            angle.setSuffix("°")
            angle.setValue(branch.azimuth)
            angle.valueChanged.connect(self._geometry_changed)
            self.geometry_table.setCellWidget(row, 5, angle)
        self.geometry_table.blockSignals(False)
        self._update_geometry_visibility()

    def _update_geometry_visibility(self) -> None:
        count = int(self.branch_count_combo.currentData() or 4)
        for row in range(4):
            self.geometry_table.setRowHidden(row, row >= count)

    def _geometry_changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_geometry_visibility()
        self._update_project_geometry_from_ui()
        self._refresh_input_table()
        self._refresh_signal_table()
        self._mark_dirty()

    def _update_project_geometry_from_ui(self) -> None:
        if not hasattr(self, "geometry_table"):
            return
        branches: list[BranchInput] = []
        for row in range(4):
            code_item = self.geometry_table.item(row, 0)
            name_item = self.geometry_table.item(row, 1)
            position_item = self.geometry_table.item(row, 2)
            inbound = self.geometry_table.cellWidget(row, 3)
            outbound = self.geometry_table.cellWidget(row, 4)
            angle = self.geometry_table.cellWidget(row, 5)
            if code_item is None or name_item is None or position_item is None:
                continue
            branches.append(
                BranchInput(
                    code=code_item.text().strip(),
                    name=name_item.text().strip(),
                    position=position_item.text().strip(),
                    inbound_lanes=inbound.value(),
                    outbound_lanes=outbound.value(),
                    azimuth_deg=angle.value(),
                )
            )
        if len(branches) == 4:
            self.project.branches = branches
        self.project.branch_count = int(self.branch_count_combo.currentData() or 4)

    def _build_groups_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Movimientos y asignación de carriles")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Cada fila indica de qué ramal parte el flujo, a cuál llega y qué carriles utiliza."
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch()

        add_button = QPushButton("Agregar grupo")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self.add_group)
        edit_button = QPushButton("Editar")
        edit_button.clicked.connect(self.edit_selected_group)
        duplicate_button = QPushButton("Duplicar")
        duplicate_button.clicked.connect(self.duplicate_selected_group)
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_selected_group)
        for button in (add_button, edit_button, duplicate_button, delete_button):
            heading.addWidget(button)
        layout.addLayout(heading)

        self.input_table = QTableWidget(0, 11)
        self.input_table.setHorizontalHeaderLabels(
            [
                "Origen → destino",
                "Carriles",
                "Fase",
                "V (veh/h)",
                "g (s)",
                "FHMD",
                "s₀",
                "VFL (km/h)",
                "Longitud (m)",
                "Pesados",
                "Observaciones",
            ]
        )
        self.input_table.setAlternatingRowColors(True)
        self.input_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.input_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.input_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.input_table.verticalHeader().setVisible(False)
        self.input_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.input_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.input_table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        self.input_table.doubleClicked.connect(self.edit_selected_group)
        layout.addWidget(self.input_table, 1)

        footer = QHBoxLayout()
        self.groups_summary = QLabel()
        self.groups_summary.setObjectName("pageSubtitle")
        footer.addWidget(self.groups_summary)
        footer.addStretch()
        up_button = QPushButton("Subir")
        down_button = QPushButton("Bajar")
        up_button.clicked.connect(lambda: self.move_selected_group(-1))
        down_button.clicked.connect(lambda: self.move_selected_group(1))
        footer.addWidget(up_button)
        footer.addWidget(down_button)
        layout.addLayout(footer)
        self.input_table.setMinimumHeight(240)
        return self._scrollable(page)

    def _build_signals_tab(self) -> QWidget:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Configuración y optimización semafórica")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Ubica cada semáforo, asigna los movimientos que controla y optimiza el ciclo."
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box)
        top.addStretch()
        self.optimize_button = QPushButton("Optimizar intersección")
        self.optimize_button.setObjectName("primaryButton")
        self.optimize_button.clicked.connect(self._open_optimizer)
        self.optimize_button.setEnabled(False)
        top.addWidget(self.optimize_button)
        layout.addLayout(top)

        configuration = QGroupBox("Verde mínimo y valores iniciales para fases nuevas")
        config_layout = QGridLayout(configuration)
        self.optimization_method_combo = QComboBox()
        self.optimization_method_combo.addItem("Webster · ciclo y reparto de verdes", "Webster")
        self.signal_lost_spin = QDoubleSpinBox()
        self.signal_lost_spin.setRange(0.1, 30)
        self.signal_lost_spin.setDecimals(1)
        self.signal_lost_spin.setSuffix(" s/fase")
        self.minimum_green_spin = QDoubleSpinBox()
        self.minimum_green_spin.setRange(1, 120)
        self.minimum_green_spin.setDecimals(1)
        self.minimum_green_spin.setSuffix(" s")
        self.yellow_spin = QDoubleSpinBox()
        self.yellow_spin.setRange(0, 15)
        self.yellow_spin.setDecimals(1)
        self.yellow_spin.setSuffix(" s")
        self.all_red_spin = QDoubleSpinBox()
        self.all_red_spin.setRange(0, 15)
        self.all_red_spin.setDecimals(1)
        self.all_red_spin.setSuffix(" s")
        self.optimization_method_combo.hide()
        config_layout.addWidget(QLabel("Pérdida para Webster:"), 0, 2)
        config_layout.addWidget(self.signal_lost_spin, 0, 3)
        config_layout.addWidget(QLabel("Verde mínimo:"), 1, 0)
        config_layout.addWidget(self.minimum_green_spin, 1, 1)
        config_layout.addWidget(QLabel("Amarillo:"), 1, 2)
        config_layout.addWidget(self.yellow_spin, 1, 3)
        config_layout.addWidget(QLabel("Todo rojo:"), 1, 4)
        config_layout.addWidget(self.all_red_spin, 1, 5)
        for widget in (
            self.optimization_method_combo,
            self.signal_lost_spin,
            self.minimum_green_spin,
            self.yellow_spin,
            self.all_red_spin,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._mark_dirty)
            else:
                widget.valueChanged.connect(self._mark_dirty)
        layout.addWidget(configuration)
        self.phase_editor = PhaseEditor()
        self.phase_editor.changed.connect(self._phases_changed)
        layout.addWidget(self.phase_editor)

        heads_box = QGroupBox("Semáforos instalados")
        heads_layout = QVBoxLayout(heads_box)
        buttons = QHBoxLayout()
        add_button = QPushButton("Agregar semáforo")
        add_button.clicked.connect(self.add_signal_head)
        edit_button = QPushButton("Editar")
        edit_button.clicked.connect(self.edit_selected_signal_head)
        delete_button = QPushButton("Eliminar")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_selected_signal_head)
        buttons.addWidget(add_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        self.signal_count_label = QLabel()
        self.signal_count_label.setObjectName("pageSubtitle")
        buttons.addWidget(self.signal_count_label)
        heads_layout.addLayout(buttons)
        self.signal_table = QTableWidget(0, 5)
        self.signal_table.setHorizontalHeaderLabels(
            ["Semáforo", "Ramal", "Tipo", "Fase", "Movimientos controlados"]
        )
        self.signal_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.signal_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.signal_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.signal_table.setMinimumHeight(245)
        self.signal_table.verticalHeader().setVisible(False)
        self.signal_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.signal_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.signal_table.doubleClicked.connect(self.edit_selected_signal_head)
        heads_layout.addWidget(self.signal_table)
        layout.addWidget(heads_box)

        diagram_box = QGroupBox("Diagrama de bandas · condiciones actuales")
        diagram_layout = QVBoxLayout(diagram_box)
        self.optimization_summary = QLabel("Sin optimización calculada.")
        self.optimization_summary.setObjectName("pageSubtitle")
        self.optimization_summary.setWordWrap(True)
        diagram_layout.addWidget(self.optimization_summary)
        self.timing_diagram = SignalTimingDiagram()
        time_controls = QHBoxLayout()
        self.cycles = QSpinBox()
        self.cycles.setRange(1, 3)
        self.cycles.valueChanged.connect(self.timing_diagram.set_cycles)
        self.play_button = QPushButton("Reproducir ciclo")
        self.play_button.clicked.connect(self._play_cycle)
        self.play_reset = QPushButton("Reiniciar")
        self.play_reset.clicked.connect(self._reset_cycle)
        self.play_timer = QTimer(self, interval=100)
        self.play_timer.timeout.connect(self._advance_cycle)
        self.play_time = 0.0
        self.displayed_timeline: SignalOptimizationResult | None = None
        self.play_label = QLabel()
        for control in (QLabel("Ciclos"), self.cycles, self.play_button, self.play_reset,
                        self.play_label):
            time_controls.addWidget(control)
        diagram_layout.addLayout(time_controls)
        diagram_layout.addWidget(self.timing_diagram)
        layout.addWidget(diagram_box)
        scroll.setWidget(page)
        outer_layout.addWidget(scroll)
        return outer

    def _build_results_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Desempeño operacional")
        title.setObjectName("sectionTitle")
        self.result_timestamp = QLabel("Sin resultados")
        self.result_timestamp.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.result_timestamp)
        top.addLayout(title_box)
        top.addStretch()
        calculate_button = QPushButton("Calcular situación actual")
        calculate_button.setObjectName("primaryButton")
        calculate_button.clicked.connect(self.calculate)
        top.addWidget(calculate_button)
        layout.addLayout(top)

        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        self.los_card = MetricCard("NIVEL DE SERVICIO")
        self.delay_card = MetricCard("DEMORA PONDERADA")
        self.x_card = MetricCard("GRADO DE SATURACIÓN CRÍTICO")
        self.volume_card = MetricCard("VOLUMEN DE ENTRADA")
        self.queue_card = MetricCard("COLA P95 MÁXIMA")
        self.travel_time_card = MetricCard("TIEMPO DE VIAJE PONDERADO")
        cards.addWidget(self.los_card, 0, 0)
        cards.addWidget(self.delay_card, 0, 1)
        cards.addWidget(self.x_card, 0, 2)
        cards.addWidget(self.volume_card, 0, 3)
        cards.addWidget(self.queue_card, 1, 0, 1, 2)
        cards.addWidget(self.travel_time_card, 1, 2, 1, 2)
        layout.addLayout(cards)

        splitter = QSplitter(Qt.Orientation.Vertical)
        chart_box = QGroupBox("Grado de saturación por grupo, X = v/c")
        chart_layout = QVBoxLayout(chart_box)
        self.saturation_chart = SaturationChart()
        chart_layout.addWidget(self.saturation_chart)
        splitter.addWidget(chart_box)

        lower = QSplitter(Qt.Orientation.Horizontal)
        self.results_table = QTableWidget(0, 15)
        self.results_table.setHorizontalHeaderLabels(
            [
                "Movimiento",
                "Fase",
                "v",
                "s",
                "c",
                "X",
                "d",
                "LOS",
                "Cola media",
                "Cola P95",
                "P95 (m)",
                "VFL",
                "t₀",
                "t viaje",
                "Residual",
            ]
        )
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.results_table.doubleClicked.connect(self._open_trace_from_result)
        lower.addWidget(self.results_table)

        diagnosis_box = QWidget()
        diagnosis_layout = QVBoxLayout(diagnosis_box)
        diagnosis_layout.setContentsMargins(8, 0, 0, 0)
        diagnosis_title = QLabel("Diagnóstico")
        diagnosis_title.setObjectName("sectionTitle")
        self.warning_list = QListWidget()
        self.warning_list.setWordWrap(True)
        diagnosis_layout.addWidget(diagnosis_title)
        diagnosis_layout.addWidget(self.warning_list, 1)
        lower.addWidget(diagnosis_box)
        lower.setSizes([850, 340])
        splitter.addWidget(lower)
        splitter.setSizes([280, 330])
        splitter.setMinimumHeight(430)
        layout.addWidget(splitter, 1)
        return self._scrollable(page)

    def _build_trace_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Reporte técnico y memoria de cálculo")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Revisa las ecuaciones por grupo o exporta el informe completo como LaTeX."
        )
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        export_button = QPushButton("Exportar reporte .tex")
        export_button.setObjectName("primaryButton")
        export_button.clicked.connect(self.export_tex)
        header.addWidget(export_button)
        self.trace_selector = QComboBox()
        self.trace_selector.setMinimumWidth(290)
        self.trace_selector.currentIndexChanged.connect(self.refresh_trace)
        header.addWidget(self.trace_selector)
        layout.addLayout(header)

        self.trace_browser = QTextBrowser()
        self.trace_browser.setOpenExternalLinks(True)
        layout.addWidget(self.trace_browser, 1)
        self.trace_browser.setMinimumHeight(280)
        return self._scrollable(page)

    def _build_scope_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        self.scope_browser = browser
        self.scope_html = f"""
            <style>
              body {{ font-family: sans-serif; color: #202124; margin: 22px; }}
              h1 {{ color: #202124; font-size: 26px; margin-bottom: 2px; }}
              h2, h3 {{ color: #30343b; }}
              .lead {{ color: #5f6368; font-size: 14px; margin-bottom: 18px; }}
              .panel {{ background: #f1f3f4; border-left: 4px solid #5f6368;
                        padding: 12px; margin: 14px 0; }}
              .scope {{ background: #f7f7f7; border: 1px solid #dadce0;
                        padding: 12px; margin: 14px 0; }}
              table {{ border-collapse: collapse; margin: 10px 0 18px 0; width: 100%; }}
              th, td {{ border-bottom: 1px solid #dadce0; padding: 7px; text-align: left; }}
              th {{ color: #30343b; width: 180px; }}
              li {{ margin: 5px 0; }}
              a {{ color: #3f444b; }}
            </style>
            <h1>HCNet Transport</h1>
            <p class="lead"><b>Highway Capacity and Network Evaluation Tool</b><br>
            Herramienta libre para el análisis transparente de capacidad,
            desempeño operacional y nivel de servicio.</p>

            <table>
              <tr><th>Versión</th><td>{__version__}</td></tr>
              <tr><th>Desarrollador</th><td>Héctor Alonso Benítez García</td></tr>
              <tr><th>Licencia</th><td>GNU General Public License v3.0</td></tr>
              <tr><th>Plataforma actual</th><td>Linux</td></tr>
              <tr><th>Repositorio</th><td>
                <a href="https://github.com/VanLinux/hcnet-transport">
                github.com/VanLinux/hcnet-transport</a></td></tr>
            </table>

            <div class="scope"><b>Pestañas:</b> ↔ análisis de intersección compartido.
            ◇ cálculo independiente con reporte propio.</div>
            <div class="scope"><b>Alcance implementado:</b> intersecciones aisladas de
            dos, tres o cuatro ramales; movimientos A–D por carril y fase; capacidad, grado
            de saturación X, demora d₁+d₂+d₃, nivel de servicio A–F, colas diagnósticas,
            tiempo de viaje y comparación de programas semafóricos. Incluye además planeación
            de una línea de transporte público: velocidades, ciclo, flota, frecuencia,
            capacidad, paradas, acceso, intercambio de pasajeros y comparación de
            funciones volumen–demora. El módulo de rotondas de un carril estima capacidad,
            colas, demora y LOS, y permite predimensionar la geometría.</div>

            <h3>Flujo de trabajo</h3>
            <ol>
              <li>Identifica el estudio y captura el nombre del analista.</li>
              <li>Define ramales, carriles y recorridos origen–destino.</li>
              <li>Configura semáforos y optimiza el plan de tiempo fijo.</li>
              <li>Dimensiona la línea de transporte público y compara la congestión.</li>
              <li>Calcula y revisa el diagnóstico de la intersección.</li>
              <li>Examina la memoria matemática y exporta resultados CSV o el reporte
              técnico completo en LaTeX.</li>
            </ol>

            <h3>Supuestos principales</h3>
            <ul>
              <li>Demanda estacionaria durante el periodo de análisis.</li>
              <li>El usuario define correctamente los grupos de carriles y verdes efectivos.</li>
              <li>Los factores fLU, fa, fturn, PF, k e I proceden del estudio
              o de una fuente autorizada.</li>
              <li>d₃ se introduce directamente cuando existe una cola inicial.</li>
              <li>La demanda de transporte público es direccional y estacionaria; los
              ascensos y descensos capturados representan la parada crítica media.</li>
            </ul>
            <h3>No incluido todavía</h3>
            <ul>
              <li>Detección automática de conflictos entre movimientos.</li>
              <li>Cola percentil 95 certificada por HCM/HCS.</li>
              <li>Coordinación de corredores, control actuado y mínimos peatonales.</li>
              <li>Rotondas multicarril, otros cruces no semaforizados y autopistas.</li>
              <li>Calibración automática para condiciones mexicanas.</li>
              <li>Asignación de red, matrices OD, transbordos, tarifas y uso de suelo
              propios de modelos estratégicos como TRANUS.</li>
            </ul>

            <div class="panel"><b>Uso responsable:</b> es una herramienta educativa
            independiente,
            no una implementación certificada del HCM 7 ni un sustituto de HCS. Verifica
            los resultados antes de utilizarlos en un estudio profesional.</div>
            """
        browser.setHtml(themed_text(self.scope_html))
        layout.addWidget(browser)
        return page

    def _project_from_ui(self) -> IntersectionProject:
        self._update_project_geometry_from_ui()
        return replace(
            self.project,
            name=self.name_edit.text().strip(),
            location=self.location_edit.text().strip(),
            analyst=self.analyst_edit.text().strip(),
            study_date=self.date_edit.date().toString("yyyy-MM-dd"),
            cycle_length_s=self.cycle_spin.value(),
            analysis_period_h=self.period_spin.value(),
            branch_count=int(self.branch_count_combo.currentData() or 4),
            optimization_method=str(self.optimization_method_combo.currentData() or "Webster"),
            signal_lost_time_s=self.signal_lost_spin.value(),
            minimum_green_s=self.minimum_green_spin.value(),
            yellow_time_s=self.yellow_spin.value(),
            all_red_time_s=self.all_red_spin.value(),
            public_transport=self.transit_tab.input_data(),
            workspace=(
                self.workspace_choice.currentData() if self.workspace_choice.currentData() != "help"
                else self.project.workspace
            ),
            notes=self.project_notes.toPlainText().strip(),
        )

    def _load_project_into_ui(self, project: IntersectionProject) -> None:
        self._loading = True
        self.project = project
        self.name_edit.setText(project.name)
        self.location_edit.setText(project.location)
        self.analyst_edit.setText(project.analyst)
        parsed_date = QDate.fromString(project.study_date, "yyyy-MM-dd")
        self.date_edit.setDate(parsed_date if parsed_date.isValid() else QDate.currentDate())
        self.cycle_spin.setValue(project.cycle_length_s)
        self.period_spin.setValue(project.analysis_period_h)
        self.project_notes.setPlainText(project.notes)
        self.branch_count_combo.setCurrentIndex(
            max(0, self.branch_count_combo.findData(project.branch_count))
        )
        self._populate_geometry_table()
        self.optimization_method_combo.setCurrentIndex(
            max(0, self.optimization_method_combo.findData(project.optimization_method))
        )
        self.signal_lost_spin.setValue(project.signal_lost_time_s)
        self.minimum_green_spin.setValue(project.minimum_green_s)
        self.yellow_spin.setValue(project.yellow_time_s)
        self.all_red_spin.setValue(project.all_red_time_s)
        self.transit_tab.set_input(project.public_transport)
        self.roundabout_tab.set_input(project.roundabout)
        self.workspace_choice.setCurrentIndex(max(0, self.workspace_choice.findData(
            project.workspace
        )))
        self._refresh_input_table()
        self._refresh_signal_table()
        self.sketch.set_project(project)
        self._clear_results()
        self._refresh_program()
        self._loading = False
        self.dirty = False
        self._refresh_window_title()

    def _refresh_input_table(self, selected_row: int | None = None) -> None:
        table = self.input_table
        table.setRowCount(len(self.project.lane_groups))
        for row, group in enumerate(self.project.lane_groups):
            try:
                effective = aggregate_demand(group)
            except ValueError:
                effective = None
            volume = effective.volume_veh_h if effective is not None else 0.0
            green = next((p.green for p in self.project.phases if p.number == group.signal_phase),
                         group.effective_green_s)
            values = [
                f"{group.origin_branch} → {'/'.join(group.destination_branches)}",
                ", ".join(str(item) for item in group.lane_indices),
                str(group.signal_phase),
                f"{volume:,.1f}",
                f"{green:.2f}",
                f"{group.peak_hour_factor:.3f}",
                f"{group.base_saturation_flow_pc_h_ln:,.0f}",
                f"{group.free_flow_speed_kmh:.1f}",
                f"{group.approach_length_m:.1f}",
                f"{group.heavy_vehicles_percent:.1f} %",
                group.notes,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {1, 2, 3, 4, 5, 6, 7, 8, 9}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
        total = sum(float(table.item(i, 3).text().replace(",", ""))
                    for i in range(table.rowCount()))
        self.groups_summary.setText(
            f"{len(self.project.lane_groups)} grupos · Volumen total: {total:,.0f} veh/h · "
            "Doble clic para editar"
        )
        if selected_row is not None and 0 <= selected_row < table.rowCount():
            table.selectRow(selected_row)
        if hasattr(self, "sketch"):
            self.sketch.set_project(self.project)
            self.live_sketch.set_project(self.project)

    def _phases_changed(self) -> None:
        self._refresh_input_table()
        self._refresh_signal_table()
        self._mark_dirty()

    def selected_group_index(self) -> int | None:
        selection = self.input_table.selectionModel().selectedRows()
        return selection[0].row() if selection else None

    def add_group(self) -> None:
        self._add_at_branch("")

    def _add_at_branch(self, code: str) -> None:
        self.project = self._project_from_ui()
        branch = self.project.branch(code or "A")
        if branch is None:
            return
        self.tabs.setCurrentWidget(self.groups_tab)
        self.compact_view.setCurrentIndex(0)
        dialog = LaneGroupDialog(
            origin=branch.code,
            cycle_length_s=self.cycle_spin.value(),
            project=self.project,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project.lane_groups.append(dialog.lane_group())
            self._refresh_input_table(len(self.project.lane_groups) - 1)
            self._mark_dirty()

    def edit_selected_group(self, *_args) -> None:
        index = self.selected_group_index()
        if index is None:
            QMessageBox.information(
                self, "Selecciona un grupo", "Selecciona la fila que deseas editar."
            )
            return
        self.project = self._project_from_ui()
        dialog = LaneGroupDialog(
            self.project.lane_groups[index],
            cycle_length_s=self.cycle_spin.value(),
            project=self.project,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project.lane_groups[index] = dialog.lane_group()
            self._refresh_input_table(index)
            self._mark_dirty()

    def duplicate_selected_group(self) -> None:
        index = self.selected_group_index()
        if index is None:
            QMessageBox.information(
                self, "Selecciona un grupo", "Selecciona la fila que deseas duplicar."
            )
            return
        source = self.project.lane_groups[index]
        duplicate = replace(
            source,
            identifier=uuid4().hex[:12],
            movement=f"{source.movement} (copia)",
        )
        self.project.lane_groups.insert(index + 1, duplicate)
        self._refresh_input_table(index + 1)
        self._mark_dirty()

    def delete_selected_group(self) -> None:
        index = self.selected_group_index()
        if index is None:
            QMessageBox.information(
                self, "Selecciona un grupo", "Selecciona la fila que deseas eliminar."
            )
            return
        group = self.project.lane_groups[index]
        answer = QMessageBox.question(
            self,
            "Eliminar grupo",
            f"¿Eliminar {group.label}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            removed_id = self.project.lane_groups[index].identifier
            del self.project.lane_groups[index]
            for head in self.project.signal_heads:
                head.controlled_group_ids = tuple(
                    item for item in head.controlled_group_ids if item != removed_id
                )
            self._refresh_input_table(min(index, len(self.project.lane_groups) - 1))
            self._refresh_signal_table()
            self._mark_dirty()

    def move_selected_group(self, offset: int) -> None:
        index = self.selected_group_index()
        if index is None:
            return
        destination = index + offset
        if not 0 <= destination < len(self.project.lane_groups):
            return
        groups = self.project.lane_groups
        groups[index], groups[destination] = groups[destination], groups[index]
        self._refresh_input_table(destination)
        self._mark_dirty()

    def _refresh_signal_table(self, selected_row: int | None = None) -> None:
        if not hasattr(self, "signal_table"):
            return
        groups = {group.identifier: group.label for group in self.project.lane_groups}
        self.signal_table.setRowCount(len(self.project.signal_heads))
        for row, head in enumerate(self.project.signal_heads):
            movement_labels = [
                groups[identifier]
                for identifier in head.controlled_group_ids
                if identifier in groups
            ]
            values = [
                head.name,
                head.branch_code,
                head.signal_type,
                str(head.signal_phase),
                "; ".join(movement_labels) or "Sin movimientos",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {1, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.signal_table.setItem(row, column, item)
        self.signal_count_label.setText(
            f"{len(self.project.signal_heads)} semáforo"
            f"{'s' if len(self.project.signal_heads) != 1 else ''} configurado"
            f"{'s' if len(self.project.signal_heads) != 1 else ''}"
        )
        if selected_row is not None and 0 <= selected_row < self.signal_table.rowCount():
            self.signal_table.selectRow(selected_row)

    def selected_signal_head_index(self) -> int | None:
        selection = self.signal_table.selectionModel().selectedRows()
        return selection[0].row() if selection else None

    def add_signal_head(self) -> None:
        self.project = self._project_from_ui()
        if not self.project.lane_groups:
            QMessageBox.information(
                self,
                "Primero crea movimientos",
                "Agrega al menos un movimiento antes de configurar sus semáforos.",
            )
            self.tabs.setCurrentWidget(self.groups_tab)
            return
        dialog = SignalHeadDialog(self.project, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project.signal_heads.append(dialog.signal_head())
            self._refresh_signal_table(len(self.project.signal_heads) - 1)
            self._mark_dirty()

    def edit_selected_signal_head(self, *_args) -> None:
        index = self.selected_signal_head_index()
        if index is None:
            QMessageBox.information(
                self, "Selecciona un semáforo", "Selecciona la fila que deseas editar."
            )
            return
        self.project = self._project_from_ui()
        dialog = SignalHeadDialog(self.project, self.project.signal_heads[index], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.project.signal_heads[index] = dialog.signal_head()
            self._refresh_signal_table(index)
            self._mark_dirty()

    def delete_selected_signal_head(self) -> None:
        index = self.selected_signal_head_index()
        if index is None:
            QMessageBox.information(
                self, "Selecciona un semáforo", "Selecciona la fila que deseas eliminar."
            )
            return
        head = self.project.signal_heads[index]
        answer = QMessageBox.question(
            self,
            "Eliminar semáforo",
            f"¿Eliminar {head.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            del self.project.signal_heads[index]
            self._refresh_signal_table(min(index, len(self.project.signal_heads) - 1))
            self._mark_dirty()

    def _open_optimizer(self) -> None:
        dialog = OptimizationDialog(self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.optimize_signal_plan(dialog.settings())

    def optimize_signal_plan(self, settings: SearchSettings | None = None) -> bool:
        if self.last_result is None:
            QMessageBox.information(
                self, "Evaluación pendiente", "Primero calcula las condiciones actuales.",
            )
            return False
        try:
            scenarios = optimize(self._project_from_ui(), settings or SearchSettings())
        except ValueError as exc:
            QMessageBox.warning(self, "No es posible optimizar", str(exc))
            return False
        self.project.scenarios.extend(scenarios)
        self.last_optimization = scenarios[-1].plan
        self._mark_document_dirty()
        self.scenario_panel.refresh(self.project, self.last_result)
        self.detail_tabs.setCurrentWidget(self.scenario_panel)
        self.compact_view.setCurrentIndex(2)
        self.statusBar().showMessage(f"{len(scenarios)} alternativas calculadas", 6000)
        return True

    def _show_optimization(self, optimization: SignalOptimizationResult) -> None:
        self.last_optimization = optimization
        self.optimization_summary.setText(
            f"Plan histórico de una versión anterior · {optimization.method}"
        )

    def _refresh_program(self) -> None:
        project = self._project_from_ui()
        self.phase_editor.refresh(project)
        self._reset_cycle()
        try:
            prepared = prepare_project(project)
            self.displayed_timeline = timeline(prepared)
        except ValueError as exc:
            self.displayed_timeline = None
            self.optimization_summary.setText(str(exc))
        else:
            self.optimization_summary.setText(
                "Condiciones actuales"
                if self.displayed_timeline else "Define los intervalos de un ciclo completo."
            )
        self.play_button.setEnabled(self.displayed_timeline is not None)
        self.timing_diagram.set_data(project, self.displayed_timeline)

    def _play_cycle(self) -> None:
        if self.displayed_timeline is None:
            return
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.play_button.setText("Continuar ciclo")
        else:
            self.play_timer.start()
            self.play_button.setText("Pausar ciclo")

    def _reset_cycle(self) -> None:
        self.play_timer.stop()
        self.play_time = 0.0
        self.play_label.clear()
        self.play_button.setText("Reproducir ciclo")
        self.live_sketch.active_phase = None
        self.live_sketch.update()
        self.timing_diagram.set_cursor(None)

    def _advance_cycle(self) -> None:
        plan = self.displayed_timeline
        if plan is None:
            return
        self.play_time = (self.play_time + 0.1) % plan.cycle_length_s
        for phase in plan.phases:
            if phase.start_s <= self.play_time < phase.end_s:
                elapsed = self.play_time - phase.start_s
                if elapsed < phase.green_s:
                    state, active = "verde", phase.phase_number
                elif elapsed < phase.green_s + phase.yellow_s:
                    state, active = "amarillo", -1
                else:
                    state, active = "todo rojo", -1
                self.live_sketch.active_phase = active
                self.live_sketch.update()
                self.timing_diagram.set_cursor(self.play_time)
                self.play_label.setText(f"{self.play_time:.1f} s · F{phase.phase_number} · {state}")
                break

    def _calculate_active(self) -> None:
        if self.workspaces.currentWidget() is self.transit_tab:
            self.calculate_transit()
        elif self.workspaces.currentWidget() is self.roundabout_tab:
            self.calculate_roundabout()
        else:
            self.calculate()

    def calculate(self, *_args, switch_tab: bool = True, show_errors: bool = True) -> bool:
        self.project = self._project_from_ui()
        try:
            result = calculate_intersection(self.project)
        except CalculationError as exc:
            if show_errors:
                QMessageBox.warning(
                    self, "No es posible calcular", "\n".join(exc.messages),
                )
            self.statusBar().showMessage("Cálculo detenido por datos inválidos", 6000)
            return False

        self.last_result = result
        snapshot = baseline_snapshot(self.project)
        if snapshot != self.project.last_evaluated:
            self.project.last_evaluated = snapshot
            if show_errors:
                self._mark_document_dirty()
        prepared = prepare_project(self.project)
        self._show_results(result, prepared)
        self.scenario_panel.refresh(self.project, result)
        self.optimize_button.setEnabled(self.displayed_timeline is not None)
        self._set_summary_status("Escenario 0 · Cálculo vigente")
        self.summary.setText(
            f"Nivel de servicio {result.level_of_service}\n"
            f"Demora {result.weighted_control_delay_s_veh:.1f} s/veh\n"
            f"v/c crítico {result.critical_degree_of_saturation:.3f}\n"
            f"Cola P95 máxima {result.maximum_queue_95_m:.1f} m\n"
            f"Volumen {result.total_entering_volume_veh_h:,.0f} veh/h\n"
            f"Tiempo de viaje {result.weighted_travel_time_s:.1f} s\n\n"
            f"Grupo crítico\n{result.critical_lane_group}"
        )
        self._record_calculation("intersection")
        if switch_tab:
            self.detail_tabs.setCurrentWidget(self.results_tab)
            self.compact_view.setCurrentIndex(2)
        self.statusBar().showMessage("Cálculo completado correctamente", 5000)
        return True

    def calculate_transit(self, *_args, show_errors: bool = True) -> bool:
        """Calcula el módulo de línea sin condicionar el análisis de intersección."""

        self.project = self._project_from_ui()
        data = self.project.public_transport
        try:
            result = calculate_transit_line(data)
        except TransitCalculationError as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    "No es posible calcular la línea",
                    "Corrige los siguientes datos:\n\n• " + "\n• ".join(exc.messages),
                )
            self.statusBar().showMessage("Transporte público: datos inválidos", 6000)
            return False

        self.last_transit_result = result
        self.transit_tab.set_result(data, result)
        self._record_calculation("transit")
        self.statusBar().showMessage("Línea de transporte público calculada", 5000)
        return True

    def calculate_roundabout(self, *, show_errors: bool = True) -> bool:
        try:
            data = self.roundabout_tab.input_data()
            result = calculate_roundabout(data)
        except (ValueError, ArithmeticError) as exc:
            if show_errors:
                QMessageBox.warning(self, "No es posible calcular la rotonda", str(exc))
            return False
        self.project.roundabout = data
        self.roundabout_tab.set_result(data, result)
        self._record_calculation("roundabout")
        if show_errors and self.workspaces.currentWidget() is self.roundabout_tab:
            self.roundabout_tab.ensureWidgetVisible(self.roundabout_tab.summary, 0, 80)
        self.statusBar().showMessage("Rotonda calculada", 5000)
        return True

    def _record_calculation(self, module: str) -> None:
        if module not in self.project.calculated_modules:
            self.project.calculated_modules += (module,)
            self._mark_document_dirty()

    def _show_results(self, result: IntersectionResult, prepared: IntersectionProject) -> None:
        self.result_timestamp.setText(
            f"{self.project.name} · C = {self.project.cycle_length_s:.1f} s · "
            f"T = {self.project.analysis_period_h:.2f} h"
        )
        los_color = LOS_COLORS[result.level_of_service]
        self.los_card.set_metric(f"LOS {result.level_of_service}", "Intersección", los_color)
        self.delay_card.set_metric(f"{result.weighted_control_delay_s_veh:.1f}", "s/veh")
        x_color = (
            COLORS["red"]
            if result.critical_degree_of_saturation > 1
            else COLORS["orange"]
            if result.critical_degree_of_saturation >= 0.9
            else COLORS["green"]
        )
        self.x_card.set_metric(
            f"{result.critical_degree_of_saturation:.3f}",
            result.critical_lane_group,
            x_color,
        )
        self.volume_card.set_metric(
            f"{result.total_entering_volume_veh_h:,.0f}", "veh/h observados"
        )
        self.queue_card.set_metric(f"{result.maximum_queue_95_m:.1f}", "m · aproximación crítica")
        self.travel_time_card.set_metric(
            f"{result.weighted_travel_time_s:.1f}", "s · recorrido libre + demora"
        )

        self.results_table.setRowCount(len(result.lane_groups))
        groups_by_id = {group.identifier: group for group in prepared.lane_groups}
        for row_index, row in enumerate(result.lane_groups):
            source = groups_by_id[row.identifier]
            values = [
                row.label,
                str(source.signal_phase),
                f"{row.demand_flow_rate_veh_h:,.1f}",
                f"{row.saturation_flow_veh_h:,.1f}",
                f"{row.capacity_veh_h:,.1f}",
                f"{row.degree_of_saturation:.3f}",
                f"{row.control_delay_s_veh:.1f}",
                row.level_of_service,
                f"{row.average_queue_veh:.1f}",
                f"{row.queue_95_veh:.1f}",
                f"{row.queue_95_m:.1f}",
                f"{source.free_flow_speed_kmh:.1f}",
                f"{row.free_flow_travel_time_s:.1f}",
                f"{row.travel_time_s:.1f}",
                f"{row.residual_demand_veh:.1f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (Qt.AlignmentFlag.AlignLeft if column == 0 else Qt.AlignmentFlag.AlignCenter)
                )
                if column == 7:
                    item.setBackground(QColor(LOS_COLORS[row.level_of_service]))
                    item.setForeground(QColor("#FFFFFF"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.results_table.setItem(row_index, column, item)

        self.warning_list.clear()
        if result.warnings:
            self.warning_list.addItems(result.warnings)
        else:
            self.warning_list.addItem("Sin advertencias automáticas.")

        self.saturation_chart.set_result(result)
        self.trace_selector.blockSignals(True)
        self.trace_selector.clear()
        for row in result.lane_groups:
            self.trace_selector.addItem(row.label, row.identifier)
        self.trace_selector.blockSignals(False)
        self.refresh_trace()

    def _clear_results(self) -> None:
        self.last_result = None
        self.last_transit_result = None
        if not hasattr(self, "results_table"):
            return
        self.result_timestamp.setText("Sin resultados")
        self.los_card.set_metric("—")
        self.delay_card.set_metric("—")
        self.x_card.set_metric("—")
        self.volume_card.set_metric("—")
        self.queue_card.set_metric("—")
        self.travel_time_card.set_metric("—")
        self.results_table.setRowCount(0)
        self.warning_list.clear()
        self.saturation_chart.set_result(None)
        self.trace_selector.clear()
        self.trace_browser.setHtml(
            "<p style='color:#657987'>Calcula el proyecto para generar la memoria.</p>"
        )
        self.last_optimization = None
        self.optimize_button.setEnabled(False)
        self._set_summary_status("Calcula la situación actual.")
        self.summary.clear()
        self.scenario_panel.refresh(self.project, None)
        if hasattr(self, "timing_diagram"):
            self.optimization_summary.setText("Sin optimización calculada.")
            self.timing_diagram.set_data(self.project, None)
        if hasattr(self, "transit_tab"):
            self.transit_tab.clear_result()
            self.roundabout_tab.clear_result()

    def refresh_trace(self, *_args) -> None:
        if self.last_result is None or self.trace_selector.count() == 0:
            return
        identifier = self.trace_selector.currentData()
        row = next(
            (item for item in self.last_result.lane_groups if item.identifier == identifier),
            None,
        )
        if row is not None:
            trace = calculation_trace_html(prepare_project(self.project), row)
            self.trace_browser.setHtml(themed_text(trace))

    def _open_trace_from_result(self, index) -> None:  # noqa: ANN001
        if self.last_result is None:
            return
        row = index.row()
        if 0 <= row < self.trace_selector.count():
            self.trace_selector.setCurrentIndex(row)
            self.detail_tabs.setCurrentWidget(self.trace_tab)

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        project = self._blank_project()
        self.current_path = None
        self._load_project_into_ui(project)
        self.tabs.setCurrentWidget(self.project_tab)
        self.compact_view.setCurrentIndex(0)
        self.statusBar().showMessage("Proyecto nuevo", 4000)

    def load_demo(self) -> None:
        if not self._confirm_discard():
            return
        self.current_path = None
        self._load_project_into_ui(demonstration_project())
        self.calculate(switch_tab=False)
        self.calculate_transit()
        self.calculate_roundabout()
        self.dirty = False
        self._refresh_window_title()
        self.tabs.setCurrentWidget(self.project_tab)
        self.compact_view.setCurrentIndex(0)
        self.statusBar().showMessage("Caso demostrativo cargado", 4000)

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir proyecto HCNet",
            str(Path.home()),
            self.OPEN_FILTER,
        )
        if not filename:
            return
        try:
            project = load_project(filename)
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            QMessageBox.critical(self, "No se pudo abrir", str(exc))
            return
        self.current_path = Path(filename)
        self._load_project_into_ui(project)
        if "intersection" in project.calculated_modules:
            self.calculate(switch_tab=False, show_errors=False)
        if "transit" in project.calculated_modules:
            self.calculate_transit(show_errors=False)
        if "roundabout" in project.calculated_modules:
            self.calculate_roundabout(show_errors=False)
        if project.signal_optimization is not None:
            self._show_optimization(project.signal_optimization)
        elif project.scenarios:
            self.last_optimization = project.scenarios[-1].plan
        self.statusBar().showMessage(f"Proyecto abierto: {filename}", 5000)

    def save(self) -> bool:
        if self.current_path is None or self.current_path.suffix.lower() != ".hcnet":
            return self.save_as()
        return self._save_to_path(self.current_path)

    def save_as(self) -> bool:
        suggested = _safe_filename(self.name_edit.text()) + ".hcnet"
        initial = (self.current_path.parent if self.current_path else Path.home()) / suggested
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar proyecto HCNet",
            str(initial),
            self.PROJECT_FILTER,
        )
        if not filename:
            return False
        path = Path(filename)
        if path.suffix.lower() != ".hcnet":
            path = path.with_name(path.name + ".hcnet")
        return self._save_to_path(path)

    def _save_to_path(self, path: Path) -> bool:
        try:
            self.project = replace(
                self._project_from_ui(), roundabout=self.roundabout_tab.input_data(),
            )
            save_project(self.project, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return False
        self.current_path = path
        self.dirty = False
        self._refresh_window_title()
        self.statusBar().showMessage(f"Proyecto guardado: {path}", 5000)
        return True

    def export_csv(self) -> None:
        if not self.calculate(switch_tab=False):
            return
        assert self.last_result is not None
        suggested = _safe_filename(self.project.name) + "_resultados.csv"
        initial = (self.current_path.parent if self.current_path else Path.home()) / suggested
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar resultados",
            str(initial),
            "Valores separados por comas (*.csv)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        try:
            export_results_csv(self.project, self.last_result, path)
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))
            return
        self.statusBar().showMessage(f"Resultados exportados: {path}", 5000)

    def export_tex(self) -> None:
        if self.calculate(switch_tab=False):
            self._export_module_tex("interseccion", self.project.name, self._write_intersection_tex)

    def _export_general(self) -> None:
        self.project = self._project_from_ui()
        if not self.project.calculated_modules:
            QMessageBox.information(
                self, "Informe pendiente", "Calcula al menos un módulo antes de exportar.",
            )
            return
        self._export_module_tex("informe_general", self.project.name, export_general_tex)

    def _write_intersection_tex(self, project: IntersectionProject, path: Path) -> Path:
        assert self.last_result is not None
        return export_report_tex(project, self.last_result, path)

    def _export_transit(self) -> None:
        if self.calculate_transit():
            self._export_module_tex(
                "transporte_publico", self.project.public_transport.name, export_transit_tex,
            )

    def _export_roundabout(self) -> None:
        if self.calculate_roundabout():
            self._export_module_tex("rotonda", self.project.roundabout.name, export_roundabout_tex)

    def _export_module_tex(self, module: str, name: str, exporter: _ReportExporter) -> None:
        analyst, accepted = QInputDialog.getText(
            self, "Identificación del reporte", "Nombre del analista:",
            text=self.analyst_edit.text().strip(),
        )
        if not accepted:
            return
        if not analyst.strip():
            QMessageBox.information(self, "Nombre requerido", "Captura el nombre del analista.")
            return
        suggested = _safe_filename(name) + f"_{module}.tex"
        initial = (self.current_path.parent if self.current_path else Path.home()) / suggested
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar reporte técnico",
            str(initial),
            "Documento LaTeX (*.tex)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".tex":
            path = path.with_suffix(".tex")
        try:
            project = replace(self.project, analyst=analyst.strip())
            exporter(project, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))
            return
        self.statusBar().showMessage(f"Reporte LaTeX exportado: {path}", 5000)

    def _mark_dirty(self, *_args) -> None:
        if self._loading:
            return
        self._invalidate("intersection")
        if self.project.signal_optimization is not None:
            self.project.signal_optimization = None
        if self.last_result is not None:
            self.last_result = None
            self.result_timestamp.setText("Resultados anteriores · Presiona F5 para actualizar")
            self._set_summary_status("Datos modificados. Presiona F5 para recalcular.", stale=True)
            self.summary.clear()
            self.trace_selector.clear()
            self.trace_browser.setPlainText("Vuelve a calcular para actualizar la memoria.")
        self.optimize_button.setEnabled(False)
        self.scenario_panel.refresh(self.project, None)
        self._refresh_program()

    def _mark_document_dirty(self, *_args) -> None:
        if not self._loading:
            self.dirty = True
            self._refresh_window_title()

    def _invalidate(self, module: str) -> None:
        self.project.calculated_modules = tuple(
            previous for previous in self.project.calculated_modules if previous != module
        )
        self._mark_document_dirty()

    def _transit_changed(self) -> None:
        if not self._loading:
            self._invalidate("transit")
            if self.last_transit_result is not None:
                self.last_transit_result = None
                self.transit_tab.clear_result()

    def _roundabout_changed(self) -> None:
        if not self._loading and "roundabout" in self.project.calculated_modules:
            self._invalidate("roundabout")
            self.roundabout_tab.clear_result()
        else:
            self._mark_document_dirty()

    def _refresh_window_title(self) -> None:
        name = self.current_path.name if self.current_path else (
            self.name_edit.text().strip() or "Proyecto sin nombre"
        )
        marker = " *" if self.dirty else ""
        self.setWindowTitle(f"{name}{marker} — HCNet Transport {__version__}")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Cambios sin guardar",
            "El proyecto tiene cambios sin guardar. ¿Deseas guardarlos?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "Acerca de HCNet Transport",
            f"""
            <h2>HCNet Transport {__version__}</h2>
            <p><b>Highway Capacity and Network Evaluation Tool</b></p>
            <p>Software libre y educativo para el análisis de capacidad, desempeño
            operacional y nivel de servicio.</p>
            <p>Desarrollador: Héctor Alonso Benítez García</p>
            <p>Licencia GNU GPL v3.0</p>
            <p><small>Proyecto independiente, no afiliado ni certificado por TRB,
            National Academies, McTrans o HCS.</small></p>
            """,
        )


def _safe_filename(value: str) -> str:
    clean = "".join(character if character.isalnum() else "_" for character in value.strip())
    clean = "_".join(part for part in clean.split("_") if part)
    return clean.lower() or "proyecto_hcnet"


class _ProjectScrollArea(QScrollArea):
    def __init__(self, page: QWidget, splitter: QSplitter) -> None:
        super().__init__()
        self._splitter = splitter
        self.setWidgetResizable(True)
        self.setWidget(page)

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        super().resizeEvent(event)
        orientation = (
            Qt.Orientation.Horizontal if self.viewport().width() >= 810
            else Qt.Orientation.Vertical
        )
        if orientation != self._splitter.orientation():
            self._splitter.setOrientation(orientation)


class _ReportExporter(Protocol):
    def __call__(self, project: IntersectionProject, path: Path, /) -> Path: ...
