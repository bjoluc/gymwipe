"""
Core components for networking simulation
"""
import warnings
from typing import List, Tuple
from math import sqrt
from simpy import Event
from gymwipe.networking.messages import Packet
from gymwipe.simtools import SimMan

class Position:
    """
    A simple class for representing 2-dimensional positions, stored as two float values.
    """

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
    
    def __eq__(self, p):
        return p.x == self.x & p.y == self.y
    
    def distanceTo(self, p: Position) -> float:
        """
        Returns the euclidic distance of this `Position` to `p`.

        Args:
            p: The position to calculate the distance to
        """
        return sqrt((self.x - p.x)**2 + (self.y - p.y)**2)

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
    """

    def __init__(self, startTime: int, power: float, bitrateHeader: int, bitratePayload: int, sender: NetworkDevice, packet: Packet):
        if startTime < SimMan.now:
            warnings.warn("A packet's startTime is in the past. This might lead to invalid simulation results.", RuntimeWarning, stacklevel=2) 
        self._startTime = startTime
        self._power = power
        self._bitrateHeader = bitrateHeader
        self._bitratePayload = bitratePayload
        self._sender = sender
        self._packet = packet

        # calculate duration
        self._duration = len(str(packet.header)) * 16 / bitrateHeader + len(str(packet.payload)) * 16 / bitratePayload

        self._completesEvent = Event(SimMan.env)
    
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
        return self._startTime + self._duration

    @property
    def completes(self):
        """Event: A SimPy event that is triggered as soon as the transmission's stop time is over"""
        return self._completesEvent

class AttenuationProvider:
    """

    """

class Channel:
    """
    The Channel class serves as a manager for transmission objects and represents a physical channel.
    It also holds the corresponding AttenuationProvider instance.
    """

    def __init__(self, attenuationProvider: AttenuationProvider):
        self._attenuationProvider = attenuationProvider
        self._transmissions = []
        self._transmissionAddedEvent = Event(SimMan.env)
    
    @property
    def attenuationProvider(self):
        """AttenuationProvider: The AttenuationProvider instance belonging to the Channel"""
        return self._attenuationProvider

    def addTransmission(self, t: Transmission) -> None:
        self._transmissions.append((t, t.getStartTime, t.getStopTime))
        self._transmissionAddedEvent.succeed(t)
        self._transmissionAddedEvent = Event(SimMan.env)
    
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
    
    @property
    def transmissionAdded(self):
        """
        Event: A SimPy event that is triggered when a transmission is added to the channel.
        Its value is the transmission object that was added.
        """
        return self._transmissionAddedEvent
        