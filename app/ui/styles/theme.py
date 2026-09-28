"""
Dark industrial theme — QSS stylesheet generator.
Colors: dark grays, muted blue accent, minimal palette.
"""
from __future__ import annotations

_PRIMARY = "#3B82F6"
_PRIMARY_HOVER = "#2563EB"
_PRIMARY_PRESSED = "#1D4ED8"
_BG_DARK = "#0F1117"
_BG_PANEL = "#1A1D27"
_BG_CARD = "#21242F"
_BG_INPUT = "#2A2D3A"
_BORDER = "#2E3140"
_BORDER_FOCUS = "#3B82F6"
_TEXT = "#E2E8F0"
_TEXT_DIM = "#8892A4"
_TEXT_BRIGHT = "#FFFFFF"
_DANGER = "#EF4444"
_SUCCESS = "#22C55E"
_WARNING = "#F59E0B"
_SCROLLBAR_BG = "#1A1D27"
_SCROLLBAR_HANDLE = "#3A3D4A"

_RADIUS_SM = "4px"
_RADIUS_MD = "6px"
_RADIUS_LG = "8px"


def generate_dark_theme() -> str:
    """Returns the complete dark theme QSS string."""
    return f"""
    /* ── Global ─────────────────────────────────────── */
    * {{
        font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
        font-size: 13px;
        color: {_TEXT};
        outline: none;
    }}
    QWidget {{
        background-color: {_BG_DARK};
    }}

    /* ── Main Window ────────────────────────────────── */
    QMainWindow {{
        background-color: {_BG_DARK};
    }}

    /* ── Panels ─────────────────────────────────────── */
    QWidget#sidebar {{
        background-color: {_BG_PANEL};
        border-right: 1px solid {_BORDER};
    }}
    QWidget#toolbar {{
        background-color: {_BG_PANEL};
        border-bottom: 1px solid {_BORDER};
    }}
    QWidget#statusbar {{
        background-color: {_BG_PANEL};
        border-top: 1px solid {_BORDER};
    }}
    QWidget#workspace {{
        background-color: {_BG_DARK};
    }}

    /* ── Buttons ────────────────────────────────────── */
    QPushButton {{
        background-color: {_BG_CARD};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_MD};
        padding: 6px 14px;
        color: {_TEXT};
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {_BG_INPUT};
        border-color: {_PRIMARY};
    }}
    QPushButton:pressed {{
        background-color: {_PRIMARY_PRESSED};
        border-color: {_PRIMARY};
    }}
    QPushButton:disabled {{
        background-color: {_BG_CARD};
        color: {_TEXT_DIM};
        border-color: {_BORDER};
    }}
    QPushButton#accent {{
        background-color: {_PRIMARY};
        border: 1px solid {_PRIMARY};
        color: {_TEXT_BRIGHT};
        font-weight: 600;
    }}
    QPushButton#accent:hover {{
        background-color: {_PRIMARY_HOVER};
    }}
    QPushButton#accent:pressed {{
        background-color: {_PRIMARY_PRESSED};
    }}
    QPushButton#danger {{
        background-color: transparent;
        border: 1px solid {_DANGER};
        color: {_DANGER};
    }}
    QPushButton#danger:hover {{
        background-color: {_DANGER};
        color: {_TEXT_BRIGHT};
    }}
    QPushButton#iconButton {{
        background-color: transparent;
        border: none;
        border-radius: {_RADIUS_SM};
        padding: 6px;
    }}
    QPushButton#iconButton:hover {{
        background-color: {_BG_CARD};
    }}

    /* ── Line Edit / Search ─────────────────────────── */
    QLineEdit {{
        background-color: {_BG_INPUT};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_MD};
        padding: 6px 10px;
        color: {_TEXT};
        selection-background-color: {_PRIMARY};
    }}
    QLineEdit:focus {{
        border-color: {_BORDER_FOCUS};
    }}
    QLineEdit::placeholder {{
        color: {_TEXT_DIM};
    }}

    /* ── Combo Box ──────────────────────────────────── */
    QComboBox {{
        background-color: {_BG_INPUT};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_MD};
        padding: 5px 10px;
        color: {_TEXT};
        min-height: 20px;
    }}
    QComboBox:hover {{
        border-color: {_PRIMARY};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {_BG_PANEL};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_MD};
        selection-background-color: {_PRIMARY};
        selection-color: {_TEXT_BRIGHT};
        padding: 4px;
    }}

    /* ── Tree View ──────────────────────────────────── */
    QTreeView {{
        background-color: transparent;
        border: none;
        padding: 4px;
        outline: none;
    }}
    QTreeView::item {{
        padding: 4px 6px;
        border-radius: {_RADIUS_SM};
    }}
    QTreeView::item:hover {{
        background-color: {_BG_CARD};
    }}
    QTreeView::item:selected {{
        background-color: {_PRIMARY};
        color: {_TEXT_BRIGHT};
    }}
    QTreeView::branch {{
        background-color: transparent;
    }}
    QTreeView::branch:has-children:closed {{
        border-image: none;
    }}
    QTreeView::branch:has-children:open {{
        border-image: none;
    }}

    /* ── Scroll Bar ─────────────────────────────────── */
    QScrollBar:vertical {{
        background: {_SCROLLBAR_BG};
        width: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {_SCROLLBAR_HANDLE};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {_TEXT_DIM};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background: {_SCROLLBAR_BG};
        height: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {_SCROLLBAR_HANDLE};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {_TEXT_DIM};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── Menu ───────────────────────────────────────── */
    QMenu {{
        background-color: {_BG_PANEL};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_MD};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 12px;
        border-radius: {_RADIUS_SM};
    }}
    QMenu::item:selected {{
        background-color: {_PRIMARY};
        color: {_TEXT_BRIGHT};
    }}
    QMenu::separator {{
        height: 1px;
        background: {_BORDER};
        margin: 4px 8px;
    }}

    /* ── Tooltip ────────────────────────────────────── */
    QToolTip {{
        background-color: {_BG_CARD};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_SM};
        padding: 6px 10px;
        color: {_TEXT};
    }}

    /* ── Tab Widget ─────────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_MD};
        background-color: {_BG_PANEL};
    }}
    QTabBar::tab {{
        background-color: {_BG_CARD};
        border: 1px solid {_BORDER};
        border-bottom: none;
        border-top-left-radius: {_RADIUS_MD};
        border-top-right-radius: {_RADIUS_MD};
        padding: 6px 16px;
        margin-right: 2px;
        color: {_TEXT_DIM};
    }}
    QTabBar::tab:selected {{
        background-color: {_BG_PANEL};
        color: {_TEXT};
        border-bottom: 2px solid {_PRIMARY};
    }}

    /* ── Status Label ───────────────────────────────── */
    QLabel#statusOnline {{
        color: {_SUCCESS};
    }}
    QLabel#statusOffline {{
        color: {_DANGER};
    }}
    QLabel#statusWarning {{
        color: {_WARNING};
    }}

    /* ── Splitter ───────────────────────────────────── */
    QSplitter::handle {{
        background-color: {_BORDER};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* ── Frame / Card ───────────────────────────────── */
    QFrame#card {{
        background-color: {_BG_CARD};
        border: 1px solid {_BORDER};
        border-radius: {_RADIUS_LG};
    }}
    QFrame#card:hover {{
        border-color: {_PRIMARY};
    }}
    """
