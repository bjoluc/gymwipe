""" 
    Contains different MAC layer implementations
"""
import logging

from simpy.events import Event

from gymwipe.control.scheduler import Schedule, TDMAEncode
from gymwipe.devices import Device
from gymwipe.networking.construction import GateListener, Module
from gymwipe.networking.mac_headers import NCSMacHeader
from gymwipe.networking.messages import (Message, Packet, StackMessageTypes,
                                         Transmittable)
from gymwipe.networking.physical import BpskMcs, FrequencyBandSpec
from gymwipe.simtools import Notifier, SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

macCounter = 0 #global mac counter


TIME_SLOT_LENGTH = 1e-6
"""
float: The length of one time slot in seconds (used for simulating slotted time)
"""

def newUniqueMacAddress() -> bytes:
        """
        A method for generating unique 6-byte-long MAC addresses (currently counting upwards starting at 1)
        """
        global macCounter
        macCounter += 1
        addr = bytearray(6)
        addr[5] = macCounter
        logger.debug("New mac requested")
        return bytes(addr)



class SensorMac(Module):
    """
        A sensor's mac layer implementation using a :class:`~gymwipe.control.scheduler.TDMASchedule` object.
        It sends its most recent sensordata if the next timeslot is reserved according to the schedule.

    """

    @GateListener.setup
    def __init__(self, name: str, device: Device,frequencyBandSpec: FrequencyBandSpec, addr: bytes):
        super(SensorMac, self).__init__(name , owner=device)
        self._addPort("phy")
        self._addPort("network")
        self.addr = addr
        self._packetAddedEvent = Event(SimMan.env)
        self._schedule = None
        self._lastDatapacket = None
        self._packetAddedEvent = Event(SimMan.env)
        self._transmissionPower = 0.0 # dBm
        self._mcs = BpskMcs(frequencyBandSpec)
        self._receiving = False
        self._receiveCmd = None
        self._receiveTimeout = None
        """
        The most recent clock signal sent by the gateway. Is sent within a scheduling Packet.
        """
        self._lastGatewayClock = 0
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", Packet, queued=True)
    def phyInGateListener(self, packet: Packet):
        header = packet.header
        if not isinstance(header, NCSMacHeader):
            raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header), sender=self)
        if header.type[0] == 0: # received schedule from gateway
            self._schedule = packet.payload.value
            self.gatewayAdress = header.sourceMAC
            logger.debug("received a schedule: %s", packet , sender=self)

    @GateListener("networkIn",(Message, Packet), queued = False)
    def networkInGateListener(self, cmd):
        if isinstance(cmd, Packet):
            payload = packet.payload
            sensorSendingType = bytearray(1)
            sensorSendingType[0] = 1
            packet = Packet(NCSMacHeader(sensorSendingType, self.addr), payload)
            self._lastDatapacket = packet
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


class ActuatorMacTDMA(Module):
    """
        An actuator's mac layer implementation using a :class:`~gymwipe.control.scheduler.TDMASchedule` object.
    """

    @GateListener.setup
    def __init__(self, name: str, device: Device, frequencyBandSpec: FrequencyBandSpec, addr: bytes):
        super(ActuatorMacTDMA, self).__init__(name , owner=device)
        self._addPort("phy")
        self._addPort("network")
        self.addr = addr
        self._lastDatapacket = None
        self._packetAddedEvent = Event(SimMan.env)
        self._mcs = BpskMcs(frequencyBandSpec)
        self._transmissionPower = 0.0 # dBm
        self._receiving = False
        self._receiveCmd = None
        self._receiveTimeout = None
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", Packet, queued=True)
    def phyInGateListener(self, packet: Packet):
        header = packet.header
        if not isinstance(header, NCSMacHeader):
            raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header), sender=self)
        if header.type[0] == 0: # received schedule from gateway
            self.schedule = packet.payload.value
            self.gatewayAdress = header.sourceMAC
            logger.debug("received a schedule", sender=self)
        if header.type[0] == 1: # received sensordata
            if header.destMAC == self.addr: #sensordata is for me
                logger.debug("received relevant sensordata", sender=self)
                self.gates["networkOut"].send(packet.payload)

    @GateListener("networkIn",(Message, Packet), queued = True)
    def networkInGateListener(self, cmd):
        if isinstance(cmd, Message):
            if cmd.type is StackMessageTypes.RECEIVE:
                logger.debug("%s: Entering receive mode.", self)
                # start receiving
                self._receiveCmd = cmd
                # set _receiving and a timeout event
                self._receiving = True
                self._receiveTimeout = SimMan.timeout(cmd.args["duration"])
                self._receiveTimeout.callbacks.append(self._receiveTimeoutCallback)

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




