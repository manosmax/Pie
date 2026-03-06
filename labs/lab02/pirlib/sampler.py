from gpiozero import DigitalInputDevice

class PirSampler:
    """
    Hardware interface for the lab's PIR motion sensor.


    Used for only reading the raw GPIO signal HIGH OR LOW.
    Rest is handled by interpreter.
    """

    def __init__(self, pin: int):
        """
        Initialization
        """
        self.pin = pin
        self.dev = DigitalInputDevice(pin)

    def read(self) -> bool:
        """
        Read Current Sensor State.

        Returns:bool True (HIGH), False (LOW)
        """
        return bool(self.dev.value)

    def read_raw(self) -> int:
        """Return raw GPIO value (0 or 1)."""
        return self.dev.value

    def close(self):
        """Release the GPIO device."""
        self.dev.close()