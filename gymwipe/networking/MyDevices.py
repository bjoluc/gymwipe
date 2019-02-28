import logging
import time
from typing import Any, Dict, Tuple
import numpy as np
import math
from gymwipe.baSimulation.constants import TIMESLOT_LENGTH, SCHEDULER, PROTOCOL, \
    PLANT_SAMPLE_TIME, SENSOR_SAMPLE_TIME, SAMPLE_TO_TIMESLOT_RATIO, EPISODES, T, ProtocolType, SchedulerType, \
    Configuration
from gymwipe.control.scheduler import RoundRobinTDMAScheduler, RandomTDMAScheduler, GreedyWaitingTimeTDMAScheduler
from gymwipe.control.paper_scheduler import DQNTDMAScheduler
from gymwipe.envs.core import Interpreter
from gymwipe.networking.devices import NetworkDevice
from gymwipe.networking.mac_layers import (ActuatorMac, GatewayMac,
                                           SensorMac, newUniqueMacAddress)
from gymwipe.networking.messages import (Message, Packet,
                                         StackMessageTypes)
from gymwipe.networking.physical import FrequencyBand
from gymwipe.networking.simple_stack import SimpleMac, SimplePhy
from gymwipe.plants.state_space_plants import StateSpacePlant
from gymwipe.simtools import SimMan, SimTimePrepender, Notifier
from simpy.events import Event
from filterpy.kalman import KalmanFilter

logger = SimTimePrepender(logging.getLogger(__name__))


class Control:
    def __init__(self, id_to_controller: {}, sensor_id_to_controller_id: {int, int},
                 controller_id_id_to_actuator: {int, int}, controller_id_to_plant: {int, StateSpacePlant}):
        self.controller_id_to_controller = id_to_controller
        self.controller_id_to_plant = controller_id_to_plant
        self.controller_id_to_latest_state = {}
        self.controller_id_to_latest_state_slot = {}
        self.controller_id_to_latest_u = {}
        for i in range(len(self.controller_id_to_plant)):
            plant: StateSpacePlant = self.controller_id_to_plant[i]
            self.controller_id_to_latest_state[i] = plant.state
            self.controller_id_to_latest_state_slot[i] = 0
            self.controller_id_to_latest_u[i] = 0.0
        self.sensor_id_to_controller_id = sensor_id_to_controller_id
        self.controller_id_to_actuator_id = controller_id_id_to_actuator
        self.actuator_id_to_controller_id = {y: x for x, y in self.controller_id_to_actuator_id.items()}
        self.gateway = None  # set after init
        for i in range(len(sensor_id_to_controller_id)):
            self.controller_id_to_latest_state_slot[i] = 0
        logger.debug("Control initialized\ncontrollerid: %s\nsensor: %s\nactuator: %s",
                     self.controller_id_to_controller,
                     self.sensor_id_to_controller_id,
                     self.controller_id_to_actuator_id,
                     sender="Control")

    def reset(self):
        self.controller_id_to_latest_state = {}
        self.controller_id_to_latest_state_slot = {}
        self.controller_id_to_latest_u = {}
        for i in range(len(self.controller_id_to_plant)):
            plant: StateSpacePlant = self.controller_id_to_plant[i]
            self.controller_id_to_latest_state[i] = plant.state
            self.controller_id_to_latest_state_slot[i] = 0
            self.controller_id_to_latest_u[i] = 0.0

    def onPacketReceived(self, senderIndex, state):
        self.controller_id_to_latest_state_slot[self.sensor_id_to_controller_id[senderIndex]] = self.gateway.simulatedSlot
        self.controller_id_to_latest_state[self.sensor_id_to_controller_id[senderIndex]] = state
        logger.debug("received a packet with estimated state", sender="Control")

    def getControl(self, actuator_id, hypothetical: bool):
        controller_id = self.actuator_id_to_controller_id[actuator_id]
        diff = (self.gateway.simulatedSlot - self.controller_id_to_latest_state_slot[controller_id]) * \
               SAMPLE_TO_TIMESLOT_RATIO
        diff = int(diff) + 1
        estimated_state = self.estimateState(diff, controller_id)
        controller = self.controller_id_to_controller[controller_id]
        control = controller @ estimated_state
        if not hypothetical:
            self.controller_id_to_latest_u[controller_id] = control
            return control
        else:
            return [control, estimated_state]

    def estimateState(self, timeslots, controller_id):
        plant: StateSpacePlant = self.controller_id_to_plant[controller_id]
        last_state = self.controller_id_to_latest_state[controller_id]

        last_state = np.array([[last_state[0]], [last_state[1]]])
        logger.debug("last received state from sensor is %s. This was %d timeslots ago", last_state.__str__(),
                     timeslots, sender="Control")
        last_u = self.controller_id_to_latest_u[controller_id]

        for i in range(timeslots):
            last_state = plant.a @ last_state + plant.b * last_u

        logger.debug("estimated state at timeslot %d for plant %d is %s", self.gateway.simulatedSlot, controller_id,
                     last_state.__str__())
        return last_state


