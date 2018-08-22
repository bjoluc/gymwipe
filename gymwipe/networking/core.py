"""
Core components for networking simulation
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple
from math import sqrt, log10
from simpy import Event
from gymwipe.networking.messages import Packet
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class Position:
    """
    A simple class for representing 2-dimensional positions, stored as two float values.
    """

    def __init__(self, x: float, y: float):
        """
        Args:
            x: The distance to a fixed origin in x direction, measured in meters
            y: The distance to a fixed origin in y direction, measured in meters
        """
        self.x = x
        self.y = y
    
    def __eq__(self, p):
        return p.x == self.x & p.y == self.y
    
    def distanceTo(self, p: 'Position') -> float:
        """
        Returns the euclidean distance of this :class:`Position` to `p`, measured in meters.

        Args:
            p: The :class:`Position` to calculate the distance to
        """
        return sqrt((self.x - p.x)**2 + (self.y - p.y)**2)
    
    def __str__(self):
        return "Position({},{})".format(self.x, self.y)

class NetworkDevice:
    """

    """

    def __init__(self, name: str, position: Position):
        self._name = name
        self._position = position
    
    def __str__(self):
        return "NetworkDevice('{}')".format(self.name)
    
    @property
    def position(self):
        """Position: The device's physical position"""
        return self._position
    
    @position.setter
    def setPosition(self, position):
        self._position = position
    
    @property
    def name(self) -> str:
        """str: The device name (for debugging and plotting)"""
        return self._name

class Transmission:
    """
    A :class:`Transmission` models the process of a device sending a specific packet via a communication channel.

    Note:
        The proper way to instantiate :class:`Transmission` objects is via :meth:`Channel.transmit`.
    """

    def __init__(self, sender: NetworkDevice, power: float, bitrateHeader: int, bitratePayload: int, packet: Packet, startTime: int):
        self._sender = sender
        self._power = power
        self._bitrateHeader = bitrateHeader
        self._bitratePayload = bitratePayload
        self._packet = packet
        self._startTime = startTime

        # calculate duration
        self._duration = packet.header.byteSize() * 8 / bitrateHeader + packet.payload.byteSize() * 8 / bitratePayload
        self._stopTime = startTime + self._duration
        # create the completesEvent
        self._completesEvent = SimMan.timeoutUntil(self._stopTime)
    
    def __str__(self):
        return "Transmission from {} with power {} and duration {}".format(self.sender, self.power, self.duration)
    
    @property
    def startTime(self):
        """int: The time at which the transmission started"""
        return self._startTime
    
    @property
    def power(self):
        """float: The tramsmission power"""
        return self._power
    
    @property
    def bitrateHeader(self):
        """int: The header's bitrate given in bits / time step"""
        return self._bitrateHeader
    
    @property
    def bitratePayload(self):
        """int: The payload's bitrate given in bits / time step"""
        return self._bitratePayload
    
    @property
    def sender(self):
        """NetworkDevice: The device that initiated the transmission"""
        return self._sender
    
    @property
    def packet(self):
        """Packet: The packet sent in the transmission"""
        return self._packet
    
    @property
    def duration(self):
        """int: The number of time steps taken by the transmission"""
        return self._duration
    
    @property
    def stopTime(self):
        """int: The number of the last time step in which the transmission is active"""
        return self._stopTime

    @property
    def completes(self):
        """Event: A SimPy :class:`~simpy.events.Event` that is triggered as soon as the transmission's stop time is over"""
        return self._completesEvent

class AttenuationModel(ABC):
    """
    Todo:
        * Documentation
        * Ways to retrieve values for time intervals
    """

    @abstractmethod
    def getSample(self, a: Position, b: Position, time: int) -> float:
        """
        Returns the attenuation of any signal sent from :class:`Position` `a`
        to :class:`Position` `b` at the simulated time specified by `time`.

        Args:
            a: Position a
            b: Position b
            time: The moment in simulated time to be considered
        
        Returns:
            The attenuation between a and b, measured in db
        """
    
    @abstractmethod
    def getIntervalsAboveThreshold(self, a: Position, b: Position, fromTime: float, toTime: float, threshold: float) -> List[Tuple[float, float]]:
        """
        Returns a chronologically sorted list of (from, to) tuples, where [from, to] is a
        maximum-length time interval in which the model's attenuation values constantly outrun `threshold`.

        Args:
            a: Position a
            b: Position b
            fromTime: The first moment in simulated time to be considered
            toTime: The last moment in simulated time to be considered
            threshold: The attenuation threshold (measured in db)
        """

