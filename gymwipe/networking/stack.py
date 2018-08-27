"""
The Stack package contains implementations of network stack layers. Layers are modeled by :class:`~gymwipe.networking.construction.Module` objects.
"""
import logging
from typing import Any
from collections import deque
from simpy.events import Event
from gymwipe.networking.construction import Module, Gate, GateListener
from gymwipe.networking.core import NetworkDevice
from gymwipe.networking.physical import Channel, Transmission
from gymwipe.networking.messages import Signal, StackSignals, Transmittable, Packet, SimpleMacHeader
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class StackLayer(Module):

    def __init__(self, name: str, device: NetworkDevice):
        super(StackLayer, self).__init__(name)
        self._device = device
    
    def __str__(self):
        return "{}.{}('{}')".format(self._device, self.__class__.__name__, self._name)

class SimplePhy(StackLayer):
    """
    A very basic physical layer implementation, mainly for demonstration purposes.
    It provides a single gate called `mac` to be connected to the mac layer.
    Slotted time is used, with the size of a time slot being defined by
    :attr:`~gymwipe.simtools.SimulationManager.timeSlotSize`.
    
    During simulation the the channel is sensed for transmissions and
    any successfully received packet is sent out via the `mac` gate.

    The `mac` gate accepts :class:`~gymwipe.networking.messages.Signal` objects
    of the following types:

    * :attr:`~gymwipe.networking.messages.StackSignals.SEND`

        Send a specified packet via the channel.

        :class:`~gymwipe.networking.messages.Signal` properties:

        :packet: The :class:`~gymwipe.networking.messages.Packet` object representing the packet to be sent
        :power: The transmission power [dBm]
        :bitrate: The bitrate of the transmission [bits/time step]
    
    Todo:
        * Interrupt receiver while sending?
        * Sample attenuation while receiving (find something more performant than brute-force sampling)
    """

    @GateListener.setup
    def __init__(self, name: str, device: NetworkDevice, channel: Channel):
        super(SimplePhy, self).__init__(name, device)
        self._channel = channel
        self._addGate("mac")
        self._currentTransmission = None
        self._receiverProcess = SimMan.process(self.receiver())
        logger.debug("Initialized %s", self)
    
    RECV_THRESHOLD = -80 # dBm (https://www.metageek.com/training/resources/wifi-signal-strength-basics.html)
    
    @GateListener("mac", Signal, buffered=True)
    def macGateListener(self, cmd):
        p = cmd.properties

        if cmd.type is StackSignals.SEND:
            logger.debug("%s: Received SEND command", self)
            # wait for the beginning of the next time slot
            yield SimMan.nextTimeSlot()
            # simulate sending
            t = self._channel.transmit(self._device, p["power"], p["bitrate"], p["bitrate"], p["packet"])
            self._currentTransmission = t
            # wait for the transmission to finish
            yield t.completes
            # indicate that processing the send command was completed
            cmd.triggerProcessed()
    
    def receiver(self):
        while True:
            # simulate channel sensing & receiving
            t = yield self._channel.transmissionStarted
            if not t == self._currentTransmission:
                logger.debug("%s: Sensed a transmission.", self)
                # wait until the transmission has finished
                yield t.completes
                # check for collisions
                if len(self._channel.getTransmissions(t.startTime, t.stopTime)) > 1:
                    logger.debug("%s: Colliding transmission(s) were detected, transmission could not be received.", self)
                    pass
                else:
                    # no colliding transmissions, check attenuation
                    a = self._channel.attenuationModel.getSample(t.sender.position, self._device.position, t.startTime)
                    recvPower = t.power - a
                    if recvPower < self.RECV_THRESHOLD:
                        logger.debug("%s: Signal strength of %6d dBm is insufficient (RECV_THRESHOLD is %6d dBm), packet could not be received correctly.", self, recvPower, self.RECV_THRESHOLD)
                        pass
                    else:
                        logger.debug("%s: Packet successfully received (Signal power was %6d dBm)!", self, recvPower)
                        packet = t.packet
                        # sending the packet via the mac gate
                        self.gates["mac"].output.send(packet)

