"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/


Look layer for QualCoder.

One stylesheet appended after the chosen colour theme, plus a proxy style
that tags widgets when Qt first styles them. Translucent colours only, so a
look sits on top of any theme. It keys on conventions the .ui files already
follow, so no .ui file needs to change:

    QPushButton[iconOnly="true"]   icon-only buttons in the tool strips
    QGroupBox[toolStrip="true"]    untitled group boxes used as tool strips

Setting: ui_look = classic | modern | soft | aurora
"""

from pathlib import Path

import re

from PyQt6 import QtCore, QtGui, QtWidgets

# labels the dark theme paints grey by id, kept transparent here
THEME_PAINTED_LABELS = [
    "label_search_regex", "label_search_case_sensitive", "label_search_all_files",
    "label_font_size", "label_search_all_journals", "label_exports", "label_time_3",
    "label_volume",
]

CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
    '<path d="M3 7.5 L6 10.5 L11 4" fill="none" stroke="@color@" stroke-width="2.2" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
DOT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
    '<circle cx="7" cy="7" r="3.5" fill="@color@"/></svg>'
)
CHEVRON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
    '<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="@color@" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
CHEVRON_UP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
    '<path d="M2.5 7.5 L6 4 L9.5 7.5" fill="none" stroke="@color@" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

GREY = "rgba(127, 127, 127, %s)"

# Each look only sets these tokens; the stylesheet template below is shared.
# Keep a radius under half the control height, Qt draws square corners otherwise.
LOOKS = {
    "modern": {
        "gap": 6, "icon": 20,
        "r_button": 8, "r_strip": 12, "r_field": 8, "r_area": 6, "r_tab": 8,
        "strip_bg": GREY % 0.10,
        "hover": GREY % 0.22, "pressed": GREY % 0.36, "checked": GREY % 0.30,
        "focus": "rgba(46, 134, 222, 0.85)", "accent": "rgba(46, 134, 222, 0.65)",
        "fill": GREY % 0.14, "fill_disabled": GREY % 0.06,
        "border": GREY % 0.40, "border_soft": GREY % 0.30,
        "tab_sel": GREY % 0.26, "tab_hover": GREY % 0.14,
        "tab_pad": "5px 12px",
        "scroll_w": 10, "scroll_bg": GREY % 0.45, "scroll_hover": GREY % 0.70,
        "mark": "#333333", "chevron": "#8a8a8a",
        "extra": "",
    },
    "soft": {
        "gap": 8, "icon": 20,
        "r_button": 12, "r_strip": 14, "r_field": 11, "r_area": 12, "r_tab": 11,
        "strip_bg": ("qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                     "stop:0 rgba(127, 127, 127, 0.16), stop:1 rgba(127, 127, 127, 0.06))"),
        "hover": GREY % 0.18, "pressed": GREY % 0.30, "checked": GREY % 0.26,
        "focus": "rgba(90, 160, 200, 0.80)", "accent": "rgba(90, 160, 200, 0.60)",
        "fill": GREY % 0.12, "fill_disabled": GREY % 0.05,
        "border": GREY % 0.28, "border_soft": GREY % 0.20,
        "tab_sel": GREY % 0.22, "tab_hover": GREY % 0.12,
        "tab_pad": "6px 16px",
        "scroll_w": 8, "scroll_bg": GREY % 0.35, "scroll_hover": GREY % 0.60,
        "mark": "#444444", "chevron": "#9a9a9a",
        "extra": """
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 3px 10px; }
QPushButton[iconOnly="true"], QToolButton { padding: 2px; }
""",
    },
    "aurora": {
        "gap": 6, "icon": 20,
        "r_button": 10, "r_strip": 14, "r_field": 10, "r_area": 8, "r_tab": 10,
        "strip_bg": ("qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                     "stop:0 rgba(120, 80, 255, 0.16), stop:0.5 rgba(60, 140, 240, 0.12), "
                     "stop:1 rgba(0, 200, 180, 0.16))"),
        "hover": "rgba(120, 80, 255, 0.26)", "pressed": "rgba(120, 80, 255, 0.40)",
        "checked": "rgba(0, 200, 180, 0.34)",
        "focus": "rgba(150, 110, 255, 0.95)", "accent": "rgba(120, 80, 255, 0.60)",
        "fill": "rgba(120, 80, 255, 0.10)", "fill_disabled": GREY % 0.05,
        "border": "rgba(120, 100, 220, 0.42)", "border_soft": "rgba(120, 100, 220, 0.30)",
        "tab_sel": ("qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                    "stop:0 rgba(120, 80, 255, 0.34), stop:1 rgba(0, 200, 180, 0.34))"),
        "tab_hover": "rgba(120, 80, 255, 0.16)",
        "tab_pad": "5px 14px",
        "scroll_w": 10, "scroll_bg": "rgba(120, 110, 220, 0.50)", "scroll_hover": "rgba(0, 200, 180, 0.80)",
        "mark": "#6a4cff", "chevron": "#8a78e0",
        "extra": """
