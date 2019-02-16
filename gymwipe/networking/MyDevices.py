import logging
from typing import Any, Dict, Tuple
from gymwipe.baSimulation import BAEnivronment as env
from gymwipe.baSimulation.constants import TIMESLOT_LENGTH, SCHEDULER, PROTOCOL, PLANT_SAMPLE_TIME, SENSOR_SAMPLE_TIME
from gymwipe.control.scheduler import RoundRobinTDMAScheduler, MyDQNTDMAScheduler
from gymwipe.envs.core import Interpreter
from gymwipe.networking.devices import NetworkDevice
from gymwipe.networking.mac_layers import (ActuatorMacTDMA, GatewayMac,
                                           SensorMacTDMA, newUniqueMacAddress)
from gymwipe.networking.messages import (Message, Packet, SimpleNetworkHeader,
                                         StackMessageTypes, Transmittable)
from gymwipe.networking.physical import FrequencyBand
from gymwipe.networking.simple_stack import SimpleMac, SimplePhy
from gymwipe.plants.core import OdePlant
from gymwipe.plants.state_space_plants import StateSpacePlant
from gymwipe.simtools import SimMan, SimTimePrepender, Notifier

logger = SimTimePrepender(logging.getLogger(__name__))


class Control:
    def __init__(self, id_to_controller: {}, sensor_id_to_controller_id: {int, int}, controller_id_id_to_actuator: {int, int}, controller_id_to_plant: {}):
        self.controller_id_to_controller = id_to_controller
        self.controller_id_to_plant = controller_id_to_plant
        self.sensor_id_to_controller_id = sensor_id_to_controller_id
        self.controller_id_to_actuator_id = controller_id_id_to_actuator
        self.actuator_id_to_controller_id = {y: x for x, y in self.controller_id_to_actuator_id.items()}
        self.controller_id_to_latest_state = {}
        self.controller_id_to_latest_state_slot = {}
        self.gateway = None  # set after init
        for i in range(len(sensor_id_to_controller_id)):
            self.controller_id_to_latest_state_slot[i] = 0
        logger.debug("Control initialized\ncontrollerid: %s\nsensor: %s\nactuator: %s",
                     self.controller_id_to_controller,
                     self.sensor_id_to_controller_id,
                     self.controller_id_to_actuator_id,
                     sender=self)

    def onPacketReceived(self, senderIndex, state):
        self.controller_id_to_latest_state_slot[self.sensor_id_to_controller_id[senderIndex]] = self.gateway.simulatedSlot
        self.controller_id_to_latest_state[self.sensor_id_to_controller_id[senderIndex]] = state

    def getControl(self, actuatorId):
        controllerId = self.actuator_id_to_controller_id[actuatorId]
        controller = self.controller_id_to_controller[controllerId]
        diff = self.gateway.simulatedSlot - self.controller_id_to_latest_state_slot[controllerId]

    def estimateState(self, timeslots, controller_id):

        # TODO: state estimation
        pass


