import logging
import time
from typing import Dict
import numpy as np
import math
from gymwipe.baSimulation.constants import ProtocolType, SchedulerType, Configuration, RewardType
from gymwipe.control.scheduler import RoundRobinTDMAScheduler, RandomTDMAScheduler, GreedyWaitingTimeTDMAScheduler, \
    RandomCSMAScheduler, CSMASchedule, CSMAControllerSchedule
from gymwipe.control.paper_scheduler import DQNTDMAScheduler, FixedDQNTDMAScheduler, DQNCSMAScheduler
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
from filterpy.kalman import KalmanFilter

logger = SimTimePrepender(logging.getLogger(__name__))


class Control:
    """
    The controlling part from the gateway. It manages the controllers for every Plant within the environment.
    """
    def __init__(self, id_to_controller: {}, sensor_id_to_controller_id: {int, int},
                 controller_id_to_actuator_id: {int, int}, controller_id_to_plant: {int, StateSpacePlant}):
        """
        Args:
            id_to_controller: A dictionary mapping the controller ids to the controllers
            sensor_id_to_controller_id: A dictionary mapping the sensor ids to their corresponding controller ids
            controller_id_to_actuator_id: A dictionary mapping the controller ids to their corresponding actuator id
            controller_id_to_plant: A dictionary mapping the controller ids to their corresponding plants. This is
                only used to get access to the A and b matrices from the plant's state space representation
        """
        self.controller_id_to_controller = id_to_controller
        self.controller_id_to_plant = controller_id_to_plant
        self.sensor_id_to_controller_id = sensor_id_to_controller_id
        self.controller_id_to_sensor_id = {y: x for x, y in self.sensor_id_to_controller_id.items()}
        self.controller_id_to_actuator_id = controller_id_to_actuator_id
        self.actuator_id_to_controller_id = {y: x for x, y in self.controller_id_to_actuator_id.items()}
        self.gateway = None  # set after init

        self.sensor_id_to_current_state = {}
        """
        A dictionary mapping the controller id to the current estimated state
        """

        self.controller_id_to_control_sent= {}
        """
        Keeps track of computed control signals
        """

        self.track_estimated_states = {}
        """
        A dictionary that sores every estimated state from every plant
        """
        self.track_estimated_outputs = {}
        """
        A dictionary that sores every estimated output from every plant. ONLY USE FOR EVALUATION! USUALLY NOT KNOWN
        """

        for i in range(len(self.controller_id_to_plant)):
            plant: StateSpacePlant = self.controller_id_to_plant[i]
            self.sensor_id_to_current_state[i] = plant.state
            self.track_estimated_states[i] = []
            self.track_estimated_outputs[i] = []
            self.controller_id_to_control_sent[i] = np.array([0.0])

    def onPacketReceived(self, senderIndex, state):
        """
        Is executed whenever the gateway receives a packet that contains sensor data
        :param senderIndex: The sender id of that packet
        :param state: The estimated state that has been sent
        """
        self.sensor_id_to_current_state[senderIndex] = state
        logger.debug("received a packet with estimated state", sender="Control")

    def schedule_executed(self):
        """
        Is executed whenever a schedule is processed. Updates the state estimates for every plant.
        """
        sensor_ids = list(self.sensor_id_to_controller_id.keys())
        # save old state estimates
        for i in range(len(sensor_ids)):
            current_estimated_state = self.sensor_id_to_current_state[sensor_ids[i]]
            # the following is just for evaluation, usually not known!
            c = np.array([[0.5, 1.5]])
            estimated_output = c @ current_estimated_state # not used, just for evaluation
            self.track_estimated_states[sensor_ids[i]].append(self.sensor_id_to_current_state[sensor_ids[i]])
            self.track_estimated_outputs[sensor_ids[i]].append(estimated_output[0])
        # compute new estimates
        for i in range(len(sensor_ids)):
            sensor_id = sensor_ids[i]
            controller_id = self.sensor_id_to_controller_id[sensor_id]
            plant: StateSpacePlant = self.controller_id_to_plant[controller_id]

            last_state = self.sensor_id_to_current_state[sensor_id]
            control = self.controller_id_to_control_sent[controller_id]
            new_estimated_state = np.einsum('ij,j->i', plant.a, last_state) + \
                                  np.einsum('ij,j->i', plant.b, control)
            self.sensor_id_to_current_state[sensor_id] = new_estimated_state

            self.controller_id_to_control_sent[controller_id] = np.array([0.0])

    def getControl(self, actuator_id, hypothetical: bool):
        """
        Computes the control signal that should be applied to the plant belonging to the given actuator. Based on
        current state estimate
        :param actuator_id: The actuator that will receive the control signal
        :param hypothetical: Should the computed control signal be saved to apply it to the next state estimation?
        """
        controller_id = self.actuator_id_to_controller_id[actuator_id]
        controller = self.controller_id_to_controller[controller_id]
        estimated_state = self.sensor_id_to_current_state[self.controller_id_to_sensor_id[controller_id]]

        control = controller @ estimated_state

        if not hypothetical:
            self.controller_id_to_control_sent[controller_id] = control
            return [control]
        else:
            return [control, estimated_state]

    def reset(self):
        self.sensor_id_to_current_state = {}
        self.controller_id_to_control_sent = {}
        self.track_estimated_states = {}
        for i in range(len(self.controller_id_to_plant)):
            plant: StateSpacePlant = self.controller_id_to_plant[i]
            self.sensor_id_to_current_state[i] = plant.state
            self.track_estimated_states[i] = []
            self.track_estimated_outputs[i] = []
            self.controller_id_to_control_sent[i] = np.array([0.0])


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
                 done_event, episode_done_event, simulation_done_event, configuration: Configuration):
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
        self.done_event = done_event
        self.episode_done_event = episode_done_event
        self.simualtion_done_event = simulation_done_event
        self.mac: bytes = newUniqueMacAddress()
        self.send_schedule_count = 0
        self.send_control_amount = {}
        self.received_ack_amount = {}
        self.received_data_amount = {}
        self._nSendControl = Notifier("control should be send")
        self._nSendControl.subscribeProcess(self.send_control)
        """
        The mac address
        """
        super(GatewayDevice, self).__init__(name, xPos, yPos, frequencyBand)

        self.sensor_macs = sensors
        for i in range(len(self.sensor_macs)):
            self.received_data_amount[self.sensor_macs[i]] = 0
        self.actuator_macs = actuators
        for i in range(len(self.actuator_macs)):
            self.send_control_amount[self.actuator_macs[i]] = 0
            self.received_ack_amount[self.actuator_macs[i]] = 0
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
                    if message.args["sender"] in self.received_data_amount:
                        self.received_data_amount[message.args["sender"]] += 1
                    else:
                        self.received_data_amount[message.args["sender"]] = 1
                    self.control.onPacketReceived(senderIndex, message.args["state"])
                    logger.debug("received sensor data, transmitted id and state to control", sender=self)
                    self.interpreter.onPacketReceived(message, senderIndex)
                    logger.debug("transmitted whole message to interpreter", sender=self)
                elif message.args["sender"] in self.actuator_macs:
                    if message.args["sender"] in self.received_ack_amount:
                        self.received_ack_amount[message.args["sender"]] += 1
                    else:
                        self.received_ack_amount[message.args["sender"]] = 1
                    self.interpreter.onPacketReceived(message, senderIndex)
                    logger.debug("transmitted whole message to interpreter", sender=self)
            if message.type is StackMessageTypes.GETCONTROL:
                logger.debug("should send control message", sender=self)
                controller = message.args["controller"]
                actuator_id = self.control.controller_id_to_actuator_id[controller]
                control_value = self.control.getControl(actuator_id, False)
                self._nSendControl.trigger((self.deviceIndexToMacDict[actuator_id], control_value[0][0]))
        self._mac.gates["networkOut"].nReceives.subscribeCallback(onPacketReceived)

    def send_control(self, values):
        logger.debug("will send control message %f to actuator %d", values[1], values[0], sender=self)
        send_cmd = Message(
            StackMessageTypes.SENDCONTROL, {
                "control": values[1],
                "receiver": values[0]
            }
        )
        self._mac.gates["networkIn"].send(send_cmd)
        yield send_cmd.eProcessed
        if values[0] in self.send_control_amount:
            self.send_control_amount[values[0]] += 1
        else:
            self.send_control_amount[values[0]] = 1

    # merge __init__ docstrings
    __init__.__doc__ = NetworkDevice.__init__.__doc__ + __init__.__doc__


