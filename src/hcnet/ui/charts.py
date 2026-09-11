"""Visualizaciones compactas dibujadas con Qt."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from hcnet.domain.models import IntersectionProject, IntersectionResult
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
        road = size * 0.30
        cx, cy = width / 2, height / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#43545D"))
        painter.drawRect(QRectF(cx - road / 2, 0, road, height))
        painter.drawRect(QRectF(0, cy - road / 2, width, road))

        pen = QPen(QColor("#D5D7DA"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(cx), 0, int(cx), int(cy - road / 2))
        painter.drawLine(int(cx), int(cy + road / 2), int(cx), height)
        painter.drawLine(0, int(cy), int(cx - road / 2), int(cy))
        painter.drawLine(int(cx + road / 2), int(cy), width, int(cy))

        painter.setPen(QPen(QColor("#F6F8F9"), 3))
        stop_offset = road / 2 + 9
        painter.drawLine(
            int(cx - road / 2), int(cy - stop_offset), int(cx + road / 2), int(cy - stop_offset)
        )
        painter.drawLine(
            int(cx - road / 2), int(cy + stop_offset), int(cx + road / 2), int(cy + stop_offset)
        )
        painter.drawLine(
            int(cx - stop_offset), int(cy - road / 2), int(cx - stop_offset), int(cy + road / 2)
        )
        painter.drawLine(
            int(cx + stop_offset), int(cy - road / 2), int(cx + stop_offset), int(cy + road / 2)
        )

        totals: defaultdict[str, float] = defaultdict(float)
        if self._project is not None:
            for group in self._project.lane_groups:
                totals[group.approach.strip().lower()] += group.volume_veh_h

        painter.setFont(QFont(painter.font().family(), 9, QFont.Weight.DemiBold))
        painter.setPen(QColor(COLORS["navy"]))
        labels = (
            ("Norte", totals["norte"], QRectF(cx - 70, 8, 140, 42)),
            ("Sur", totals["sur"], QRectF(cx - 70, height - 50, 140, 42)),
            ("Poniente", totals["poniente"], QRectF(8, cy - 46, 100, 42)),
            ("Oriente", totals["oriente"], QRectF(width - 108, cy - 46, 100, 42)),
        )
        for name, value, rectangle in labels:
            text = f"{name}\n{value:,.0f} veh/h" if value else name
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