class ComplexNetworkDevice(NetworkDevice):
    """
    A :class:`NetworkDevice` implementation running a network stack that
    consists of a SimplePHY and a SimpleMAC, SensorMAC or ControllerMAC. It offers a method for sending a
    packet using the MAC layer, as well as a callback method that will be
    invoked when a packet is received. Also, receiving can be turned on or of by
    setting :attr:`receiving` either to ``True`` or to ``False``.
    """

    def __init__(self, name: str, xPos: float, yPos: float, frequencyBand: FrequencyBand, type: ""):
        super(ComplexNetworkDevice, self).__init__(name, xPos, yPos, frequencyBand)
        self._receiving = False
        self._receiverProcess = None # a SimPy receiver process

        self.mac: bytes = newUniqueMacAddress()
        """bytes: The address that is used by the MAC layer to identify this device"""

        if type is "Sensor":
            # Initialize PHY and MAC
            self._phy = SimplePhy("phy", self, self.frequencyBand)
            self._mac = SensorMacTDMA("mac", self, self.frequencyBand.spec, self.mac)
        elif type is "Controller":
            # Initialize PHY and MAC
            self._phy = SimplePhy("phy", self, self.frequencyBand)
            self._mac = ActuatorMacTDMA("mac", self, self.frequencyBand.spec, self.mac)
        else:
            # Initialize PHY and MAC
            self._phy = SimplePhy("phy", self, self.frequencyBand)
            self._mac = SimpleMac("mac", self, self.frequencyBand.spec, self.mac)

        # Connect them with each other
        self._mac.ports["phy"].biConnectWith(self._phy.ports["mac"])
    
    # inherit __init__ docstring
    __init__.__doc__ = NetworkDevice.__init__.__doc__

    def mac_address(self):
        return self._mac.addr

    def send(self, data):
        raise NotImplementedError

    def onReceive(self, packet: Packet):
        """
        This method is invoked whenever :attr:`receiving` is ``True`` and a
        packet has been received.

        Note:
            After :attr:`receiving` has been set to ``False`` it might still be
            called within :attr:`RECEIVE_TIMEOUT` seconds.

        Args:
            packet: The packet that has been received
        """
        raise NotImplementedError


class GatewayDevice(NetworkDevice):
    """
    A Radio Resource Management :class:`NetworkDevice` implementation. It runs a
    network stack consisting of a SimplePHY and a GatewayMAC. It offers a
    method for frequency band assignment and operates an
    :class:`~gymwipe.envs.core.Interpreter` instance that provides observations
    and rewards for a learning agent.
    """

    def __init__(self, name: str, xPos: float, yPos: float, frequencyBand: FrequencyBand,
                    deviceIndexToMacDict: Dict[int, bytes], sensors, actuators, interpreter, control):
        # No type definition for 'interpreter' to avoid circular dependencies
        """
            deviceIndexToMacDict: A dictionary mapping integer indexes to device
                MAC addresses. This allows to pass the device index used by a
                learning agent instead of a MAC address to
                :meth:`assignFrequencyBand`.
            interpreter(:class:`~gymwipe.envs.core.Interpreter`): The
                :class:`~gymwipe.envs.core.Interpreter` instance to be used for
                observation and reward calculations
        """
        self.mac: bytes = newUniqueMacAddress()
        """
        The mac address
        """
        super(GatewayDevice, self).__init__(name, xPos, yPos, frequencyBand)

        self.sensor_macs = sensors
        self.actuator_macs = actuators

        self.control = control
        """
        :class:'~gymwipe.networking.MyDevices': The
        :class:'~gymwipe.networking.MyDevices' instance that manages every controller in the system
        """

        self.interpreter = interpreter
        """
        :class:`~gymwipe.envs.core.Interpreter`: The
        :class:`~gymwipe.envs.core.Interpreter` instance that provides
        domain-specific feedback on the consequences of :meth:`assignFrequencyBand`
        calls
        """
        self.interpreter.gateway = self

        self.deviceIndexToMacDict = deviceIndexToMacDict
        """
        A dictionary mapping integer indexes to device MAC addresses. This
        allows to pass the device index used by a learning agent instead of a
        MAC address to :meth:`assignFrequencyBand`.
        """

        self.macToDeviceIndexDict: Dict[bytes, int] = {mac: index for index, mac in self.deviceIndexToMacDict.items()}
        """
        The counterpart to :attr:`deviceIndexToMacDict`
        """

        # Initialize PHY and MAC
        self._phy = SimplePhy("phy", self, self.frequencyBand)
        self._mac = GatewayMac("mac", self, self.frequencyBand.spec, self.mac)
        # Connect them with each other
        self._mac.ports["phy"].biConnectWith(self._phy.ports["mac"])

        # Connect the "upper" mac layer output to the interpreter
        def onPacketReceived(message: Message):
            if message.type is StackMessageTypes.RECEIVED:
                # Mapping MAC addresses to indexes
                senderIndex = self.macToDeviceIndexDict[message.args["sender"]]
                if message.args["sender"] in self.sensor_macs:
                    self.control.onPacketReceived(senderIndex, message.args["state"])
                    logger.debug("received sensor data, transmitted id and state to control", sender=self)
                    self.interpreter.onPacketReceived(message, senderIndex)
                    logger.debug("transmitted whole message to interpreter", sender=self)
                elif message.args["sender"] in self.actuator_macs:
                    self.interpreter.onPacketReceived(message, senderIndex)
                    logger.debug("transmitted whole message to interpreter", sender=self)
        self._mac.gates["networkOut"].nReceives.subscribeCallback(onPacketReceived)


    # merge __init__ docstrings
    __init__.__doc__ = NetworkDevice.__init__.__doc__ + __init__.__doc__


