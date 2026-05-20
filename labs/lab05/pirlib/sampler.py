try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


class PirSampler:


    def __init__(self, pin: int):
        self.pin = pin
        self._stub = not _GPIO_AVAILABLE

        if not self._stub:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN)

    def read(self) -> bool:
        """Return the current PIR state: True = motion detected."""
        if self._stub:

            return False
        return bool(GPIO.input(self.pin))

    def cleanup(self):
        """Release GPIO resources. Call on shutdown."""
        if not self._stub:
            GPIO.cleanup()