class SimpleMac(StackLayer):
    """
    A MAC layer implementation of the contention-free protocol described as follows:
    
        *   Every SimpleMac has a unique 6-byte-long MAC address.
        *   The MAC layer with address ``0`` is considered to belong to the RRM.
        *   Time slots are grouped into frames.
        *   Every second frame is reserved for the RRM and has a fixed length
            (number of time slots).
        *   The RRM uses those frames to send a short *announcement*,
            containing a destination MAC address and the frame length (number of time slots
            **n**) of the following frame.
            By doing so it allows the specified device to use the channel for the
            next frame.
            *Announcements* are packets with a :class:`~gymwipe.networking.messages.SimpleMacHeader`
            having the following attributes:

                :attr:`~gymwipe.networking.messages.SimpleMacHeader.sourceMAC`: The RRM MAC address

                :attr:`~gymwipe.networking.messages.SimpleMacHeader.destMAC`: The MAC address of the device that may transmit next

                :attr:`~gymwipe.networking.messages.SimpleMacHeader.flag`: ``1`` (flag for allowing a device to transmit)
            
            The packet's :attr:`~gymwipe.networking.messages.Packet.payload` is the number **n**
            mentioned above (wrapped inside a :class:`~gymwipe.networking.messages.Transmittable`)
        *   Every other packet sent has a :class:`~gymwipe.networking.messages.SimpleMacHeader`
            with :attr:`~gymwipe.networking.messages.SimpleMacHeader.flag` ``0``.
    
    The `transport` gate accepts objects of the following types:

        * :class:`~gymwipe.networking.messages.Signal`

            Types:

            * :attr:`~gymwipe.networking.messages.StackSignals.RECEIVE`

                Listen for packets sent to this device.

                :class:`~gymwipe.networking.messages.Signal` properties:

                :duration: The number of time steps to listen for

                When a packet destinated to this device is received, the
                :class:`~gymwipe.networking.messages.Signal.processed` event of the
                :class:`~gymwipe.networking.messages.Signal` will be triggered with the packet as a value.
                If the time given by `duration` has passed and no packet was received,
                it will be triggered with ``None``.

        * :attr:`~gymwipe.networking.messages.Packet`

            Send a given packet (with a :attr:`~gymwipe.networking.messages.SimpleTransportHeader`) to the MAC address defined in the header.
    
    The `phy` gate accepts objects of the following types:

        * :attr:`~gymwipe.networking.messages.Packet`

            A packet received by the physical layer
    """

    @GateListener.setup
    def __init__(self, name: str, device: NetworkDevice, addr: bytes):
        """
        Args:
            name: The layer's name
            device: The NetworkDevice that operates the SimpleMac layer
            addr: The 6-byte-long MAC address to be assigned to this MAC layer
        """
        super(SimpleMac, self).__init__(name, device)
        self._addGate("phy")
        self._addGate("transport")
        self.addr = addr
        self._packetQueue = deque(maxlen=1000) # allow 1000 packets to be queued
        self._packetAddedEvent = Event(SimMan.env)
        self._bitrate = 16 # fixed bitrate, might be adopted later
        self._receiving = False
        self._receiveCmd = None
        self._receiveTimeout = None
        
        logger.debug("Initialized %s, assigned MAC address %s", self, self.addr)
    
    rrmAddr = bytes(6)
    """bytes: The 6 bytes long RRM MAC address"""

    _macCounter = 0
    
    @classmethod
    def newMacAddress(cls) -> bytes:
        """
        A method for generating unique 6-byte-long MAC addresses (currently counting upwards starting at 1)
        """
        cls._macCounter += 1
        addr = bytearray(6)
        addr[5] = cls._macCounter
        return bytes(addr)
    
    @GateListener("phy", Packet)
    def phyGateListener(self, packet):
        header = packet.header
        if not isinstance(header, SimpleMacHeader):
            raise ValueError("{}: Can only deal with header of type SimpleMacHeader. Got {}.".format(self, type(header)))
        
        if header.destMAC == self.addr:
            # packet for us
            if header.sourceMAC == self.rrmAddr:
                # RRM sent the packet
                logger.debug("%s: Received a packet from RRM: %s", self, packet)
                if header.flag == 1:
                    # we may transmit
                    timeTotal = packet.payload.obj
                    stopTime = SimMan.now + timeTotal
                    def timeLeft():
                        return stopTime - SimMan.now
                    logger.debug("%s: Got permission to transmit for %d time steps", self, timeTotal)

                    timeoutEvent = SimMan.timeout(timeTotal)
                    queuedPackets = True
                    while not timeoutEvent.processed:
                        if len(self._packetQueue) == 0:
                            queuedPackets = False
                            logger.debug("%s: Packet queue empty, nothing to transmit. Time left: %d", self, timeLeft())
                            yield self._packetAddedEvent | timeoutEvent
                            if not timeoutEvent.processed:
                                # new packet was added for sending
                                logger.debug("%s: Packet queue was filled again. Time left: %d", self, timeLeft())
                                queuedPackets = True
                        if queuedPackets:
                            if not timeLeft() > self._packetQueue[0].transmissionTime(self._bitrate)+5:
                                # TODO: +5 is a dirty cheat: It would be best to calculate
                                # the trailer size right here
                                logger.debug("%s: Next packet is too large to be transmitted. Idling. Time left: %d", self, timeLeft())
                                yield timeoutEvent
                            else:
                                # enough time left to transmit the next packet
                                payload = self._packetQueue.popleft()
                                packet = Packet(
                                    SimpleMacHeader(self.addr, payload.header.destMAC, flag=0),
                                    payload,
                                    Transmittable(len(self._packetQueue)) # append queue length as a trailer (reward for RRM agent)
                                )
                                signal = Signal(StackSignals.SEND, {"packet": packet, "power": -20, "bitrate": self._bitrate})
                                self.gates["phy"].output.send(signal) # make the PHY send the packet
                                logger.debug("%s: Transmitting packet. Time left: %d", self, timeLeft())
                                logger.debug("%s: Packet: %s", self, packet)
                                yield signal.processed # wait until the transmission has completed
            else:
                # packet from any other device
                if self._receiving:
                    logger.info("%s: Received Packet.", self)
                    logger.debug("%s: Packet: %s", self, packet.payload)
                    # return the packet's payload to the transport layer
                    self._receiveCmd.triggerProcessed(packet.payload)
                    self._stopReceiving()
                else:
                    logger.debug("%s: Received Packet from Phy, but not in receiving mode. Packet ignored.", self)

        elif header.destMAC == self.rrmAddr:
            # packet from RRM to all devices
            pass
    
    @GateListener("transport", (Signal, Packet))
    def transportGateListener(self, cmd):

        if isinstance(cmd, Signal):
            if cmd.type is StackSignals.RECEIVE:
                logger.debug("%s: Entering receive mode.", self)
                # start receiving
                self._receiveCmd = cmd
                # set _receiving and a timeout event
                self._receiving = True
                self._receiveTimeout = SimMan.timeout(cmd.properties["duration"])
                self._receiveTimeout.callbacks.append(self._receiveTimeoutCallback)

        elif isinstance(cmd, Packet):
            self._packetQueue.append(cmd)
            self._packetAddedEvent.succeed()
            self._packetAddedEvent = Event(SimMan.env)
    
    def _receiveTimeoutCallback(self, event: Event):
        if event is self._receiveTimeout:
            # the current receive signal has timed out
            logger.debug("%s: Receive timed out.", self)
            self._receiveCmd.setProcessed()
            self._stopReceiving()
    
    def _stopReceiving(self):
        logger.debug("%s: Stopping to receive.", self)
        self._receiveCmd = None
        self._receiving = False
        self._receiveTimeout = None
        