class JoinedAttenuation(AttenuationModel):
    """
    An :class:`AttenuationModel` that combines the attenuation values of two or more
    given :class:`AttenuationModel` instances.
    """

    def __init__(self, *args):
        """
        Args:
            Two or more :class:`AttenuationModel` instances
        """
        self._models = args
    
    def getSample(self, a: Position, b: Position, time: int) -> float:
        return sum([model.getSample(a, b, time) for model in self._models])
    
    def getIntervalsAboveThreshold(self, a: Position, b: Position, fromTime: float, toTime: float, threshold: float) -> List[Tuple[float, float]]:
        #TODO
        pass


class FSPLAttenuation(AttenuationModel):
    """
    Free-space path loss (FSPL) attenuation model.
    """

    f = 2.4e9 # 2.4 GHz

    def getSample(self, a: Position, b: Position, time: int) -> float:
        # https://en.wikipedia.org/wiki/Free-space_path_loss#Free-space_path_loss_in_decibels
        if a == b:
            logger.info("FSPLAttenuation: Source and destination position are equivalent.")
            return 0
        return 20*log10(a.distanceTo(b)) + 20*log10(self.f) - 147.55
    
    def getIntervalsAboveThreshold(self, a: Position, b: Position, fromTime: float, toTime: float, threshold: float) -> List[Tuple[float, float]]:
        # path loss is constant in time
        if self.getSample(a, b, fromTime) > threshold:
            return [(fromTime, toTime)]
        else:
            return []


class Channel:
    """
    The Channel class serves as a manager for transmission objects and represents a physical channel.
    It also holds the corresponding AttenuationModel instance.
    """

    def __init__(self, attenuationModel: AttenuationModel):
        self._attenuationModel = attenuationModel
        self._transmissions = []
        self._transmissionStartedEvent = Event(SimMan.env)
    
    @property
    def attenuationModel(self):
        """AttenuationModel: The AttenuationModel instance belonging to the Channel"""
        return self._attenuationModel

    def transmit(self, sender: NetworkDevice, power: float, brHeader: int, brPayload: int, packet: Packet) -> Transmission:
        """
        Creates a :class:`Transmission` object with the values passed and stores it. Also triggers the :attr:`~Channel.transmissionStarted` event of the :class:`Channel`.

        Args:
            sender: The NetworkDevice that transmits
            power: Transmission power [dBm]
            brHeader: Header bitrate
            brPayload: Payload bitrate
            packet: :class:`~gymwipe.networking.messages.Packet` object representing the packet being transmitted
        
        Returns:
            The :class:`Transmission` object representing the transmission
        """
        t = Transmission(sender, power, brHeader, brPayload, packet, SimMan.now)
        self._transmissions.append((t, t.startTime, t.stopTime))
        logger.debug("Transmission %s added to channel", t)
        self._transmissionStartedEvent.succeed(t)
        self._transmissionStartedEvent = Event(SimMan.env)
        return t
    
    def getTransmissions(self, fromTime: int, toTime: int) -> List[Tuple[Transmission, int, int]]:
        """
        Returns the transmissions that were active within the timely interval of [`fromTime`,`toTime`].

        Args:
            fromTime: The number of the first time step of the interval to return transmissions for
            toTime: The number of the last time step of the interval to return transmissions for
        
        Returns:
            A list of tuples, one for each :class:`Transmission`, each consisting of the transmission's start time, stop time and the :class:`Transmission` object.
        """
        return [(t, a, b) for (t, a, b) in self._transmissions
                    if a <= fromTime <= toTime <= b
                    or fromTime <= a <= toTime
                    or fromTime <= b <= toTime]
    
    def getActiveTransmissions(self, time: int) -> List[Transmission]:
        """
        Returns a list of transmissions that are active at the moment specified by `time`
        
        Args:
            time: The time step for which to return active transmissions
        """
        return [t for (t, a, b) in self._transmissions if a <= time <= b]

    
    @property
    def transmissionStarted(self):
        """
        Event: A SimPy :class:`Event` that is triggered when :meth:`Channel.transmit` is executed.
        Its value is the :class:`Transmission` object representing the transmission.
        """
        return self._transmissionStartedEvent
        