class ComplexNetworkDevice(NetworkDevice):
    """
    A :class:`NetworkDevice` implementation running a network stack that
    consists of a SimplePHY and a SimpleMAC, SensorMAC or ControllerMAC. It offers a method for sending a
    packet using the MAC layer, as well as a callback method that will be
    invoked when a packet is received. Also, receiving can be turned on or of by
    setting :attr:`receiving` either to ``True`` or to ``False``.
    """

    def __init__(self, name: str, xPos: float, yPos: float, frequencyBand: FrequencyBand, plant, type: "",
                 configuration: Configuration):
        super(ComplexNetworkDevice, self).__init__(name, xPos, yPos, frequencyBand)
        self.configuration = configuration
        self._receiving = False
        self._receiverProcess = None # a SimPy receiver process

        self.plant = plant

        self.mac: bytes = newUniqueMacAddress()
        """bytes: The address that is used by the MAC layer to identify this device"""

        if type is "Sensor":
            # Initialize PHY and MAC
            self._phy = SimplePhy("phy", self, self.frequencyBand)
            self._mac = SensorMac("mac", self, self.frequencyBand.spec, self.mac, self.configuration)
        elif type is "Actuator":
            # Initialize PHY and MAC
            self._phy = SimplePhy("phy", self, self.frequencyBand)
            self._mac = ActuatorMac("mac", self, self.frequencyBand.spec, self.mac, self.configuration)
        else:
            # Initialize PHY and MAC
            self._phy = SimplePhy("phy", self, self.frequencyBand)
            self._mac = SimpleMac("mac", self, self.frequencyBand.spec, self.mac)

        # Connect them with each other
        self._mac.ports["phy"].biConnectWith(self._phy.ports["mac"])

        def onPacketReceived(payload):
            if type is "Actuator":
                logger.debug("received new control command, command is %f", payload.value, sender=self)
                # TODO: plant variable for both
                self.plant.set_control(payload.value)

        self._mac.gates["networkOut"].nReceives.subscribeCallback(onPacketReceived)
    
    # inherit __init__ docstring
    __init__.__doc__ = NetworkDevice.__init__.__doc__

    def mac_address(self):
        return self._mac.addr

    def send(self, data):
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
                    deviceIndexToMacDict: Dict[int, bytes], sensors, actuators, interpreter, control,
                 reset_event, done_event, episode_done_event, configuration: Configuration):
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
        self.configuration = configuration
        self.reset_event = reset_event
        self.done_event = done_event
        self.episode_done_event = episode_done_event
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
        self._mac = GatewayMac("mac", self, self.frequencyBand.spec, self.mac, self.configuration)
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
                 frequencyBand: FrequencyBand, reset_event: Notifier, done_event: Notifier,
                 episode_done_event: Notifier, configuration: Configuration):

        indexToMAC = {}
        self.nextScheduleCreation = 0
        self.last_schedule_creation = 0
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

        interpreter = MyInterpreter(configuration)

        super(Gateway, self).__init__(name, xPos, yPos, frequencyBand, indexToMAC, sensorMACS, actuatorMACS,
                                      interpreter,
                                      Control(controller_id_to_controller,
                                              sensor_id_to_controller_id,
                                              controller_id_to_actuator_id,
                                              controller_id_to_plant),
                                      reset_event, done_event, episode_done_event, configuration)
        self.control.gateway = self
        self.interpreter.gateway = self

        self._create_scheduler()
        self._n_schedule_created = Notifier("new Schedule created", self)
        self._n_schedule_created.subscribeProcess(self._schedule_handler)

        SimMan.process(self._gateway())
        SimMan.process(self._slotCount())

    def _schedule_handler(self, schedule):
        self.interpreter.onScheduleCreated(schedule)
        if self.configuration.protocol_type == ProtocolType.TDMA:
            last_control_slot = 0
            next_control_line = self.scheduler.get_next_control_slot(last_control_slot)
            while next_control_line is not None:
                yield SimMan.timeoutUntil(self.last_schedule_creation
                                          + self.configuration.timeslot_length * next_control_line[0])
                logger.debug("next control line is %s", next_control_line, sender=self)
                actuator_id = self.macToDeviceIndexDict[next_control_line[1]]
                control = self.control.getControl(actuator_id, False)
                logger.debug("will send control message %f to actuator %d", control, actuator_id, sender=self)
                send_cmd = Message(
                    StackMessageTypes.SENDCONTROL, {
                        "control": control[0][0],
                        "receiver": next_control_line[1]
                    }
                )
                self._mac.gates["networkIn"].send(send_cmd)
                yield send_cmd.eProcessed
                last_control_slot = next_control_line[0]
                next_control_line = self.scheduler.get_next_control_slot(last_control_slot)

    def _slotCount(self):
        while True:
            yield SimMan.timeout(TIMESLOT_LENGTH)
            self.simulatedSlot += 1
            # logger.info("simulated Slot num %d", self.simulatedSlot, sender=self)

    def _create_scheduler(self):
        if self.configuration.scheduler_type == SchedulerType.ROUNDROBIN:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = RoundRobinTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                         self.actuator_macs,
                                                         self.schedule_timeslots)
                logger.debug("RoundRobinTDMAScheduler created", sender=self)
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

        elif self.configuration.scheduler_type == SchedulerType.MYDQN:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                pass
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

        elif self.configuration.scheduler_type == SchedulerType.DQN:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = DQNTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                  self.actuator_macs, self.schedule_timeslots)
                logger.debug("DQNTDMAScheduler created", sender=self)
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

        elif self.configuration.scheduler_type == SchedulerType.RANDOM:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = RandomTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.actuator_macs,
                                                     self.schedule_timeslots)
                logger.debug("RandomTDMA Scheduler created")
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

        elif self.configuration.scheduler_type == SchedulerType.GREEDYWAIT:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = GreedyWaitingTimeTDMAScheduler(list(self.deviceIndexToMacDict.values()),
                                                                self.actuator_macs,
                                                                self.schedule_timeslots)
                logger.debug("Greedy waiting time TDMA Scheduler created")
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

    def _gateway(self):
        if PROTOCOL == ProtocolType.TDMA:
            logger.debug("protocol is TDMA", sender=self)
            if isinstance(self.scheduler, RoundRobinTDMAScheduler):  # Round Robin
                avgloss = []
                for i in range(EPISODES):
                    logger.debug("starting episode %d", i, sender=self)
                    start = time.time()
                    cum_loss = 0
                    for t in range(T):
                        schedule = self.scheduler.next_schedule()
                        self.last_schedule_creation = SimMan.now
                        send_cmd = Message(
                            StackMessageTypes.SEND, {
                                "schedule": schedule,
                                "clock": self.last_schedule_creation
                            }
                        )
                        self._mac.gates["networkIn"].send(send_cmd)
                        self.nextScheduleCreation = SimMan.now + schedule.get_end_time() * TIMESLOT_LENGTH
                        self._n_schedule_created.trigger(schedule)
                        yield send_cmd.eProcessed
                        yield SimMan.timeoutUntil(self.nextScheduleCreation)
                        reward = self.interpreter.getReward()
                        cum_loss += -reward
                    logger.debug("episode %d is done", i, sender=self)
                    avgloss.append(cum_loss / T)
                    end_time = time.time()
                    for p in range(len(self.control.controller_id_to_plant)):
                        plant = self.control.controller_id_to_plant[p]
                        plant.reset()
                    self.simulatedSlot = 0
                    self.control.reset()
                    self.interpreter.reset()
                    info = [i, end_time-start, cum_loss/T]
                    logger.debug("episode %d done. Average loss is %f", i, cum_loss/T)
                    if self.episode_done_event is not None:
                        self.episode_done_event.trigger(info)

                if self.done_event is not None:
                    self.done_event.trigger(avgloss)

            elif isinstance(self.scheduler, DQNTDMAScheduler):
                logger.debug("starting dqn process", sender=self)
                avgloss = []
                for e in range(self.configuration.episodes):
                    logger.debug("starting episode %d", e, sender=self)
                    start = time.time()
                    observation = self.interpreter.get_first_observation()
                    cum_loss = 0
                    for t in range(self.configuration.horizon):
                        schedule = self.scheduler.next_schedule(observation)
                        self.last_schedule_creation = SimMan.now
                        self.nextScheduleCreation = SimMan.now + schedule.get_end_time() * TIMESLOT_LENGTH
                        self._n_schedule_created.trigger(schedule)
                        send_cmd = Message(
                            StackMessageTypes.SEND, {
                                "schedule": schedule,
                                "clock": self.last_schedule_creation
                            }
                        )
                        self._mac.gates["networkIn"].send(send_cmd)
                        yield send_cmd.eProcessed
                        yield SimMan.timeoutUntil(self.nextScheduleCreation)
                        next_observation = self.interpreter.getObservation()
                        logger.debug("last observation was %s\nnext observation is %s", str(observation),
                                     str(next_observation), sender=self)
                        reward = self.interpreter.getReward()
                        cum_loss += -reward
                        action_id = self.scheduler.action_id
                        self.scheduler.remember(observation, action_id,
                                                reward, next_observation)
                        observation = next_observation
                        if np.mod(t, self.scheduler.c) == 0:
                            self.scheduler.update_target_model()
                        if len(self.scheduler.memory) > self.scheduler.batch_size:
                            self.scheduler.replay()
                    avg = cum_loss/self.configuration.horizon
                    avgloss.append(avg)
                    end_time = time.time()
                    for p in range(len(self.control.controller_id_to_plant)):
                        plant = self.control.controller_id_to_plant[p]
                        plant.reset()
                    self.simulatedSlot = 0
                    self.control.reset()
                    self.interpreter.reset()
                    info = [e, end_time-start, avg]
                    logger.debug("episode %d done. Average loss is %f", e, cum_loss/self.configuration.horizon)

                    self.episode_done_event.trigger(info)
                self.done_event.trigger(avgloss)

        elif self.configuration.protocol_type == ProtocolType.CSMA:
            pass


