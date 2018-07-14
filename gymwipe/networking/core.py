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
        Returns the euclidic distance of this `Position` to `p`, measured in meters.

        Args:
            p: The position to calculate the distance to
        """
        return sqrt((self.x - p.x)**2 + (self.y - p.y)**2)
    
    def __str__(self):
        return "Position({},{})".format(self.x, self.y)

class NetworkDevice:
    """

    """

    def __init__(self, name: str, position: Position):
        """
        Args:
            name
            position
        """
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
        """str: The device name (only for debugging and plotting)"""
        return self._name

class Transmission:
    """
    A Transmission models the process of a device sending a specific packet via a communication channel.
    Note: The proper way to instanciate transmission objects is via the `transmit` method of a `Channel`.
    """

    def __init__(self, sender: NetworkDevice, power: float, bitrateHeader: int, bitratePayload: int, packet: Packet, startTime: int):
        self._sender = sender
        self._power = power
        self._bitrateHeader = bitrateHeader
        self._bitratePayload = bitratePayload
        self._packet = packet
        self._startTime = startTime

        # calculate duration
        self._duration = len(str(packet.header)) * 16 / bitrateHeader + len(str(packet.payload)) * 16 / bitratePayload
        self._stopTime = startTime + self._duration
        # create the completesEvent
        self._completesEvent = SimMan.timeoutUntil(self._stopTime + 1)
    
    def __str__(self):
        return "Transmission from {} with power {} and duration {}".format(self.sender, self.power, self.duration)
    
    @property
    def startTime(self):
        """int: The number of the time step in which the transmission started"""
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
        """Event: A SimPy event that is triggered as soon as the transmission's stop time is over"""
        return self._completesEvent

class AttenuationProvider(ABC):
    """

    """

    @abstractmethod
    def getAttenuation(self, a: Position, b: Position, time: int) -> float:
        """
        Returns the attenuation of any signal sent from position `a` to position `b` at the time step specified by `time`.

        Args:
            a: Position a
            b: Position b
            time: The time step to be considered
        
        Returns:
            The attenuation between a and b, measured in db
        """
        pass

class FSPLAttenuationProvider(AttenuationProvider):
    """
    Free-space path loss (FSPL) attenuation provider.
    To be used for demonstration purposes only.
    """

    f = 2.4e9 # 2.4 GHz

    def getAttenuation(self, a: Position, b: Position, time: int) -> float:
        # https://en.wikipedia.org/wiki/Free-space_path_loss#Free-space_path_loss_in_decibels
        return 20*log10(a.distanceTo(b)) + 20*log10(self.f) - 147.55


class Channel:
    """
    The Channel class serves as a manager for transmission objects and represents a physical channel.
    It also holds the corresponding AttenuationProvider instance.
    """

    def __init__(self, attenuationProvider: AttenuationProvider):
        self._attenuationProvider = attenuationProvider
        self._transmissions = []
        self._transmissionStartedEvent = Event(SimMan.env)
    
    @property
    def attenuationProvider(self):
        """AttenuationProvider: The AttenuationProvider instance belonging to the Channel"""
        return self._attenuationProvider

    def transmit(self, sender: NetworkDevice, power: float, brHeader: int, brPayload: int, packet: Packet) -> Transmission:
        """
        Creates a `Transmission` object with the values passed and stores it. Also triggers the `transmissionStarted` event of the `Channel`.

        Args:
            sender: The NetworkDevice that transmits
            power: Transmission power [dBm]
            brHeader: Header bitrate
            brPayload: Payload bitrate
            packet: `Packet` object representing the packet being transmitted
        
        Returns:
            The `Transmission` object representing the transmission
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
            A list of tuples, one for each transmission, each consisting of the transmission's start time, stop time and the transmission object.
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
        Event: A SimPy event that is triggered when the transmit method of the channel is executed.
        Its value is the transmission object representing the transmission.
        """
        return self._transmissionStartedEvent
        