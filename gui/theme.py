"""
gui/theme.py — zentrales Dark-Theme für die gesamte Anwendung.

Alle Farben, Abstände und Steuerelement-Größen stehen hier an einer Stelle.
Widgets sollen keine eigenen Farben mehr hart setzen, sondern entweder vom
globalen Stylesheet profitieren oder die Konstanten von hier importieren
(z. B. für Statusfarben, die sich zur Laufzeit ändern).

Anwendung beim Start:

    from gui.theme import apply_theme
    app = QApplication(sys.argv)
    apply_theme(app)
"""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

# ── Farben ───────────────────────────────────────────────────────────
BG_WINDOW   = "#16191d"   # Fensterhintergrund
BG_SIDEBAR  = "#1a1e23"   # Seitenleiste
BG_PANEL    = "#1e2228"   # Gruppen/Karten
BG_CONTROL  = "#262b32"   # Eingabefelder, Buttons
BG_HOVER    = "#2f353d"
BG_PLOT     = "#12151a"   # Plot-Flächen

BORDER        = "#333a43"
BORDER_STRONG = "#3a424c"

TEXT_PRIMARY   = "#e6e9ed"
TEXT_SECONDARY = "#98a2ae"
TEXT_MUTED     = "#7d8794"
TEXT_DISABLED  = "#5b636d"

ACCENT     = "#4a9eff"
ACCENT_ON  = "#07203c"   # Text auf Accent-Flächen
ACCENT_DIM = "#3d84d8"

SUCCESS = "#3ddc84"
WARNING = "#ffa726"
DANGER  = "#ef5350"

# Kanalfarben für die EEG-Kurven (auf dunklem Grund abgestimmt)
CHANNEL_COLORS = ["#4a9eff", "#3ddc84", "#e5a8f0", "#ffa726",
                  "#8b7cf6", "#42d4f4", "#f97b8b", "#bfef45"]

# ── Maße ─────────────────────────────────────────────────────────────
CONTROL_HEIGHT = 36
RADIUS         = 6
SIDEBAR_WIDTH  = 300


def status_color(state: str) -> str:
    """Einheitliche Statusfarben: off | running | ok | error"""
    return {
        "off":     TEXT_MUTED,
        "running": WARNING,
        "ok":      SUCCESS,
        "error":   DANGER,
    }.get(state, TEXT_MUTED)


STYLESHEET = f"""
QWidget {{
    background: {BG_WINDOW};
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background: {BG_WINDOW};
}}

QLabel {{
    background: transparent;
    color: {TEXT_PRIMARY};
}}

QLabel[role="caption"] {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

QLabel[role="secondary"] {{
    color: {TEXT_SECONDARY};
}}

/* ── Gruppen ─────────────────────────────────────────────────── */
QGroupBox {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS + 2}px;
    margin-top: 14px;
    padding: 10px;
    font-size: 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_MUTED};
}}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {{
    background: {BG_CONTROL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS}px;
    min-height: {CONTROL_HEIGHT}px;
    padding: 0 12px;
    text-align: center;
}}

QPushButton:hover:enabled {{
    background: {BG_HOVER};
    border-color: {TEXT_MUTED};
}}

QPushButton:pressed:enabled {{
    background: {BORDER};
}}

QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BORDER};
    background: {BG_PANEL};
}}

QPushButton[variant="primary"] {{
    background: {ACCENT};
    color: {ACCENT_ON};
    border: none;
}}

QPushButton[variant="primary"]:hover:enabled {{
    background: {ACCENT_DIM};
}}

QPushButton[variant="primary"]:disabled {{
    background: {BG_PANEL};
    color: {TEXT_DISABLED};
}}

QPushButton[variant="compact"] {{
    min-height: 28px;
    padding: 0 8px;
    font-size: 12px;
}}

/* ── Eingaben ────────────────────────────────────────────────── */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {BG_CONTROL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS}px;
    min-height: {CONTROL_HEIGHT - 4}px;
    padding: 0 8px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}

QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox QAbstractItemView {{
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_ON};
}}

QTextEdit {{
    background: {BG_PLOT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 6px;
}}

/* ── Checkboxen ──────────────────────────────────────────────── */
QCheckBox {{
    background: transparent;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background: {BG_CONTROL};
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Slider ──────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {TEXT_PRIMARY};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* ── Tabs ────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {BG_WINDOW};
}}

QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}}

QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT};
}}

QTabBar::tab:hover:!selected {{
    color: {TEXT_SECONDARY};
}}

/* ── Scrollbars ──────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}

QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0;
}}

/* ── Splitter ────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {BORDER};
}}

QSplitter::handle:hover {{
    background: {ACCENT};
}}

QToolTip {{
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_STRONG};
    padding: 4px;
}}
"""


def _build_palette() -> QPalette:
    """QPalette sorgt dafür, dass auch native Elemente (Menüs, Scrollbars,
    Tooltips) dem dunklen Schema folgen, statt hell zu bleiben."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(BG_WINDOW))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Base,            QColor(BG_CONTROL))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_PANEL))
    p.setColor(QPalette.ColorRole.Text,            QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Button,          QColor(BG_CONTROL))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_ON))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(BG_PANEL))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text, QColor(TEXT_DISABLED))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText, QColor(TEXT_DISABLED))
    return p


def apply_theme(app: QApplication):
    """Dark-Theme auf die gesamte Anwendung anwenden."""
    app.setStyle("Fusion")
    app.setPalette(_build_palette())
    app.setStyleSheet(STYLESHEET)

    # pyqtgraph hat eigene Hintergrundfarben und folgt dem Qt-Stylesheet nicht
    try:
        import pyqtgraph as pg
        pg.setConfigOption("background", BG_PLOT)
        pg.setConfigOption("foreground", TEXT_SECONDARY)
        pg.setConfigOption("antialias", True)
    except ImportError:
        pass
