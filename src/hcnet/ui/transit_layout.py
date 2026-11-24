"""Distribución ajustable de la captura y los resultados de transporte público."""

from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import QBoxLayout, QSplitter, QStackedWidget, QTabBar, QVBoxLayout, QWidget


class AdaptiveColumns(QWidget):
    """Alinea secciones en columnas cuando caben en el ancho disponible."""

    def __init__(self, *widgets, minimum_width=0, stretches=()):
        super().__init__()
        self.minimum_width = minimum_width
        self.columns = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.columns.setContentsMargins(0, 0, 0, 0)
        for index, widget in enumerate(widgets):
            stretch = stretches[index] if stretches else 1
            self.columns.addWidget(widget, stretch)

    def _items(self):
        return [
            item
            for index in range(self.columns.count())
            if not (item := self.columns.itemAt(index)).isEmpty()
        ]

    def minimumSizeHint(self):  # noqa: N802
        size = self.columns.minimumSize()
        items = self._items()
        width = max((item.minimumSize().width() for item in items), default=0)
        return QSize(width, size.height())

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        items = self._items()
        required = sum(item.minimumSize().width() for item in items)
        required += self.columns.spacing() * max(0, len(items) - 1)
        direction = (
            QBoxLayout.Direction.LeftToRight
            if self.width() >= max(required, self.minimum_width)
            else QBoxLayout.Direction.TopToBottom
        )
        if direction != self.columns.direction():
            self.columns.setDirection(direction)
            self.updateGeometry()


class TransitPages(QStackedWidget):
    """Reserva altura para las pestañas; los formularios se desplazan dentro de cada panel."""

    def heightForWidth(self, _width):  # noqa: N802
        return self.minimumSizeHint().height()


class TransitPanels(QWidget):
    """Alterna entre paneles amplios y una vista simultánea redimensionable."""

    CAPTURE, PARALLEL, RESULTS = range(3)
    PARALLEL_MIN_WIDTH = 920

    def __init__(self, capture, results):
        super().__init__()
        self.capture, self.results = capture, results
        self.setMinimumHeight(205)
        self._preferred = self.PARALLEL
        self._last_single = self.CAPTURE
        self._sizes = [620, 380]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabBar()
        self.tabs.setObjectName("transitPanelTabs")
        self.tabs.setAccessibleName("Paneles de transporte público")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        for title, tip in (
            ("Captura", "Amplía el panel de datos y configuración."),
            ("En paralelo", "Muestra captura y resultados lado a lado."),
            ("Resultados", "Amplía el panel de indicadores, gráficos y tablas."),
        ):
            index = self.tabs.addTab(title)
            self.tabs.setTabToolTip(index, tip)
        layout.addWidget(self.tabs)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(capture)
        self.splitter.addWidget(results)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)
        self._apply_view(self.CAPTURE)
        self.tabs.currentChanged.connect(self._choose_view)
        self.splitter.splitterMoved.connect(self._remember_sizes)

    def _choose_view(self, index):
        self._preferred = index
        if index != self.PARALLEL:
            self._last_single = index
        self._apply_view(index)

    def _remember_sizes(self, *_):
        if self.tabs.currentIndex() == self.PARALLEL:
            self._sizes = self.splitter.sizes()

    def _apply_view(self, index):
        with QSignalBlocker(self.tabs):
            self.tabs.setCurrentIndex(index)
        self.capture.setVisible(index != self.RESULTS)
        self.results.setVisible(index != self.CAPTURE)
        if index == self.PARALLEL:
            self.splitter.setSizes(self._sizes)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        wide = self.width() >= self.PARALLEL_MIN_WIDTH
        was_wide = self.tabs.isTabEnabled(self.PARALLEL)
        if was_wide != wide:
            with QSignalBlocker(self.tabs):
                self.tabs.setTabEnabled(self.PARALLEL, wide)
            self.tabs.setTabToolTip(
                self.PARALLEL,
                "Muestra captura y resultados lado a lado."
                if wide
                else "Amplía el ancho de la ventana para ver ambos paneles.",
            )
        index = self._preferred if wide or self._preferred != self.PARALLEL else self._last_single
        if was_wide != wide or index != self.tabs.currentIndex():
            self._apply_view(index)
