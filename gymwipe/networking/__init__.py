"""
The networking module provides the NetworkDevice baseclass along with network stack models, a framework for network stack modeling and physical channel simulations.
"""
import warnings
from typing import List, Tuple
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
    
    @property
    def attenuationProvider(self):
        """AttenuationProvider: The AttenuationProvider instance belonging to the Channel"""
        return self._attenuationProvider

    def addTransmission(self, t: Transmission) -> None:
        self._transmissions.append((t, t.getStartTime, t.getStopTime))
    
    def getTransmissions(self, time: int) -> List[Tuple[Transmission, int, int]]:
        """
        Returns the transmissions that are active at the time that was passed.

        Args
            time: The time for which to return active transmissions
        
        Returns
            A list of tuples, one for each active transmission, each consisting of the transmission's start time, stop time and the transmission object.
        """
        return [(t, a, b) for (t, a, b) in self._transmissions if a <= time and time <= b]
