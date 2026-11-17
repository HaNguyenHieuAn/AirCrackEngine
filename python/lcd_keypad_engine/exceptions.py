"""
Custom exceptions for LCDKeypadPyEngine.
"""

class LCDKeypadError(Exception):
    """Base exception for all LCDKeypadPyEngine errors."""
    pass


class SerialConnectionError(LCDKeypadError):
    """Raised when serial port cannot be opened or is lost."""
    pass


class ProtocolError(LCDKeypadError):
    """Raised when received packet is malformed or invalid."""
    pass


class ChecksumError(ProtocolError):
    """Raised when packet checksum does not match."""
    pass


class CommandError(LCDKeypadError):
    """Raised when Arduino returns NACK or ERROR for a command."""
    pass


class TimeoutError(LCDKeypadError):
    """Raised when waiting for Arduino response times out."""
    pass


class ButtonError(LCDKeypadError):
    """Raised when button code is unknown."""
    pass