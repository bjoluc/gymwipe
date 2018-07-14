"""
The messages module provides classes for network packet representation.
"""
from typing import Any, Dict
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

class Signal:
    """
    A class used for the exchange of arbitrary signals between components.

    Attributes:
        type(Enum): An enumeration object that defines the signal type
        properties(Dict[str, Any]): A dictionary containing additional signal properties
    """

    def __init__(self, type: Enum, properties: Dict[str, Any] = None):
        self.type = type
        self.properties = properties

class PhySignals(Enum):
    """
    An enumeration of control signal types to be used for `Signal` objects sent to a Phy layer.
    """
    RECEIVE = 0
    """
    Sense the channel for transmissions and output any successfully received message via the `mac` gate.
    """

    SEND = 1
    """
    Send a specified message via the channel.
    """