class Gateway(GatewayDevice):
    scheduler = None

    def __init__(self, sensorMACS: [], actuatorMACS: [], control: [], plants: [], name: str, xPos: float, yPos: float,
                 frequencyBand: FrequencyBand, schedule_timeslots: int):

        indexToMAC = {}
        self.nextScheduleCreation = 0
        self.last_schedule_creation = 0
        self.schedule_timeslots = schedule_timeslots
        self.schedule = None
        self.simulatedSlot = 0

        controller_id_to_controller = {}
        controller_id_to_plant = {}
        controller_id_to_actuator_id = {}
        sensor_id_to_controller_id = {}
        for i in range(len(control)):
            controller_id_to_controller[i] = control[i]
            controller_id_to_plant[i] = plants[i]
        for i in range(len(sensorMACS)):
            indexToMAC[i] = sensorMACS[i]
            sensor_id_to_controller_id[i] = i

        for i in range(len(sensorMACS), (len(sensorMACS)+len(actuatorMACS))):
            indexToMAC[i] = actuatorMACS[i-len(sensorMACS)]
            controller_id_to_actuator_id[i - len(sensorMACS)] = i

        super(Gateway, self).__init__(name, xPos, yPos, frequencyBand, indexToMAC, sensorMACS, actuatorMACS,
                                      MyInterpreter(SCHEDULER), Control(controller_id_to_controller, sensor_id_to_controller_id, controller_id_to_actuator_id, controller_id_to_plant))
        self.control.gateway = self

        self._create_scheduler()
        self._n_schedule_created = Notifier("new Schedule created", self)
        self._n_schedule_created.subscribeCallback(self.interpreter.onFrequencyBandAssignment())

        SimMan.process(self._gateway())
        SimMan.process(self._slotCount())

    def _slotCount(self):
        yield SimMan.timeout(TIMESLOT_LENGTH)
        self.simulatedSlot +=1
        logger.info("simulated Slot num %d", self.simulatedSlot, sender=self)

    def _create_scheduler(self):
        if SCHEDULER == 1:  # Round Robin
            if PROTOCOL == 1:  # TDMA
                self.scheduler = RoundRobinTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                         self.actuator_macs,
                                                         self.schedule_timeslots)
                logger.debug("RoundRobinTDMAScheduler created", sender=self)
            elif PROTOCOL == 2:  # CSMA
                pass
        elif SCHEDULER == 2:  # My DQN
            if PROTOCOL == 1:  # TDMA
                self.scheduler = MyDQNTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                    self.actuator_macs,
                                                    self.schedule_timeslots)
                logger.debug("DQNTDMAScheduler created", sender=self)
            elif PROTOCOL == 2:  # CSMA
                pass
        elif SCHEDULER == 3:  # paper DQN
            if PROTOCOL == 1:  # TDMA
                pass
            elif PROTOCOL == 2:  # CSMA
                pass

    def _gateway(self):
        if PROTOCOL == 1:  # TDMA
            if SCHEDULER == 1:  # Round Robin
                while True:
                    yield SimMan.timeoutUntil(self.nextScheduleCreation)
                    self.schedule = self.scheduler.next_schedule()
                    self.last_schedule_creation = SimMan.now
                    send_cmd = Message(
                        StackMessageTypes.SEND, {
                            "schedule": self.schedule,
                            "clock": self.last_schedule_creation
                        }
                    )
                    self._mac.gates["networkIn"].send(send_cmd)
                    self.nextScheduleCreation = SimMan.now + self.schedule.get_end_time() * TIMESLOT_LENGTH
                    yield send_cmd.eProcessed
                    # TODO: wait for control slot and activate controller

            elif SCHEDULER == 2:
                observation = self.interpreter.getObservation()
                self.schedule = self.scheduler.next_schedule(observation)
                self._n_schedule_created.trigger()
                while True:
                    yield SimMan.timeoutUntil(self.nextScheduleCreation)
                    observation = self.interpreter.getObservation()
                    reward = self.interpreter.getReward()
                    self.schedule = self.scheduler.next_schedule(observation, reward)
            elif SCHEDULER == 3:
                pass

        elif PROTOCOL == 2:  # CSMA
            pass


