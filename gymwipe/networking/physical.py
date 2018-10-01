"""
Physical layer related components
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple
from math import sqrt, log10
from simpy import Event
from gymwipe.networking.messages import Packet
from gymwipe.simtools import SimMan, SimTimePrepender
from gymwipe.networking.core import Position, NetworkDevice

logger = SimTimePrepender(logging.getLogger(__name__))

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
    An :class:`AttenuationModel` calculates the attenuation (measured in db)
    of any signal sent from one network device to another.
    It runs a SimPy process and subscribes to the positionChanged events
    of the :class:`NetworkDevice` instances it belongs to.
    When the attenuation value changes, the :attr:`attenuationChanged` event succeeds.
    """

    def __init__(self, deviceA: NetworkDevice, deviceB: NetworkDevice):
        self.devices = (deviceA, deviceB)
        self._attenuationChangedEvent = SimMan.event()
        SimMan.process(self._process)

        # TODO subscribe to events - how to achieve this -> Own PubSub mechanism? SimPy PubSub integration?

    @abstractmethod
    def getAttenuation(self) -> float:
        """
        Returns the attenuation of any signal sent from :class:`Position` `a`
        to :class:`Position` `b` at the currently simulated time.

        Args:
            a: Position a
            b: Position b
            time: The moment in simulated time to be considered
        
        Returns:
            The attenuation between a and b, measured in db
        """
    
    #@abstractmethod
    def _process(self):
        pass

    #@property
    def attenuationChanged(self):
        """
        Event: A SimPy event that succeeds when the attenuation value changes.
        The event's value is the new attenuation value.
        """
        if self._attenuationChangedEvent.processed:
            self._attenuationChangedEvent = SimMan.event()
        return self._attenuationChangedEvent
    

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


class AttenuationModelFactory():
    """
    A factory for the instantiation of JoinedAttenuationModel instances.
    It is instantiated providing the AttenuationModel subclasses that will be used.
    """

    def __init__(self, *args):
        self.modelClasses = args
        self.instances = {}
    
    def getInstance(self, deviceA: NetworkDevice, deviceB: NetworkDevice):
        if deviceB > deviceA:
            deviceA, deviceB = deviceB, deviceA
            # sorting references in order to create unique dictionary entries for every pair of devices
        key = (deviceA, deviceB)
        if key in self.instances:
            return self.instances.get(key)
        else:
            # initializing new instance
            if len(self.modelClasses) == 1:
                instance = self.modelClasses[0]()
            else:
                instance = None#JoinedAttenuationModel(*self.modelClasses)
            self.instances[key] = instance
            return instance
