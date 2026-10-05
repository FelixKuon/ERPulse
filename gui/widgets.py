"""gui/widgets.py — kleine Eingabe-Widgets mit abgeschaltetem Mausrad.

Standardmäßig ändern QSpinBox/QDoubleSpinBox/QSlider ihren Wert, sobald das
Mausrad über ihnen gedreht wird — auch ohne Klick. Beim Scrollen durch die
Seitenleiste verstellt man so unbemerkt Filtergrenzen oder die Artefakt-
Schwelle. Diese Ableitungen nehmen das Rad nur an, wenn das Feld den Fokus
hat (also bewusst angeklickt wurde); sonst wird das Ereignis an die
Seitenleiste weitergereicht und scrollt dort wie erwartet.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QSlider


class _NoWheelMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Kein Fokus allein durchs Drüberrollen — nur per Klick/Tab
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()   # an die Scroll-Area weiterreichen


class NoWheelDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    pass


class NoWheelSpinBox(_NoWheelMixin, QSpinBox):
    pass


class NoWheelSlider(_NoWheelMixin, QSlider):
    pass


class NoWheelComboBox(_NoWheelMixin, QComboBox):
    pass
