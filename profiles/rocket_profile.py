from typing import Dict, List

from .label import TYPE_CHECKING, Label
from connections.sim.hw_sim import HWSim

if TYPE_CHECKING:
    from main_window.main import MainApp


class RocketProfile:
    def __init__(
        self, buttons: Dict[str, str], labels: List[Label], hw_sim_dat: HWSim = None
    ):
        self.buttons = buttons
        self.labels = labels
        self.hw_sim_dat = hw_sim_dat

    def update_labels(self, main_window: "MainApp") -> None:
        for label in self.labels:
            getattr(main_window, label.name + "Label").setText(
                label.update(main_window)
            )
