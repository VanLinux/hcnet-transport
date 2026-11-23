"""Edición de fases y comparación de alternativas."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.models import IntersectionProject, IntersectionResult, PhaseInput
from hcnet.domain.scenarios import (
    METHODS,
    OBJECTIVES,
    SearchSettings,
    baseline_key,
    evaluate_scenario,
    scenario_project,
)
from hcnet.domain.signals import timeline
from hcnet.ui.charts import IntersectionSketch, SignalTimingDiagram


def _scroll(page: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    return scroll


def _button(text: str, handler) -> QPushButton:  # noqa: ANN001
    button = QPushButton(text)
    button.clicked.connect(handler)
    return button


class PhaseEditor(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.project = IntersectionProject()
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Secuencia de fases"), 1)
        header.addWidget(_button("Añadir fase", lambda: self._edit(None)))
        header.addWidget(_button("Importar programa existente", self._import))
        layout.addLayout(header)
        self.cards = QGridLayout()
        layout.addLayout(self.cards)

    def refresh(self, project: IntersectionProject) -> None:
        self.project = project
        while self.cards.count():
            item = self.cards.takeAt(0)
            item.widget().deleteLater()
        for index, phase in enumerate(project.phases):
            frame = QFrame()
            frame.setObjectName("metricCard")
            box = QVBoxLayout(frame)
            box.addWidget(QLabel(f"Fase {phase.number}"))
            sketch = IntersectionSketch(compact=True)
            sketch.set_project(project)
            sketch.active_phase = phase.number
            box.addWidget(sketch)
            box.addWidget(
                QLabel(f"Verde {phase.green:g} · Amar. {phase.yellow:g} · Rojo {phase.all_red:g} s")
            )
            controls = QHBoxLayout()
            for text, action in (
                ("Editar", lambda _=False, i=index: self._edit(i)),
                ("↑", lambda _=False, i=index: self._move(i, -1)),
                ("↓", lambda _=False, i=index: self._move(i, 1)),
                ("Quitar", lambda _=False, i=index: self._remove(i)),
            ):
                controls.addWidget(_button(text, action))
            box.addLayout(controls)
            self.cards.addWidget(frame, index // 2, index % 2)

    def _import(self) -> None:
        if self.project.phases:
            QMessageBox.information(self, "Programa existente", "Ya hay fases configuradas.")
            return
        plan = timeline(self.project)
        if plan is None:
            QMessageBox.information(
                self,
                "Programa incompleto",
                "Los verdes existentes no describen un ciclo completo. Captura las fases.",
            )
            return
        self.project.phases[:] = [
            PhaseInput(p.phase_number, p.green_s, p.yellow_s, p.all_red_s) for p in plan.phases
        ]
        self.changed.emit()

    def _edit(self, index: int | None) -> None:
        project = self.project
        if index is None:
            number = next(
                (i for i in range(1, 17) if all(p.number != i for p in project.phases)), None
            )
            if number is None:
                return
            phase = PhaseInput(
                number,
                project.minimum_green_s,
                project.yellow_time_s,
                project.all_red_time_s,
            )
        else:
            phase = project.phases[index]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Fase {phase.number}")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        fields = []
        for name, value, limit in (
            ("Verde (s)", phase.green, 600),
            ("Amarillo (s)", phase.yellow, 30),
            ("Todo rojo (s)", phase.all_red, 30),
        ):
            field = QDoubleSpinBox()
            field.setRange(0, limit)
            field.setValue(value)
            form.addRow(name, field)
            fields.append(field)
        layout.addLayout(form)
        selection = QListWidget()
        selection.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for group in project.lane_groups:
            item = QListWidgetItem(f"{group.label} · F{group.signal_phase}")
            selection.addItem(item)
            item.setSelected(group.signal_phase == phase.number)
        layout.addWidget(QLabel("Grupos de carriles que reciben verde"))
        layout.addWidget(selection)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_phase = PhaseInput(phase.number, *(field.value() for field in fields))
        if index is None:
            project.phases.append(new_phase)
        else:
            project.phases[index] = new_phase
        assignments = {}
        for row, group in enumerate(project.lane_groups):
            if selection.item(row).isSelected():
                group.signal_phase = phase.number
            elif group.signal_phase == phase.number:
                group.signal_phase = 0
            assignments[group.identifier] = group.signal_phase
        for i, head in enumerate(project.signal_heads):
            mapped = {assignments[g] for g in head.controlled_group_ids if g in assignments}
            if len(mapped) == 1 and 0 not in mapped:
                project.signal_heads[i] = replace(head, signal_phase=mapped.pop())
        self.changed.emit()

    def _move(self, index: int, offset: int) -> None:
        phases = self.project.phases
        target = index + offset
        if 0 <= target < len(phases):
            phases[index], phases[target] = phases[target], phases[index]
            self.changed.emit()

    def _remove(self, index: int) -> None:
        del self.project.phases[index]
        self.changed.emit()


class OptimizationDialog(QDialog):
    def __init__(self, project: IntersectionProject, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Optimizar intersección")
        layout = QVBoxLayout(self)
        page = QWidget()
        form = QFormLayout(page)
        self.method = QComboBox()
        self.method.addItems(METHODS)
        self.objective = QComboBox()
        self.objective.addItems(OBJECTIVES)
        form.addRow("Método", self.method)
        form.addRow("Objetivo", self.objective)
        self.low = self._integer(form, "Ciclo mínimo (s)", 1, 600, 40)
        self.high = self._integer(form, "Ciclo máximo (s)", 1, 600, 180)
        self.fixed = QCheckBox("Conservar ciclo original")
        self.regroup = QCheckBox("Permitir reasignación a fases existentes")
        form.addRow(self.fixed)
        form.addRow(self.regroup)
        self.locks = QListWidget()
        for group in project.lane_groups:
            item = QListWidgetItem(group.label)
            item.setData(Qt.ItemDataRole.UserRole, group.identifier)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.locks.addItem(item)
        self.locks.setMinimumHeight(110)
        form.addRow("Asignaciones fijas", self.locks)
        self.population = self._integer(form, "Población", 4, 64, 24)
        self.generations = self._integer(form, "Iteraciones máximas", 1, 100, 25)
        self.patience = self._integer(form, "Generaciones sin cambio", 1, 100, 8)
        self.seed = self._integer(form, "Semilla", 0, 2_147_483_646, 42)
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        form.addRow(self.explanation)
        self.method.currentIndexChanged.connect(self._method_changed)
        self.regroup.toggled.connect(self._method_changed)
        self._method_changed()
        layout.addWidget(_scroll(page))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(565, min(600, self.screen().availableGeometry().height() - 50))

    @staticmethod
    def _integer(form: QFormLayout, label: str, low: int, high: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        form.addRow(label, spin)
        return spin

    def _method_changed(self) -> None:
        index = self.method.currentIndex()
        stochastic = index >= 2
        self.objective.setEnabled(index in (1, 2))
        self.regroup.setEnabled(stochastic)
        self.locks.setEnabled(stochastic and self.regroup.isChecked())
        for widget in (self.population, self.patience, self.seed):
            widget.setEnabled(stochastic)
        self.generations.setEnabled(index > 0)
        self.explanation.setText(
            (
                "Ciclo y verdes por relaciones críticas. Webster no usa un objetivo seleccionable.",
                "Búsqueda por vecinos. Evalúa la demora con el modelo de Akçelik y compara "
                "la alternativa con los indicadores HCNet del escenario original.",
            "Búsqueda reproducible con un objetivo. Conserva despejes y mínimos de verde.",
                "Alternativas no dominadas entre los programas evaluados. Se minimizan demora, "
                "cola y saturación. La búsqueda no garantiza un frente global.",
            )[index]
        )

    def settings(self) -> SearchSettings:
        locked = tuple(
            self.locks.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.locks.count())
            if self.locks.item(i).checkState() == Qt.CheckState.Checked
        )
        return SearchSettings(
            method=self.method.currentText(),
            objective=self.objective.currentText(),
            min_cycle=self.low.value(),
            max_cycle=self.high.value(),
            fixed_cycle=self.fixed.isChecked(),
            regroup=self.regroup.isEnabled() and self.regroup.isChecked(),
            locked_groups=locked,
            population=self.population.value(),
            generations=self.generations.value(),
            patience=self.patience.value(),
            seed=self.seed.value(),
        )


class ScenarioPanel(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setMaximumHeight(126)
        self.list.itemSelectionChanged.connect(self._compare)
        layout.addWidget(self.list)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.level = QComboBox()
        self.level.addItems(["Intersección", "Acceso", "Grupo de carriles", "Movimiento"])
        self.level.currentIndexChanged.connect(self._compare)
        layout.addWidget(self.level)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(240)
        layout.addWidget(self.table)
        self.chart_metric = QComboBox()
        self.chart_metric.addItems(
            ["Demora (s/veh)", "Cola P95 máx. (m)", "v/c crítico", "Ciclo (s)"]
        )
        self.chart_metric.currentIndexChanged.connect(self._compare)
        layout.addWidget(self.chart_metric)
        self.bars = QFormLayout()
        layout.addLayout(self.bars)
        self.diagrams = QVBoxLayout()
        layout.addLayout(self.diagrams)
        layout.addStretch()
        self.setWidget(page)
        self.project = IntersectionProject()
        self.baseline: IntersectionResult | None = None
        self.key = ""

    def refresh(self, project: IntersectionProject, baseline: IntersectionResult | None) -> None:
        self.project, self.baseline = project, baseline
        self.key = baseline_key(project) if baseline else ""
        self.list.blockSignals(True)
        self.list.clear()
        newest_current = None
        for index, scenario in enumerate(project.scenarios, 1):
            status = "" if scenario.baseline_key == self.key else " · histórico"
            self.list.addItem(f"{index}. {scenario.name}{status}")
            if not status:
                newest_current = index - 1
        if newest_current is not None:
            self.list.item(newest_current).setSelected(True)
        self.list.blockSignals(False)
        self._compare()

    def _compare(self, *_args) -> None:
        for layout in (self.bars, self.diagrams):
            while layout.count():
                layout.takeAt(0).widget().deleteLater()
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        selection = [
            (i.row(), self.project.scenarios[i.row()])
            for i in self.list.selectedIndexes()
        ]
        keys = {scenario.baseline_key for _, scenario in selection}
        if len(keys) > 1:
            self.status.setText("Selecciona alternativas con el mismo escenario original.")
            return
        if selection and keys != {self.key}:
            archived = IntersectionProject.from_dict(selection[0][1].baseline)
            original = calculate_intersection(archived)
            datasets = [("Original archivado", archived, original, timeline(archived))]
            self.status.setText("Comparación con el escenario original archivado.")
        elif self.baseline is not None:
            datasets = [("Actual", self.project, self.baseline, timeline(self.project))]
            self.status.setText("Selecciona una o varias alternativas para comparar.")
        else:
            self.status.setText("Calcula la situación actual o selecciona un escenario histórico.")
            return
        for index, scenario in selection:
            datasets.append(
                (
                    f"{index + 1}. {scenario.name}",
                    scenario_project(scenario),
                    evaluate_scenario(scenario),
                    scenario.plan,
                )
            )
        symbols = ["Indicador", datasets[0][0]]
        for label, *_ in datasets[1:]:
            symbols.extend([label, "Δ abs. / %"])
        self.table.setColumnCount(len(symbols))
        self.table.setHorizontalHeaderLabels(symbols)
        summaries = [
            self._indicators(project, result, self.level.currentIndex())
            for _, project, result, _ in datasets
        ]
        self.table.setRowCount(len(summaries[0]))
        for i, indicator in enumerate(summaries[0]):
            original = summaries[0][indicator]
            cells = [indicator, self._number(original)]
            for summary in summaries[1:]:
                value = summary.get(indicator)
                delta = "—"
                if isinstance(value, float | int) and isinstance(original, float | int):
                    difference = value - original
                    percent = f"{difference / original:+.1%}" if original else "—"
                    delta = f"{difference:+.2f} / {percent}"
                cells.extend([self._number(value), delta])
            for j, cell in enumerate(cells):
                self.table.setItem(i, j, QTableWidgetItem(cell))
        metric = self.chart_metric.currentIndex()
        values = [
            (
                r.weighted_control_delay_s_veh,
                r.maximum_queue_95_m,
                r.critical_degree_of_saturation,
                p.cycle_length_s,
            )[metric]
            for _, p, r, _ in datasets
        ]
        for (label, project, _, plan), value in zip(datasets, values, strict=True):
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(round(1000 * value / max(max(values), 1e-9)))
            bar.setFormat(f"{value:.2f} {self.chart_metric.currentText()}")
            self.bars.addRow(label, bar)
            if plan is not None:
                chart = SignalTimingDiagram()
                chart.set_data(project, plan)
                self.diagrams.addWidget(QLabel(label))
                self.diagrams.addWidget(chart)

    @staticmethod
    def _number(value: float | str | None) -> str:
        if value is None:
            return "—"
        return f"{value:.2f}" if isinstance(value, float | int) else value

    @staticmethod
    def _indicators(
        project: IntersectionProject,
        result: IntersectionResult,
        level: int,
    ) -> dict[str, float | str]:
        if level == 0:
            return {
                "Demora (s/veh)": result.weighted_control_delay_s_veh,
                "LOS": result.level_of_service,
                "v/c crítico": result.critical_degree_of_saturation,
                "Cola P95 máxima (m)": result.maximum_queue_95_m,
                "Capacidad sumada (veh/h)": sum(r.capacity_veh_h for r in result.lane_groups),
                "Ciclo (s)": project.cycle_length_s,
            }
        from hcnet.domain.signals import prepare_project

        groups = {g.identifier: g for g in prepare_project(project).lane_groups}
        access = defaultdict(list)
        values: dict[str, float | str] = {}
        for row in result.lane_groups:
            group = groups[row.identifier]
            access[group.origin_branch].append(row)
            if level == 2:
                values.update(
                    {
                        f"{row.label} · demora (s/veh)": row.control_delay_s_veh,
                        f"{row.label} · capacidad (veh/h)": row.capacity_veh_h,
                        f"{row.label} · v/c": row.degree_of_saturation,
                        f"{row.label} · cola P95 (m)": row.queue_95_m,
                        f"{row.label} · verde (s)": group.effective_green_s,
                        f"{row.label} · LOS": row.level_of_service,
                    }
                )
            elif level == 3:
                for move in group.movements:
                    if move.enabled:
                        label = f"{group.origin_branch} → {move.destination} · {row.label}"
                        values[f"{label} · flujo ajustado (veh/h)"] = move.volume / move.phf
                        values[f"{label} · fase"] = str(group.signal_phase)
                        values[f"{label} · verde (s)"] = group.effective_green_s
        if level == 1:
            for branch, rows in access.items():
                demand = sum(r.demand_flow_rate_veh_h for r in rows)
                values[f"{branch} · demora (s/veh)"] = (
                    sum(r.control_delay_s_veh * r.demand_flow_rate_veh_h for r in rows) / demand
                    if demand
                    else 0
                )
                values[f"{branch} · v/c crítico"] = max(r.degree_of_saturation for r in rows)
                values[f"{branch} · cola P95 máxima (m)"] = max(r.queue_95_m for r in rows)
                values[f"{branch} · capacidad (veh/h)"] = sum(r.capacity_veh_h for r in rows)
        return values
