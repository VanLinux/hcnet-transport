"""Sistema visual inicial de HCNet Transport 1.0."""

from __future__ import annotations

COLORS = {
    "navy": "#0B3954",
    "blue": "#176B87",
    "cyan": "#1F8AAB",
    "green": "#18794E",
    "orange": "#C66A15",
    "red": "#B42318",
    "ink": "#233746",
    "muted": "#657987",
    "canvas": "#F3F6F8",
    "surface": "#FFFFFF",
    "line": "#D9E3E8",
}


LOS_COLORS = {
    "A": "#1B7F5A",
    "B": "#4B9B50",
    "C": "#A6A832",
    "D": "#D88A1D",
    "E": "#D05226",
    "F": "#B42318",
}


APP_STYLESHEET = """
QMainWindow, QDialog {
    background: #F3F6F8;
    color: #233746;
}
QWidget {
    font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 10pt;
}
QToolBar {
    background: #FFFFFF;
    border: 0;
    border-bottom: 1px solid #D9E3E8;
    padding: 6px 10px;
    spacing: 5px;
}
QToolBar QToolButton {
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 9px;
}
QToolBar QToolButton:hover {
    background: #EAF2F5;
    border-color: #C9DAE2;
}
QMenuBar {
    background: #FFFFFF;
    border-bottom: 1px solid #E2EAEE;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #DCECF2;
    color: #0B3954;
}
QMenu {
    background: #FFFFFF;
    border: 1px solid #C9D6DC;
    padding: 5px;
}
QTabWidget::pane {
    border: 0;
    background: #F3F6F8;
}
QTabBar::tab {
    background: transparent;
    color: #657987;
    border: 0;
    border-bottom: 3px solid transparent;
    padding: 11px 18px;
    font-weight: 600;
}
QTabBar::tab:selected {
    color: #0B3954;
    border-bottom-color: #1F8AAB;
}
QTabBar::tab:hover:!selected {
    color: #176B87;
    background: #EAF2F5;
}
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #D9E3E8;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 600;
    color: #0B3954;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 13px;
    padding: 0 6px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background: #FFFFFF;
    color: #233746;
    border: 1px solid #C6D3D9;
    border-radius: 5px;
    padding: 6px;
    selection-background-color: #176B87;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 2px solid #1F8AAB;
    padding: 5px;
}
QPushButton {
    background: #FFFFFF;
    color: #0B3954;
    border: 1px solid #B9CAD2;
    border-radius: 6px;
    padding: 7px 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #EAF2F5;
    border-color: #77A8BA;
}
QPushButton:pressed {
    background: #D6E8EF;
}
QPushButton#primaryButton {
    background: #176B87;
    color: #FFFFFF;
    border-color: #176B87;
}
QPushButton#primaryButton:hover {
    background: #0F5B76;
}
QPushButton#dangerButton {
    color: #B42318;
}
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F7FAFB;
    border: 1px solid #D9E3E8;
    border-radius: 7px;
    gridline-color: #E8EEF1;
    selection-background-color: #D9ECF3;
    selection-color: #17384A;
}
QHeaderView::section {
    background: #EAF1F4;
    color: #294A5A;
    border: 0;
    border-right: 1px solid #D6E1E6;
    border-bottom: 1px solid #C8D7DE;
    padding: 8px 6px;
    font-weight: 600;
}
QTextBrowser, QListWidget {
    background: #FFFFFF;
    border: 1px solid #D9E3E8;
    border-radius: 7px;
}
QStatusBar {
    background: #FFFFFF;
    color: #657987;
    border-top: 1px solid #D9E3E8;
}
QLabel#pageTitle {
    color: #0B3954;
    font-size: 19pt;
    font-weight: 700;
}
QLabel#pageSubtitle {
    color: #657987;
    font-size: 10pt;
}
QLabel#sectionTitle {
    color: #0B3954;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#infoBanner {
    background: #E8F4F8;
    color: #174B61;
    border-left: 4px solid #1F8AAB;
    border-radius: 4px;
    padding: 10px;
}
QLabel#warningBanner {
    background: #FFF4DC;
    color: #704C08;
    border-left: 4px solid #D99B00;
    border-radius: 4px;
    padding: 10px;
}
QFrame#metricCard {
    background: #FFFFFF;
    border: 1px solid #D9E3E8;
    border-radius: 8px;
}
QLabel#metricLabel {
    color: #657987;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#metricValue {
    color: #0B3954;
    font-size: 20pt;
    font-weight: 700;
}
QScrollArea {
    border: 0;
    background: transparent;
}
QSplitter::handle {
    background: #D9E3E8;
}
"""
