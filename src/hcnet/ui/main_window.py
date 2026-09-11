"""Ventana principal de HCNet Transport."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon
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
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from hcnet import __version__
from hcnet.domain.calculations import CalculationError, calculate_intersection
from hcnet.domain.models import IntersectionProject, IntersectionResult, LaneGroupInput
from hcnet.domain.reporting import calculation_trace_html
from hcnet.domain.sample import demonstration_project
from hcnet.io.project import export_report_tex, export_results_csv, load_project, save_project
from hcnet.ui.charts import IntersectionSketch, SaturationChart
from hcnet.ui.dialogs import LaneGroupDialog
from hcnet.ui.styles import COLORS, LOS_COLORS


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
        if color:
            self.value.setStyleSheet(f"color: {color};")
        else:
            self.value.setStyleSheet("")


class MainWindow(QMainWindow):
    PROJECT_FILTER = "Proyecto HCNet (*.hcnet.json);;Archivo JSON (*.json)"

    def __init__(self) -> None:
        super().__init__()
        self.project = demonstration_project()
        self.current_path: Path | None = None
        self.last_result: IntersectionResult | None = None
        self.dirty = False
        self._loading = False

        self.setWindowTitle(f"HCNet Transport {__version__}")
        self.setMinimumSize(1080, 720)
        self.resize(1380, 880)
        self._set_icon()
        self._create_actions()
        self._create_menu_and_toolbar()
        self._build_ui()
        self._load_project_into_ui(self.project)
        QTimer.singleShot(0, lambda: self.calculate(switch_tab=False))

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

        self.export_tex_action = QAction("Exportar reporte LaTeX…", self)
        self.export_tex_action.setIcon(self._resource_icon("report_tex.svg"))
        self.export_tex_action.setShortcut("Ctrl+Shift+E")
        self.export_tex_action.triggered.connect(self.export_tex)

        self.demo_action = QAction("Cargar caso demostrativo", self)
        self.demo_action.triggered.connect(self.load_demo)

        self.calculate_action = QAction(self._resource_icon("calculate.svg"), "Calcular", self)
        self.calculate_action.setShortcut("F5")
        self.calculate_action.triggered.connect(self.calculate)

        self.quit_action = QAction("Salir", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

        self.repository_action = QAction("Abrir repositorio", self)
        self.repository_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/VanLinux/hcnet-transport"))
        )

        self.about_action = QAction("Acerca de HCNet", self)
        self.about_action.triggered.connect(self.show_about)

    def _create_menu_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        file_menu.addActions([self.new_action, self.open_action])
        file_menu.addSeparator()
        file_menu.addActions([self.save_action, self.save_as_action])
        export_menu = file_menu.addMenu("Exportar")
        export_menu.addActions([self.export_action, self.export_tex_action])
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        project_menu = self.menuBar().addMenu("Proyecto")
        project_menu.addAction(self.demo_action)
        project_menu.addAction(self.calculate_action)

        help_menu = self.menuBar().addMenu("Ayuda")
        help_menu.addActions([self.repository_action, self.about_action])

        toolbar = QToolBar("Herramientas principales")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addAction(self.calculate_action)
        toolbar.addSeparator()
        toolbar.addAction(self.export_action)
        toolbar.addAction(self.export_tex_action)
        self.addToolBar(toolbar)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("HCNet Transport")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Highway Capacity and Network Evaluation Tool · Intersecciones semaforizadas"
        )
        subtitle.setObjectName("pageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        version = QLabel(f"VERSIÓN {__version__}")
        version.setStyleSheet(
            "background: #30343B; color: white; border-radius: 5px; "
            "padding: 6px 10px; font-weight: 700;"
        )
        header.addWidget(version, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.scope_tab = self._build_scope_tab()
        self.project_tab = self._build_project_tab()
        self.groups_tab = self._build_groups_tab()
        self.results_tab = self._build_results_tab()
        self.trace_tab = self._build_trace_tab()
        self.tabs.addTab(self.scope_tab, "1  Inicio y alcance")
        self.tabs.addTab(self.project_tab, "2  Proyecto")
        self.tabs.addTab(self.groups_tab, "3  Grupos de carriles")
        self.tabs.addTab(self.results_tab, "4  Resultados")
        self.tabs.addTab(self.trace_tab, "5  Reporte técnico")
        root.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("HCNet Transport listo")

    def _build_project_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        banner = QLabel(
            "Módulo actual: análisis educativo de una intersección semaforizada aislada "
            "con control de tiempo fijo y periodo de demanda uniforme."
        )
        banner.setObjectName("infoBanner")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 10, 0)

        identification = QGroupBox("Identificación del estudio")
        form = QFormLayout(identification)
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
        self.cycle_spin = QDoubleSpinBox()
        self.cycle_spin.setRange(1, 600)
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
        self.project_notes.setMaximumHeight(110)
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
            widget.textChanged.connect(self._mark_dirty)
        self.date_edit.dateChanged.connect(self._mark_dirty)
        self.cycle_spin.valueChanged.connect(self._mark_dirty)
        self.period_spin.valueChanged.connect(self._mark_dirty)
        self.project_notes.textChanged.connect(self._mark_dirty)
        return page

    def _build_groups_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Grupos de carriles")
        title.setObjectName("sectionTitle")
        subtitle = QLabel(
            "Cada fila representa movimientos que comparten carriles y condiciones operacionales."
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

        self.input_table = QTableWidget(0, 9)
        self.input_table.setHorizontalHeaderLabels(
            [
                "Acceso",
                "Movimiento",
                "V (veh/h)",
                "Carriles",
                "g (s)",
                "FHMD",
                "s₀",
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
        self.input_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.input_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
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
        return page

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
        calculate_button = QPushButton("Calcular proyecto")
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
        cards.addWidget(self.los_card, 0, 0)
        cards.addWidget(self.delay_card, 0, 1)
        cards.addWidget(self.x_card, 0, 2)
        cards.addWidget(self.volume_card, 0, 3)
        layout.addLayout(cards)

        splitter = QSplitter(Qt.Orientation.Vertical)
        chart_box = QGroupBox("Grado de saturación por grupo, X = v/c")
        chart_layout = QVBoxLayout(chart_box)
        self.saturation_chart = SaturationChart()
        chart_layout.addWidget(self.saturation_chart)
        splitter.addWidget(chart_box)

        lower = QSplitter(Qt.Orientation.Horizontal)
        self.results_table = QTableWidget(0, 11)
        self.results_table.setHorizontalHeaderLabels(
            ["Grupo", "v", "s", "c", "X", "d₁", "d₂", "d₃", "d", "LOS", "Residual"]
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
        layout.addWidget(splitter, 1)
        return page

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
        return page

    def _build_scope_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(
            f"""
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

            <div class="scope"><b>Alcance implementado:</b> análisis de una intersección
            semaforizada aislada mediante grupos de carriles, control de tiempo fijo,
            factores de ajuste del flujo de saturación, capacidad, grado de saturación
            X, demora d₁+d₂+d₃ y nivel de servicio A–F.</div>

            <h3>Flujo de trabajo</h3>
            <ol>
              <li>Identifica el estudio y captura el nombre del analista.</li>
              <li>Configura los grupos de carriles y sus condiciones operacionales.</li>
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
            </ul>
            <h3>No incluido todavía</h3>
            <ul>
              <li>Asignación automática de carriles compartidos y giros permitidos.</li>
              <li>Estimación interna de cola inicial o cola percentil 95.</li>
              <li>Coordinación de corredores, fases actuadas, bicicletas y peatones.</li>
              <li>Glorietas, intersecciones no semaforizadas, autopistas y carreteras.</li>
              <li>Calibración automática para condiciones mexicanas.</li>
            </ul>

            <div class="panel"><b>Uso responsable:</b> es una herramienta educativa
            independiente,
            no una implementación certificada del HCM 7 ni un sustituto de HCS. Verifica
            los resultados antes de utilizarlos en un estudio profesional.</div>
            """
        )
        layout.addWidget(browser)
        return page

    def _project_from_ui(self) -> IntersectionProject:
        return replace(
            self.project,
            name=self.name_edit.text().strip(),
            location=self.location_edit.text().strip(),
            analyst=self.analyst_edit.text().strip(),
            study_date=self.date_edit.date().toString("yyyy-MM-dd"),
            cycle_length_s=self.cycle_spin.value(),
            analysis_period_h=self.period_spin.value(),
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
        self._refresh_input_table()
        self.sketch.set_project(project)
        self._clear_results()
        self._loading = False
        self.dirty = False
        self._refresh_window_title()

    def _refresh_input_table(self, selected_row: int | None = None) -> None:
        table = self.input_table
        table.setRowCount(len(self.project.lane_groups))
        for row, group in enumerate(self.project.lane_groups):
            values = [
                group.approach,
                group.movement,
                f"{group.volume_veh_h:,.1f}",
                str(group.lanes),
                f"{group.effective_green_s:.1f}",
                f"{group.peak_hour_factor:.3f}",
                f"{group.base_saturation_flow_pc_h_ln:,.0f}",
                f"{group.heavy_vehicles_percent:.1f} %",
                group.notes,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {2, 3, 4, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
        total = sum(group.volume_veh_h for group in self.project.lane_groups)
        self.groups_summary.setText(
            f"{len(self.project.lane_groups)} grupos · Volumen total: {total:,.0f} veh/h · "
            "Doble clic para editar"
        )
        if selected_row is not None and 0 <= selected_row < table.rowCount():
            table.selectRow(selected_row)
        if hasattr(self, "sketch"):
            self.sketch.set_project(self._project_from_ui())

    def selected_group_index(self) -> int | None:
        selection = self.input_table.selectionModel().selectedRows()
        return selection[0].row() if selection else None

    def add_group(self) -> None:
        dialog = LaneGroupDialog(
            cycle_length_s=self.cycle_spin.value(),
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
        dialog = LaneGroupDialog(
            self.project.lane_groups[index],
            cycle_length_s=self.cycle_spin.value(),
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
            del self.project.lane_groups[index]
            self._refresh_input_table(min(index, len(self.project.lane_groups) - 1))
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

    def calculate(self, *_args, switch_tab: bool = True) -> bool:
        self.project = self._project_from_ui()
        try:
            result = calculate_intersection(self.project)
        except CalculationError as exc:
            QMessageBox.warning(
                self,
                "No es posible calcular",
                "Corrige los siguientes datos:\n\n• " + "\n• ".join(exc.messages),
            )
            self.statusBar().showMessage("Cálculo detenido por datos inválidos", 6000)
            return False

        self.last_result = result
        self._show_results(result)
        if switch_tab:
            self.tabs.setCurrentWidget(self.results_tab)
        self.statusBar().showMessage("Cálculo completado correctamente", 5000)
        return True

    def _show_results(self, result: IntersectionResult) -> None:
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

        self.results_table.setRowCount(len(result.lane_groups))
        for row_index, row in enumerate(result.lane_groups):
            values = [
                row.label,
                f"{row.demand_flow_rate_veh_h:,.1f}",
                f"{row.saturation_flow_veh_h:,.1f}",
                f"{row.capacity_veh_h:,.1f}",
                f"{row.degree_of_saturation:.3f}",
                f"{row.uniform_delay_s_veh:.1f}",
                f"{row.incremental_delay_s_veh:.1f}",
                f"{row.initial_queue_delay_s_veh:.1f}",
                f"{row.control_delay_s_veh:.1f}",
                row.level_of_service,
                f"{row.residual_demand_veh:.1f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (Qt.AlignmentFlag.AlignLeft if column == 0 else Qt.AlignmentFlag.AlignCenter)
                )
                if column == 9:
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
        if not hasattr(self, "results_table"):
            return
        self.result_timestamp.setText("Sin resultados")
        self.los_card.set_metric("—")
        self.delay_card.set_metric("—")
        self.x_card.set_metric("—")
        self.volume_card.set_metric("—")
        self.results_table.setRowCount(0)
        self.warning_list.clear()
        self.saturation_chart.set_result(None)
        self.trace_selector.clear()
        self.trace_browser.setHtml(
            "<p style='color:#657987'>Calcula el proyecto para generar la memoria.</p>"
        )

    def refresh_trace(self, *_args) -> None:
        if self.last_result is None or self.trace_selector.count() == 0:
            return
        identifier = self.trace_selector.currentData()
        row = next(
            (item for item in self.last_result.lane_groups if item.identifier == identifier),
            None,
        )
        if row is not None:
            self.trace_browser.setHtml(calculation_trace_html(self.project, row))

    def _open_trace_from_result(self, index) -> None:  # noqa: ANN001
        if self.last_result is None:
            return
        row = index.row()
        if 0 <= row < self.trace_selector.count():
            self.trace_selector.setCurrentIndex(row)
            self.tabs.setCurrentWidget(self.trace_tab)

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        project = IntersectionProject(lane_groups=[LaneGroupInput()])
        self.current_path = None
        self._load_project_into_ui(project)
        self.tabs.setCurrentWidget(self.project_tab)
        self.statusBar().showMessage("Proyecto nuevo", 4000)

    def load_demo(self) -> None:
        if not self._confirm_discard():
            return
        self.current_path = None
        self._load_project_into_ui(demonstration_project())
        self.calculate(switch_tab=False)
        self.tabs.setCurrentWidget(self.project_tab)
        self.statusBar().showMessage("Caso demostrativo cargado", 4000)

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir proyecto HCNet",
            str(Path.home()),
            self.PROJECT_FILTER,
        )
        if not filename:
            return
        try:
            project = load_project(filename)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "No se pudo abrir", str(exc))
            return
        self.current_path = Path(filename)
        self._load_project_into_ui(project)
        self.calculate(switch_tab=False)
        self.statusBar().showMessage(f"Proyecto abierto: {filename}", 5000)

    def save(self) -> bool:
        if self.current_path is None:
            return self.save_as()
        return self._save_to_path(self.current_path)

    def save_as(self) -> bool:
        suggested = _safe_filename(self.name_edit.text()) + ".hcnet.json"
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
        if not path.name.endswith((".hcnet.json", ".json")):
            path = path.with_name(path.name + ".hcnet.json")
        return self._save_to_path(path)

    def _save_to_path(self, path: Path) -> bool:
        self.project = self._project_from_ui()
        try:
            save_project(self.project, path)
        except OSError as exc:
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
        self.project = self._project_from_ui()
        if not self.project.analyst:
            QMessageBox.information(
                self,
                "Nombre del analista requerido",
                "Ingresa el nombre del analista en la pestaña Proyecto antes de "
                "generar el reporte técnico.",
            )
            self.tabs.setCurrentWidget(self.project_tab)
            self.analyst_edit.setFocus()
            return
        if not self.calculate(switch_tab=False):
            return
        assert self.last_result is not None
        suggested = _safe_filename(self.project.name) + "_reporte_hcnet.tex"
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
            export_report_tex(self.project, self.last_result, path)
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo exportar", str(exc))
            return
        self.statusBar().showMessage(f"Reporte LaTeX exportado: {path}", 5000)

    def _mark_dirty(self, *_args) -> None:
        if self._loading:
            return
        self.dirty = True
        self._refresh_window_title()
        if self.last_result is not None:
            self.result_timestamp.setText("Resultados anteriores · Presiona F5 para actualizar")

    def _refresh_window_title(self) -> None:
        name = self.current_path.name if self.current_path else self.project.name
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