QSplitter::handle:horizontal:hover, QSplitter::handle:vertical:hover,
QSplitter::handle:pressed { background: rgba(0, 200, 180, 0.60); }
""",
    },
}
LOOK_OPTIONS = ["classic"] + list(LOOKS)

TEMPLATE = """
/* ---- icon buttons: flat, rounded, highlight on hover ---- */
QPushButton[iconOnly="true"], QToolButton {
    border: 1px solid transparent;
    border-radius: @r_button@px;
    background: transparent;
    padding: 1px;
    icon-size: @icon@px;
}
QPushButton[iconOnly="true"]:hover, QToolButton:hover { background: @hover@; }
QPushButton[iconOnly="true"]:pressed, QToolButton:pressed { background: @pressed@; }
QPushButton[iconOnly="true"]:checked, QToolButton:checked { background: @checked@; }
QPushButton[iconOnly="true"]:focus, QToolButton:focus { border: 1px solid @focus@; }
QPushButton[iconOnly="true"]:disabled, QToolButton:disabled { background: transparent; }

QPushButton[iconOnly="true"][bigIcon="true"], QToolButton[bigIcon="true"] { icon-size: 32px; }

/* ---- text buttons: same rounding, light fill ---- */
QPushButton {
    border: 1px solid @border@;
    border-radius: @r_field@px;
    background: @fill@;
    padding: 3px 10px;
}
QPushButton:hover { background: @hover@; border: 1px solid @border@; }
QPushButton:pressed { background: @pressed@; border: 1px solid @border@; }
QPushButton:focus { border: 1px solid @focus@; }
QPushButton:default { border: 1px solid @focus@; }
QPushButton:disabled { background: @fill_disabled@; border: 1px solid @border_soft@; }
QPushButton[compact="true"] { padding: 0px 2px; }

/* ---- titled group boxes ---- */
QGroupBox {
    border: 1px solid @border_soft@;
    border-radius: @r_area@px;
    background: transparent;
    margin-top: 18px;
    padding-top: 4px;
}
QGroupBox:focus { border: 1px solid @border_soft@; }
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: 2px;
    padding: 0px 4px;
    background: transparent;
}

/* ---- separator lines from the .ui files: ModernStyle draws them centred ---- */
QFrame[separator="h"], QFrame[separator="v"] { background: transparent; }

/* ---- untitled group boxes are the tool strips ---- */
QGroupBox[toolStrip="true"] {
    border: none;
    border-radius: @r_strip@px;
    background: @strip_bg@;
    margin-top: 0px;
    padding: 0px;
}
QGroupBox[toolStrip="true"]:focus { border: none; }

/* ---- fields ---- */
QLineEdit, QSpinBox, QDoubleSpinBox {
    border: 1px solid @border@;
    border-radius: @r_field@px;
    padding: 2px 6px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid @focus@; }
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    border: none;
    background: transparent;
    width: 16px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("@img_chevron_up@"); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("@img_chevron@"); width: 10px; height: 10px; }
