"""Constructor de rotondas y lectura espacial de movimientos y colas."""

from math import atan2, degrees

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QWidget

from hcnet.domain.roundabout_engineering import order, point


class RoundCanvas(QWidget):
    selected = Signal(str)
    moved = Signal(str, float)
    connected = Signal(str, str)

    def __init__(self, *, editable=False):
        super().__init__()
        self.setMinimumSize(245, 245)
        self.setAccessibleName("Esquema de geometría, movimientos y colas")
        self.site = None
        self.geometry_data = None
        self.editable = editable
        self.link_mode = False
        self.active = ""
        self.source = ""
        self.link = None
        self.queue = {}
        self.traffic = {}
        self.conflicts = []
        self.zoom = 1.0
        self.pan = QPointF()
        self.anchor = QPointF()
        self.drag = ""
        self.hits = {}
        self.mouse_origin = None
        self.same_scale = 0.0
        self.circular = True
        self.display_dimensions = True

    def set_site(self, site, geometry=None):
        self.site, self.geometry_data = site, geometry
        self.update()

    def reset_view(self):
        self.zoom = 1.0
        self.pan = QPointF()
        self.update()

    def magnify(self, factor):
        self.zoom = max(0.6, min(self.zoom * factor, 4))
        self.update()

    def set_link_mode(self, enabled):
        self.link_mode = enabled
        self.source = ""
        self.update()

    def _ray(self, azimuth, length):
        x, y = point(azimuth, length)
        return QPointF(x, -y)

    def _radius(self):
        if not self.circular:
            return 0
        if self.geometry_data:
            return self.geometry_data["diameter"] / 2
        return (self.site.diameter or 38) / 2

    def _scale(self, area):
        return (
            min(area.width(), area.height())
            * 0.31
            / max(self.same_scale or self._radius(), 12)
            * self.zoom
        )

    def render_vector(self, filename):
        generator = QSvgGenerator()
        generator.setFileName(str(filename))
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle("Esquema de rotonda HCNet")
        painter = QPainter(generator)
        if not painter.isActive():
            raise OSError("No se pudo escribir el SVG.")
        self._paint(painter, QRectF(self.rect()))
        painter.end()

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        self._paint(painter, QRectF(self.rect()))
        painter.end()

    def _paint(self, painter, area):
        palette = self.palette()
        ink = palette.text().color()
        painter.fillRect(area, palette.base())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.hits = {}
        if not self.site:
            return
        self.anchor = area.center() + self.pan
        scale = self._scale(area)
        radius = self._radius() * scale
        if self.circular:
            road = palette.mid().color()
            painter.setPen(QPen(ink, 1))
            painter.setBrush(road)
            painter.drawEllipse(self.anchor, radius, radius)
            dim = self.geometry_data
            ring = (dim["width"] if dim else self.site.width or 5 * self.site.lanes) * scale
            island = max(0, radius - ring)
            painter.setBrush(QColor("#6f906a"))
            painter.drawEllipse(self.anchor, island, island)
            apron = (dim["apron"] if dim else self.site.apron) * scale
            if 0 < apron <= island:
                painter.setPen(QPen(QColor("#bca58d"), apron))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(self.anchor, island - apron / 2, island - apron / 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#e7e8e0"), 1, Qt.PenStyle.DashLine))
            for i in range(1, self.site.lanes):
                r = island + ring * i / self.site.lanes
                painter.drawEllipse(self.anchor, r, r)
            self._direction(painter, max(radius - ring / 2, 2), scale)
            if self.display_dimensions and dim:
                painter.setPen(ink)
                painter.drawText(
                    QRectF(self.anchor.x() - 80, self.anchor.y() - 10, 160, 20),
                    Qt.AlignmentFlag.AlignCenter,
                    f"Ø {dim['diameter']:g} m",
                )
        arms = order(self.site)
        for arm in arms:
            self._arm(painter, area, arm, radius, scale, ink)
        if self.conflicts and self.circular:
            angles = {a.code: a.azimuth for a in arms}
            sign = -1 if self.site.direction == "Antihorario" else 1
            for arm, lane, kind, offset in self.conflicts:
                at = self.anchor + self._ray(
                    angles[arm] + sign * (6 if offset == 0 else -6), radius - scale * (lane + 1)
                )
                color = (
                    "#c83e48"
                    if kind.startswith("Cruce")
                    else "#f2b134"
                    if kind == "Convergencia"
                    else "#40a9da"
                )
                painter.setPen(QPen(ink, 1))
                painter.setBrush(QColor(color))
                painter.drawEllipse(at, 4, 4)
        if self.link and self.circular:
            self._connection(painter, radius, scale, arms)

    def _direction(self, painter, radius, scale):
        for angle in (45, 135, 225, 315):
            sign = -1 if self.site.direction == "Antihorario" else 1
            at = self.anchor + self._ray(angle, radius)
            earlier = self.anchor + self._ray(angle - sign * 8, radius)
            tangent = at - earlier
            length = max((tangent.x() ** 2 + tangent.y() ** 2) ** 0.5, 1)
            unit = tangent / length
            normal = QPointF(-unit.y(), unit.x())
            painter.setPen(QPen(QColor("#f5f3ea"), max(1, scale / 4)))
            painter.drawLine(QLineF(earlier, at))
            for side in (-1, 1):
                painter.drawLine(QLineF(at, at - unit * 6 + normal * 4 * side))

    def _arm(self, painter, area, arm, radius, scale, ink):
        unit = self._ray(arm.azimuth, 1)
        right = QPointF(-unit.y(), unit.x())
        inbound_sign = -1 if self.site.driving == "Derecha" else 1
        start = self.anchor + unit * (radius * 0.92)
        reach = min(area.width(), area.height()) * 0.127 * self.zoom
        lane_width = max(3.4 * scale, 4)
        # Separador, calzadas y carriles mantienen el lado de circulación elegido.
        for count, sign, entry in (
            (arm.inbound, inbound_sign, True),
            (arm.outbound, -inbound_sign, False),
        ):
            for i in range(count):
                offset = (
                    right
                    * ((i + 0.5) * lane_width + max(scale * 0.35, arm.splitter * scale / 2))
                    * sign
                )
                if (arm.splitter and self.circular) and i == 0:
                    painter.setPen(QPen(QColor("#71936e"), max(2, arm.splitter * scale * 0.55)))
                    painter.drawLine(QLineF(start + unit * 6, start + unit * reach * 0.74))
                painter.setPen(QPen(self.palette().mid().color(), lane_width * 0.94))
                painter.drawLine(QLineF(start + offset, start + offset + unit * reach))
                if entry:
                    queue = self.queue.get((arm.code, i + 1))
                    if queue:
                        base = arm.storage or arm.length or max(queue, 100)
                        trace = min(queue / base, 1) * reach
                        painter.setPen(QPen(QColor("#f6c447"), max(2, lane_width * 0.67)))
                        painter.drawLine(QLineF(start + offset, start + offset + unit * trace))
        if arm.bypass_width:
            offset = right * lane_width * (arm.inbound + 1) * inbound_sign
            painter.setPen(QPen(QColor("#c58e4a"), max(2, arm.bypass_width * scale)))
            painter.drawLine(QLineF(start + offset, start + offset + unit * reach))
        hub = start + unit * (reach + 5)
        hit = QRectF(hub.x() - 15, hub.y() - 14, 30, 28)
        self.hits[arm.code] = hit
        selected = arm.code in (self.active, self.source)
        painter.setPen(QPen(ink, 1))
        painter.setBrush(QColor("#36576e") if selected else self.palette().base().color())
        painter.drawRoundedRect(hit, 5, 5)
        painter.setPen(Qt.GlobalColor.white if selected else ink)
        painter.drawText(hit, Qt.AlignmentFlag.AlignCenter, arm.code)
        if arm.code in self.traffic:
            info = self.traffic[arm.code]
            painter.setPen(ink)
            point = hub + right * 27
            painter.drawText(
                QRectF(point.x() - 24, point.y() - 10, 48, 20),
                Qt.AlignmentFlag.AlignCenter,
                f"{info:.0f}",
            )

    def _connection(self, painter, radius, scale, arms):
        origin, dest = self.link
        azimuth = {a.code: a.azimuth for a in arms}
        if origin not in azimuth or dest not in azimuth:
            return
        sign = -1 if self.site.direction == "Antihorario" else 1
        rotation = ((azimuth[dest] - azimuth[origin]) * sign) % 360 or 360
        path = QPainterPath()
        path.moveTo(self.anchor + self._ray(azimuth[origin], radius + 15))
        r = max(1, radius - (self.geometry_data or {}).get("width", 4) * scale / 2)
        for step in range(37):
            path.lineTo(self.anchor + self._ray(azimuth[origin] + sign * rotation * step / 36, r))
        path.lineTo(self.anchor + self._ray(azimuth[dest], radius + 15))
        painter.setPen(QPen(QColor("#5dcced"), 3))
        painter.drawPath(path)

    def mousePressEvent(self, event):  # noqa: N802
        self.mouse_origin = event.position()
        self.drag = ""
        if not self.editable or event.button() != Qt.MouseButton.LeftButton:
            return
        code = next((key for key, hit in self.hits.items() if hit.contains(event.position())), "")
        if not code:
            return
        if self.link_mode:
            if self.source:
                self.link = (self.source, code)
                self.connected.emit(*self.link)
                self.source = ""
            else:
                self.source = code
            self.update()
        else:
            self.active = code
            self.drag = code
            self.selected.emit(code)
            self.update()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self.mouse_origin is None or not event.buttons():
            return
        if self.drag:
            if (event.position() - self.mouse_origin).manhattanLength() < 4:
                return
            diff = event.position() - self.anchor
            theta = round(degrees(atan2(diff.x(), -diff.y())) % 360, 1) % 360
            self.moved.emit(self.drag, theta)
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            self.pan += event.position() - self.mouse_origin
            self.mouse_origin = event.position()
            self.update()

    def mouseReleaseEvent(self, _event):  # noqa: N802
        self.mouse_origin = None
        self.drag = ""