class Gateway(GatewayDevice):
    scheduler = None

    def __init__(self, sensorMACS: [], actuatorMACS: [], control: [], plants: [], name: str, xPos: float, yPos: float,
                 frequencyBand: FrequencyBand, done_event: Notifier,
                 episode_done_event: Notifier, simulation_done_event: Notifier, configuration: Configuration):

        indexToMAC = {}

        self.nextScheduleCreation = 0
        self.last_schedule_creation = 0
        self.simulatedSlot = 0

        self.controller_id_to_controller = {}
        self.controller_id_to_plant = {}
        self.controller_id_to_actuator_id = {}
        self.sensor_id_to_controller_id = {}
        self.send_schedule_amount = 0
        self.chosen_schedules = {}
        self.chosen_devices = {}
        self.schedule_sequence = []
        for i in range(len(control)):
            self.controller_id_to_controller[i] = control[i]
            self.controller_id_to_plant[i] = plants[i]
        for i in range(len(sensorMACS)):
            indexToMAC[i] = sensorMACS[i]
            self.sensor_id_to_controller_id[i] = i

        for i in range(len(sensorMACS), (len(sensorMACS)+len(actuatorMACS))):
            indexToMAC[i] = actuatorMACS[i-len(sensorMACS)]
            self.controller_id_to_actuator_id[i - len(sensorMACS)] = i

        interpreter = MyInterpreter(configuration)

        super(Gateway, self).__init__(name, xPos, yPos, frequencyBand, indexToMAC, sensorMACS, actuatorMACS,
                                      interpreter,
                                      Control(self.controller_id_to_controller,
                                              self.sensor_id_to_controller_id,
                                              self.controller_id_to_actuator_id,
                                              self.controller_id_to_plant),
                                      done_event, episode_done_event, simulation_done_event,
                                      configuration)
        self.control.gateway = self
        self.interpreter.gateway = self

        self._create_scheduler()
        self._n_schedule_created = Notifier("new Schedule created", self)
        self._n_schedule_created.subscribeProcess(self._schedule_handler)
        self.n_simulate = Notifier("start simulation")
        self.n_simulate.subscribeProcess(self._simulate)

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

                logger.debug("will send control message %f to actuator %d", control[0][0], actuator_id, sender=self)
                send_cmd = Message(
                    StackMessageTypes.SENDCONTROL, {
                        "control": control[0][0],
                        "receiver": next_control_line[1]
                    }
                )
                self._mac.gates["networkIn"].send(send_cmd)
                yield send_cmd.eProcessed
                if next_control_line[1] in self.send_control_amount:
                    self.send_control_amount[next_control_line[1]] += 1
                else:
                    self.send_control_amount[next_control_line[1]] = 1
                last_control_slot = next_control_line[0]
                next_control_line = self.scheduler.get_next_control_slot(last_control_slot)

    def schedule_analysis(self):
        if self.configuration.protocol_type == ProtocolType.TDMA:
            if self.scheduler.get_schedule_string() in self.chosen_schedules:
                self.chosen_schedules[self.scheduler.get_schedule_string()] += 1
            else:
                self.chosen_schedules[self.scheduler.get_schedule_string()] = 1
            chosen_devices = self.scheduler.get_chosen_devices()
            for i in range(len(chosen_devices)):
                if chosen_devices[i] in self.chosen_devices:
                    self.chosen_devices[chosen_devices[i]] += 1
                else:
                    self.chosen_devices[chosen_devices[i]] = 1

            self.send_schedule_amount += 1

    def _slotCount(self):
        while True:
            yield SimMan.timeout(self.configuration.timeslot_length)
            self.simulatedSlot += 1
            # logger.info("simulated Slot num %d", self.simulatedSlot, sender=self)

    def _create_scheduler(self):
        if self.configuration.scheduler_type == SchedulerType.ROUNDROBIN:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = RoundRobinTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                         self.actuator_macs,
                                                         self.configuration.schedule_length)
                logger.debug("RoundRobinTDMAScheduler created", sender=self)
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

        elif self.configuration.scheduler_type == SchedulerType.FIXEDDQN:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = FixedDQNTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                       self.actuator_macs, self.configuration.schedule_length)
                logger.debug("FixedDQNTDMAScheduler created", sender=self)
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

        elif self.configuration.scheduler_type == SchedulerType.DQN:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = DQNTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                  self.actuator_macs, self.configuration.schedule_length)
                logger.debug("DQNTDMAScheduler created", sender=self)
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                self.scheduler = DQNCSMAScheduler(self.sensor_macs, self.mac, self.configuration.schedule_length)

        elif self.configuration.scheduler_type == SchedulerType.RANDOM:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = RandomTDMAScheduler(list(self.deviceIndexToMacDict.values()), self.sensor_macs,
                                                     self.actuator_macs,
                                                     self.configuration.schedule_length)
                logger.debug("RandomTDMA Scheduler created")
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                self.scheduler = RandomCSMAScheduler(self.sensor_macs, self.mac, self.configuration.schedule_length)

        elif self.configuration.scheduler_type == SchedulerType.GREEDYWAIT:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                self.scheduler = GreedyWaitingTimeTDMAScheduler(list(self.deviceIndexToMacDict.values()),
                                                                self.sensor_macs,
                                                                self.actuator_macs,
                                                                self.configuration.schedule_length)
                logger.debug("Greedy waiting time TDMA Scheduler created")
            elif self.configuration.protocol_type == ProtocolType.CSMA:
                pass

    def _gateway(self):
        if self.configuration.train:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                logger.debug("protocol is TDMA", sender=self)
                if isinstance(self.scheduler, RoundRobinTDMAScheduler):  # Round Robin

                    logger.debug("scheduler is round robin scheduler", sender=self)
                    avgloss = []
                    for i in range(self.configuration.episodes):
                        logger.debug("starting episode %d", i, sender=self)
                        start = time.time()
                        cum_loss = 0
                        for t in range(self.configuration.horizon):
                            schedule = self.scheduler.next_schedule()
                            self.schedule_analysis()
                            self.last_schedule_creation = SimMan.now
                            send_cmd = Message(
                                StackMessageTypes.SEND, {
                                    "schedule": schedule,
                                    "clock": self.last_schedule_creation
                                }
                            )
                            self._mac.gates["networkIn"].send(send_cmd)
                            self.nextScheduleCreation = SimMan.now + schedule.get_end_time() * \
                                                        self.configuration.timeslot_length
                            self._n_schedule_created.trigger(schedule)
                            yield send_cmd.eProcessed
                            yield SimMan.timeoutUntil(self.nextScheduleCreation)
                            self.control.schedule_executed()
                            reward = self.interpreter.getReward()
                            cum_loss += -reward
                        logger.debug("episode %d is done", i, sender=self)
                        avgloss.append(cum_loss / self.configuration.horizon)
                        end_time = time.time()
                        info = [i, end_time-start, cum_loss/self.configuration.horizon]
                        logger.debug("episode %d done. Average loss is %f", i, cum_loss/self.configuration.horizon)
                        if self.episode_done_event is not None:
                            self.episode_done_event.trigger(info)

                    if self.done_event is not None:
                        self.done_event.trigger(avgloss)

                elif isinstance(self.scheduler, DQNTDMAScheduler) or isinstance(self.scheduler, FixedDQNTDMAScheduler):
                    logger.debug("scheduler is dqn scheduler", sender=self)
                    avgloss = []
                    for e in range(self.configuration.episodes):
                        logger.debug("starting episode %d", e, sender=self)
                        start = time.time()
                        observation = self.interpreter.get_first_observation()
                        cum_loss = 0
                        for t in range(self.configuration.horizon):
                            schedule = self.scheduler.next_schedule(observation)
                            self.schedule_analysis()
                            self.last_schedule_creation = SimMan.now
                            self.nextScheduleCreation = (SimMan.now + schedule.get_end_time() *
                                                         self.configuration.timeslot_length)
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
                            self.control.schedule_executed()
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
                        info = [e, end_time-start, avg]
                        logger.debug("episode %d done. Average loss is %f", e, cum_loss/self.configuration.horizon)

                        self.episode_done_event.trigger(info)
                    self.done_event.trigger(avgloss)

                elif isinstance(self.scheduler, RandomTDMAScheduler):
                    logger.debug("scheduler is random scheduler", sender=self)
                    avgloss = []
                    for i in range(self.configuration.episodes):
                        logger.debug("starting episode %d", i, sender=self)
                        start = time.time()
                        cum_loss = 0
                        for t in range(self.configuration.horizon):
                            schedule = self.scheduler.next_schedule()
                            self.schedule_analysis()
                            self.last_schedule_creation = SimMan.now
                            send_cmd = Message(
                                StackMessageTypes.SEND, {
                                    "schedule": schedule,
                                    "clock": self.last_schedule_creation
                                }
                            )
                            self._mac.gates["networkIn"].send(send_cmd)
                            self.nextScheduleCreation = SimMan.now + schedule.get_end_time() * \
                                                        self.configuration.timeslot_length
                            self._n_schedule_created.trigger(schedule)
                            yield send_cmd.eProcessed
                            yield SimMan.timeoutUntil(self.nextScheduleCreation)
                            self.control.schedule_executed()
                            reward = self.interpreter.getReward()
                            cum_loss += -reward
                        logger.debug("episode %d is done", i, sender=self)
                        avgloss.append(cum_loss / self.configuration.horizon)
                        end_time = time.time()
                        info = [i, end_time-start, cum_loss/self.configuration.horizon]
                        logger.debug("episode %d done. Average loss is %f", i, cum_loss/self.configuration.horizon)
                        if self.episode_done_event is not None:
                            self.episode_done_event.trigger(info)

                    if self.done_event is not None:
                        self.done_event.trigger(avgloss)

                elif isinstance(self.scheduler, GreedyWaitingTimeTDMAScheduler):
                    logger.debug("scheduler is dqn scheduler", sender=self)
                    avgloss = []
                    for e in range(self.configuration.episodes):
                        logger.debug("starting episode %d", e, sender=self)
                        start = time.time()
                        observation = self.interpreter.get_first_observation()
                        cum_loss = 0
                        for t in range(self.configuration.horizon):
                            schedule = self.scheduler.next_schedule(observation)
                            self.schedule_analysis()
                            self.last_schedule_creation = SimMan.now
                            self.nextScheduleCreation = SimMan.now + schedule.get_end_time() * \
                                                        self.configuration.timeslot_length
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
                            self.control.schedule_executed()
                            observation = self.interpreter.getObservation()
                            logger.debug("last observation was %s", str(observation), sender=self)
                            reward = self.interpreter.getReward()
                            cum_loss += -reward
                        avg = cum_loss / self.configuration.horizon
                        avgloss.append(avg)
                        end_time = time.time()
                        info = [e, end_time - start, avg]
                        logger.debug("episode %d done. Average loss is %f", e, cum_loss / self.configuration.horizon)

                        self.episode_done_event.trigger(info)
                    self.done_event.trigger(avgloss)

            elif self.configuration.protocol_type == ProtocolType.CSMA:
                if isinstance(self.scheduler, RandomCSMAScheduler):
                    logger.debug("scheduler is random scheduler", sender=self)
                    avgloss = []
                    for i in range(self.configuration.episodes):
                        logger.debug("starting episode %d", i, sender=self)
                        start = time.time()
                        cum_loss = 0
                        for t in range(self.configuration.horizon):
                            schedules = self.scheduler.next_schedule()
                            sensor_schedule = schedules[0]
                            controller_schedule = schedules[1]
                            self.last_schedule_creation = SimMan.now
                            send_cmd = Message(
                                StackMessageTypes.SEND, {
                                    "schedule": sensor_schedule,
                                    "controller_schedule": controller_schedule,
                                    "clock": self.last_schedule_creation
                                }
                            )
                            self._mac.gates["networkIn"].send(send_cmd)
                            self.nextScheduleCreation = SimMan.now + sensor_schedule.get_end_time() * \
                                                        self.configuration.timeslot_length
                            self._n_schedule_created.trigger(controller_schedule)
                            yield send_cmd.eProcessed
                            self.send_schedule_amount += 1
                            yield SimMan.timeoutUntil(self.nextScheduleCreation)
                            self.control.schedule_executed()
                            reward = self.interpreter.getReward()
                            cum_loss += -reward
                        logger.debug("episode %d is done", i, sender=self)
                        avgloss.append(cum_loss / self.configuration.horizon)
                        end_time = time.time()
                        info = [i, end_time-start, cum_loss/self.configuration.horizon]
                        logger.debug("episode %d done. Average loss is %f", i, cum_loss/self.configuration.horizon)
                        if self.episode_done_event is not None:
                            self.episode_done_event.trigger(info)

                    if self.done_event is not None:
                        self.done_event.trigger(avgloss)

                if isinstance(self.scheduler, DQNCSMAScheduler):
                    logger.debug("scheduler is dqn scheduler", sender=self)
                    avgloss = []
                    for e in range(self.configuration.episodes):
                        logger.debug("starting episode %d", e, sender=self)
                        start = time.time()
                        observation = self.interpreter.get_first_observation()
                        cum_loss = 0
                        for t in range(self.configuration.horizon):
                            sensor_schedule, controller_schedule = self.scheduler.next_schedule(observation)
                            self.schedule_analysis()
                            self.last_schedule_creation = SimMan.now
                            self.nextScheduleCreation = (SimMan.now + sensor_schedule.get_end_time() *
                                                         self.configuration.timeslot_length)
                            self._n_schedule_created.trigger(sensor_schedule)
                            send_cmd = Message(
                                StackMessageTypes.SEND, {
                                    "schedule": sensor_schedule,
                                    "controller_schedule": controller_schedule,
                                    "clock": self.last_schedule_creation
                                }
                            )
                            self._mac.gates["networkIn"].send(send_cmd)
                            yield send_cmd.eProcessed
                            yield SimMan.timeoutUntil(self.nextScheduleCreation)
                            self.control.schedule_executed()
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
                        avg = cum_loss / self.configuration.horizon
                        avgloss.append(avg)
                        end_time = time.time()
                        info = [e, end_time - start, avg]
                        logger.debug("episode %d done. Average loss is %f", e, cum_loss / self.configuration.horizon)

                        self.episode_done_event.trigger(info)
                    self.done_event.trigger(avgloss)
        else:
            self.done_event.trigger([])

    def _simulate(self, horizon):

        if self.configuration.simulate:
            if self.configuration.protocol_type == ProtocolType.TDMA:
                loss = []
                cum_loss = 0
                observation = self.interpreter.get_first_observation()
                for i in range(horizon):
                    schedule = self.scheduler.next_schedule(observation)
                    self.schedule_sequence.append(self.scheduler.get_schedule_string())
                    self.schedule_analysis()
                    self.last_schedule_creation = SimMan.now
                    self.nextScheduleCreation = SimMan.now + schedule.get_end_time() * \
                                                self.configuration.timeslot_length
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
                    self.control.schedule_executed()
                    next_observation = self.interpreter.getObservation()
                    logger.debug("last observation was %s\nnext observation is %s", str(observation),
                                 str(next_observation), sender=self)
                    reward = self.interpreter.getReward()
                    loss.append(-reward)
                    cum_loss += -reward
                    observation = next_observation
                self.simualtion_done_event.trigger(loss)
            if self.configuration.protocol_type == ProtocolType.CSMA:
                loss = []
                cum_loss = 0
                observation = self.interpreter.get_first_observation()
                for i in range(horizon):
                    schedules = self.scheduler.next_schedule(observation)
                    sensor_schedule = schedules[0]
                    controller_schedule = schedules[1]
                    self.last_schedule_creation = SimMan.now
                    send_cmd = Message(
                        StackMessageTypes.SEND, {
                            "schedule": sensor_schedule,
                            "controller_schedule": controller_schedule,
                            "clock": self.last_schedule_creation
                        }
                    )
                    self._mac.gates["networkIn"].send(send_cmd)
                    self.nextScheduleCreation = SimMan.now + sensor_schedule.get_end_time() * \
                                                self.configuration.timeslot_length
                    self._n_schedule_created.trigger(controller_schedule)
                    yield send_cmd.eProcessed
                    self.send_schedule_amount += 1
                    yield SimMan.timeoutUntil(self.nextScheduleCreation)
                    self.control.schedule_executed()
                    reward = self.interpreter.getReward()
                    cum_loss += -reward
                    loss.append(-reward)
                self.simualtion_done_event.trigger(loss)


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

        # needed because of switch between training and simulation
        initial_state = self.plant.get_state()
        initial_output = self.c @ initial_state + np.random.multivariate_normal(self.mean, self.cov)
        self.outputs = [initial_output[0]]
        self.inputs = [0.0]  # just for evaluation, the sensor usually doesn't know these
        self.is_simulating = False

    def reset(self):
        if self.configuration.kalman_reset:
            self.kalman = KalmanFilter(dim_x=2, dim_z=1)
            self.kalman.x = self.plant.state
            self.kalman.F = self.plant.a
            self.kalman.H = self.c
            self.kalman.P = self.plant.x0_cov
            self.kalman.R = np.array([[self.plant.r_subsystem]])
            self.kalman.Q = self.plant.q_subsystem

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
            if self.configuration.show_inputs_and_outputs is True and self.is_simulating is True:
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
        pass


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
        self.timestep_errorrate_sender = np.ones(self.schedule_length, dtype=int)
        self.timestep_errorrate_gateway = np.ones(self.schedule_length, dtype=int)
        self.last_update = np.zeros(self.device_amount, dtype=int)
        self.observation_size = self.device_amount + self.schedule_length
        self.device_amount = self.device_amount

    def reset(self):
        self.timestep_success = np.zeros(self.schedule_length, dtype=int)
        self.timestep_errorrate_sender = np.ones(self.schedule_length, dtype=int)
        self.timestep_errorrate_gateway = np.ones(self.schedule_length, dtype=int)
        self.last_update = np.zeros(self.device_amount, dtype=int)

    def onPacketReceived(self, message, senderIndex: int, receiverIndex= None, payload=None):
        logger.debug("received arrived packet information", sender="Interpreter")
        # TODO: action for different schedulers same?

        time_since_schedule = SimMan.now - self.gateway.last_schedule_creation
        schedule_timeslot = math.trunc(time_since_schedule/self.configuration.timeslot_length) - 1
        self.timestep_success[schedule_timeslot] = 1
        error_sender = message.args["csisender"]
        error_gateway = message.args["csigateway"]
        self.timestep_errorrate_sender[schedule_timeslot] = error_sender
        self.timestep_errorrate_gateway[schedule_timeslot] = error_gateway
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
        self.timestep_errorrate_sender = np.ones(self.schedule_length, dtype=int)
        self.timestep_errorrate_gateway = np.ones(self.schedule_length, dtype=int)

    def onFrequencyBandAssignment(self, deviceIndex=None, duration=None):
        pass

    def getReward(self) -> float:
        """
        Computes the reward for the last schedule. The result is only effected by the scheduler type, not by the
        protocol type
        Computed as follows:

        :return: The computed reward
        """

        reward = [[0.0]]  # paper scheduler

        id_to_plant = self.gateway.control.controller_id_to_plant
        for i in range(len(id_to_plant)):
            plant: StateSpacePlant = id_to_plant[i]
            q = plant.q_subsystem
            r = plant.r_subsystem
            control_output = self.gateway.control.getControl(self.gateway.control.controller_id_to_actuator_id[i], True)
            control = control_output[0]
            estimated_state = control_output[1]
            real_state = plant.state
            logger.debug("plant %d: last control is %s, estimated state is %s", i, control.__str__(), estimated_state.__str__(),
                         sender="Interpreter")
            single_reward = -1
            if self.configuration.reward == RewardType.GoalEstimatedStateError:
                single_reward = -(estimated_state.transpose()@q@estimated_state + control.transpose()*r*control)
            if self.configuration.reward == RewardType.GoalRealStateError:
                single_reward = -(real_state.transpose() @ q @ real_state + control.transpose() * r * control)
            if self.configuration.reward == RewardType.EstimationError:
                pass
            logger.debug("single reward is %f", single_reward, sender="Interpreter")
            reward += single_reward
        logger.debug("computed reward is %f", reward, sender="Interpreter")
        return reward[0][0]

    def get_first_observation(self):
        observation = None
        if self.configuration.scheduler_type == SchedulerType.MYDQN:  # my scheduler
            tau = np.zeros(len(self.last_update), dtype=int)
            observation = np.hstack((tau,
                                     self.timestep_success,
                                     self.timestep_errorrate_sender,
                                     self.timestep_errorrate_gateway))
        elif self.configuration.scheduler_type == SchedulerType.DQN or self.configuration.scheduler_type == SchedulerType.FIXEDDQN:
            tau = np.zeros(len(self.last_update), dtype=int)
            observation = np.hstack((tau, self.timestep_success))
        elif self.configuration.scheduler_type == SchedulerType.GREEDYWAIT:
            observation = np.zeros(len(self.last_update), dtype=int)
        logger.debug("computed observation: %s", observation.__str__(), sender="Interpreter")
        return observation

    def getObservation(self):
        observation = None

        if self.configuration.scheduler_type == SchedulerType.MYDQN:
            current_slot = self.gateway.simulatedSlot
            tau = np.zeros(len(self.last_update), dtype=int)
            for i in range(len(self.last_update)):
                tau[i] = current_slot - self.last_update[i]
            observation = np.hstack((tau,
                                     self.timestep_success,
                                     self.timestep_errorrate_sender,
                                     self.timestep_errorrate_gateway))

        elif self.configuration.scheduler_type == SchedulerType.DQN or self.configuration.scheduler_type == SchedulerType.FIXEDDQN:
            current_slot = self.gateway.simulatedSlot
            tau = np.zeros(len(self.last_update), dtype=int)
            for i in range(len(self.last_update)):
                tau[i] = current_slot-self.last_update[i]
            observation = np.hstack((tau, self.timestep_success))

        elif self.configuration.scheduler_type == SchedulerType.GREEDYERROR:
            observation = []
            for i in range(len(self.gateway.deviceIndexToMacDict)):
                pass

        elif self.configuration.scheduler_type == SchedulerType.GREEDYWAIT:
            current_slot = self.gateway.simulatedSlot
            tau = np.zeros(len(self.last_update), dtype=int)
            for i in range(len(self.last_update)):
                tau[i] = current_slot - self.last_update[i]
            observation = tau
        logger.debug("computed observation: %s", observation.__str__(), sender="Interpreter")
        return observation

    def getDone(self):
        return False

    def getInfo(self):
        pass


