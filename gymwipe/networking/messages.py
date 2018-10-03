"""
The messages module provides classes for network packet representation and inter-module communication.

.. autosummary::

    ~gymwipe.networking.messages.Signal
    ~gymwipe.networking.messages.Transmittable
    ~gymwipe.networking.messages.Packet
    ~gymwipe.networking.messages.SimpleMacHeader
    ~gymwipe.networking.messages.SimpleTransportHeader
    

"""
from typing import Any, Dict
from enum import Enum
from simpy.events import Event
from gymwipe.simtools import SimMan

class Transmittable:
    """
    The :class:`Transmittable` class provides a :meth:`byteSize` method allowing
    objects of it to be nested in packets and sent via a channel. Unless for
    representing simple objects such as strings, it should be subclassed and
    both the :meth:`byteSize` and the :meth:`__str__` method should be
    overridden.

    Attributes:
        obj(Any): The object that has been provided to the constructor
    """

    def __init__(self, obj: Any):
        """
        The constructor takes any object and creates a
        :class:`Transmittable` with the byte length of its UTF-8 string representation.

        Note:
            Subclasses should not invoke the constructor, unless they also wrap a single object
            and use its string representation for :meth:`byteSize` calculation.
        
        Args:
            obj: The object of which the string representation will be used
        """
        self._str = str(obj)
        self._size = len(self._str.encode("utf-8"))
        self.obj = obj

    def __str__(self):
        return self._str

    def byteSize(self) -> int:
        """
        Returns the number of bytes that are to be transmitted when
        the data represented by this object is sent via a physical channel.
        """
        return self._size
    
    def transmissionTime(self, bitrate: int) -> int:
        """
        Returns the number of time steps needed to transmit the data represented by the
        :class:`Transmittable` at a specified bit rate.

        Args:
            bitrate: The number of bits that are transmitted in a single timeStep
        """
        return self.byteSize()*8 / bitrate


class Packet(Transmittable):
    """
    The Packet class represents packets. A Packet consists of a header and a
    payload. Packets can be nested by providing them as payloads to the packet
    constructor.

    Attributes:
        header(Transmittable): The object representing the Packet's
            header
        payload(Transmittable): The object representing the Packet's payload.
            Might be another :class:`Packet`.
        trailer(Transmittable): The object representing the Packet's trailer
            (defaults to ``None``)

    .. force documenting the __str__ function .. automethod:: __str__
    """

    def __init__(self, header: Transmittable, payload: Transmittable, trailer: Transmittable = None):
        self.header = header
        self.payload = payload
        self.trailer = trailer

    def __str__(self):
        """
        Returns the comma-seperated list of ``str(header)``, ``str(payload)``,
        and ``str(trailer)`` (if provided).
        """
        return ','.join([str(c) for c in [self.header, self.payload, self.trailer] if not c is None])
    
    def byteSize(self):
        return self.header.byteSize() + self.payload.byteSize()

class SimpleMacHeader(Transmittable):
    """
    A class for representing MAC packet headers

    Attributes:
        sourceMAC(bytes): The 6-byte-long source MAC address
        destMAC(bytes): The 6-byte-long destination MAC address
        flag(int): A single byte flag (stored as an integer in range(256))
    """

    def __init__(self, sourceMAC: bytes, destMAC: bytes, flag: int):
        if len(sourceMAC) != 6:
            raise ValueError("sourceMAC: Expected 6 bytes, got {:d}.".format(len(sourceMAC)))
        if len(destMAC) != 6:
            raise ValueError("destMAC: Expected 6 bytes, got {:d}.".format(len(destMAC)))
        if not flag in range(256):
            raise ValueError("flag has to be in range(256), got {:d}.".format(flag))
        self.sourceMAC = sourceMAC
        self.destMAC = destMAC
        self.flag = flag
    
    def __str__(self):
        return "(SimpleMacHeader: source: {}, dest: {}, flag: {:d})".format(self.sourceMAC, self.destMAC, self.flag)

    def byteSize(self):
        return 13

class SimpleTransportHeader(Transmittable):
    """
    Since IP is not implemented in gymwipe, there is a need for some interim way
    to specify source and destination addresses in packets that are passed to
    the :class:`SimpleMAC` layer. Therefore, a :class:`SimpleTransportHeader`
    holds a source and a destination MAC address. The destination address will
    be used by the :class:`SimpleMAC` layer.

    Attributes:
        sourceMAC(bytes): The 6-byte-long source MAC address
        destMAC(bytes): The 6-byte-long destination MAC address
    """

    def __init__(self, sourceMAC: bytes, destMAC: bytes):
        if len(sourceMAC) != 6:
            raise ValueError("sourceMAC: Expected 6 bytes, got {:d}.".format(len(destMAC)))
        if len(destMAC) != 6:
            raise ValueError("destMAC: Expected 6 bytes, got {:d}.".format(len(destMAC)))
        self.sourceMAC = sourceMAC
        self.destMAC = destMAC

    def __str__(self):
        return "(SimpleTransportHeader: source: {}, dest: {})".format(self.sourceMAC, self.destMAC)

    def byteSize(self):
        return 12
        

class Signal:
    """
    A class used for the exchange of arbitrary signals between components.
    Signals can be used to simulate both asynchronous and synchronous function
    calls.

    Attributes:
        type(Enum): An enumeration object that defines the signal type
        properties(Dict[str, Any]): A dictionary containing additional signal
            properties
        processed(Event): A SimPy event that is triggered when setProcessed is
            called. This is useful for simulating synchronous function calls.
    """

    def __init__(self, type: Enum, properties: Dict[str, Any] = None):
        self.type = type
        self.properties = properties
        self.processed = Event(SimMan.env)

    def triggerProcessed(self, returnValue: Any = None):
        """
        Triggers the :attr:`processed` event.

        Args:
            returnValue: If specified, will be used as the `value` of the
                :attr:`processed` event.

        Examples:
            If `returnValue` is specified, SimPy processes can use Signals for
            simulating synchronous function calls with return values like this:

            ::

                signal = Signal(myType, {"key", value})
                gate.output.send(signal)
                value = yield signal.processed
                # value now contains the `returnValue` that :meth:`setProcessed` was called with
        """
        self.processed.succeed(returnValue)
    
    @property
    def processedTriggered(self):
        """boolean: Whether or not the :attr:`processed` event was triggered"""
        return self.processed.triggered
    
    def __str__(self):
        return "Signal('{}', properties: {})".format(self.type.name, self.properties)

class StackSignals(Enum):
    """
    An enumeration of control signal types to be used for
    the exchange of `Signal` objects between network stack layers.
    """
    RECEIVE = 0
    SEND = 1
    ASSIGN = 2