class SimpleSensor(ComplexNetworkDevice):
    """
    A sensor that observes the given plant (noise added)
    """
    def __init__(self, name: str, xpos: float, yPos: float, frequencyBand: FrequencyBand,
                    plant: StateSpacePlant, configuration: Configuration):
        super(SimpleSensor, self).__init__(name, xpos, yPos, frequencyBand, plant, "Sensor", configuration)
        logger.debug("Sensor initialized, Position is (%f, %f)", xpos, yPos, sender=self)
        self.c = np.array([[0.5, 1.5]])
        self.mean = np.zeros((1,))
        self.cov = np.eye(1) * 0.1
        self.kalman = KalmanFilter(dim_x=2, dim_z=1)
        self.kalman.x = self.plant.state
        self.kalman.F = self.plant.a
        self.kalman.H = self.c
        self.kalman.P = self.plant.x0_cov
        self.kalman.R = np.array([[self.plant.r_subsystem]])
        self.kalman.Q = self.plant.q_subsystem
        SimMan.process(self._sensor())
        self.outputs = []
        self.inputs = []  # just for evaluation, the sensor usually doesn't know these

    def send(self, data):
        """
            Sends the last observed state to the mac layer
        """
        send_cmd = Message(StackMessageTypes.SEND, {"state": data})
        self._mac.gates["networkIn"].send(send_cmd)

    def _sensor(self):

        while True:
            state = self.plant.get_state()
            output = self.c @ state + np.random.multivariate_normal(self.mean, self.cov)
            self.outputs.append(output[0])
            self.inputs.append(self.plant.control)
            self.kalman.predict()
            self.kalman.update(output)
            # logger.info("output sampled: " + output.__str__(), sender=self)
            logger.info("filtered state: %s", self.kalman.x.__str__(), sender=self)
            self.send(self.kalman.x)
            yield SimMan.timeout(self.configuration.sensor_sample_time)

    def onReceive(self, packet: Packet):
        pass


