"""
The Stack package contains implementations of network stack layers. Layers are modeled by :class:`~gymwipe.networking.construction.Module` objects.
"""
import logging
from collections import deque
from functools import partial
from typing import Any, Deque, Dict, List

import numpy as np
from simpy.events import Event

from gymwipe.devices import Device
from gymwipe.networking.construction import Gate, GateListener, Module
from gymwipe.networking.messages import (Packet, Signal, SimpleMacHeader,
                                         StackSignals, Transmittable)
from gymwipe.networking.physical import (AttenuationModel, BpskMcs, Channel,
                                         Mcs, Transmission,
                                         temperatureToNoisePowerDensity)
from gymwipe.simtools import Notifier, SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class StackLayer(Module):

    def __init__(self, name: str, device: Device):
        super(StackLayer, self).__init__(name)
        self.device = device
    
    def __str__(self):
        return "{}.{}('{}')".format(self.device, self.__class__.__name__, self._name)

class SimplePhy(StackLayer):
    """
    A phy layer implementation that does not take propagation delays into
    account. It provides a gate called `mac` to be connected to the mac layer.
    Slotted time is used, with the size of a time slot being defined by
    :attr:`~gymwipe.simtools.SimulationManager.timeSlotSize`.
    
    During simulation the channel is sensed and every successfully received
    packet is sent via the `mac` gate.

    The `mac` gate accepts :class:`~gymwipe.networking.messages.Signal` objects
    of the following types:

    * :attr:`~gymwipe.networking.messages.StackSignals.SEND`

        Send a specified packet via the channel.

        :class:`~gymwipe.networking.messages.Signal` properties:

        :packet: The :class:`~gymwipe.networking.messages.Packet` object
            representing the packet to be sent
        :power: The transmission power [dBm]
        :bitrate: The bitrate of the transmission [bits/time step]
    
    Todo:
        * Interrupt receiver while sending?
        * React to attenuation changes, calculate SNR values, concern MCS

        * Get MCS objects for the transmission
    """

    NOISE_POWER_DENSITY = temperatureToNoisePowerDensity(20.0)
    """float: The receiver's noise power density in Watts/Hertz"""

    @GateListener.setup
    def __init__(self, name: str, device: Device, channel: Channel, mcs: Mcs = BpskMcs()):
        super(SimplePhy, self).__init__(name, device)
        self.channel = channel
        self.mcs = mcs
        self._addGate("mac")

        # Attributes related to sending
        self._currentTransmission = None
        self._transmitting = False

        # Attributes related to receiving
        self._thermalNoiseLevel = self.NOISE_POWER_DENSITY * channel.spec.bandwidth
        self._transmissionToReceivedPowerDict: Dict[Transmission, float] = {}
        self._transmissionToAttenuationChangedCallbackDict = {}
        self._receivedLevel = self._thermalNoiseLevel
        def updateReceivedLevel(delta: float):
            self._receivedLevel += delta
        self._nReceivedLevelChanges = Notifier("Received level changes", self)
        self._nReceivedLevelChanges.subscribeCallback(updateReceivedLevel, priority=1)

        self.channel.nNewTransmission.subscribeCallback(self._onNewTransmission)
        self.channel.nNewTransmission.subscribeProcess(self._receive)
        logger.debug("%s: Initialization completed", self)

    def _getAttenuationModelByTransmission(self, t: Transmission) -> AttenuationModel:
        """
        Returns the attenuation model for this device and the sender of the
        passed transmission.
        """
        return self.channel.getAttenuationModel(self.device, t.sender)

    def _calculateReceivedPower(self, t: Transmission, attenuation = None) -> float:
        """
        Calculates the power that is received from a certain transmission.

        Args:
            t: The transmission to calculate the received power for
            attenuation: The attenuation between the sender and this Phy's
                device. If not provided, it will be requested by the corresponding
                attenuation model.
        """
        if attenuation is None:
            attenuation = self._getAttenuationModelByTransmission(t).attenuation
        return t.power - attenuation

    # Callbacks
    # The purpose of the following callbacks is to maintain a dict that maps
    # active transmissions to their received power. This is used to calculate
    # signal and noise levels.

    def _onAttenuationChange(self, t: Transmission, attenuation: float):
        """
        Callback that is invoked when the attenuation to the sender of
        `transmission` changes, providing the new attenuation value
        """
        newReceivedPower = self._calculateReceivedPower(t, attenuation)
        delta = self._transmissionToReceivedPowerDict[t] - newReceivedPower
        self._nReceivedLevelChanges.trigger(delta)
    
    def _onNewTransmission(self, t: Transmission):
        """
        Is called whenever a transmission starts
        """
        if t is not self._currentTransmission:
            receivedPower = self._calculateReceivedPower(t)
            self._transmissionToReceivedPowerDict[t] = receivedPower
            self._nReceivedLevelChanges.trigger(receivedPower)
            t.completes.callbacks.append(self._onCompletingTransmission)
            # subscribe to changes of attenuation for the transmission
            onAttenuationChange = partial(self._onAttenuationChange, t)
            self._transmissionToAttenuationChangedCallbackDict[t] = onAttenuationChange
            self._getAttenuationModelByTransmission(t).nAttenuationChanges.subscribeCallback(onAttenuationChange)
    
    def _onCompletingTransmission(self, t: Transmission):
        """
        Is called when a transmission completes
        """
        # Making sure the transmission has been added (this is not the case if
        # this Phy is the sender)
        if t in self._transmissionToReceivedPowerDict:
            receivedPower = self._transmissionToReceivedPowerDict.pop(t)
            self._nReceivedLevelChanges.trigger(-receivedPower)
            # unsubscribe from changes of attenuation for the transmission
            callback = self._transmissionToAttenuationChangedCallbackDict[t]
            self._getAttenuationModelByTransmission(t).nAttenuationChanges.unsubscribeCallback(callback)
    
    # SimPy generators

    @GateListener("mac", Signal, queued=True)
    def macGateListener(self, cmd):
        p = cmd.properties

        if cmd.type is StackSignals.SEND:
            logger.debug("%s: Received SEND command", self)
            # wait for the beginning of the next time slot
            yield SimMan.nextTimeSlot()
            # simulate transmitting
            self._transmitting = True
            t = self.channel.transmit(self.device, self.mcs, p["power"], p["bitrate"], p["bitrate"], p["packet"])
            self._currentTransmission = t
            # wait for the transmission to finish
            yield t.completes
            self._transmitting = False
            # indicate that the send command was processed
            cmd.setProcessed()
    
    def _receive(self, t: Transmission):
        # Simulates receiving via the channel
        if not self._transmitting:
            logger.debug("%s: Sensed a transmission.", self)

            currentBitRate = t.bitrateHeader
            bitErrorSum = 0
            lastLevelChange = SimMan.now

            # Callback for reacting to changes of the received level
            def onLevelChange(delta: float):
                nonlocal bitErrorSum
                if delta != 0:
                    # Calculate the duration for that the previous level was
                    # "constant"
                    now = SimMan.now
                    prevLevelDuration = now - lastLevelChange

                    # Calculate the bit error rate for that duration
                    signalLevel = self._transmissionToReceivedPowerDict[t]
                    noiseLevel = self._receivedLevel - signalLevel
                    prevBitErrorRate = t.mcs.calculateBitErrorRate(signalLevel, noiseLevel, currentBitRate)
                    
                    # Derive the number of bit errors for that duration
                    bitErrors = round(prevBitErrorRate * prevLevelDuration)
                    bitErrorSum += bitErrors
            
            self._nReceivedLevelChanges.subscribeCallback(onLevelChange)
            
            # Wait for the header to be transmitted
            yield t.headerCompletes

            # Update the bitrate for the payload
            currentBitRate = t.bitratePayload

            # Wait for the payload to be transmitted
            yield t.completes

            # Alright, we have the number of bit errors in bitErrorSum now!
            bitErrorRate = bitErrorSum / t.duration
            maxCorrectableBer = t.mcs.maxCorrectableBer()
            if bitErrorRate > maxCorrectableBer:
                logger.debug("%s: Packet received with uncorectable errors "
                             "(bit error rate: %6d, maximum correctable bit error rate: %6d)!",
                             self, bitErrorRate, maxCorrectableBer)
            else:
                logger.debug("%s: Packet successfully received (bit error rate: %6d)!",
                             self, bitErrorRate)
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
    def __init__(self, name: str, device: Device, addr: bytes):
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
    
    @GateListener("phy", Packet, queued=True)
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
                    self._receiveCmd.setProcessed(packet.payload)
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
    def __init__(self, name: str, device: Device):
        super(SimpleRrmMac, self).__init__(name, device)
        self._addGate("phy")
        self._addGate("transport")
        self.macAddress = bytes(6) # 6 zero bytes
        """bytes: The RRM's MAC address"""

        self._announcementBitrate = 16
        self._nAnnouncementReceived = Notifier("new announcement signal received", self)
        self._currentAssignSignal = None
        self._currentAssignReward = float('inf')
        self._nAnnouncementReceived.subscribeProcess(self._sendAnnouncement, queued=True)
    
    @GateListener("phy", Packet)
    def phyGateListener(self, packet: Packet):
        if packet.header.sourceMAC == self._currentAssignSignal.properties["dest"]:
            # packet was sent by the device mentioned in the current announcement
            # Use the object wrapped in the packet's trailer Transmittable as the reward
            reward = packet.trailer.obj
            logger.debug("%s: Extracted reward from %s: %d", self, packet.header.sourceMAC, reward)
            self._currentAssignReward = reward
            
    @GateListener("transport", Signal)
    def transportGateListener(self, signal: Signal):
        logger.debug("%s: Got new ASSIGN Signal %s.", self, signal)
        self._nAnnouncementReceived.trigger(signal)
    
    def _sendAnnouncement(self, assignSignal: Signal):
        """
        Is executed by the `_nAnnouncementReceived` notifier in a blocking and
        queued way for every assignSignal that is received on the `transport`
        gate.
        """
        self._currentAssignSignal = assignSignal

        destination = assignSignal.properties["dest"]
        duration = assignSignal.properties["duration"]
        announcement = Packet(
            SimpleMacHeader(self.macAddress, destination, flag=1),
            Transmittable(duration)
        )
        sendCmd = Signal(
            StackSignals.SEND,
            {"packet": announcement, "power": -20, "bitrate": self._announcementBitrate}
        )
        logger.debug("%s: Sending new announcement: %s", self, announcement)
        self.gates["phy"].output.send(sendCmd)
        yield sendCmd.processed
        yield SimMan.timeout(duration+1) # one extra time slot to prevent collisions

        # mark the current ASSIGN signal as processed and return the reward
        self._currentAssignSignal.setProcessed(self._currentAssignReward)
