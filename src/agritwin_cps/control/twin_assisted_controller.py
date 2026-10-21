"""Same hysteresis as baseline; estimated state and bounded prediction horizon replace readings."""

from agritwin_cps.control.threshold_controller import ThresholdController


class TwinAssistedController(ThresholdController):
    @property
    def max_age(self) -> int:
        return self.config.max_prediction_age_steps