class SimpleSensor(ComplexNetworkDevice):
    """
    A sensor that observes the given plant (noise added)
    """
    def __init__(self, name: str, xpos: float, yPos: float, frequencyBand: FrequencyBand,
                    plant: StateSpacePlant):
        super(SimpleSensor, self).__init__(name, xpos, yPos, frequencyBand, "Sensor")
        self.plant = plant
        logger.debug("Sensor initialized, Position is (%f, %f)", xpos, yPos, sender=self)
        SimMan.process(self._sensor())

    def send(self, data):
        """
            Sends the last observed state to the mac layer
        """
        send_cmd = Message(StackMessageTypes.SEND, {"state": data})
        self._mac.gates["networkIn"].send(send_cmd)

    def _sensor(self):

        while True:
            state = self.plant.get_state()
            logger.debug("State sampled: " + state.__str__(), sender=self)
            self.send(state)
            yield SimMan.timeout(SENSOR_SAMPLE_TIME)

    def onReceive(self, packet: Packet):
        pass


class SimpleActuator(ComplexNetworkDevice):
    def __init__(self, name: str, xpos: float, yPos: float, frequencyBand: FrequencyBand, plant: StateSpacePlant):
        super(SimpleActuator, self).__init__(name, xpos, yPos, frequencyBand, "Actuator")
        self.plant = plant
        logger.debug("Actuator initialized, Position is (%f, %f)", xpos, yPos, sender=self)

    def send(self, data):
        pass

    def onReceive(self, packet: Packet):
        self.plant.set_control(packet.payload.value)


class MyInterpreter(Interpreter):
    """
    Interpretes the received packages/informations according to the chosen scheduler to get an observation of the
    systems state and a reward for the last schedule round.
    """

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.gateway = None  # set after gateway creation
        self.timestepResults = {}  # received information from every timestep in the last schedule round

    def onPacketReceived(self, message, senderIndex: int, receiverIndex= None, payload=None):
        logger.debug("received arrived packet information", sender=self)
        # TODO: compute current timestep to save received data in timestepResults dict
        # TODO: action for different schedulers same?
        if self.scheduler == 2:
            pass
        elif self.scheduler == 3:
            pass
        # nothing to to for round robin scheduler

    def onFrequencyBandAssignment(self, deviceIndex=None, duration=None):
        """
        is called whenever a new schedule has been created. Resets the timestep results
        :param deviceIndex: Not needed for this Interpreter
        :param duration: Not needed for this Interpreter
        """
        self.timestepResults = {}

    def getReward(self) -> float:
        """
        Computes the reward for the last schedule. The result is only effected by the scheduler type, not by the
        protocol type
        Computed as follows:

        :return: The computed reward
        """
        if self.scheduler == 2:   # my scheduler
            pass
        elif self.scheduler == 3:  # paper scheduler
            pass
        return 0.0

    def getObservation(self):
        if self.scheduler == 2:  # my scheduler
            pass
        elif self.scheduler == 3:  # paper scheduler
            pass
        return None

    def getDone(self):
        return False

    def getInfo(self):
        pass


