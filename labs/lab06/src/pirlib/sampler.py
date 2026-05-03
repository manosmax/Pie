try:
    import lgpio
    _handle = lgpio.gpiochip_open(0)
    _GPIO_AVAILABLE = True
except Exception:
    _handle = None
    _GPIO_AVAILABLE = False

class PirSampler:
    def __init__(self, pin: int):
        self.pin = pin
        self._stub = not _GPIO_AVAILABLE
        if not self._stub:
            lgpio.gpio_claim_input(_handle, self.pin)

    def read(self) -> bool:
        if self._stub:
            return False
        return bool(lgpio.gpio_read(_handle, self.pin))

    def cleanup(self):
        if not self._stub:
            lgpio.gpiochip_close(_handle)