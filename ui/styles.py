"""Application themes — modern dark and light mode."""

from dataclasses import dataclass

PROCESS_COLORS = [
    "#4C6EF5", "#E8644A", "#40C057", "#FAB005", "#9B59B6",
    "#1ABC9C", "#E67E22", "#3498DB", "#E74C3C", "#2ECC71",
    "#F39C12", "#8E44AD", "#16A085", "#D35400", "#2980B9",
    "#C0392B", "#27AE60", "#F1C40F", "#7D3C98", "#148F77",
]

IDLE_COLOR = "#ADB5BD"
OFFLINE_COLOR = "#6C757D"


def color_for_process(process_name: str) -> str:
    h = hash(process_name.lower())
    return PROCESS_COLORS[h % len(PROCESS_COLORS)]


@dataclass
class Theme:
    name: str
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_input: str
    bg_card: str
    border: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    accent_light: str
    selection_bg: str
    hover_bg: str
    success: str
    warning: str
    danger: str
    scrollbar_bg: str
    scrollbar_handle: str
    now_line: str
    shadow: str
    # Memory aid specific
    slot_even: str
    slot_odd: str
    slot_hover: str
    # Time entries
    entry_bg: str


DARK = Theme(
    name="dark",
    bg_primary="#1A1B1E",
    bg_secondary="#25262B",
    bg_tertiary="#2C2E33",
    bg_input="#2C2E33",
    bg_card="#2C2E33",
    border="#373A40",
    border_subtle="#2C2E33",
    text_primary="#E4E5E7",
    text_secondary="#A6A7AB",
    text_muted="#5C5F66",
    accent="#4C6EF5",
    accent_hover="#5C7CFF",
    accent_text="#FFFFFF",
    accent_light="#4C6EF520",
    selection_bg="#4C6EF540",
    hover_bg="#2C2E33",
    success="#40C057",
    warning="#FAB005",
    danger="#FA5252",
    scrollbar_bg="#1A1B1E",
    scrollbar_handle="#373A40",
    now_line="#FA5252",
    shadow="rgba(0,0,0,0.3)",
    slot_even="#1A1B1E",
    slot_odd="#1F2023",
    slot_hover="#25262B",
    entry_bg="#1A1B1E",
)

LIGHT = Theme(
    name="light",
    bg_primary="#FFFFFF",
    bg_secondary="#F8F9FA",
    bg_tertiary="#F1F3F5",
    bg_input="#FFFFFF",
    bg_card="#FFFFFF",
    border="#E9ECEF",
    border_subtle="#F1F3F5",
    text_primary="#212529",
    text_secondary="#495057",
    text_muted="#ADB5BD",
    accent="#4C6EF5",
    accent_hover="#3B5BDB",
    accent_text="#FFFFFF",
    accent_light="#EDF2FF",
    selection_bg="#4C6EF520",
    hover_bg="#F8F9FA",
    success="#40C057",
    warning="#FAB005",
    danger="#FA5252",
    scrollbar_bg="#F8F9FA",
    scrollbar_handle="#CED4DA",
    now_line="#FA5252",
    shadow="rgba(0,0,0,0.06)",
    slot_even="#FFFFFF",
    slot_odd="#F8F9FA",
    slot_hover="#EDF2FF",
    entry_bg="#F8F9FA",
)

THEMES = {"dark": DARK, "light": LIGHT}
_current_theme: Theme = DARK


def get_theme() -> Theme:
    return _current_theme


def set_theme(name: str):
    global _current_theme
    _current_theme = THEMES.get(name, DARK)


def build_stylesheet(t: Theme) -> str:
    return f"""
* {{
    font-family: "Segoe UI", system-ui, sans-serif;
}}
QMainWindow, QDialog, QWidget {{
    background-color: {t.bg_primary};
    color: {t.text_primary};
}}
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {t.border};
}}
QTabBar::tab {{
    background: transparent;
    color: {t.text_secondary};
    padding: 10px 24px;
    border: none;
    border-bottom: 3px solid transparent;
    font-size: 13px;
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {t.text_primary};
    background: {t.hover_bg};
}}
QTabBar::tab:selected {{
    color: {t.accent};
    border-bottom: 3px solid {t.accent};
}}
QPushButton {{
    background: {t.bg_tertiary};
    color: {t.text_primary};
    border: 1px solid {t.border};
    padding: 7px 18px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {t.hover_bg};
    border-color: {t.accent};
}}
QPushButton#primary {{
    background: {t.accent};
    color: {t.accent_text};
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {t.accent_hover};
}}
QTableView, QTableWidget {{
    background: {t.bg_primary};
    alternate-background-color: {t.bg_secondary};
    gridline-color: {t.border_subtle};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
    border: 1px solid {t.border};
    border-radius: 8px;
}}
QHeaderView::section {{
    background: {t.bg_secondary};
    color: {t.text_secondary};
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {t.border};
    font-weight: 600;
    font-size: 11px;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background: {t.bg_input};
    color: {t.text_primary};
    border: 1px solid {t.border};
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {t.accent};
}}
QComboBox QAbstractItemView {{
    background: {t.bg_secondary};
    color: {t.text_primary};
    border: 1px solid {t.border};
    selection-background-color: {t.accent};
}}
QScrollBar:vertical {{
    background: {t.scrollbar_bg};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {t.scrollbar_handle};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{ height: 0; }}
QMenu {{
    background: {t.bg_card};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {t.accent};
    color: {t.accent_text};
}}
QToolTip {{
    background: {t.bg_card};
    color: {t.text_primary};
    border: 1px solid {t.border};
    padding: 6px 10px;
    border-radius: 6px;
}}
QStatusBar {{
    background: {t.bg_secondary};
    border-top: 1px solid {t.border};
}}
QScrollArea {{ border: none; }}
"""
