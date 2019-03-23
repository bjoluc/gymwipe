""" 
    Contains different MAC layer implementations
"""
import logging
import math
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

from gymwipe.baSimulation.constants import ProtocolType, Configuration

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
        self._schedule_error = 0.0
        self._lastState = None
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
        self.biterror_sums = []
        """
        The most recent clock signal sent by the gateway. Is sent within a scheduling Packet.
        """
        self._lastGatewayClock = 0
        self.received_schedule_count = 0
        self.send_data_count = 0

        self.assigned_ps = []
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", Message)
    def phyInGateListener(self, msg):
        if msg.type == StackMessageTypes.RECEIVED:
            if self._receiving is True:
                if self.configuration.protocol_type == ProtocolType.TDMA:
                    logger.debug("received a packet from phy, am in receiving mode", sender=self)
                    header = msg.args["packet"].header
                    if not isinstance(header, NCSMacHeader):
                        raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header))
                    if header.type[0] == 0:  # received schedule from gateway
                        self._schedule = msg.args["packet"].payload.value
                        self._schedule_error = msg.args["error_rate"]
                        trailer = msg.args["packet"].trailer.value
                        self._lastGatewayClock = trailer
                        logger.debug("gateway clock is %f", self._lastGatewayClock, sender=self)
                        self.gateway_address = header.sourceMAC
                        self._nScheduleAdded.trigger(msg)
                        schedulestr = self._schedule.get_string()
                        self.received_schedule_count += 1
                        if self.configuration.show_error_rates:
                            self.error_rates.append(msg.args["error_rate"])
                            self.biterror_sums.append(msg.args["biterrors"])
                        logger.debug("received a schedule: gateway clock: %s schedule: %s", self._lastGatewayClock.__str__(),
                                     schedulestr, sender=self)
                    else:
                        pass
                elif self.configuration.protocol_type == ProtocolType.CSMA:
                    logger.debug("received a packet from phy, am in receiving mode", sender=self)
                    header = msg.args["packet"].header
                    if not isinstance(header, NCSMacHeader):
                        raise ValueError("Can only deal with header of type NCSMacHeader. Got %s.", type(header))
                    if header.type[0] == 0:  # received schedule from gateway
                        schedule = msg.args["packet"].payload.value
                        self._schedule_error = msg.args["error_rate"]
                        if not isinstance(schedule, CSMASchedule):
                            raise ValueError("Can only deal with schedule of type CSMASchedule. Got %s.", type(schedule))
                        logger.debug("received new p value", sender=self)
                        self._lastGatewayClock = msg.args["packet"].trailer.value
                        logger.debug("gateway clock is %f", self._lastGatewayClock, sender=self)
                        self._next_receive_time = schedule.get_end_time()
                        self.gateway_address = header.sourceMAC
                        self.received_schedule_count += 1
                        if self.configuration.show_error_rates:
                            self.error_rates.append(msg.args["error_rate"])
                            self.biterror_sums.append(msg.args["biterrors"])
                        self._nNewP.trigger(schedule.get_my_p(self.addr))
                    else:
                        pass
            else:
                logger.debug("received a packet from phy, but not in receiving mode. packet ignored", sender=self)
                pass

        if msg.type == StackMessageTypes.FAILED:
            self.error_rates.append(msg.args["error_rate"])
            self.biterror_sums.append(msg.args["biterrors"])

    @GateListener("networkIn", (Message, Packet), queued=False)
    def networkInGateListener(self, cmd):
        if isinstance(cmd, Message):
            if cmd.type is StackMessageTypes.SEND:
                data = cmd.args["state"]
                self._lastState = data
                cmd.setProcessed()
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
                    yield SimMan.timeoutUntil(self._lastGatewayClock + i*self.configuration.timeslot_length)
                    sensorsendingtype = bytearray(1)
                    sensorsendingtype[0] = 1
                    datapacket = Packet(
                        NCSMacHeader(self.configuration.protocol_type, bytes(sensorsendingtype), self.addr),
                        Transmittable([self._lastState, self._schedule_error], 6)
                    )
                    send_cmd = Message(
                        StackMessageTypes.SEND, {
                            "packet": datapacket,
                            "power": self._transmissionPower,
                            "mcs": self._mcs
                        }
                    )
                    self.gates["phyOut"].send(send_cmd)
                    logger.debug("Transmitting data. Schedule timestep %d", i, sender=self)
                    yield send_cmd.eProcessed
                    self.send_data_count += 1
                relevant_span = self._schedule.get_next_relevant_timespan(self.addr, relevant_span[1])
            self._start_receiving()
        elif self.configuration.protocol_type == ProtocolType.CSMA:
            logger.debug("my p is %f", arg, sender=self)
            self.assigned_ps.append(arg)
            current_slot = 1
            while current_slot < self._next_receive_time:
                yield SimMan.timeoutUntil(self._lastGatewayClock + current_slot * self.configuration.timeslot_length)
                ask_cmd = Message(
                    StackMessageTypes.ISRECEIVING
                )
                self.gates["phyOut"].send(ask_cmd)
                channel_blocked = yield ask_cmd.eProcessed
                if not channel_blocked:
                    if self._lastState is not None: # send datapacket just once
                        logger.debug("channel is free", sender=self)
                        decide = random.random()
                        if decide <= arg:  # send
                            logger.debug("will send now, decide value was %f", decide, sender=self)
                            self._stop_receiving()
                            sensorsendingtype = bytearray(1)
                            sensorsendingtype[0] = 1
                            datapacket = Packet(
                                NCSMacHeader(self.configuration.protocol_type, bytes(sensorsendingtype), self.addr),
                                Transmittable([self._lastState, self._schedule_error], 6)
                            )
                            send_cmd = Message(
                                StackMessageTypes.SEND, {
                                    "packet": datapacket,
                                    "power": self._transmissionPower,
                                    "mcs": self._mcs
                                }
                            )
                            self.gates["phyOut"].send(send_cmd)
                            logger.debug("Transmitting data. Schedule timestep %d", current_slot, sender=self)
                            yield send_cmd.eProcessed
                            self.send_data_count += 1
                            self._start_receiving()
                            self._lastState = None
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
        self.control_received_count = 0
        self.ack_send_count = 0
        self.error_rates_schedule = []

        self.biterror_sums_schedule = []
        self.error_rates_control = []

        self.biterror_sums_control = []
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    @GateListener("phyIn", Message)
    def phyInGateListener(self, cmd):
        if cmd.type == StackMessageTypes.RECEIVED:
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
                        self.biterror_sums_schedule.append(cmd.args["biterrors"])
                if header.type[0] == 2: #received control message
                    # TODO: check if timeslot is mine, not if addr is mine
                    if self.configuration.protocol_type == ProtocolType.TDMA:
                        time_since_schedule = SimMan.now - self._lastGatewayClock
                        current_slot = math.trunc(time_since_schedule / self.configuration.timeslot_length)
                        if self.schedule is not None:
                            my_slot = self.schedule.get_next_relevant_timespan(self.addr, 0)
                            if my_slot is not None:
                                if current_slot == my_slot[0]:  # message for me
                                    logger.debug("received control message", sender=self)
                                    if self.configuration.show_error_rates:
                                        self.error_rates_control.append(cmd.args["error_rate"])
                                        self.biterror_sums_control.append(cmd.args["biterrors"])
                                    self.gates["networkOut"].send(cmd.args["packet"].payload)
                                    self.control_received_count += 1
                                    self._n_control_received.trigger(cmd.args["error_rate"])
                    if self.configuration.protocol_type == ProtocolType.CSMA:
                        if header.destMAC == self.addr:
                            logger.debug("received control message", sender=self)
                            if self.configuration.show_error_rates:
                                self.error_rates_control.append(cmd.args["error_rate"])
                                self.biterror_sums_control.append(cmd.args["biterrors"])
                            self.gates["networkOut"].send(cmd.args["packet"].payload)
                            self.control_received_count += 1
                            self._n_control_received.trigger(cmd.args["error_rate"])

        if cmd.type == StackMessageTypes.FAILED:
            pass

    @GateListener("networkIn", (Message, Packet))
    def networkInGateListener(self, cmd):
        if isinstance(cmd, Message):
            pass

    def _sendcsi(self, csi):
        self._stopReceiving()
        csisendingtype = bytearray(1)
        csisendingtype[0] = 3
        sendPackage = Packet(NCSMacHeader(self.configuration.protocol_type, csisendingtype, self.addr), Transmittable(csi, 2))
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
        self.ack_send_count += 1
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
        self._receivingMode = True

        self.assigned_ps = []
        logger.debug("Initialization completed, MAC address: %s", self.addr, sender=self)

    def _stop_receiving(self):
        logger.debug("%s: Stopping to receive.", self)
        self._receivingMode = False

    def _start_receiving(self):
        logger.debug("%s: Starting to receive.", self)
        self._receivingMode = True

    @GateListener("phyIn", Message)
    def phyInGateListener(self, cmd: Message):
        if cmd.type == StackMessageTypes.RECEIVED:
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
                            "state": packet.payload.value[0],
                            "csisender": packet.payload.value[1],
                            "csigateway": cmd.args["error_rate"]
                        }
                    )
                    self.gates["networkOut"].send(receive_message)
                    # TODO: csi integration
                if message_type == 3: #received Actuator ACK
                    logger.debug("received actuator csi from %s. csi is %s", header.sourceMAC, packet.payload.value, sender=self)
                    receive_message = Message(
                        StackMessageTypes.RECEIVED, {
                            "sender": header.sourceMAC,
                            "csisender": packet.payload.value,
                            "csigateway": cmd.args["error_rate"]
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
        controller_schedule: CSMAControllerSchedule = message.args["controller_schedule"]
        sensor_schedule: CSMASchedule = message.args["schedule"]
        gateway_p = sensor_schedule.get_my_p(self.addr)
        logger.debug("My p is %f", gateway_p, sender=self)
        self.assigned_ps.append(gateway_p)
        current_slot = 1
        while current_slot < sensor_schedule.get_end_time():
            yield SimMan.timeoutUntil(SimMan.now + current_slot * self.configuration.timeslot_length)
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
                    controller_decide = random.randrange(0, 1)
                    controller = controller_schedule.get_chosen_controller(controller_decide)
                    logger.debug("will send control message from controller %d", controller, sender=self)
                    controller_cmd = Message(
                        StackMessageTypes.GETCONTROL, {
                            "controller": controller
                        }
                    )
                    self.gates["networkOut"].send(controller_cmd)
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
            NCSMacHeader(self.configuration.protocol_type, bytes(type), self.addr, receiver),
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
            NCSMacHeader(self.configuration.protocol_type, bytes(type), self.addr),
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
        self._start_receiving()
        if self.configuration.protocol_type == ProtocolType.CSMA:
            SimMan.process(self._handle_controller_schedule(message))

        message.setProcessed()
