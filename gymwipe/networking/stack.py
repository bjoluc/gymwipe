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
from gymwipe.networking.construction import Module, Port, PortListener
from gymwipe.networking.messages import (Message, Packet, SimpleMacHeader,
                                         StackMessages, Transmittable)
from gymwipe.networking.physical import (AttenuationModel, BpskMcs,
                                         FrequencyBand, FrequencyBandSpec, Mcs,
                                         Transmission, dbmToMilliwatts,
                                         milliwattsToDbm,
                                         temperatureToNoisePowerDensity,
                                         wattsToDbm)
from gymwipe.simtools import Notifier, SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

TIME_SLOT_LENGTH = 1e-6
"""
float: The length of one time slot in seconds (used for simulating slotted time)
"""

class StackLayer(Module):

    def __init__(self, name: str, device: Device):
        super(StackLayer, self).__init__(name)
        self.device = device
    
    def __repr__(self):
        return "{}.{}('{}')".format(repr(self.device), self.__class__.__name__, self.name)

class SimplePhy(StackLayer):
    """
    A phy layer implementation that does not take propagation delays into
    account. It provides a port called `mac` to be connected to a mac layer.
    Slotted time is used, with the length of a time slot being defined by
    :attr:`TIME_SLOT_LENGTH`.
    
    During simulation the frequency band is sensed and every successfully received
    packet is sent via the `mac` gate.

    The `mac` port accepts :class:`~gymwipe.networking.messages.Message` objects
    of the following types:

    * :attr:`~gymwipe.networking.messages.StackMessages.SEND`

        Send a specified packet on the frequency band.

        :class:`~gymwipe.networking.messages.Message` args:

        :packet: The :class:`~gymwipe.networking.messages.Packet` object
            representing the packet to be sent
        :power: The transmission power in dBm
        :mcs: The :class:`Mcs` object representing the MCS for the transmission
    """

    NOISE_POWER_DENSITY = temperatureToNoisePowerDensity(20.0)
    """float: The receiver's noise power density in Watts/Hertz"""

    @PortListener.setup
    def __init__(self, name: str, device: Device, frequencyBand: FrequencyBand):
        super(SimplePhy, self).__init__(name, device)
        self.frequencyBand = frequencyBand
        self._addPort("mac")

        # Attributes related to sending
        self._currentTransmission = None
        self._transmitting = False

        # Attributes related to receiving
        # thermal noise power in mW
        self._thermalNoisePower = self.NOISE_POWER_DENSITY * frequencyBand.spec.bandwidth * 1000
        self._transmissionToReceivedPowerDict: Dict[Transmission, float] = {}
        self._transmissionToAttenuationChangedCallbackDict = {}
        self._receivedPower = self._thermalNoisePower
        def updateReceivedPower(delta: float):
            self._receivedPower += delta
            logger.debug("%s: Received level changed by %s mW, updated to %s mW",
                            self, delta, self._receivedPower)
        self._nReceivedPowerChanges = Notifier("Received power changes", self)
        self._nReceivedPowerChanges.subscribeCallback(updateReceivedPower, priority=1)

        self.frequencyBand.nNewTransmission.subscribeCallback(self._onNewTransmission)
        self.frequencyBand.nNewTransmission.subscribeProcess(self._receive)
        logger.info("Initialized %s with noise power %s dBm", self, milliwattsToDbm(self._thermalNoisePower))

    def _getAttenuationModelByTransmission(self, t: Transmission) -> AttenuationModel:
        """
        Returns the attenuation model for this device and the sender of the
        transmission `t`.
        """
        return self.frequencyBand.getAttenuationModel(self.device, t.sender)

    def _calculateReceivedPower(self, t: Transmission, attenuation = None) -> float:
        """
        Calculates the power in mW that is received from a certain transmission.

        Args:
            t: The transmission to calculate the received power for
            attenuation: The attenuation between the sender's antenna and the
                antenna of this Phy's device. If not provided, it will be
                requested by the corresponding attenuation model.
        """
        if attenuation is None:
            attenuation = self._getAttenuationModelByTransmission(t).attenuation
        return dbmToMilliwatts(t.power - attenuation)

    # Callbacks
    # The purpose of the following callbacks is to maintain a dict that maps
    # active transmissions to their received power. This is used to calculate
    # signal and noise levels.

    def _onAttenuationChange(self, t: Transmission, attenuation: float):
        """
        Callback that is invoked when the attenuation to the sender of
        `transmission` changes, providing the new attenuation value
        """
        logger.debug("%s: Attenuation to the sender of %s changed to %s dB.", self, t, attenuation)
        newReceivedPower = self._calculateReceivedPower(t, attenuation)
        delta = newReceivedPower - self._transmissionToReceivedPowerDict[t]
        self._transmissionToReceivedPowerDict[t] = newReceivedPower
        self._nReceivedPowerChanges.trigger(delta)
    
    def _onNewTransmission(self, t: Transmission):
        """
        Is called whenever a transmission starts
        """
        if t is not self._currentTransmission:
            receivedPower = self._calculateReceivedPower(t)
            self._transmissionToReceivedPowerDict[t] = receivedPower
            logger.debug("%s: %s was added, received power from that "
                            "transmission: %s mW", self, t, receivedPower)
            self._nReceivedPowerChanges.trigger(receivedPower)
            t.eCompletes.callbacks.append(self._onCompletingTransmission)
            # subscribe to changes of attenuation for the transmission
            onAttenuationChange = partial(self._onAttenuationChange, t)
            self._transmissionToAttenuationChangedCallbackDict[t] = onAttenuationChange
            self._getAttenuationModelByTransmission(t).nAttenuationChanges.subscribeCallback(onAttenuationChange)
            
    def _onCompletingTransmission(self, event: Event):
        """
        Is called when a transmission from another device completes
        """
        t: Transmission = event.value
        assert t in self._transmissionToReceivedPowerDict
        receivedPower = self._transmissionToReceivedPowerDict[t]
        self._transmissionToReceivedPowerDict.pop(t)
        self._nReceivedPowerChanges.trigger(-receivedPower)
        # Unsubscribe from changes of attenuation for the transmission
        callback = self._transmissionToAttenuationChangedCallbackDict.pop(t)
        self._getAttenuationModelByTransmission(t).nAttenuationChanges.unsubscribeCallback(callback)
    
    # SimPy generators

    @PortListener("mac", Message, queued=True)
    def macPortListener(self, cmd):
        p = cmd.args

        if cmd.type is StackMessages.SEND:
            logger.info("Received SEND command", sender=self)
            # wait for the beginning of the next time slot
            yield SimMan.nextTimeSlot(TIME_SLOT_LENGTH)
            # simulate transmitting
            self._transmitting = True
            t = self.frequencyBand.transmit(self.device, p["power"],  p["packet"], p["mcs"], p["mcs"])
            self._currentTransmission = t
            # wait for the transmission to finish
            yield t.eCompletes
            self._transmitting = False
            # indicate that the send command was processed
            cmd.setProcessed()
    
    def _receive(self, t: Transmission):
        # Simulates receiving via the frequency band
        if not self._transmitting:
            logger.info("Sensed a transmission.", sender=self)

            currentMcs = t.mcsHeader
            bitErrorSum = 0
            currentBitErrorRate = 0.0
            lastErrorCountTime = SimMan.now

            def updateBitErrorRate():
                """
                Sets `bitErrorRate` to the current bit error rate for the
                transmission `t` if t has not yet completed.
                """
                nonlocal currentBitErrorRate
                signalPower = self._transmissionToReceivedPowerDict[t]
                noisePower = self._receivedPower - signalPower
                assert signalPower >= 0
                assert noisePower >= 0
                signalPowerDbm = milliwattsToDbm(signalPower)
                noisePowerDbm = milliwattsToDbm(noisePower)
                currentBitErrorRate = currentMcs.calculateBitErrorRate(signalPowerDbm, noisePowerDbm)
                logger.debug("Currently simulated bit error rate: " + str(currentBitErrorRate), sender=self)
            
            def countBitErrors():
                nonlocal bitErrorSum
                # Calculate the duration since last time that we counted errors
                now = SimMan.now
                duration = now - lastErrorCountTime

                # Derive the number of bit errors for that duration (still
                # as a float, rounding is done in the end)
                bitErrors = currentBitErrorRate * duration * currentMcs.bitRate
                bitErrorSum += bitErrors

            # Callback for reacting to changes of the received power
            def onReceivedPowerChange(delta: float):
                nonlocal bitErrorSum
                if delta != 0:
                    # Count bit errors for the duration in which the power was "constant"
                    countBitErrors()

                    if not t.completed:
                        # Update the bit error rate accordingly
                        updateBitErrorRate()
            
            self._nReceivedPowerChanges.subscribeCallback(onReceivedPowerChange)

            updateBitErrorRate() # Calculate initial bitErrorRate
            
            # Wait for the header to be transmitted
            yield t.eHeaderCompletes

            countBitErrors() # count errors since the last time that the received power has changed

            # Decide whether the header could be received
            if self._decide(bitErrorSum, t.headerBits, t.mcsHeader, logSubject="Header"):
                # Possibly switch MCS
                currentMcs = t.mcsPayload
                bitErrorSum = 0

                # Wait for the payload to be transmitted
                yield t.eCompletes
                self._nReceivedPowerChanges.unsubscribeCallback(onReceivedPowerChange)

                countBitErrors()
                # Decide whether the payload could be received
                logger.debug("{:.3} of {:.3} payload bits were errors.".format(bitErrorSum, t.payloadBits), sender=self)
                if self._decide(bitErrorSum, t.payloadBits, t.mcsPayload, logSubject="Payload"):
                    # sending the packet via the mac gate
                    self.ports["mac"].output.send(t.packet)
                else:
                    logger.info("Receiving transmission payload failed for %s", t, sender=self)
                
    def _decide(self, bitErrorSum, totalBits, mcs, logSubject = "Data") -> bool:
        """
        Returns ``True`` if `bitErrorSum` errors can be corrected for
        `totalBits` transmitted bits when applying `mcs`
        """
        bitErrorSum = round(bitErrorSum)
        bitErrorRate = bitErrorSum / totalBits
        maxCorrectableBer = mcs.maxCorrectableBer()
        if bitErrorRate <= maxCorrectableBer:
            logger.info("Decider: {} successfully received "
                            "(bit error rate: {:.3%})".format(logSubject, bitErrorRate), sender=self)
            return True
        else:
            logger.info("Decider: Data received with uncorectable errors "
                            "(bit error rate: {:.3%}, max. correctable "
                            "bit error rate: {:.3%})!".format(bitErrorRate, maxCorrectableBer), sender=self)
            return False
        