QComboBox {
    border: 1px solid @border@;
    border-radius: @r_field@px;
    padding: 2px 24px 2px 6px;
}
QComboBox:hover { border: 1px solid @border@; background: @hover@; }
QComboBox:focus { border: 1px solid @focus@; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow { image: url("@img_chevron@"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { border: 1px solid @border@; }

/* ---- content areas ---- */
QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget, QTableView,
QTextEdit, QPlainTextEdit, QTextBrowser, QGraphicsView {
    border: 1px solid @border_soft@;
    border-radius: @r_area@px;
}
QListWidget:focus, QListView:focus, QTreeWidget:focus, QTreeView:focus, QTableWidget:focus, QTableView:focus,
QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QGraphicsView:focus { border: 1px solid @focus@; }
QHeaderView::section {
    border: none;
    border-right: 1px solid @border_soft@;
    border-bottom: 1px solid @border@;
    padding: 3px 6px;
}
QTableCornerButton::section {
    border: none;
    border-bottom: 1px solid @border@;
    background: transparent;
}

/* ---- tabs as pills ---- */
QTabWidget { border: none; background: transparent; }
QTabWidget:focus { border: none; }
QTabWidget::pane { border: none; }
QTabBar { border: none; background: transparent; }
QTabBar::tab, QTabBar::tab:selected, QTabBar::tab:!selected {
    border: none;
    background: transparent;
    padding: @tab_pad@;
    margin: 0px 4px 0px 0px;
    border-radius: @r_tab@px;
}
QTabBar::tab:selected { background: @tab_sel@; }
QTabBar::tab:hover { background: @tab_hover@; }

/* ---- check boxes and radio buttons: white box, coloured mark ---- */
QCheckBox, QRadioButton { background: transparent; border: 1px solid transparent; border-radius: 4px; }
QCheckBox:focus, QRadioButton:focus { border: 1px solid @focus@; }
QCheckBox::indicator, QTreeView::indicator, QListView::indicator, QTableView::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #8a8a8a;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked, QTreeView::indicator:checked,
QListView::indicator:checked, QTableView::indicator:checked {
    border: 1px solid #8a8a8a;
    background: #ffffff;
    image: url("@img_check@");
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: #d8d8d8; border-color: #b0b0b0; }
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #8a8a8a;
    border-radius: 8px;
    background: #ffffff;
}
QRadioButton::indicator:checked {
    border: 1px solid #8a8a8a;
    background: #ffffff;
    image: url("@img_dot@");
}

/* ---- progress and sliders ---- */
QProgressBar {
    border: 1px solid @border@;
    border-radius: @r_field@px;
    background: @fill@;
    text-align: center;
}
QProgressBar::chunk { border-radius: @r_field@px; background: @accent@; }
QSlider { background: transparent; border: none; }
QSlider:focus { border: none; }
QSlider::groove:horizontal { height: 4px; border-radius: 2px; background: @border@; }
QSlider::groove:vertical { width: 4px; border-radius: 2px; background: @border@; }
QSlider::sub-page:horizontal, QSlider::add-page:vertical { border-radius: 2px; background: @accent@; }
QSlider::handle:horizontal {
    width: 14px;
    margin: -6px 0px;
    border-radius: 7px;
    border: 1px solid @border@;
    background: #ffffff;
}
QSlider::handle:vertical {
    height: 14px;
    margin: 0px -6px;
    border-radius: 7px;
    border: 1px solid @border@;
    background: #ffffff;
}
QSlider::handle:horizontal:hover, QSlider::handle:vertical:hover { border: 1px solid @focus@; }

/* ---- keep containers, labels and splitters quiet under themes that paint everything ---- */
.QWidget { background: transparent; }
QLabel { background: transparent; }
@painted_labels@ { background: transparent; }
QAbstractScrollArea::corner { background: transparent; }
QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { background: transparent; border-left: 1px solid @border_soft@; margin: 8px 3px; }
QSplitter::handle:vertical { background: transparent; border-top: 1px solid @border_soft@; margin: 3px 8px; }
QSplitter::handle:hover, QSplitter::handle:horizontal:hover, QSplitter::handle:vertical:hover,
QSplitter::handle:pressed { background: transparent; border-color: @focus@; }

/* ---- thin scrollbars ---- */
QScrollBar:vertical { border: none; background: transparent; width: @scroll_w@px; margin: 0px; }
QScrollBar:horizontal { border: none; background: transparent; height: @scroll_w@px; margin: 0px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: @scroll_bg@;
    border-radius: @scroll_r@px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: @scroll_hover@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def _write_images(folder, look, tokens):
    """Write the mark images the stylesheet points at. Returns url paths."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, svg, color in (("check", CHECK_SVG, tokens["mark"]), ("dot", DOT_SVG, tokens["mark"]),
                             ("chevron", CHEVRON_SVG, tokens["chevron"]),
                             ("chevron_up", CHEVRON_UP_SVG, tokens["chevron"])):
        path = folder / f"look_{look}_{name}.svg"
        content = svg.replace("@color@", color)
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
        paths[name] = path.as_posix()
    return paths


def current_look(settings):
    """Look name from settings, classic when unset or unknown."""
    look = str(settings.get("ui_look", "modern"))
    return look if look in LOOKS else "classic"


def look_stylesheet(look, image_folder=None):
    """Build the stylesheet for a look. Empty for classic."""
    if look not in LOOKS:
        return ""
    tokens = dict(LOOKS[look])
    folder = image_folder or Path.home() / ".qualcoder"
    for name, path in _write_images(folder, look, tokens).items():
        tokens["img_" + name] = path
    tokens["scroll_r"] = tokens["scroll_w"] // 2
    tokens["painted_labels"] = ", ".join(f"QLabel#{n}" for n in THEME_PAINTED_LABELS)
    qss = TEMPLATE + tokens["extra"]
    for key, value in tokens.items():
        qss = qss.replace(f"@{key}@", str(value))
    return qss


def modern_layer(settings, image_folder=None):
    """Stylesheet layer for the look in settings. Empty for classic."""
    return look_stylesheet(current_look(settings), image_folder)


def _qcolor(rgba):
    """QColor from an rgba(r, g, b, a) string."""
    m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", rgba)
    r, g, b, a = m.groups()
    return QtGui.QColor(int(r), int(g), int(b), int(float(a) * 255))


def _center_strip_children(box, gap):
    """Give absolutely placed rows a top and bottom gap inside the strip.

    The .ui files pin the first row at y=0. Spare room is used first; a strip
    with a fixed height grows by what is missing.
    """
    if box.layout() is not None or box.property("toolStripCentered"):
        return
    kids = [c for c in box.children() if isinstance(c, QtWidgets.QWidget)]
    if not kids:
        return
    box.setProperty("toolStripCentered", True)
    top = min(c.y() for c in kids)
    bottom = max(c.y() + c.height() for c in kids)
    fixed = box.minimumHeight() == box.maximumHeight() and box.maximumHeight() < 10000
    height = box.maximumHeight() if box.maximumHeight() < 10000 else box.height()
    needed = bottom - top + 2 * gap
    if fixed and height < needed:
        box.setMinimumHeight(needed)
        box.setMaximumHeight(needed)
        height = needed
    room = height - bottom
    shift = min(gap - top, room - gap if room >= 2 * gap else room // 2)
    if shift <= 0:
        return
    for c in kids:
        c.move(c.x(), c.y() + shift)


class ModernStyle(QtWidgets.QProxyStyle):
    """Tags icon-only buttons and untitled group boxes when Qt first styles them.

    Runs once per widget at polish time, so it adds nothing to event handling.
    A button that receives text before it is shown, or a group box with a
    title, keeps the theme look.
    """

    def __init__(self, base, gap=6, line_color="rgba(127, 127, 127, 0.40)"):
        super().__init__(base)
        self.gap = gap
        self.line_color = _qcolor(line_color)

    def drawControl(self, element, option, painter, widget=None):
        if (element == QtWidgets.QStyle.ControlElement.CE_ShapedFrame and widget is not None
                and widget.property("separator")):
            r = option.rect
            painter.save()
            painter.setPen(QtGui.QPen(self.line_color, 1))
            if widget.property("separator") == "h":
                y = r.top() + r.height() // 2
                painter.drawLine(r.left() + 1, y, r.right() - 1, y)
            else:
                x = r.left() + r.width() // 2
                painter.drawLine(x, r.top() + 1, x, r.bottom() - 1)
            painter.restore()
            return
        super().drawControl(element, option, painter, widget)

    def polish(self, obj):
        if isinstance(obj, QtWidgets.QPushButton):
            if not obj.text().strip() and obj.property("iconOnly") is None:
                obj.setProperty("iconOnly", True)
                fixed = obj.minimumHeight() == obj.maximumHeight()
                if (obj.maximumHeight() if fixed else obj.height()) > 34:
                    obj.setProperty("bigIcon", True)
            elif obj.maximumWidth() <= 32 and obj.property("compact") is None:
                obj.setProperty("compact", True)
        elif isinstance(obj, QtWidgets.QGroupBox):
            if not obj.title().strip() and obj.property("toolStrip") is None:
                obj.setProperty("toolStrip", True)
                _center_strip_children(obj, self.gap)
        elif type(obj) is QtWidgets.QFrame and obj.property("separator") is None:
            shape = obj.frameShape()
            if shape == QtWidgets.QFrame.Shape.HLine:
                obj.setProperty("separator", "h")
            elif shape == QtWidgets.QFrame.Shape.VLine:
                obj.setProperty("separator", "v")
        return super().polish(obj)


def install_modern_look(app, settings, image_folder=None):
    """Append the layer once and wrap the current style. Safe to call again."""
    look = current_look(settings)
    layer = look_stylesheet(look, image_folder)
    if not layer:
        return
    if not getattr(app, "_modern_layer_installed", False):
        app.setStyleSheet(app.styleSheet() + layer)
        app._modern_layer_installed = True
    if not isinstance(app.style(), ModernStyle):
        base = QtWidgets.QStyleFactory.create(app.style().objectName())
        app.setStyle(ModernStyle(base, LOOKS[look]["gap"], LOOKS[look]["border"]))
