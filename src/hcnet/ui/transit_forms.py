"""Controles compartidos por los análisis de transporte público."""

from math import isfinite

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hcnet.ui.transit_layout import AdaptiveColumns


def label(text, name="pageSubtitle"):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def scroll(page):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    return area


def row(*widgets, wrap=True):
    if wrap:
        bar = AdaptiveColumns(*widgets, stretches=(0,) * len(widgets))
        bar.columns.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return bar
    bar = QWidget()
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch()
    return bar


def button(title, action):
    widget = QPushButton(title)
    widget.clicked.connect(action)
    return widget


def table(headers, *, editable=True):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    widget.horizontalHeader().setMinimumSectionSize(75)
    header = widget.horizontalHeader()
    for index, title in enumerate(headers):
        widget.setColumnWidth(index, max(132, header.fontMetrics().horizontalAdvance(title) + 25))
    widget.verticalHeader().setDefaultSectionSize(29)
    widget.setMinimumHeight(155)
    if not editable:
        widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    return widget


def read_table(widget):
    data = []
    for i in range(widget.rowCount()):
        values = []
        for j in range(widget.columnCount()):
            cell = widget.item(i, j)
            values.append(cell.text().strip() if cell else "")
        if any(values):
            data.append(values)
    return data


def show_number(value):
    return str(value) if value is not None else ""


def fill_table(widget, rows):
    previous = widget.blockSignals(True)
    widget.setRowCount(len(rows))
    for i, record in enumerate(rows):
        for j in range(widget.columnCount()):
            value = record[j] if j < len(record) else None
            widget.setItem(i, j, QTableWidgetItem(show_number(value)))
    widget.blockSignals(previous)


