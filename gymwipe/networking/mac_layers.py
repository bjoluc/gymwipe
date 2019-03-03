""" 
    Contains different MAC layer implementations
"""
import logging
import random
from simpy.events import Event

from gymwipe.control.scheduler import tdma_encode, CSMASchedule, CSMAControllerSchedule
from gymwipe.devices import Device
from gymwipe.networking.construction import GateListener, Module
from gymwipe.networking.mac_headers import NCSMacHeader
from gymwipe.networking.messages import (Message, Packet, StackMessageTypes,
                                         Transmittable)
from gymwipe.networking.physical import BpskMcs, FrequencyBandSpec
from gymwipe.simtools import Notifier, SimMan, SimTimePrepender

from gymwipe.baSimulation.constants import TIMESLOT_LENGTH, ProtocolType, PROTOCOL, Configuration

logger = SimTimePrepender(logging.getLogger(__name__))

macCounter = 0 #global mac counter


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
    def __init__(self, name: str, device: Device,frequencyBandSpec: FrequencyBandSpec, addr: bytes,
                 configuration: Configuration):
        super(SensorMac, self).__init__(name, owner=device)
        self._addPort("phy")
        self._addPort("network")

        self.configuration = configuration

        self.addr = addr
        self._schedule = None
        self._lastDatapacket = None
        self._nScheduleAdded = Notifier("new schedule received", self)
        self._nScheduleAdded.subscribeProcess(self._send_data, queued=False)
        self._transmissionPower = 0.0 # dBm
        self._mcs = BpskMcs(frequencyBandSpec)
        self._receiving = True
        self.gateway_address = None
        self._network_cmd: Message = None

        self._nNewP = Notifier("new p received", self)
        self._nNewP.subscribeProcess(self._send_data, queued=False)

        self._next_receive_time = 0
        self.error_rates = []
        """
        The most recent clock signal sent by the gateway. Is sent within a scheduling Packet.
        """
        self._lastGatewayClock = 0
        self.received_schedule_count = 0
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", (Message))
    def phyInGateListener(self, msg):

        if self._receiving is True:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                logger.debug("received a packet from phy, am in receiving mode", sender=self)
                header = msg.args["packet"].header
                if not isinstance(header, NCSMacHeader):
                    raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header))
                if header.type[0] == 0:  # received schedule from gateway
                    self._schedule = msg.args["packet"].payload.value
                    trailer = msg.args["packet"].trailer.value
                    self._lastGatewayClock = trailer
                    logger.debug("gateway clock is %f", self._lastGatewayClock, sender=self)
                    self.gateway_address = header.sourceMAC
                    self._nScheduleAdded.trigger(msg)
                    schedulestr = self._schedule.get_string()
                    self.received_schedule_count += 1
                    if self.configuration.show_error_rates:
                        self.error_rates.append(msg.args["error_rate"])
                    logger.debug("received a schedule: gateway clock: %s schedule: %s", self._lastGatewayClock.__str__(),
                                 schedulestr, sender=self)
                    # TODO: save csi, given by phy
                else:
                    pass
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                logger.debug("received a packet from phy, am in receiving mode", sender=self)
                header = msg.args["packet"].header
                if not isinstance(header, NCSMacHeader):
                    raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header))
                if header.type[0] == 0:  # received schedule from gateway
                    schedule = msg.payload.value
                    if not isinstance(schedule, CSMASchedule):
                        raise ValueError("Can only deal with schedule of type CSMASchedule. Got %s.", type(schedule))
                    logger.debug("received new p value", sender=self)
                    self._lastGatewayClock = msg.trailer.value
                    logger.debug("gateway clock is %f", self._lastGatewayClock, sender=self)
                    self._next_receive_time = schedule.get_end_time()
                    self.gateway_address = header.sourceMAC
                    self.received_schedule_count += 1
                    self._nNewP.trigger(schedule.get_my_p(self.addr))

                    # TODO: save csi, given by phy
                else:
                    pass
        else:
            logger.debug("received a packet from phy, but not in receiving mode. packet ignored", sender=self)
            pass

    @GateListener("networkIn", (Message, Packet), queued=False)
    def networkInGateListener(self, cmd):
        if isinstance(cmd, Message):
            if cmd.type is StackMessageTypes.SEND:
                self._network_cmd = cmd
                data = cmd.args["state"]
                sensorsendingtype = bytearray(1)
                sensorsendingtype[0] = 1
                datapacket = Packet(
                    NCSMacHeader(bytes(sensorsendingtype), self.addr),
                    Transmittable(data, 4)
                )
                self._lastDatapacket = datapacket
                logger.debug("%s received new sensordata: %s , saved it", self, data)

    def _stop_receiving(self):
        logger.debug("%s: Stopping to receive.", self)
        self._receiving = False

    def _start_receiving(self):
        logger.debug("%s: Starting to receive.", self)
        self._receiving = True

    def _send_data(self, arg):
        if self.configuration.protocol_type == ProtocolType.TDMA:
            self._stop_receiving()
            relevant_span = self._schedule.get_next_relevant_timespan(self.addr, 0)
            while relevant_span is not None:
                logger.debug("%s: next relevant timespan is [%d, %d]", self, relevant_span[0], relevant_span[1])
                for i in range(relevant_span[0], relevant_span[1]):
                    yield SimMan.timeoutUntil(self._lastGatewayClock + i*TIMESLOT_LENGTH)
                    # TODO: put csi in packet
                    send_cmd = Message(
                        StackMessageTypes.SEND, {
                            "packet": self._lastDatapacket,
                            "power": self._transmissionPower,
                            "mcs": self._mcs
                        }
                    )
                    self.gates["phyOut"].send(send_cmd)
                    logger.debug("Transmitting data. Schedule timestep %d", i, sender=self)
                    yield send_cmd.eProcessed
                    self._network_cmd.setProcessed()
                relevant_span = self._schedule.get_next_relevant_timespan(self.addr, relevant_span[1])
            self._start_receiving()
        elif self.configuration.protocol_type == ProtocolType.CSMA:
            logger.debug("my p is %f", arg, sender=self)
            current_slot = 1
            while current_slot < self._next_receive_time:
                yield SimMan.timeoutUntil(self._lastGatewayClock + current_slot * TIMESLOT_LENGTH)
                ask_cmd = Message(
                    StackMessageTypes.ISRECEIVING
                )
                self.gates["phyOut"].send(ask_cmd)
                channel_blocked = yield ask_cmd.eProcessed
                if not channel_blocked:
                    logger.debug("channel is free", sender=self)
                    decide = random.random()
                    if decide <= arg:  # send
                        logger.debug("will send now, decide value was %f", decide, sender=self)
                        self._stop_receiving()
                        send_cmd = Message(
                            StackMessageTypes.SEND, {
                                "packet": self._lastDatapacket,
                                "power": self._transmissionPower,
                                "mcs": self._mcs
                            }
                        )
                        self.gates["phyOut"].send(send_cmd)
                        logger.debug("Transmitting data. Schedule timestep %d", current_slot, sender=self)
                        yield send_cmd.eProcessed
                        self._start_receiving()
                        self._network_cmd.setProcessed()
                    else:  # dont send
                        logger.debug("Passing this timestep. Schedule timestep %d", current_slot, sender=self)

                else:
                    logger.debug("channel is not free", sender=self)
                current_slot += 1


