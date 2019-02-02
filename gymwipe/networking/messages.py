"""
The messages module provides classes for network packet representations and
inter-module communication.

The following classes are used for transmission simulation:

.. autosummary::

    ~gymwipe.networking.messages.Transmittable
    ~gymwipe.networking.messages.FakeTransmittable
    ~gymwipe.networking.messages.Packet
    ~gymwipe.networking.messages.SimpleMacHeader
    ~gymwipe.networking.messages.SimpleNetworkHeader

The following classes are used for inter-module communication:

.. autosummary::

    ~gymwipe.networking.messages.Message
    ~gymwipe.networking.messages.StackMessageTypes
"""
from enum import Enum
from typing import Any, Dict

from simpy.events import Event

from gymwipe.simtools import SimMan


class Transmittable:
    """
    The :class:`Transmittable` class provides a :attr:`byteSize` attribute
    allowing the simulated sending of :class:`Transmittable` objects via a
    frequency band.

    Attributes:
        value(Any): The object that has been passed to the constructor as
            `value`
        byteSize: The transmittable's byteSize as it was passed to the constructor
    """

    def __init__(self, value: Any, byteSize = None):
        """
        Args:
            value: The object of which the string representation will be used
            byteSize: The number of bytes that are simulated to be transmitted
                when the data represented by this :class:`Transmittable` is sent via
                a frequency band. Defaults to the length of the UTF-8 encoding of
                `str(value)`.
        """
        if byteSize is None:
            self.byteSize = len(str(value).encode("utf-8"))
        else:
            self.byteSize = byteSize
        self.value = value

    def __repr__(self):
        return "{}(value={}, byteSize={:d})".format(self.__class__.__name__, self.value, self.byteSize)
    
    @property
    def bitSize(self) -> int:
        """
        :attr:`byteSize` :math:`\\times 8`
        """
        return self.byteSize * 8
    
    def transmissionTime(self, bitrate: float) -> float:
        """
        Returns the time in seconds needed to transmit the data represented
        by the :class:`Transmittable` at the specified bit rate.

        Args:
            bitrate: The bitrate in bps
        """
        return self.bitSize / bitrate


class FakeTransmittable(Transmittable):
    """
    A :class:`Transmittable` implementation that sets its value to None. It can
    be helpful for test applications when the data itself is irrelevant and only
    its size has to be considered.
    """

    def __init__(self, byteSize: int):
        """
        Args:
            byteSize: The number of bytes that the :class:`FakeTransmittable`
                represents
        """
        super(FakeTransmittable, self).__init__(None, byteSize)
    
    def __str__(self):
        return "FakeTransmittable(byteSize={:d})".format(self.byteSize)


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

        # Set value and byteSize
        value = (header, payload, trailer)
        byteSize = 0
        for t in value:
            if t is not None:
                byteSize += t.byteSize
        super(Packet, self).__init__((header, payload, trailer), byteSize)
    
    def __repr__(self):
        return "Packet(header={},payload={},trailer={},byteSize={:d})".format(
            repr(self.header), repr(self.payload), repr(self.trailer), self.byteSize)

    def __str__(self):
        return "({})".format(','.join([str(c) for c in self.value if not c is None]))


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
        # Set Transmittable value and byteSize
        super(SimpleMacHeader, self).__init__((sourceMAC, destMAC, flag), byteSize=13)
    
    def __str__(self):
        return "(SimpleMacHeader: source: {}, dest: {}, flag: {:d})".format(self.sourceMAC, self.destMAC, self.flag)


class SimpleNetworkHeader(Transmittable):
    """
    Since no network protocol is implemented in Gym-WiPE, there is a need for
    some interim way to specify source and destination addresses in packets that
    are passed to the :class:`SimpleMAC` layer. Therefore, a
    :class:`SimpleNetworkHeader` holds a source and a destination MAC address.
    The destination address is used by the :class:`SimpleMAC` layer.

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
        # Set Transmittable value and byteSize
        super(SimpleNetworkHeader, self).__init__((sourceMAC, destMAC), byteSize=12)

    def __str__(self):
        return "(SimpleNetworkHeader: source: {}, dest: {})".format(self.sourceMAC, self.destMAC)
        

class Message:
    """
    A class used for the exchange of arbitrary messages between components.
    A :class:`Message` can be used to simulate both asynchronous and synchronous function
    calls.

    Attributes:
        type(Enum): An enumeration object that defines the message type
        args(Dict[str, Any]): A dictionary containing the message's arguments
        eProcessed(Event): A SimPy event that is triggered when
            :meth:`setProcessed` is called. This is useful for simulating
            synchronous function calls and also allows for return values (an
            example is provided in :meth:`setProcessed`).
    """

    def __init__(self, type: Enum, args: Dict[str, Any] = None):
        self.type = type
        self.args = args
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
    
    def __repr__(self):
        return "Message(type: '{}', args: {})".format(self.type.name, self.args)


class StackMessageTypes(Enum):
    """
    An enumeration of control message types to be used for the exchange of
    `Message` objects between network stack layers.
    """
    RECEIVE = 0
    SEND = 1
    ASSIGN = 2
    SENDCONTROL = 3
    RECEIVED = 4
