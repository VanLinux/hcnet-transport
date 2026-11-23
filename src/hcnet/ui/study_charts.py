"""Gráficos de emisiones compactos para el cuadro de estudios."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QWidget

from hcnet.ui.styles import chart_color


class StudyChart(QWidget):
    def __init__(self, *, line: bool = False) -> None:
        super().__init__()
        self.line = line
        self.values: list[float] = []
        self.labels: list[str] = []
        self.unit = ""
        self.setMinimumHeight(150)

    def set_data(self, labels: list[str], values: list[float], unit: str) -> None:
        self.labels, self.values, self.unit = labels, values, unit
        self.setVisible(bool(values))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), chart_color(self, QPalette.ColorRole.Base))
        ink = chart_color(self)
        painter.setPen(ink)
        if not self.values:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin datos para mostrar")
            return
        color = QColor("#3289AA")
        peak = max(map(abs, self.values)) or 1
        if self.line:
            area = QRectF(58, 14, max(1, self.width() - 74), self.height() - 48)
            floor = min(0, min(self.values))
            ceiling = max(0, max(self.values)) or 1
            painter.drawLine(area.bottomLeft(), area.bottomRight())
            painter.drawLine(area.bottomLeft(), area.topLeft())
            painter.drawText(5, 17, f"{ceiling:.3g}")
            painter.drawText(5, int(area.bottom()), f"{floor:.3g}")
            painter.drawText(
                58, self.height() - 8, f"{self.labels[0]}–{self.labels[-1]} s · {self.unit}"
            )
            path = QPainterPath()
            for i, value in enumerate(self.values):
                x = area.left() + i * area.width() / max(1, len(self.values) - 1)
                y = area.bottom() - (value - floor) / (ceiling - floor) * area.height()
                if i == 0:
                    path.moveTo(QPointF(x, y))
                else:
                    path.lineTo(QPointF(x, y))
            painter.setPen(QPen(color, 1.7))
            painter.drawPath(path)
            return
        row = (self.height() - 8) / len(self.values)
        label_width = min(self.width() * 0.42, 180)
        chart_width = max(1, self.width() - label_width - 105)
        metrics = painter.fontMetrics()
        for i, (label, value) in enumerate(zip(self.labels, self.values, strict=True)):
            y = 4 + i * row
            text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(label_width - 10))
            painter.drawText(
                QRectF(6, y, label_width - 8, row), Qt.AlignmentFlag.AlignVCenter, text
            )
            painter.fillRect(
                QRectF(label_width, y + row * 0.2, chart_width * abs(value) / peak, row * 0.6),
                color,
            )
            painter.drawText(
                QRectF(label_width + chart_width + 8, y, 95, row),
                Qt.AlignmentFlag.AlignVCenter,
                f"{value:.3g} {self.unit}",
            )
