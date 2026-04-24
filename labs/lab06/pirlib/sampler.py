"""
pirlib/sampler.py

Reads a single digital sample from a PIR sensor on a GPIO pin.
Falls back to a stub implementation when RPi.GPIO is not available
(e.g. during development on a non-Pi machine).
"""

try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


class PirSampler:
    """
    Manages GPIO setup for one PIR pin and exposes a read() method
    that returns True (motion) or False (no motion).
    """

    def __init__(self, pin: int):
        self.pin = pin
        self._stub = not _GPIO_AVAILABLE

        if not self._stub:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN)

    def read(self) -> bool:
        """Return the current PIR state: True = motion detected."""
        if self._stub:
            # Stub always returns False; replace with simulation logic if needed
            return False
        return bool(GPIO.input(self.pin))

    def cleanup(self):
        """Release GPIO resources. Call on shutdown."""
        if not self._stub:
            GPIO.cleanup()