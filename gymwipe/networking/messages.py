"""
The messages module provides classes for network packet representation.
"""
from typing import Any, Dict
from enum import Enum

class Transmittable:
    """
    The :class:`Transmittable` class provides a :meth:`byteSize` method allowing
    objects of it to be nested in packets and sent via a channel.
    Unless for representing simple objects such as strings, it should be subclassed and both the
    :meth:`byteSize` and the :meth:`__str__` method should be overridden.
    """

    def __init__(self, obj: Any):
        """
        The constructor takes any object and creates a
        :class:`Transmittable` with the byte length of its UTF-8 string representation.
        
        Args:
            obj: The object of which the string representation will be used
        """
        self._str = str(obj)
        self._size = len(self._str.encode("utf-8"))
    
    def __str__(self):
        return self._str

    def byteSize(self):
        """
        int: The number of bytes that are to be transmitted when
            the data represented by this object is sent via a physical channel
        """
        return self._size


class Packet(Transmittable):
    """
    The Packet class represents packets.
    A Packet consists of a header and a payload.
    Packets can be nested by providing them as payloads to the packet constructor.

    .. force documenting the __str__ function
    .. automethod:: __str__
    """

    def __init__(self, header: Transmittable, payload: Transmittable):
        """
        Args:
            header: The :class:`Transmittable` to be used as the Packet's header.
            payload: The :class:`Transmittable` to be used as the Packet's payload. Might be another Packet.
        """
        self.header = header
        self.payload = payload

    def __str__(self):
        """
        Returns the concatenatenation of ``str(header)`` and ``str(payload)``, divided by a newline character.
        """
        return str(self.header) + '\n' + str(self.payload)
    
    def byteSize(self):
        return self.header.byteSize() + self.payload.byteSize()

class SimpleMACHeader(Transmittable):
    """
    A class for representing MAC packet headers
    """

    def __init__(self, fromMAC: bytes, toMAC: bytes, flag: bytes):
        if len(fromMAC) != 6:
            raise ValueError("fromMAC: Expected 6 bytes, got %n", len(fromMAC))
        if len(toMAC) != 6:
            raise ValueError("toMAC: Expected 6 bytes, got %n", len(toMAC))
        if len(flag) != 1:
            raise ValueError("flag: Expected 1 byte, got %n", len(flag))
        self.fromMAC = fromMAC #:bytes: The 6 bytes long source MAC address
        self.toMAC = toMAC #:bytes: The 6 bytes long destination MAC address
        self.flag = flag #:bytes: A single byte flag for additional data

    def byteSize():
        return 13
        

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

class StackSignals(Enum):
    """
    An enumeration of control signal types to be used for
    the exchange of `Signal` objects between network stack layers.
    """
    RECEIVE = 0
    SEND = 1