def numeric(value, title, *, default=None):
    if value == "" or value is None:
        if default is not None:
            return default
        raise ValueError(f"Captura {title.lower()}.")
    try:
        result = float(str(value).strip().replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Revisa el valor de {title.lower()}.") from exc
    if not isfinite(result):
        raise ValueError(f"{title} debe ser finito.")
    return result


def integer(value, title, *, default=None):
    result = numeric(value, title, default=default)
    if result != int(result):
        raise ValueError(f"{title} debe ser entero.")
    return int(result)


def intervals(text):
    return tuple(
        numeric(x.strip(), "Intervalo observado")
        for x in text.replace("\n", ";").split(";")
        if x.strip()
    )


class Form(QWidget):
    def __init__(self, specs, edited, *, second_column=()):
        super().__init__()
        self.controls = {}
        self.forms = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        columns = (QWidget(), QWidget()) if second_column else (QWidget(),)
        forms = []
        for column in columns:
            form = QFormLayout(column)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            forms.append(form)
        layout.addWidget(
            AdaptiveColumns(*columns, minimum_width=780) if second_column else columns[0]
        )
        for key, title, initial, tip in specs:
            if isinstance(initial, tuple):
                widget = QComboBox()
                widget.addItems(initial)
                widget.currentIndexChanged.connect(lambda *_: edited())
            elif isinstance(initial, bool):
                widget = QCheckBox()
                widget.setChecked(initial)
                widget.toggled.connect(lambda *_: edited())
            else:
                widget = QLineEdit()
                widget.setText(show_number(initial))
                widget.textChanged.connect(lambda *_: edited())
            widget.setToolTip(tip or title)
            widget.setAccessibleName(title)
            self.controls[key] = widget
            form = forms[int(key in second_column)]
            form.addRow(title, widget)
            self.forms[key] = form

    def value(self, key):
        widget = self.controls[key]
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return widget.text().strip()

    def values(self):
        return {key: self.value(key) for key in self.controls}

    def number(self, key, default=None):
        widget = self.controls[key]
        return numeric(self.value(key), widget.accessibleName(), default=default)

    def whole(self, key, default=None):
        widget = self.controls[key]
        return integer(self.value(key), widget.accessibleName(), default=default)

    def set_values(self, values):
        for key, value in values.items():
            widget = self.controls.get(key)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(show_number(value))

    def visible(self, keys, visible):
        for key in keys:
            self.forms[key].setRowVisible(self.controls[key], visible)


class TransitPlot(QWidget):
    colors = ("#197eaa", "#e17634", "#43976b", "#b35eaa")

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.charts = []

    def set_charts(self, charts):
        self.charts = [chart for chart in charts if chart.get("series")]
        self.setVisible(bool(self.charts))
        self.setMinimumHeight(220 * max(1, len(self.charts)))
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        ink = palette.text().color()
        painter.fillRect(self.rect(), palette.base())
        height = self.height() / max(1, len(self.charts))
        for index, chart in enumerate(self.charts):
            area = QRectF(57, index * height + 49, max(40, self.width() - 83), height - 96)
            series = chart["series"]
            xmax = max((x for values in series.values() for x, _ in values), default=1) or 1
            xmax += 0.5 if chart.get("bars") else 0
            ymin = min(0, min((y for values in series.values() for _, y in values), default=0))
            ymax = max((y for values in series.values() for _, y in values), default=1)
            ymax = ymax if ymax > ymin else ymin + 1
            painter.setPen(ink)
            painter.drawText(15, int(area.top() - 32), chart["title"])
            painter.drawText(15, int(area.top() - 12), chart["y"])
            painter.drawText(int(area.right()) - 100, int(area.bottom() + 37), chart["x"])
            for tick in range(5):
                value = tick / 4
                h = area.bottom() - value * area.height()
                w = area.left() + value * area.width()
                painter.setPen(QPen(palette.mid().color(), 0.7))
                painter.drawLine(area.left(), h, area.right(), h)
                painter.setPen(ink)
                painter.drawText(7, int(h + 4), f"{ymin + value * (ymax - ymin):.3g}")
                if not chart.get("bars"):
                    painter.drawText(int(w - 9), int(area.bottom() + 18), f"{value * xmax:.3g}")
            xlegend = area.left() + 50
            for i, (name, points) in enumerate(series.items()):
                color = QColor(self.colors[i % len(self.colors)])
                painter.setPen(QPen(color, 2))
                positions = [
                    (
                        area.left() + x * area.width() / xmax,
                        area.bottom() - (y - ymin) * area.height() / (ymax - ymin),
                    )
                    for x, y in points
                ]
                if chart.get("bars"):
                    painter.setBrush(color)
                    bar_width = min(60, area.width() / (len(series) * 3))
                    for x, y in positions:
                        painter.drawRect(QRectF(x - bar_width / 2, y, bar_width, area.bottom() - y))
                elif name not in chart.get("markers", []):
                    for (x1, y1), (x2, y2) in zip(positions, positions[1:], strict=False):
                        painter.drawLine(x1, y1, x2, y2)
                for x, y in positions:
                    painter.drawEllipse(QRectF(x - 2, y - 2, 4, 4))
                painter.drawLine(xlegend, area.top() - 15, xlegend + 14, area.top() - 15)
                painter.setPen(ink)
                painter.drawText(int(xlegend + 17), int(area.top() - 12), name)
                xlegend += painter.fontMetrics().horizontalAdvance(name) + 28
        painter.end()


class ResultPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = label("", "sectionTitle")
        self.notes = label("")
        self.metrics = table(("Indicador", "Resultado"), editable=False)
        self.metrics.verticalHeader().hide()
        self.metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.metrics.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.plot = TransitPlot()
        self.tables = QVBoxLayout()
        layout.addWidget(self.title)
        layout.addWidget(self.notes)
        layout.addWidget(AdaptiveColumns(self.metrics, self.plot, minimum_width=880))
        layout.addLayout(self.tables)
        layout.addStretch()
        self.show_record(None)

    def show_record(self, record):
        while self.tables.count():
            widget = self.tables.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.metrics.setVisible(bool(record and record.get("metrics")))
        if not record:
            self.title.setText("Resultados pendientes")
            self.notes.setText("Captura los datos y pulsa Calcular.")
            self.plot.set_charts([])
            return
        self.title.setText(record["title"])
        self.notes.setText("\n".join(record.get("notes", [])))
        fill_table(self.metrics, list(record.get("metrics", {}).items()))
        count = len(record.get("metrics", {}))
        self.metrics.setMinimumHeight(min(380, max(80, count * 29 + 28)))
        self.plot.set_charts(record.get("charts", []))
        for name, headers, rows in record.get("tables", []):
            self.tables.addWidget(label(name, "sectionTitle"))
            widget = table(headers, editable=False)
            fill_table(widget, rows)
            self.tables.addWidget(widget)
