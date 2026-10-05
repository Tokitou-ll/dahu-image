"""界面样式。纸色底、墨色侧栏、朱红色作为强调。"""

STYLES = """
QWidget {
    color: #1e2430;
    font-size: 13px;
}
QWidget#root {
    background: #f3f0e8;
}
QMainWindow, QWidget#root, QWidget#page {
    background: #f3f0e8;
}
QWidget#sidebar {
    background: #1e2430;
}
QLabel#sideTitle {
    color: #f7f1e6;
    font-size: 22px;
    font-weight: 700;
}
QLabel#sideSubtitle,
QLabel#sideVersion,
QLabel#navSoon {
    color: #b7b1a6;
}
QStackedWidget#stack {
    background: #f3f0e8;
}
QFrame#card {
    background: #fffcf7;
    border: 1px solid #e6dfd2;
    border-radius: 16px;
}
QLabel#section {
    color: #8a8175;
    font-size: 12px;
    font-weight: 600;
}
QLabel#hint,
QLabel#footer,
QLabel#status {
    color: #6d675e;
}
QLabel#estimate {
    color: #1e2430;
    font-size: 15px;
    font-weight: 600;
}
QLabel#estimate[warn="true"] {
    color: #9a4d12;
}
QLabel#dropTitle {
    color: #1e2430;
    font-size: 20px;
    font-weight: 600;
}
QLabel#dropHint {
    color: #6d675e;
}
QFrame#dropZone {
    background: #faf7f1;
    border: 2px dashed #d5cbbd;
    border-radius: 16px;
}
QFrame#dropZone[hover="true"] {
    background: #fff4ee;
    border-color: #d3542f;
}
QListWidget#imageList {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget#imageList::item {
    background: transparent;
    border-radius: 10px;
    padding: 4px;
    color: #1e2430;
}
QListWidget#imageList::item:selected {
    background: #fff1ea;
    color: #1e2430;
}
QPushButton {
    background: #fffcf7;
    border: 1px solid #e0d8cb;
    border-radius: 8px;
    padding: 6px 12px;
}
QPushButton:hover {
    border-color: #d3542f;
}
QPushButton:disabled {
    color: #a79e93;
    background: #f6f2eb;
    border-color: #ebe4d8;
}
QPushButton#primary {
    background: #d3542f;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 12px 18px;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#primary:hover {
    background: #e06a45;
}
QPushButton#primary:disabled {
    background: #e7d5cc;
    color: #6a5348;
}
QPushButton#quiet {
    background: transparent;
    border: none;
    color: #d3542f;
    font-weight: 600;
    padding: 4px 2px;
}
QPushButton#quiet:hover {
    color: #e06a45;
}
QComboBox, QSpinBox, QDoubleSpinBox {
    background: #fffcf7;
    border: 1px solid #e0d8cb;
    border-radius: 8px;
    padding: 6px 8px;
    min-height: 22px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #d3542f;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #e6dfd2;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #e7a08c;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    margin: -6px 0;
    background: #d3542f;
    border-radius: 8px;
}
QCheckBox {
    spacing: 8px;
}
QProgressBar {
    background: #f3eee6;
    border: none;
    border-radius: 6px;
    min-height: 8px;
    max-height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #d3542f;
    border-radius: 6px;
}
QSplitter::handle {
    background: transparent;
}
QScrollArea {
    background: transparent;
    border: none;
}
QPushButton#navCurrent,
QPushButton#navItem {
    border: none;
    border-radius: 8px;
    padding: 10px 12px;
    font-weight: 600;
    text-align: left;
}
QPushButton#navCurrent {
    color: #f7f1e6;
    background: #d3542f;
}
QPushButton#navCurrent:hover {
    color: #f7f1e6;
    background: #e06a45;
}
QPushButton#navItem {
    color: #b7b1a6;
    background: transparent;
}
QPushButton#navItem:hover {
    color: #f7f1e6;
    background: #2a3140;
}
"""