class SimpleRrmMac(StackLayer):
    """
    The RRM implementation of the protocol described in :class:`SimpleMac`

    The `transport` gate accepts objects of the following types:

        * :class:`~gymwipe.networking.messages.Signal`

        Types:

            * :attr:`~gymwipe.networking.messages.StackSignals.ASSIGN`

                Send a channel assignment announcement that permits a device
                to transmit for a certain time.

                :class:`~gymwipe.networking.messages.Signal` properties:

                :dest: The 6-byte-long MAC address of the device to be allowed to transmit

                :duration: The number of time steps to assign the channel for the specified device
    """

    @GateListener.setup
    def __init__(self, name: str, device: NetworkDevice):
        super(SimpleRrmMac, self).__init__(name, device)
        self._addGate("phy")
        self._addGate("transport")
        self._macAddr = bytes(6) # 6 zero bytes
        self._announcementBitrate = 16
        self._announcementQueue = deque(maxlen=50)
        self._announcementAdded = Event(SimMan.env)
        self._currentAnnouncement = None
        self._currentAnnouncementReward = float('inf')
        SimMan.process(self.announcementSender())
    
    @GateListener("phy", Packet)
    def phyGateListener(self, packet):
        if packet.header.sourceMAC == self._currentAnnouncement.properties["dest"]:
            # packet was sent by the device mentioned in the current announcement
            # Use the object wrapped in the packet's trailer Transmittable as the reward
            reward = packet.trailer.obj
            logger.debug("%s: Extracted reward from %s: %d", self, packet.header.sourceMAC, reward)
            self._currentAnnouncementReward = reward
            
    @GateListener("transport", Signal)
    def transportGateListener(self, cmd):
        logger.debug("%s: Queuing new announcement Signal %s.", self, cmd)
        self._announcementQueue.append(cmd)
        self._announcementAdded.succeed()
        self._announcementAdded = Event(SimMan.env)
    
    def announcementSender(self):
        while True:
            if len(self._announcementQueue) == 0:
                logger.debug("%s: No announcements to be sent, idling.", self)
                yield self._announcementAdded
            
            while len(self._announcementQueue) > 0:
                # pop announcement queue
                cmd = self._announcementQueue.popleft()
                self._currentAnnouncement = cmd

                destination = cmd.properties["dest"]
                duration = cmd.properties["duration"]
                announcement = Packet(
                    SimpleMacHeader(self._macAddr, destination, flag=1),
                    Transmittable(duration)
                )
                sendCmd = Signal(
                    StackSignals.SEND,
                    {"packet": announcement, "power": -20, "bitrate": self._announcementBitrate}
                )
                logger.debug("%s: Sending new announcement: %s", self, announcement)
                self.gates["phy"].output.send(sendCmd)
                yield sendCmd.processed
                yield SimMan.timeout(duration+1) # one extra time slot to be save from collisions (in reality)

                # mark the current announcement command as processed and return the reward
                self._currentAnnouncement.triggerProcessed(self._currentAnnouncementReward)
                self._currentAnnouncementReward = float('inf')
