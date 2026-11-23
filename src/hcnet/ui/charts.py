"""Visualizaciones compactas dibujadas con Qt."""

from __future__ import annotations

from collections import defaultdict
from math import cos, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from hcnet.domain.models import IntersectionProject, IntersectionResult, SignalOptimizationResult
from hcnet.domain.signals import signal_rows
from hcnet.domain.transit import TransitLineInput, TransitLineResult, congestion_time
from hcnet.ui.styles import COLORS, LOS_COLORS, chart_color


class IntersectionSketch(QWidget):
    """Esquema orientativo que resume volumen por acceso."""

    branch_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self._project: IntersectionProject | None = None
        self.compact = compact
        self.active_phase: int | None = None
        self.interactive = False
        self.setMinimumSize(120 if compact else 220, 115 if compact else 215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_project(self, project: IntersectionProject) -> None:
        self._project = project
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        if not self.interactive or not self._project or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        size = min(self.width(), self.height())
        center = QPointF(self.width() / 2, self.height() / 2)
        point = event.position() - center
        for branch in self._project.active_branches:
            angle = radians(branch.azimuth)
            x, y = sin(angle), -cos(angle)
            along = point.x() * x + point.y() * y
            across = point.x() * y - point.y() * x
            if size * 0.14 < along < size * 0.58 and abs(across) < size * 0.13:
                self.branch_clicked.emit(branch.code)
                return

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), chart_color(self, QPalette.ColorRole.Base))

        width = self.width()
        height = self.height()
        size = min(width, height)
        road = size * 0.17
        cx, cy = width / 2, height / 2
        center = QPointF(cx, cy)
        branches = self._project.active_branches if self._project is not None else []
        ends = [
            QPointF(sin(radians(branch.azimuth)), -cos(radians(branch.azimuth)))
            for branch in branches
        ]
        for direction in ends:
            painter.setPen(QPen(QColor("#43545D"), road))
            painter.drawLine(center, center + direction * (size * 0.32))
        for branch, direction in zip(branches, ends, strict=True):
            transverse = QPointF(direction.y(), -direction.x())
            lanes = branch.inbound_lanes + branch.outbound_lanes
            for lane in range(1, lanes):
                median = lane == branch.outbound_lanes
                painter.setPen(QPen(QColor("#D5D7DA"), 1 if not median else 2,
                                    Qt.PenStyle.SolidLine if median else Qt.PenStyle.DashLine))
                offset = transverse * (road * (lane / lanes - 0.5))
                painter.drawLine(
                    center + direction * (road * 0.78) + offset,
                    center + direction * (size * 0.32) + offset,
                )

        if self._project is None:
            return
        directions = dict(zip((branch.code for branch in branches), ends, strict=True))
        for group in self._project.lane_groups:
            if self.active_phase is not None and group.signal_phase != self.active_phase:
                continue
            origin = directions.get(group.origin_branch)
            if origin is None:
                continue
            destinations = (
                tuple(m.destination for m in group.movements if m.enabled)
                if group.movements else group.destination_branches
            )
            for code in destinations:
                dest = directions.get(code)
                if dest is None:
                    continue
                beginning = center + origin * (size * 0.28)
                target = center + dest * (size * 0.26)
                beginning += QPointF(origin.y(), -origin.x()) * (road * 0.22)
                target += QPointF(-dest.y(), dest.x()) * (road * 0.22)
                path = QPainterPath(beginning)
                path.quadTo(center, target)
                painter.setPen(QPen(QColor("#50D69D" if self.active_phase else "#7DD3FC"), 2))
                painter.drawPath(path)
                tangent = target - center
                length = max(1, (tangent.x()**2 + tangent.y()**2)**0.5)
                tangent = tangent / length
                wing = QPointF(-tangent.y(), tangent.x()) * 4
                painter.drawLine(target, target - tangent*8 + wing)
                painter.drawLine(target, target - tangent*8 - wing)
        if not self.compact:
            for head in self._project.signal_heads:
                direction = directions.get(head.branch_code)
                if direction is not None:
                    dot = center + direction * (size * 0.17)
                    dot += QPointF(direction.y(), -direction.x()) * (road * 0.66)
                    painter.setBrush(QColor("#18864B" if self.active_phase == head.signal_phase
                                            else "#B3261E" if self.active_phase else "#8BA5C4"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(dot, 4, 4)

        totals: defaultdict[str, float] = defaultdict(float)
        for group in self._project.lane_groups:
            totals[group.origin_branch] += group.volume_veh_h

        painter.setFont(QFont(painter.font().family(), 9, QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        for branch, direction in zip(branches, ends, strict=True):
            position = center + direction * (size * 0.44)
            if self.compact:
                lines = [branch.code]
            else:
                value = totals[branch.code]
                volume = f" · {value:,.0f} veh/h" if value else ""
                lanes = "carril" if branch.inbound_lanes == 1 else "carriles"
                lines = [branch.label, f"{branch.inbound_lanes} {lanes}{volume}"]
                if abs(direction.x()) > abs(direction.y()):
                    position.setY(position.y() - road * 0.5 - metrics.height() - 2)

            label_width = min(width - 4, max(metrics.horizontalAdvance(line) for line in lines) + 8)
            label_height = metrics.lineSpacing() * len(lines) + 2
            x = min(width - label_width, max(0, position.x() - label_width / 2))
            y = min(height - label_height, max(0, position.y() - label_height / 2))
            rectangle = QRectF(x, y, label_width, label_height)
            painter.fillRect(rectangle, chart_color(self, QPalette.ColorRole.Base))
            painter.setPen(chart_color(self))
            text = "\n".join(
                metrics.elidedText(line, Qt.TextElideMode.ElideRight, label_width - 4)
                for line in lines
            )
            painter.drawText(rectangle, Qt.AlignmentFlag.AlignCenter, text)


class SaturationChart(QWidget):
    """Barras de grado de saturación por grupo de carriles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result: IntersectionResult | None = None
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

    def set_result(self, result: IntersectionResult | None) -> None:
        self._result = result
        rows = max(4, len(result.lane_groups) if result else 4)
        self.setMinimumHeight(40 + rows * 23)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), chart_color(self, QPalette.ColorRole.Base))

        if self._result is None:
            painter.setPen(chart_color(self))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Calcula el proyecto para ver X por grupo",
            )
            return

        left = 180
        right = 52
        top = 27
        row_height = 23
        available = max(100, self.width() - left - right)
        largest_degree = max(row.degree_of_saturation for row in self._result.lane_groups)
        scale_max = max(1.2, largest_degree * 1.08)

        painter.setFont(QFont(painter.font().family(), 8))
        painter.setPen(chart_color(self))
        for tick in (0.0, 0.5, 0.9, 1.0, scale_max):
            x = left + available * tick / scale_max
            painter.drawLine(int(x), top - 5, int(x), self.height() - 12)
            painter.drawText(QRectF(x - 20, 4, 40, 18), Qt.AlignmentFlag.AlignCenter, f"{tick:.1f}")

        capacity_x = left + available / scale_max
        painter.setPen(QPen(QColor(COLORS["red"]), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(capacity_x), top - 5, int(capacity_x), self.height() - 12)

        for index, row in enumerate(self._result.lane_groups):
            y = top + index * row_height
            painter.setPen(chart_color(self))
            label = row.label if len(row.label) <= 25 else row.label[:23] + "…"
            painter.drawText(QRectF(8, y, left - 16, 18), Qt.AlignmentFlag.AlignVCenter, label)

            bar_width = available * min(row.degree_of_saturation, scale_max) / scale_max
            color = LOS_COLORS[row.level_of_service]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(left, y + 3, bar_width, 12), 4, 4)

            painter.setPen(chart_color(self))
            painter.drawText(
                QRectF(left + bar_width + 6, y, right - 5, 18),
                Qt.AlignmentFlag.AlignVCenter,
                f"{row.degree_of_saturation:.2f}",
            )


class SignalTimingDiagram(QWidget):
    """Diagrama de bandas verde, amarillo y rojo por semáforo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: IntersectionProject | None = None
        self._optimization: SignalOptimizationResult | None = None
        self._cycles = 1
        self._cursor: float | None = None
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

    def set_data(
        self,
        project: IntersectionProject,
        optimization: SignalOptimizationResult | None,
    ) -> None:
        self._project = project
        self._optimization = optimization
        rows = max(3, len(signal_rows(project, optimization)) if optimization else 0)
        self.setMinimumHeight(72 + rows * 32)
        self.updateGeometry()
        self.update()

    def set_cycles(self, cycles: int) -> None:
        self._cycles = cycles
        self.update()

    def set_cursor(self, cursor: float | None) -> None:
        self._cursor = cursor
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), chart_color(self, QPalette.ColorRole.Base))

        if self._project is None or self._optimization is None:
            painter.setPen(chart_color(self))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Define un programa válido para ver sus bandas",
            )
            return

        cycle = self._optimization.cycle_length_s
        total = cycle * self._cycles
        left, right, top = min(170.0, self.width() * 0.29), 24.0, 42.0
        available = max(120.0, self.width() - left - right)
        row_height = 32.0

        painter.setFont(QFont(painter.font().family(), 8))
        painter.setPen(chart_color(self))
        tick_step = max(1, int(total / max(3, available // 50)))
        for second in range(0, int(total) + 1, tick_step):
            x = left + available * second / total
            painter.drawLine(int(x), int(top - 8), int(x), self.height() - 15)
            painter.drawText(QRectF(x - 18, 8, 36, 18), Qt.AlignmentFlag.AlignCenter, str(second))
        painter.drawText(
            QRectF(left, 25, available, 16),
            Qt.AlignmentFlag.AlignCenter,
            f"Tiempo (s) · C = {cycle:g} s",
        )

        phase_by_number = {phase.phase_number: phase for phase in self._optimization.phases}
        heads = signal_rows(self._project, self._optimization)
        for row, (name, number) in enumerate(heads):
            y = top + row * row_height
            label = painter.fontMetrics().elidedText(
                f"{name} · F{number}", Qt.TextElideMode.ElideRight, int(left - 14),
            )
            painter.setPen(chart_color(self))
            painter.drawText(QRectF(6, y, left - 14, 24), Qt.AlignmentFlag.AlignVCenter, label)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#B3261E"))
            painter.drawRoundedRect(QRectF(left, y + 3, available, 18), 3, 3)

            phase = phase_by_number.get(number)
            if phase is None:
                continue
            for repeat in range(self._cycles):
                green_x = left + available * (cycle * repeat + phase.start_s) / total
                green_width = available * phase.green_s / total
                yellow_width = available * phase.yellow_s / total
                painter.setBrush(QColor("#18864B"))
                painter.drawRect(QRectF(green_x, y + 3, green_width, 18))
                painter.setBrush(QColor("#E3A008"))
                painter.drawRect(QRectF(green_x + green_width, y + 3, yellow_width, 18))
                red_x = green_x + green_width + yellow_width
                painter.setBrush(QColor("#720E17"))
                painter.drawRect(QRectF(red_x, y + 3, available * phase.all_red_s / total, 18))

        if self._cursor is not None:
            x = round(left + available * self._cursor / total)
            painter.setPen(QPen(QColor("#58B8E9"), 2))
            painter.drawLine(x, int(top), x, self.height() - 25)

        legend_y = self.height() - 18
        legend = (
            ("Verde", "#18864B"), ("Amarillo", "#E3A008"), ("Rojo", "#B3261E"),
            ("Todo rojo", "#720E17"),
        )
        x = 6
        for label, color in legend:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(x, legend_y, 16, 10))
            painter.setPen(chart_color(self))
            painter.drawText(QRectF(x + 21, legend_y - 4, 70, 18), label)
            x += 68


class TransitCongestionChart(QWidget):
    """Comparación visual de funciones volumen–demora."""

    MODELS = (
        ("Lineal", "#3F6C8E"),
        ("BPR", "#8A5A9E"),
        ("Davidson", "#B05B3B"),
        ("Exponencial", "#27806B"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: TransitLineInput | None = None
        self._result: TransitLineResult | None = None
        self.setMinimumHeight(290)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

    def set_data(
        self,
        data: TransitLineInput | None,
        result: TransitLineResult | None,
    ) -> None:
        self._data = data
        self._result = result
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), chart_color(self, QPalette.ColorRole.Base))
        if self._data is None or self._result is None:
            painter.setPen(chart_color(self))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Calcula la línea para comparar modelos"
            )
            return

        left, right, top, bottom = 62.0, 24.0, 38.0, 48.0
        width = max(160.0, self.width() - left - right)
        height = max(120.0, self.height() - top - bottom)
        t0 = self._result.free_flow_time_min
        reference_values = [
            congestion_time(model, t0, 1.5, self._data)
            for model in ("Lineal", "BPR", "Exponencial")
        ]
        y_max = max(value for value in reference_values if value is not None) * 1.20
        y_max = max(y_max, t0 * 1.5)

        painter.setFont(QFont(painter.font().family(), 8))
        grid_color = chart_color(self, QPalette.ColorRole.Mid)
        painter.setPen(QPen(grid_color, 1))
        for index in range(6):
            x_value = 1.5 * index / 5
            x = left + width * x_value / 1.5
            painter.drawLine(int(x), int(top), int(x), int(top + height))
            painter.setPen(chart_color(self))
            painter.drawText(
                QRectF(x - 18, top + height + 6, 36, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"{x_value:.1f}",
            )
            painter.setPen(QPen(grid_color, 1))
        for index in range(5):
            value = y_max * index / 4
            y = top + height - height * value / y_max
            painter.drawLine(int(left), int(y), int(left + width), int(y))
            painter.setPen(chart_color(self))
            painter.drawText(
                QRectF(2, y - 8, left - 9, 16),
                Qt.AlignmentFlag.AlignRight,
                f"{value:.0f}",
            )
            painter.setPen(QPen(grid_color, 1))

        painter.setPen(chart_color(self))
        painter.drawText(
            QRectF(left, self.height() - 22, width, 18),
            Qt.AlignmentFlag.AlignCenter,
            "Grado de saturación vial, x = v/c",
        )
        painter.save()
        painter.translate(14, top + height / 2)
        painter.rotate(-90)
        painter.drawText(
            QRectF(-height / 2, -10, height, 18),
            Qt.AlignmentFlag.AlignCenter,
            "Tiempo de recorrido (min)",
        )
        painter.restore()

        clip = QRectF(left, top, width, height)
        painter.save()
        painter.setClipRect(clip)
        for model, color in self.MODELS:
            path = QPainterPath()
            active = False
            for index in range(151):
                degree = 1.5 * index / 150
                value = congestion_time(model, t0, degree, self._data)
                if value is None:
                    active = False
                    continue
                x = left + width * degree / 1.5
                y = top + height - height * min(value, y_max * 1.05) / y_max
                if not active:
                    path.moveTo(x, y)
                    active = True
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(QColor(color), 2.3))
            painter.drawPath(path)

        current_x = left + width * min(self._result.road_degree_of_saturation, 1.5) / 1.5
        painter.setPen(QPen(chart_color(self), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(int(current_x), int(top), int(current_x), int(top + height))
        painter.restore()

        legend_x = left
        for model, color in self.MODELS:
            painter.setPen(QPen(QColor(color), 3))
            painter.drawLine(int(legend_x), 18, int(legend_x + 18), 18)
            painter.setPen(chart_color(self))
            painter.drawText(QRectF(legend_x + 23, 9, 78, 18), Qt.AlignmentFlag.AlignVCenter, model)
            legend_x += 105
        painter.setPen(chart_color(self))
        painter.drawText(
            QRectF(max(left, self.width() - 185), 9, 165, 18),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Condición actual: x = {self._result.road_degree_of_saturation:.3f}",
        )
