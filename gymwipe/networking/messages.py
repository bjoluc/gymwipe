"""
The messages module provides classes for network packet representations and
inter-module communication.

The following classes are used for transmission simulation:

.. autosummary::

    ~gymwipe.networking.messages.Transmittable
    ~gymwipe.networking.messages.FakeTransmittable
    ~gymwipe.networking.messages.IntTransmittable
    ~gymwipe.networking.messages.Packet
    ~gymwipe.networking.messages.SimpleMacHeader
    ~gymwipe.networking.messages.SimpleTransportHeader

The following classes are used for inter-module communication:

.. autosummary::

    ~gymwipe.networking.messages.Signal
    ~gymwipe.networking.messages.StackSignals
"""
from enum import Enum
from typing import Any, Dict

from simpy.events import Event

from gymwipe.simtools import SimMan


class Transmittable:
    """
    The :class:`Transmittable` class provides a :meth:`byteSize` method allowing
    objects of it to be sent via a frequency band. Unless for representing
    simple objects such as strings, it should be subclassed and both
    :meth:`byteSize` and :meth:`__str__` should be overridden.

    Attributes:
        obj(Any): The object that has been provided to the constructor
    """

    def __init__(self, obj: Any):
        """
        The constructor takes any object and creates a :class:`Transmittable`
        with the byte length of its UTF-8 string representation.

        Note:
            Subclasses should not invoke the constructor, unless they also wrap
            a single object and use its string representation for
            :meth:`byteSize` calculation.
        
        Args:
            obj: The object of which the string representation will be used
        """
        self._str = str(obj)
        self._byteSize = len(self._str.encode("utf-8"))
        self.obj = obj

    def __str__(self):
        return self._str

    def byteSize(self) -> int:
        """
        Returns the number of bytes that are to be transmitted when the data
        represented by this object is sent via a frequency band.
        """
        return self._byteSize
    
    def bitSize(self) -> int:
        """
        Returns :meth:`byteSize` :math:`\\times 8`
        """
        return self.byteSize() * 8
    
    def transmissionTime(self, bitrate: float) -> float:
        """
        Returns the time in seconds needed to transmit the data represented
        by the :class:`Transmittable` at the specified bit rate.

        Args:
            bitrate: The bitrate in bps
        """
        return self.bitSize() / bitrate

class FakeTransmittable(Transmittable):
    """
    A :class:`Transmittable` implementation that fakes its byteSize. This can be
    helpful for test applications when the data itself is irrelevant and only
    its size has to be considered.
    """

    def __init__(self, byteSize: int):
        """
        Args:
            byteSize: The number of bytes that the :class:`FakeTransmittable`
                will be long
        """
        self._byteSize = byteSize
        self._str = "FakeTransmittable(byteSize={:d})".format(self._byteSize)

class IntTransmittable(Transmittable):
    """
    A :class:`Transmittable` to wrap a fixed-length integer. If for instance you
    want your payloads to be two-byte integers, initialize them like this:
    ::
    
        myIntValue = 42
        payload = IntTransmittable(2, myIntValue)
    """
    
    def __init__(self, byteSize: int, value: int):
        """
        Args:
            byteSize: The number of bytes that are simulated to be transmitted
            value: The integer value to be transmitted
        """
        self._byteSize = byteSize

        self.value = value
        """
        int:The integer value assigned at construction
        """

        self._str = "IntTransmittable(byteSize={:d},value={:d})".format(self._byteSize, self.value)

class Packet(Transmittable):
    """
    The Packet class represents packets. A Packet consists of a header, a
    payload and an optional trailer. Packets can be nested by providing them as
    payloads to the packet constructor.

    Attributes:
        header(Transmittable): The object representing the Packet's
            header
        payload(Transmittable): The object representing the Packet's payload.
            Might be another :class:`Packet`.
        trailer(Transmittable): The object representing the Packet's trailer
            (defaults to ``None``)

    .. force documenting the __str__ function
    .. automethod:: __str__
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
        eProcessed(Event): A SimPy event that is triggered when
            :meth:`setProcessed` is called. This is useful for simulating
            synchronous function calls and also allows for return values (an
            example is provided in :meth:`setProcessed`).
    """

    def __init__(self, type: Enum, properties: Dict[str, Any] = None):
        self.type = type
        self.properties = properties
        self.eProcessed = Event(SimMan.env)

    def setProcessed(self, returnValue: Any = None):
        """
        Makes the :attr:`eProcessed` event succeed.

        Args:
            returnValue: If specified, will be used as the `value` of the
                :attr:`eProcessed` event.

        Examples:
            If `returnValue` is specified, SimPy processes can use Signals for
            simulating synchronous function calls with return values like this:

            ::

                signal = Signal(myType, {"key", value})
                gate.output.send(signal)
                value = yield signal.eProcessed
                # value now contains the returnValue that setProcessed() was called with
        """
        self.eProcessed.succeed(returnValue)
    
    def __str__(self):
        return "Signal('{}', properties: {})".format(self.type.name, self.properties)

class StackSignals(Enum):
    """
    An enumeration of control signal types to be used for the exchange of
    `Signal` objects between network stack layers.
    """
    RECEIVE = 0
    SEND = 1
    ASSIGN = 2
