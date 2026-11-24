"""Sistema visual de HCNet Transport."""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

COLORS = {
    "navy": "#20242A",
    "blue": "#3F444B",
    "cyan": "#5F6368",
    "green": "#18794E",
    "orange": "#9A5B13",
    "red": "#B42318",
    "ink": "#202124",
    "muted": "#5F6368",
    "canvas": "#F5F5F5",
    "surface": "#FFFFFF",
    "line": "#DADCE0",
}


LOS_COLORS = {
    "A": "#1B7F5A",
    "B": "#4B8F55",
    "C": "#6B806B",
    "D": "#9A6A3A",
    "E": "#C34B32",
    "F": "#B42318",
}


APP_STYLESHEET = """
QMainWindow, QDialog {
    background: #F5F5F5;
    color: #202124;
}
QWidget {
    color: #202124;
    font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 10pt;
}
QToolBar {
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #DADCE0;
    padding: 6px 10px;
    spacing: 5px;
}
QToolBar QToolButton {
    background: transparent;
    color: #202124;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 9px;
}
QToolBar QToolButton:hover {
    background: #ECEDEF;
    border-color: #C7C9CC;
}
QToolBar QToolButton:pressed {
    background: #DADCE0;
}
QMenuBar {
    background: #FFFFFF;
    color: #202124;
    border-bottom: 1px solid #DADCE0;
}
QMenuBar::item {
    background: transparent;
    color: #202124;
    padding: 6px 10px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #3F444B;
    color: #FFFFFF;
}
QMenu {
    background: #FFFFFF;
    color: #202124;
    border: 1px solid #C7C9CC;
    padding: 5px;
}
QMenu::item {
    background: transparent;
    color: #202124;
    padding: 7px 28px 7px 24px;
}
QMenu::item:disabled, QMenuBar::item:disabled, QToolButton:disabled {
    color: #9AA0A6;
}
QMenu::separator {
    background: #DADCE0;
    height: 1px;
    margin: 5px 8px;
}
QTabWidget::pane {
    border: 0;
    background: #F5F5F5;
}
QToolBar#workspaceToolbar {
    padding: 3px 9px;
}
QTabBar#workspaceNavigation {
    font-size: 9pt;
}
QTabBar#workspaceNavigation::tab {
    padding: 7px 5px;
}
QWidget#publicTransport QTabBar::tab {
    padding: 6px 10px;
}
QWidget#publicTransport QLabel#infoBanner {
    padding: 6px 9px;
}
QTabBar#transitPanelTabs::tab:disabled {
    color: #9AA0A6;
}
QTabBar::tab {
    background: transparent;
    color: #5F6368;
    border: 0;
    border-bottom: 3px solid transparent;
    padding: 11px 18px;
    font-weight: 600;
}
QTabBar::tab:selected {
    color: #202124;
    border-bottom-color: #3F444B;
}
QTabBar::tab:hover:!selected {
    color: #202124;
    background: #E8EAED;
}
QGroupBox {
    background: #FFFFFF;
    color: #30343B;
    border: 1px solid #DADCE0;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 13px;
    padding: 0 6px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background: #FFFFFF;
    color: #202124;
    border: 1px solid #BFC2C5;
    border-radius: 5px;
    padding: 6px;
    selection-background-color: #4B5057;
    selection-color: #FFFFFF;
}
QComboBox {
    combobox-popup: 0;
    qproperty-maxVisibleItems: 1000;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #202124;
    border: 1px solid #BFC2C5;
    selection-background-color: #3F444B;
    selection-color: #FFFFFF;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {
    min-height: 1.35em;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 2px solid #5F6368;
    padding: 5px;
}
QPushButton {
    background: #FFFFFF;
    color: #202124;
    border: 1px solid #BFC2C5;
    border-radius: 6px;
    padding: 7px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #ECEDEF;
    border-color: #7A7F85;
}
QPushButton:pressed {
    background: #DADCE0;
}
QPushButton#primaryButton {
    background: #30343B;
    color: #FFFFFF;
    border-color: #30343B;
}
QPushButton#primaryButton:hover {
    background: #17191C;
}
QPushButton#dangerButton {
    color: #B42318;
}
QTableWidget {
    background: #FFFFFF;
    color: #202124;
    alternate-background-color: #F7F7F7;
    border: 1px solid #DADCE0;
    border-radius: 7px;
    gridline-color: #E8EAED;
    selection-background-color: #5F6368;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background: #ECEDEF;
    color: #30343B;
    border: 0;
    border-right: 1px solid #DADCE0;
    border-bottom: 1px solid #C7C9CC;
    padding: 8px 6px;
    font-weight: 600;
}
QTextBrowser, QListWidget {
    background: #FFFFFF;
    color: #202124;
    border: 1px solid #DADCE0;
    border-radius: 7px;
}
QStatusBar {
    background: #FFFFFF;
    color: #5F6368;
    border-top: 1px solid #DADCE0;
}
QLabel#pageTitle {
    color: #202124;
    font-size: 19pt;
    font-weight: 700;
}
QLabel#pageSubtitle {
    color: #5F6368;
    font-size: 10pt;
}
QLabel#sectionTitle {
    color: #30343B;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#infoBanner, QLabel#panelStatus {
    background: #ECEDEF;
    color: #30343B;
    border-left: 4px solid #5F6368;
    border-radius: 4px;
    padding: 10px;
}
QLabel#warningBanner {
    background: #F1F3F4;
    color: #30343B;
    border-left: 4px solid #7A7F85;
    border-radius: 4px;
    padding: 10px;
}
QLabel#panelStatus[stale="true"] {
    background: #FFF3D6;
    color: #603B10;
    border-left-color: #9A5B13;
}
QFrame#metricCard {
    background: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 8px;
}
QLabel#metricLabel {
    color: #5F6368;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#metricValue {
    color: #202124;
    font-size: 20pt;
    font-weight: 700;
}
QScrollArea {
    border: 0;
    background: #F5F5F5;
}
QSplitter::handle {
    background: #DADCE0;
}
QToolTip {
    background: #30343B;
    color: #FFFFFF;
    border: 1px solid #202124;
    padding: 4px;
}
"""