class SimpleActuator(ComplexNetworkDevice):
    def __init__(self, name: str, xpos: float, yPos: float, frequencyBand: FrequencyBand, plant: StateSpacePlant,
                 configuration: Configuration):
        super(SimpleActuator, self).__init__(name, xpos, yPos, frequencyBand, plant, "Actuator", configuration)

        logger.debug("Actuator initialized, Position is (%f, %f)", xpos, yPos, sender=self)

    def send(self, data):
        pass

    def onReceive(self, packet: Packet):
        self.plant.set_control(packet.payload.value)


class MyInterpreter(Interpreter):
    """
    Interprets the received packages/information according to the chosen scheduler to get an observation of the
    systems state and a reward for the last schedule round.
    """

    def __init__(self, configuration):
        self.configuration = configuration
        self.device_amount = self.configuration.num_plants*2
        self.schedule_length = self.configuration.schedule_length
        self.gateway = None  # set after gateway creation
        self.timestep_success = np.zeros(self.schedule_length, dtype=int)  # received information from every timestep in the last schedule round
        self.last_update = np.zeros(self.device_amount, dtype=int)
        self.observation_size = self.device_amount + self.schedule_length
        self.device_amount = self.device_amount

    def reset(self):
        self.timestep_success = np.zeros(self.schedule_length, dtype=int)
        self.last_update = np.zeros(self.device_amount, dtype=int)

    def onPacketReceived(self, message, senderIndex: int, receiverIndex= None, payload=None):
        logger.debug("received arrived packet information", sender="Interpreter")
        # TODO: compute current timestep to save received data in timestepResults dict
        # TODO: action for different schedulers same?

        time_since_schedule = SimMan.now - self.gateway.last_schedule_creation
        schedule_timeslot = math.trunc(time_since_schedule/TIMESLOT_LENGTH) - 1
        self.timestep_success[schedule_timeslot] = 1
        self.last_update[senderIndex] = self.gateway.simulatedSlot
        logger.debug("got received packet information. Sender %d sent %s", senderIndex, message.__repr__(),
                     sender=self)
        # nothing to do for round robin scheduler

    def onScheduleCreated(self, schedule):
        """
        is called whenever a new schedule has been created. Resets the timestep results
        :param schedule: the new schedule given by the gateway
        """
        logger.debug("received a new schedule, resetting timestep info", sender="Interpreter")
        self.timestep_success = np.zeros(len(self.timestep_success), dtype=int)

    def onFrequencyBandAssignment(self, deviceIndex=None, duration=None):

        self.timestep_success = {}
        logger.debug("received a new schedule", sender="Interpreter")

    def getReward(self) -> float:
        """
        Computes the reward for the last schedule. The result is only effected by the scheduler type, not by the
        protocol type
        Computed as follows:

        :return: The computed reward
        """

        reward = 0.0  # paper scheduler
        if self.configuration.scheduler_type == SchedulerType.DQN:
            id_to_plant = self.gateway.control.controller_id_to_plant
            for i in range(len(id_to_plant)):
                plant: StateSpacePlant = id_to_plant[i]
                q = plant.q_subsystem
                r = plant.r_subsystem
                control_output = self.gateway.control.getControl(self.gateway.control.controller_id_to_actuator_id[i], True)
                control = control_output[0]
                state = control_output[1]
                logger.debug("plant %d: last control is %s, estimated state is %s", i, control.__str__(), state.__str__(),
                             sender="Interpreter")
                single_reward = -(state.transpose()@q@state + control.transpose()*r*control)
                logger.debug("single reward is %f", single_reward, sender="Interpreter")
                reward += single_reward
            logger.debug("computed reward is %f", reward, sender="Interpreter")
        return reward[0][0]

    def get_first_observation(self):
        observation = None
        if self.configuration.scheduler_type == SchedulerType.MYDQN:  # my scheduler
            pass
        elif self.configuration.scheduler_type == SchedulerType.DQN:
            tau = np.zeros(len(self.last_update), dtype=int)
            observation = np.hstack((tau, self.timestep_success))
        logger.debug("computed observation: %s", observation.__str__(), sender="Interpreter")
        return observation

    def getObservation(self):
        observation = None
        if self.configuration.scheduler_type == SchedulerType.MYDQN:
            pass
        elif self.configuration.scheduler_type == SchedulerType.DQN:
            current_slot = self.gateway.simulatedSlot
            tau = np.zeros(len(self.last_update), dtype=int)
            for i in range(len(self.last_update)):
                tau[i] = current_slot-self.last_update[i]
            observation = np.hstack((tau, self.timestep_success))
        elif self.configuration.scheduler_type == SchedulerType.GREEDYERROR:
            observation = []
            for i in range(len(self.gateway.deviceIndexToMacDict)):
                pass
        logger.debug("computed observation: %s", observation.__str__(), sender="Interpreter")
        return observation

    def getDone(self):
        return False

    def getInfo(self):
        pass


