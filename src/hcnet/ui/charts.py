"""Visualizaciones compactas dibujadas con Qt."""

from __future__ import annotations

from collections import defaultdict
from math import cos, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from hcnet.domain.models import IntersectionProject, IntersectionResult, SignalOptimizationResult
from hcnet.domain.transit import TransitLineInput, TransitLineResult, congestion_time
from hcnet.ui.styles import COLORS, LOS_COLORS


class IntersectionSketch(QWidget):
    """Esquema orientativo que resume volumen por acceso."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: IntersectionProject | None = None
        self.setMinimumSize(310, 310)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_project(self, project: IntersectionProject) -> None:
        self._project = project
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

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
        for direction in ends:
            painter.setPen(QPen(QColor("#D5D7DA"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(
                center + direction * (road * 0.65), center + direction * (size * 0.32)
            )

        totals: defaultdict[str, float] = defaultdict(float)
        if self._project is not None:
            for group in self._project.lane_groups:
                totals[group.origin_branch] += group.volume_veh_h

        painter.setFont(QFont(painter.font().family(), 9, QFont.Weight.DemiBold))
        painter.setPen(QColor(COLORS["navy"]))
        for branch, direction in zip(branches, ends, strict=True):
            label_x = min(width - 140, max(0, cx + direction.x() * size * 0.44 - 70))
            label_y = min(height - 38, max(0, cy + direction.y() * size * 0.44 - 19))
            rectangle = QRectF(label_x, label_y, 140, 38)
            value = totals[branch.code]
            text = (
                f"{branch.label}\n{branch.inbound_lanes} carriles · "
                f"{value:,.0f} veh/h"
                if value
                else f"{branch.label}\n{branch.inbound_lanes} carriles"
            )
            painter.drawText(rectangle, Qt.AlignmentFlag.AlignCenter, text)

        painter.setBrush(QColor(COLORS["cyan"]))
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.drawEllipse(QRectF(cx - 28, cy - 28, 56, 56))
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont(painter.font().family(), 10, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 28, cy - 28, 56, 56), Qt.AlignmentFlag.AlignCenter, "HC")


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
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        if self._result is None:
            painter.setPen(QColor(COLORS["muted"]))
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
        painter.setPen(QColor(COLORS["muted"]))
        for tick in (0.0, 0.5, 0.9, 1.0, scale_max):
            x = left + available * tick / scale_max
            painter.drawLine(int(x), top - 5, int(x), self.height() - 12)
            painter.drawText(QRectF(x - 20, 4, 40, 18), Qt.AlignmentFlag.AlignCenter, f"{tick:.1f}")

        capacity_x = left + available / scale_max
        painter.setPen(QPen(QColor(COLORS["red"]), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(capacity_x), top - 5, int(capacity_x), self.height() - 12)

        for index, row in enumerate(self._result.lane_groups):
            y = top + index * row_height
            painter.setPen(QColor(COLORS["ink"]))
            label = row.label if len(row.label) <= 25 else row.label[:23] + "…"
            painter.drawText(QRectF(8, y, left - 16, 18), Qt.AlignmentFlag.AlignVCenter, label)

            bar_width = available * min(row.degree_of_saturation, scale_max) / scale_max
            color = LOS_COLORS[row.level_of_service]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(left, y + 3, bar_width, 12), 4, 4)

            painter.setPen(QColor(COLORS["ink"]))
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
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

    def set_data(
        self,
        project: IntersectionProject,
        optimization: SignalOptimizationResult | None,
    ) -> None:
        self._project = project
        self._optimization = optimization
        rows = max(3, len(project.signal_heads))
        self.setMinimumHeight(72 + rows * 32)
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        if self._project is None or self._optimization is None:
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Optimiza el plan para generar el diagrama de bandas",
            )
            return

        cycle = self._optimization.cycle_length_s
        left, right, top = 190.0, 28.0, 42.0
        available = max(120.0, self.width() - left - right)
        row_height = 32.0

        painter.setFont(QFont(painter.font().family(), 8))
        painter.setPen(QColor(COLORS["muted"]))
        tick_step = 10 if cycle <= 120 else 20
        for second in range(0, int(cycle) + 1, tick_step):
            x = left + available * second / cycle
            painter.drawLine(int(x), int(top - 8), int(x), self.height() - 15)
            painter.drawText(QRectF(x - 18, 8, 36, 18), Qt.AlignmentFlag.AlignCenter, str(second))
        painter.drawText(
            QRectF(left, 25, available, 16),
            Qt.AlignmentFlag.AlignCenter,
            f"Tiempo dentro del ciclo (s) · C = {cycle:.0f} s",
        )

        phase_by_number = {phase.phase_number: phase for phase in self._optimization.phases}
        for row, head in enumerate(self._project.signal_heads):
            y = top + row * row_height
            label = f"{head.name} · {head.branch_code} · F{head.signal_phase}"
            if len(label) > 29:
                label = label[:27] + "…"
            painter.setPen(QColor(COLORS["ink"]))
            painter.drawText(QRectF(6, y, left - 14, 24), Qt.AlignmentFlag.AlignVCenter, label)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#B3261E"))
            painter.drawRoundedRect(QRectF(left, y + 3, available, 18), 3, 3)

            phase = phase_by_number.get(head.signal_phase)
            if phase is None:
                continue
            green_x = left + available * phase.start_s / cycle
            green_width = available * phase.green_s / cycle
            yellow_width = available * phase.yellow_s / cycle
            painter.setBrush(QColor("#18864B"))
            painter.drawRect(QRectF(green_x, y + 3, green_width, 18))
            painter.setBrush(QColor("#E3A008"))
            painter.drawRect(QRectF(green_x + green_width, y + 3, yellow_width, 18))

        legend_y = self.height() - 18
        legend = (("Verde", "#18864B"), ("Amarillo", "#E3A008"), ("Rojo", "#B3261E"))
        x = left
        for label, color in legend:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(x, legend_y, 16, 10))
            painter.setPen(QColor(COLORS["ink"]))
            painter.drawText(QRectF(x + 21, legend_y - 4, 70, 18), label)
            x += 92


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
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        if self._data is None or self._result is None:
            painter.setPen(QColor(COLORS["muted"]))
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
        painter.setPen(QPen(QColor("#DADCE0"), 1))
        for index in range(6):
            x_value = 1.5 * index / 5
            x = left + width * x_value / 1.5
            painter.drawLine(int(x), int(top), int(x), int(top + height))
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(
                QRectF(x - 18, top + height + 6, 36, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"{x_value:.1f}",
            )
            painter.setPen(QPen(QColor("#DADCE0"), 1))
        for index in range(5):
            value = y_max * index / 4
            y = top + height - height * value / y_max
            painter.drawLine(int(left), int(y), int(left + width), int(y))
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(
                QRectF(2, y - 8, left - 9, 16),
                Qt.AlignmentFlag.AlignRight,
                f"{value:.0f}",
            )
            painter.setPen(QPen(QColor("#DADCE0"), 1))

        painter.setPen(QColor(COLORS["ink"]))
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
        painter.setPen(QPen(QColor(COLORS["ink"]), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(int(current_x), int(top), int(current_x), int(top + height))
        painter.restore()

        legend_x = left
        for model, color in self.MODELS:
            painter.setPen(QPen(QColor(color), 3))
            painter.drawLine(int(legend_x), 18, int(legend_x + 18), 18)
            painter.setPen(QColor(COLORS["ink"]))
            painter.drawText(QRectF(legend_x + 23, 9, 78, 18), Qt.AlignmentFlag.AlignVCenter, model)
            legend_x += 105
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(
            QRectF(max(left, self.width() - 185), 9, 165, 18),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Condición actual: x = {self._result.road_degree_of_saturation:.3f}",
        )
