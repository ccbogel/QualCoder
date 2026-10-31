"""Fusion themes: shared widget rendering with system, light or dark colors."""

import platform

from PyQt6 import QtGui, QtWidgets


STYLE_OPTIONS = ["native", "original", "dark"]
LEGACY_THEMES = {
    "blue": "original",
    "green": "original",
    "orange": "original",
    "purple": "original",
    "yellow": "original",
    "rainbow": "dark",
}

# Each row defines one palette role for the fixed light and dark themes.
# Fusion derives widget shapes and states from these colors, without custom QSS.
THEME_COLORS = {
    "Window": ("#efefef", "#2a2a2a"),
    "WindowText": ("#202020", "#eeeeee"),
    "Base": ("#fcfcfc", "#222222"),
    "AlternateBase": ("#eeeeee", "#303030"),
    "Text": ("#202020", "#eeeeee"),
    "Button": ("#dddddd", "#3b3b3b"),
    "ButtonText": ("#202020", "#eeeeee"),
    "BrightText": ("#ffffff", "#ffffff"),
    "Light": ("#ffffff", "#626262"),
    "Midlight": ("#eeeeee", "#484848"),
    "Mid": ("#b0b0b0", "#303030"),
    "Dark": ("#808080", "#1b1b1b"),
    "Shadow": ("#505050", "#101010"),
    "Highlight": ("#000000", "#ffffff"),
    "HighlightedText": ("#ffffff", "#202020"),
    "Link": ("#994600", "#ffb454"),
    "LinkVisited": ("#75458c", "#d8b4ef"),
    "ToolTipBase": ("#fff8e5", "#353535"),
    "ToolTipText": ("#202020", "#eeeeee"),
    "PlaceholderText": ("#666666", "#aaaaaa"),
    "Accent": ("#f89407", "#f89407"),
}


def normalize_theme(theme_name: str | int | None) -> str:
    """Migrate retired themes and fall back to system colors for unknown values."""
    if theme_name in STYLE_OPTIONS:
        return theme_name
    return LEGACY_THEMES.get(theme_name, "native")


def blend_colors(first: QtGui.QColor, second: QtGui.QColor, ratio: float) -> QtGui.QColor:
    """Blend colors, using ratio as the contribution of the first color."""
    return QtGui.QColor(*(
        round(front * ratio + back * (1 - ratio))
        for front, back in zip(first.getRgb()[:3], second.getRgb()[:3])
    ))


def theme_palette(theme_name: str, system_palette: QtGui.QPalette) -> QtGui.QPalette:
    """Build a palette without changing widget geometry.

    Args:
        theme_name: Selected theme, including legacy names.
        system_palette: Unmodified application palette used by the native theme.
    """
    theme_name = normalize_theme(theme_name)
    palette = QtGui.QPalette(system_palette)
    roles = QtGui.QPalette.ColorRole
    groups = QtGui.QPalette.ColorGroup
    if theme_name == "native":
        # Retain the system's text, accent, selection and disabled colors.
        for group in (groups.Active, groups.Inactive, groups.Disabled):
            palette.setColor(group, roles.AlternateBase, blend_colors(
                palette.color(group, roles.Base), palette.color(group, roles.Text), 0.95))
            if platform.system() == "Darwin":
                # macOS can supply unreadable tooltip colors with Fusion.
                dark_background = palette_is_dark(palette)
                palette.setColor(group, roles.ToolTipBase, QtGui.QColor(
                    "#2b2b2b" if dark_background else "#f7f7f7"))
                palette.setColor(group, roles.ToolTipText, QtGui.QColor(
                    "#ffffff" if dark_background else "#000000"))
        return palette

    color_index = 1 if theme_name == "dark" else 0
    for role_name, colors in THEME_COLORS.items():
        role = getattr(roles, role_name, None)
        if role is not None:  # Accent is unavailable in older Qt versions.
            palette.setColor(role, QtGui.QColor(colors[color_index]))

    disabled_text = QtGui.QColor("#767676" if theme_name == "original" else "#929292")
    for role in (roles.Text, roles.WindowText, roles.ButtonText, roles.PlaceholderText,
                 roles.ToolTipText, roles.Link, roles.LinkVisited):
        palette.setColor(groups.Disabled, role, disabled_text)
    palette.setColor(groups.Disabled, roles.Highlight, palette.color(roles.AlternateBase))
    palette.setColor(groups.Disabled, roles.HighlightedText, disabled_text)
    return palette


def palette_is_dark(palette: QtGui.QPalette | None = None) -> bool:
    """Return whether the actual content background is dark."""
    if palette is None:
        palette = QtWidgets.QApplication.instance().palette()
    return palette.color(QtGui.QPalette.ColorRole.Base).lightness() < 128