DARK_COLORS = {
    "#f5f5f5": "#161b22", "#ffffff": "#202731", "#202124": "#eef2f7",
    "#30343b": "#dce4ed", "#5f6368": "#aab9cb", "#dadce0": "#435268",
    "#ecedef": "#2d3746", "#c7c9cc": "#596a80", "#3f444b": "#496483",
    "#e8eaed": "#354154", "#bfc2c5": "#65758a", "#4b5057": "#405b77",
    "#7a7f85": "#8193a8", "#17191c": "#607fa0", "#b42318": "#faa19d",
    "#f7f7f7": "#252e3a", "#f1f3f4": "#252e3a", "#9aa0a6": "#aab9cb",
    "#657987": "#aab9cb", "#176b45": "#7ce3b4", "#eceef0": "#2d3746",
    "#fff3d6": "#3b2b1b", "#603b10": "#ffdfa3", "#9a5b13": "#e1a04d",
}


def dark_active() -> bool:
    app = QApplication.instance()
    return bool(app and app.property("hcnetDark"))


def themed_text(source: str) -> str:
    if dark_active():
        return re.sub(r"#[0-9a-fA-F]{6}", lambda m: DARK_COLORS.get(
            m[0].lower(), m[0]
        ), source)
    return source


def chart_color(widget: QWidget, role: QPalette.ColorRole = QPalette.ColorRole.Text) -> QColor:
    return widget.palette().color(role)


def set_theme(dark: bool) -> None:
    app = QApplication.instance()
    if app is None:
        return
    app.setProperty("hcnetDark", dark)
    palette = app.style().standardPalette()
    role = QPalette.ColorRole
    for color_role, color in {
        role.Window: "#f5f5f5", role.Base: "#ffffff", role.AlternateBase: "#f7f7f7",
        role.Button: "#ecedef", role.Text: "#202124", role.WindowText: "#202124",
        role.ButtonText: "#202124", role.Highlight: "#3f444b", role.Mid: "#bfc2c5",
        role.PlaceholderText: "#5f6368", role.ToolTipBase: "#ecedef", role.ToolTipText: "#202124",
    }.items():
        palette.setColor(color_role, QColor(DARK_COLORS[color] if dark else color))
    palette.setColor(role.HighlightedText, QColor("#ffffff"))
    palette.setColor(role.Link, QColor("#a6cfff" if dark else "#174a78"))
    for text_role in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, text_role,
                         QColor("#aab9cb" if dark else "#656972"))
    app.setPalette(palette)
    stylesheet = themed_text(APP_STYLESHEET)
    if dark:
        stylesheet += """
        QMenuBar::item:selected, QMenu::item:selected { color: #eef2f7; }
        QPushButton#primaryButton, QToolTip {
            background: #405b77; border-color: #65758a; color: #ffffff;
        }
        QPushButton#primaryButton:hover { background: #496483; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QComboBox QAbstractItemView {
            selection-color: #ffffff;
        }
        """
    app.setStyleSheet(stylesheet)