class SimpleMac(StackLayer):
    """
    A MAC layer implementation of the contention-free protocol described as
    follows:

        *   Every SimpleMac has a unique 6-byte-long MAC address.
        *   The MAC layer with address ``0`` is considered to belong to the RRM.
        *   Time slots are grouped into frames.
        *   Every second frame is reserved for the RRM and has a fixed length
            (number of time slots).
        *   The RRM uses those frames to send a short *announcement*
            containing a destination MAC address and the frame length (number of time slots
            **n**) of the following frame.
            By doing so it allows the specified device to use the frequency band for the
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

    The `transport` port accepts objects of the following types:

        * :class:`~gymwipe.networking.messages.Message`

            Types:

            * :attr:`~gymwipe.networking.messages.StackMessages.RECEIVE`

                Listen for packets sent to this device.

                :class:`~gymwipe.networking.messages.Message` args:

                :duration: The time in seconds to listen for

                When a packet destinated to this device is received, the
                :class:`~gymwipe.networking.messages.Message.eProcessed` event of the
                :class:`~gymwipe.networking.messages.Message` will be triggered providing the packet as the value.
                If the time given by `duration` has passed and no packet was received,
                it will be triggered with ``None``.

        * :attr:`~gymwipe.networking.messages.Packet`

            Send a given packet (with a :attr:`~gymwipe.networking.messages.SimpleNetworkHeader`) to the MAC address defined in the header.

    The `phy` port accepts objects of the following types:

        * :attr:`~gymwipe.networking.messages.Packet`

            A packet received by the physical layer
    """

    @PortListener.setup
    def __init__(self, name: str, device: Device, frequencyBandSpec: FrequencyBandSpec, addr: bytes):
        """
        Args:
            name: The layer's name
            device: The device that operates the SimpleMac layer
            addr: The 6-byte-long MAC address to be assigned to this MAC layer
        """
        super(SimpleMac, self).__init__(name, device)
        self._addPort("phy")
        self._addPort("transport")
        self.addr = addr
        self._packetQueue = deque(maxlen=100) # allow 100 packets to be queued
        self._packetAddedEvent = Event(SimMan.env)
        self._mcs = BpskMcs(frequencyBandSpec)
        self._transmissionPower = 0.0 # dBm
        self._receiving = False
        self._receiveCmd = None
        self._receiveTimeout = None
        
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)
    
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
    
    @PortListener("phy", Packet)
    def phyPortListener(self, packet):
        header = packet.header
        if not isinstance(header, SimpleMacHeader):
            raise ValueError("Can only deal with header of type SimpleMacHeader. Got %s.", type(header), sender=self)
        
        if header.destMAC == self.addr:
            # packet for us
            if header.sourceMAC == self.rrmAddr:
                # RRM sent the packet
                logger.debug("Received a packet from RRM: %s", packet, sender=self)
                if header.flag == 1:
                    # we may transmit
                    timeSlots = packet.payload.value
                    timeTotal = timeSlots*TIME_SLOT_LENGTH
                    stopTime = SimMan.now + timeTotal
                    def timeLeft():
                        return stopTime - SimMan.now
                    logger.info("Got permission to transmit for %d time slots", timeSlots, sender=self)

                    timeoutEvent = SimMan.timeout(timeTotal)
                    queuedPackets = True
                    while not timeoutEvent.processed:
                        if len(self._packetQueue) == 0:
                            queuedPackets = False
                            logger.debug("Packet queue empty, nothing to transmit. Time left: %s s", timeLeft(), sender=self)
                            yield self._packetAddedEvent | timeoutEvent
                            if not timeoutEvent.processed:
                                # new packet was added for sending
                                logger.debug("Packet queue was refilled. Time left: %s s", timeLeft(), sender=self)
                                queuedPackets = True
                        if queuedPackets:
                            if not timeLeft() > self._packetQueue[0].transmissionTime(self._mcs.dataRate):
                                logger.info("Next packet is too large to be transmitted. Idling. Time left: %s s", timeLeft(), sender=self)
                                yield timeoutEvent
                            else:
                                # enough time left to transmit the next packet
                                # TODO This has to be done before adding the
                                # packet to the queue!
                                packet = self._packetQueue.popleft()
                                message = Message(StackMessages.SEND, {
                                    "packet": packet,
                                    "power": self._transmissionPower,
                                    "mcs": self._mcs
                                })
                                self.ports["phy"].output.send(message) # make the PHY send the packet
                                logger.debug("Transmitting packet. Time left: %s", timeLeft(), sender=self)
                                logger.debug("Packet: %s", packet, sender=self)
                                yield message.eProcessed # wait until the transmission has completed
            else:
                # packet from any other device
                if self._receiving:
                    logger.info("Received Packet.", sender=self)
                    logger.debug("Packet: %s", packet.payload, sender=self)
                    # return the packet's payload to the transport layer
                    self._receiveCmd.setProcessed(packet.payload)
                    self._stopReceiving()
                else:
                    logger.debug("Received Packet from Phy, but not in receiving mode. Packet ignored.", sender=self)

        elif header.destMAC == self.rrmAddr:
            # packet from RRM to all devices
            pass
    
    @PortListener("transport", (Message, Packet))
    def transportPortListener(self, cmd):

        if isinstance(cmd, Message):
            if cmd.type is StackMessages.RECEIVE:
                logger.debug("%s: Entering receive mode.", self)
                # start receiving
                self._receiveCmd = cmd
                # set _receiving and a timeout event
                self._receiving = True
                self._receiveTimeout = SimMan.timeout(cmd.args["duration"])
                self._receiveTimeout.callbacks.append(self._receiveTimeoutCallback)

        elif isinstance(cmd, Packet):
            payload = cmd
            packet = Packet(
                SimpleMacHeader(self.addr, payload.header.destMAC, flag=0),
                payload
            )
            self._packetQueue.append(packet)
            self._packetAddedEvent.succeed()
            self._packetAddedEvent = Event(SimMan.env)
    
    def _receiveTimeoutCallback(self, event: Event):
        if event is self._receiveTimeout:
            # the current receive message has timed out
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

    The `transport` port accepts objects of the following types:

        * :class:`~gymwipe.networking.messages.Message`

        Types:

            * :attr:`~gymwipe.networking.messages.StackMessages.ASSIGN`

                Send a frequency band assignment announcement that permits a device
                to transmit for a certain time.

                :class:`~gymwipe.networking.messages.Message` args:

                :dest: The 6-byte-long MAC address of the device to be allowed to transmit

                :duration: The number of time steps to assign the frequency band for the specified device
    
    The payloads of packets from other devices are outputted via the `transport`
    gate, regardless of their destination address. This enables an interpreter
    to extract observations and rewards for a frequency band assignment learning agent.
    """

    @PortListener.setup
    def __init__(self, name: str, device: Device, frequencyBandSpec: FrequencyBandSpec):
        super(SimpleRrmMac, self).__init__(name, device)
        self._addPort("phy")
        self._addPort("transport")
        self.addr = bytes(6) # 6 zero bytes
        """bytes: The RRM's MAC address"""

        self._announcementMcs = BpskMcs(frequencyBandSpec)
        self._transmissionPower = 0.0 # dBm
        self._nAnnouncementReceived = Notifier("new announcement message received", self)
        self._nAnnouncementReceived.subscribeProcess(self._sendAnnouncement, queued=True)
        
        logger.debug("%s: Initialization completed, MAC address: %s", self, self.addr)
    
    @PortListener("phy", Packet)
    def phyPortListener(self, packet: Packet):
        self.ports["transport"].output.send(packet.payload)
    
    @PortListener("transport", Message)
    def transportPortListener(self, message: Message):
        logger.debug("%s: Got new ASSIGN Message %s.", self, message)
        self._nAnnouncementReceived.trigger(message)
    
    def _sendAnnouncement(self, assignMessage: Message):
        """
        Is executed by the `_nAnnouncementReceived` notifier in a blocking and
        queued way for every assignMessage that is received on the `transport`
        gate.
        """
        destination = assignMessage.args["dest"]
        duration = assignMessage.args["duration"]
        announcement = Packet(
            SimpleMacHeader(self.addr, destination, flag=1),
            Transmittable(duration)
        )
        sendCmd = Message(
            StackMessages.SEND, {
                "packet": announcement,
                "power": self._transmissionPower,
                "mcs": self._announcementMcs
            }
        )
        logger.debug("%s: Sending new announcement: %s", self, announcement)
        self.ports["phy"].output.send(sendCmd)
        yield sendCmd.eProcessed
        yield SimMan.timeout((duration+1)*TIME_SLOT_LENGTH) # one extra time slot to prevent collisions

        # mark the current ASSIGN message as processed
        assignMessage.setProcessed()
