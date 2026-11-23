"""Desplazamiento con la rueda sobre campos y selectores."""

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QMenu,
    QMenuBar,
    QTabBar,
    QWidget,
)


class WheelScrollFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not isinstance(watched, QWidget) or not isinstance(event, QWheelEvent):
            return False

        control = watched
        while not isinstance(
            control, (QAbstractSpinBox, QCalendarWidget, QComboBox, QMenu, QMenuBar, QTabBar)
        ):
            if control.isWindow() or control.parentWidget() is None:
                return False
            control = control.parentWidget()

        pixels = event.pixelDelta().y()
        angle = event.angleDelta().y()
        area = None if control.isWindow() else control.parentWidget()
        while area is not None and (pixels or angle):
            if isinstance(area, QAbstractScrollArea):
                bar = area.verticalScrollBar()
                can_scroll = (
                    bar.value() > bar.minimum() if (pixels or angle) > 0
                    else bar.value() < bar.maximum()
                )
                if can_scroll:
                    viewport = area.viewport()
                    scroll = QWheelEvent(
                        viewport.mapFromGlobal(event.globalPosition()), event.globalPosition(),
                        QPoint(0, pixels), QPoint(0, angle), event.buttons(),
                        Qt.KeyboardModifier.NoModifier, event.phase(), event.inverted(),
                        event.source(), event.pointingDevice(),
                    )
                    QApplication.sendEvent(viewport, scroll)
                    break
            if area.isWindow():
                break
            area = area.parentWidget()

        event.accept()
        return True