class GatewayMac(Module):
    """
        A gateway's mac layer implementation
    """

    @GateListener.setup
    def __init__(self, name: str, device: Device, frequencyBandSpec: FrequencyBandSpec, addr: bytes):
        super(GatewayMac, self).__init__(name , owner=device)
        self._addPort("phy")
        self._addPort("network")
        self.addr = addr

        self._mcs = BpskMcs(frequencyBandSpec)
        self._transmissionPower = 0.0 # dBm
        self._nControlReceived = Notifier("New control message received", self)
        self._nControlReceived.subscribeProcess(self._sendControl, queued= True)
        self._nAnnouncementReceived = Notifier("new schedule message received", self)
        self._nAnnouncementReceived.subscribeProcess(self._sendAnnouncement, queued=True)
        self._receivingMode = False
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", Packet, queued=True)
    def phyInGateListener(self, packet: Packet):
        header = packet.header
        if not isinstance(header, NCSMacHeader):
            raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header), sender=self)
        messageType = header.type[0]
        if messageType == 1: #received sensordata
            pass
        if messageType == 2: #received Actuator ACK
            pass

    @GateListener("networkIn", Message)
    def networkInGateListener(self, cmd: Message):       
        if cmd.type is StackMessageTypes.SEND:
            logger.debug("%s: Got the schedule %s.", self, cmd)
            self._nAnnouncementReceived.trigger(cmd)

        if cmd.type is StackMessageTypes.SENDCONTROL:
            logger.debug("%s: Got the control message %s.", self, cmd)
            self._nControlReceived.trigger(cmd)

    def _sendControl(self, message: Message):
        """
        Is executed by the `_nAnnouncementReceived` notifier in a blocking and
        queued way for every control Packet that is received on the `networkIn`
        gate.
        """
        control = message.args["control"]
        receiver = message.args["receiver"]
        type = bytearray(1)
        type[0] = 2
        controlpacket = Packet(
            NCSMacHeader(bytes(type),self.addr, receiver),
            Transmittable(control)
        )
        sendCmd = Message(
            StackMessageTypes.SEND, {
                "packet": controlpacket,
                "power": self._transmissionPower,
                "mcs": self._mcs
            }
        )
        logger.debug("%s: Sending control: %s", self, controlpacket)
        self.gates["phyOut"].send(sendCmd)
        yield sendCmd.eProcessed

    def _sendAnnouncement(self, message: Message):
        """
        Is executed by the `_nAnnouncementReceived` notifier in a blocking and
        queued way for every schedule Packet that is received on the `networkIn`
        gate.
        """
        schedule = message.args["schedule"]
        type = bytearray(1)
        type[0] = 0
        announcement = Packet(
            NCSMacHeader(bytes(type),self.addr),
            Transmittable(schedule, TDMAEncode(schedule, False))
        )
        sendCmd = Message(
            StackMessageTypes.SEND, {
                "packet": announcement,
                "power": self._transmissionPower,
                "mcs": self._mcs
            }
        )
        logger.debug("%s: Sending schedule: %s", self, announcement)
        self.gates["phyOut"].send(sendCmd)
        yield sendCmd.eProcessed