class ActuatorMac(Module):
    """
        An actuator's mac layer implementation using a :class:`~gymwipe.control.scheduler.TDMASchedule` object.
    """

    @GateListener.setup
    def __init__(self, name: str, device: Device, frequencyBandSpec: FrequencyBandSpec, addr: bytes,
                 configuration: Configuration):
        super(ActuatorMac, self).__init__(name, owner=device)
        self._addPort("phy")
        self._addPort("network")

        self.configuration = configuration
        self.addr = addr
        self._mcs = BpskMcs(frequencyBandSpec)
        self._transmissionPower = 0.0 # dBm
        self._receiving = True
        self.schedule = None
        self.gatewayAdress = None
        self._n_control_received = Notifier("new schedule received", self)
        self._n_control_received.subscribeProcess(self._sendcsi, queued=False)
        self._lastGatewayClock = 0
        self.schedule_received_count = 0
        self.error_rates_schedule = []
        self.error_rates_control = []
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", Message)
    def phyInGateListener(self, cmd):
        if self._receiving:
            header = cmd.args["packet"].header
            if not isinstance(header, NCSMacHeader):
                raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header), sender=self)
            if header.type[0] == 0: # received schedule from gateway
                self.schedule = cmd.args["packet"].payload.value
                self._lastGatewayClock = cmd.args["packet"].trailer.value
                self.gatewayAdress = header.sourceMAC
                logger.debug("received a schedule, gateway clock is %f", self._lastGatewayClock, sender=self)
                self.schedule_received_count += 1
                if self.configuration.show_error_rates:
                    self.error_rates_schedule.append(cmd.args["error_rate"])
            if header.type[0] == 2: #received control message
                # TODO: check if timeslot is mine, not if addr is mine
                if header.destMAC == self.addr:  # message for me
                    logger.debug("received control message", sender=self)
                    if self.configuration.show_error_rates:
                        self.error_rates_control.append(cmd.args["error_rate"])
                    self.gates["networkOut"].send(cmd.args["packet"].payload)
                    self._n_control_received.trigger(cmd)

    @GateListener("networkIn", (Message, Packet))
    def networkInGateListener(self, cmd):
        if isinstance(cmd, Message):
            pass

    def _sendcsi(self, packet):
        self._stopReceiving()
        csisendingtype = bytearray(1)
        csisendingtype[0] = 2
        sendPackage = Packet(NCSMacHeader(csisendingtype, self.addr, self.gatewayAdress), Transmittable("TODO: send csi", 1 ))
        # TODO: send csi, will be in packet
        send_cmd = Message(
            StackMessageTypes.SEND, {
                "packet": sendPackage,
                "power": self._transmissionPower,
                "mcs": self._mcs
            }
        )
        self.gates["phyOut"].send(send_cmd)
        logger.debug("sending csi back", sender=self)
        yield send_cmd.eProcessed
        self._start_receiving()

    def _stopReceiving(self):
        logger.debug("%s: Stopping to receive.", self)
        self._receiving = False

    def _start_receiving(self):
        logger.debug("%s: Starting to receive.", self)
        self._receiving = True


