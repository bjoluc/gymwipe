"""
The packets module provides classes for network packet representation.
"""
from typing import Any
from enum import Enum

class Packet():
    """
    The Packet class represents packets.
    A Packet consists of a header and a payload.
    Packets can be nested by providing them as payloads to the packet constructor.
    The packet's __str__ method concatenates the results of the __str__ methods of header and payload, devided by a newline character.
    """

    def __init__(self, header: Any, payload: Any):
        """
        Args:
            header: The object to be used as the Packet's header. Might be a String.
            payload: The object to be used as the Packet's payload. Might be a String or another Packet.
        """
        self.header = header
        self.payload = payload

    def __str__(self):
        """
        Returns the concatenatenation of the results of the __str__ methods of header and payload, divided by a newline character.
        """
        return str(self.header) + '\n' + str(self.payload)

class Signal(Enum):
    """
    A base enumeration class used for the exchange of arbitrary signals between components
    """

class CtrlSignal(Signal):
    """
    An enumeration of control signals to be exchanged between components
    """
