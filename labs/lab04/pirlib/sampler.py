

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
        if self._stub:
            # Stub always returns False; replace with simulation logic if needed
            return False
        return bool(GPIO.input(self.pin))

    def cleanup(self):
        if not self._stub:
            GPIO.cleanup()