class GatewayMac(Module):
    """
        A gateway's mac layer implementation
    """

    @GateListener.setup
    def __init__(self, name: str,
                 device: Device,
                 frequencyBandSpec: FrequencyBandSpec,
                 addr: bytes,
                 configuration: Configuration):
        super(GatewayMac, self).__init__(name, owner=device)
        self._addPort("phy")
        self._addPort("network")
        self.addr = addr

        self.configuration = configuration

        self._mcs = BpskMcs(frequencyBandSpec)
        self._transmissionPower = 0.0 # dBm
        self._nControlReceived = Notifier("New control message received", self)
        self._nControlReceived.subscribeProcess(self._sendControl, queued=True)
        self._nAnnouncementReceived = Notifier("new schedule message received", self)
        self._nAnnouncementReceived.subscribeProcess(self._sendAnnouncement, queued=True)
        self._nAnnouncementReceived.subscribeProcess(self._handle_controller_schedule)
        self._receivingMode = True
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    def _stop_receiving(self):
        logger.debug("%s: Stopping to receive.", self)
        self._receivingMode = False

    def _start_receiving(self):
        logger.debug("%s: Starting to receive.", self)
        self._receivingMode = True

    @GateListener("phyIn", Message)
    def phyInGateListener(self, cmd: Message):
        if self._receivingMode is True:
            logger.debug("%s: received a packet", self)
            packet = cmd.args["packet"]
            header = packet.header
            if not isinstance(header, NCSMacHeader):
                raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header), sender=self)
            message_type = header.type[0]
            if message_type == 1: #received sensordata
                logger.debug("received sensordata from %s. data is %s", header.sourceMAC, packet.payload.value, sender=self)
                receive_message = Message(
                    StackMessageTypes.RECEIVED, {
                        "sender": header.sourceMAC,
                        "state": packet.payload.value,
                        "csisensor": "TODO",
                        "csigateway": "TODO"
                    }
                )
                self.gates["networkOut"].send(receive_message)
                # TODO: csi integration
            if message_type == 2: #received Actuator ACK
                logger.debug("received actuator csi from %s. csi is %s", header.sourceMAC, packet.payload.value, sender=self)
                receive_message = Message(
                    StackMessageTypes.RECEIVED, {
                        "sender": header.sourceMAC,
                        "csiactuator": packet.payload.value,
                        "csigateway": "TODO"
                    }
                )
                # TODO: add gateway csi
                self.gates["networkOut"].send(receive_message)

    @GateListener("networkIn", Message)
    def networkInGateListener(self, message: Message):
        if message.type is StackMessageTypes.SEND:
            logger.debug("%s: Got the schedule %s.", self, message)
            self._nAnnouncementReceived.trigger(message)

        if message.type is StackMessageTypes.SENDCONTROL:
            logger.debug("%s: Got the control message %s.", self, message)
            self._nControlReceived.trigger(message)

    def _handle_controller_schedule(self, message: Message):
        if self.configuration.protocol_type == ProtocolType.CSMA:
            controller_schedule: CSMAControllerSchedule = message.args["controller_schedule"]
            sensor_schedule: CSMASchedule = message.args["schedule"]
            gateway_p = sensor_schedule.get_my_p(self.addr)
            current_slot = 1
            while current_slot < sensor_schedule.get_end_time():
                yield SimMan.timeoutUntil(SimMan.now + current_slot * TIMESLOT_LENGTH)
                ask_cmd = Message(
                    StackMessageTypes.ISRECEIVING
                )
                self.gates["phyOut"].send(ask_cmd)
                channel_blocked = yield ask_cmd.eProcessed
                if not channel_blocked:
                    logger.debug("channel is free", sender=self)
                    decide = random.random()
                    if decide <= gateway_p:  # send
                        logger.debug("will send now, decide value was %f", decide, sender=self)
                        self._stop_receiving()
                        controller_decide = random.randrange(0, 1)
                        controller = controller_schedule.get_chosen_controller(controller_decide)
                        send_cmd = Message(
                            StackMessageTypes.SEND, {
                                "packet": self._lastDatapacket,
                                "power": self._transmissionPower,
                                "mcs": self._mcs
                            }
                        )
                        self.gates["phyOut"].send(send_cmd)
                        logger.debug("Transmitting data. Schedule timestep %d", current_slot, sender=self)
                        yield send_cmd.eProcessed
                        self._start_receiving()
                        self._network_cmd.setProcessed()
                    else:  # dont send
                        logger.debug("Passing this timestep. Schedule timestep %d", current_slot, sender=self)

                else:
                    logger.debug("channel is not free", sender=self)
                current_slot += 1

    def _sendControl(self, message: Message):
        """
        Is executed by the `_nAnnouncementReceived` notifier in a blocking and
        queued way for every control Packet that is received on the `networkIn`
        gate.
        """
        self._stop_receiving()
        control = message.args["control"]
        receiver = message.args["receiver"]
        type = bytearray(1)
        type[0] = 2
        controlpacket = Packet(
            NCSMacHeader(bytes(type), self.addr, receiver),
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
        message.setProcessed()
        self._start_receiving()

    def _sendAnnouncement(self, message: Message):
        """
        Is executed by the `_nAnnouncementReceived` notifier in a blocking and
        queued way for every schedule that is received on the `networkIn`
        gate.
        """
        self._stop_receiving()
        schedule = message.args["schedule"]
        clock = message.args["clock"]
        type = bytearray(1)
        type[0] = 0 # schedule
        announcement = Packet(
            NCSMacHeader(bytes(type), self.addr),
            Transmittable(schedule, tdma_encode(schedule)),
            Transmittable(clock)
        )
        sendCmd = Message(
            StackMessageTypes.SEND, {
                "packet": announcement,
                "power": self._transmissionPower,
                "mcs": self._mcs
            }
        )
        logger.debug("%s: Sending schedule: %s", self, announcement.payload.value.get_string())
        self.gates["phyOut"].send(sendCmd)
        yield sendCmd.eProcessed
        message.setProcessed()
        self._start_receiving()
