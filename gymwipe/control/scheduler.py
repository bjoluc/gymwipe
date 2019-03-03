import itertools
import logging
import random
from enum import Enum

from gymwipe.simtools import SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class SendOrReceive(Enum):
    """
    An enumeration of control message types to be used for the exchange of
    `Message` objects between network stack layers.
    """
    SEND = 0
    RECEIVE = 1


class Schedule:
    """
        A framework for schedule classes. A implemented schedule will produce and contain the specific schedule for
        a scheduling descision taken by a scheduler
    """
    def __init__(self, action):
        self.action = action # Action output from Scheduler
        self.schedule = []
        self.string = ""

    def get_string(self):
        raise NotImplementedError

    def get_end_time(self):
        raise NotImplementedError


class TDMASchedule(Schedule):
    """
        A TDMA Schedule implementation. In every timeslot one single device will be allowed to send.
        If multiple consecutive timeslots are assigned to the same device,
        the device won't be written down a second time but the time in the next line will be increased
        by the amount of the consecutive timeslots
    """
    def __init__(self, action):
        super(TDMASchedule, self).__init__(action)
        last_action = None
        for i in range(len(self.action)):
            if self.action[i] != last_action:
                self.schedule.append([i+1, self.action[i][0],
                                     self.action[i][1], 1])
            last_action = self.action[i]
        self.schedule.append([len(action)+1])
        logger.debug("TDMA Schedule created. Content: %s" + self.schedule.__str__(), sender="TDMA Schedule")

    def get_string(self):
        return self.schedule.__str__()

    def get_next_relevant_timespan(self, mac_address, last_step):
        logger.debug("called function with address %s and last step %d", mac_address, last_step, sender="TDMA Schedule")
        schedule_list = self.string.split(" ")
        for i in range(len(self.schedule)-1):
            line = self.schedule[i]
            logger.debug("Found a mac address field, address is: %s", line[1], sender="TDMA Schedule")
            if line[1] == mac_address:
                logger.debug("mac addresses are the same : %s at timestep %s", mac_address, line[0],
                             sender="TDMA Schedule")
                if line[0] > last_step:
                    logger.debug("relevant span for %s is %s to %s", mac_address, line[0],
                                 self.schedule[i+1][0], sender="TDMA Schedule")
                    return [line[0], self.schedule[i+1][0]]
        return None

    def get_end_time(self) -> int:
        logger.debug("endtime is %s", self.schedule[len(self.schedule)-1][0], sender="TDMASchedule")
        return self.schedule[len(self.schedule)-1][0]


class CSMAControllerSchedule(Schedule):
    def __init__(self, action):
        """

        :param action: The action chosen by the scheduler.
        """
        super(CSMAControllerSchedule, self).__init__(action)
        sum = 0.0
        for i in range(len(self.action)):
            sum += action[i][1]

        if round(sum, 1) is 1.0:
            for i in range(len(self.action)):
                self.schedule.append([self.action[i][0], self.action[i][1]])

            self.string = self.schedule.__str__()
            logger.debug("CSMA Controller Schedule created. Content: " + self.string, sender="CSMA Schedule")
        else:
            logger.debug("p sum is higher than 1", sender=self)

    def get_chosen_controller(self, decide:float):
        chosen_controller = None
        controllers_p = 0.0
        for i in range(len(self.schedule)):
            current_p = self.schedule[i][1]
            if current_p <= decide:
                pass
    def get_string(self):
        return self.string

    def get_end_time(self):
        return None


class CSMASchedule(Schedule):
    """
    A CSMA schedule implementation. Each device is assigned a likelihood of starting to send its data when it is
    currently not receiving data.

    """
    def __init__(self, action, length):
        """

        :param action: The action chosen by the scheduler.
        :param length:  The amount of timeslots in which this schedule is valid
        """
        super(CSMASchedule, self).__init__(action)
        self.length = length
        for i in range(len(self.action)):
            self.schedule.append([self.action[i][0], self.action[i][1]])
        self.schedule.append([self.length])

        self.string = self.schedule.__str__()
        logger.debug("CSMA Schedule created. Content: " + self.string, sender="CSMA Schedule")

    def get_my_p(self, addr):
        for i in range(len(self.schedule)):
            line = self.schedule[i]
            if addr == line[0]:
                return line[1]
        return 0.0

    def get_string(self):
        return self.string

    def get_end_time(self):
        return self.length


class TDMAScheduler:
    """
        A framework for a Scheduler class, which will produce channel allocation schedules
    """
    def __init__(self, devices, actuators, timeslots: int):
        """
        Args:
            devices: a list of MAC adresses which should be considered while producing a schedule
            int timeslots: the number of timeslots for which scheduling decisions should be taken
        """
        self.devices = devices  # list of sensor/controller mac addresses
        self.actuators = actuators
        self.schedule = None  # current schedule
        self.timeslots = timeslots  # length of schedule

    def next_schedule(self, observation) -> Schedule:
        """
            produces the next schedule, possibly given information about the system's state. Raises a
            NotImplementedError if not overridden by a subclass

            Args:
                observation: a representation of the observed state
        """
        raise NotImplementedError

    def get_next_control_slot(self, last_control_slot) -> [int, str]:
        for i in range(len(self.schedule.schedule)-1):
            line = self.schedule.schedule[i]
            logger.debug("found line %s", line.__str__(), sender="Scheduler")
            if line[1] in self.actuators:  # is control line
                if line[0] > last_control_slot:  # is next control line
                    return [line[0], line[1]]
        return None


class CSMAScheduler:
    def __init__(self, sensors, gatewaymac, timeslots:int):
        self.sensors = sensors
        self.gatewaymac = gatewaymac
        self.timeslots = timeslots
        self.sensor_schedule = None
        self.controller_schedule = None

    def next_schedule(self, observation) -> [CSMASchedule, CSMAControllerSchedule]:
        raise NotImplementedError


class RandomTDMAScheduler(TDMAScheduler):
    def __init__(self, devices: [], actuators: [], timeslots: int):
        super(RandomTDMAScheduler, self).__init__(devices, actuators, timeslots)
        self.action_set = self.action_set = list(itertools.permutations(range(len(devices)), timeslots))
        self.action_size = len(self.action_set)

    def next_schedule(self, observation=None):
        action = []
        devices = self.action_set[random.randrange(self.action_size)]
        logger.debug("chosen devices are %s", devices.__str__(), sender=self)
        for i in range(len(devices)):
            device = self.devices[devices[i]]
            if device in self.actuators:
                action.append([device, SendOrReceive.RECEIVE])
            else:
                action.append([device, SendOrReceive.SEND])
        self.schedule = TDMASchedule(action)
        logger.debug("new random schedule generated, content is %s", self.schedule.schedule.__str__(),
                     sender="RandomTDMAScheduler")
        return self.schedule


class RoundRobinTDMAScheduler(TDMAScheduler):
    """
    A implementation of the :class:`~gymwipe.networking.scheduler.Scheduler` class that realizes a round robin
    approach. That means, that every device gets one slot in a fixed order.
    """
    def __init__(self, devices: [], sensors: [], actuators: [], timeslots: int):
        super(RoundRobinTDMAScheduler, self).__init__(devices, actuators, timeslots)
        self.sensors = sensors
        self.nextDevice = 0 # position in device list of the first device in the next schedule
        self.wasActuator = False

    def next_schedule(self, observation=None) -> TDMASchedule:
        """
        Returns the next TDMA schedule. The :class:`~gymwipe.networking.scheduler.RoundRobinTDMAScheduler` doesn't
        need an observation, since it just remembers the first next device, which should be given a timeslot and then
        assigns a slot to the next T devices.
        :return The generated TDMA schedule
        """
        action = []
        for i in range(self.timeslots):
            device = self.devices[self.nextDevice]
            if device in self.actuators:
                action.append([device, SendOrReceive.RECEIVE])
            else:
                action.append([device, SendOrReceive.SEND])
            if self.nextDevice == (len(self.devices) - 1):
                self.nextDevice = 0
            else:
                self.nextDevice += 1
            
        logger.debug("new schedule generated", sender="RoundRobinTDMAScheduler")
        self.schedule = TDMASchedule(action)
        return self.schedule


class GreedyWaitingTimeTDMAScheduler(TDMAScheduler):
    """
    A implementation of the :class:`~gymwipe.networking.scheduler.Scheduler` class that realizes a greedy waiting time
    approach. That means, that the devices that waited the most slots since their last successful transmission are
    scheduled next.
    """
    def __init__(self, devices: [], actuators: [], timeslots: int):
        super(GreedyWaitingTimeTDMAScheduler, self).__init__(devices, actuators, timeslots)

    def next_schedule(self, observation: list) -> TDMASchedule:
        """
        Returns the next TDMA Schedule, based on the given observation. The observation contains for every device
        the amount of slots that have passed since their last successful transmission.
        :param observation: The given observation. Needs to be an array filled with the waiting time of every device,
        where the index represents the device's id
        :return The generated TDMA schedule
        """
        action = []
        for i in range(self.timeslots):
            max_value = max(observation)
            max_index = observation.index(max_value)
            device = self.devices[max_index]
            if device in self.actuators:
                action.append([device, SendOrReceive.RECEIVE])
            else:
                action.append([device, SendOrReceive.SEND])
            observation[max_index] = -1

        logger.debug("new schedule generated", sender="TDMAGreedyWaitingTime")
        self.schedule = TDMASchedule(action)
        return self.schedule


class GreedyErrorTDMAScheduler(TDMAScheduler):
    def __init__(self, devices: [], actuators: [], timeslots: int):
        super(GreedyErrorTDMAScheduler, self).__init__(devices, actuators, timeslots)

    def next_schedule(self, observation: list) -> TDMASchedule:
        """
        Returns the next TDMA Schedule, based on the given observation. The observation contains for every device
        the computed error.
        :param observation: The given observation. Needs to be an array filled with the error of every device,
        where the index represents the device's id
        :return The generated TDMA schedule
        """
        pass


class GreedyWaitingTimeCSMAScheduler(CSMAScheduler):
    def __init__(self, sensors: [], timeslots: int):
        super(GreedyWaitingTimeCSMAScheduler, self).__init__(sensors, timeslots)

    def next_schedule(self, observation) -> [CSMASchedule, CSMAControllerSchedule]:
        action_sensors = []
        action_controllers = []
        for i in range(len(self.sensors)):
            pass


class RandomCSMAScheduler(CSMAScheduler):
    def __init__(self, sensors: [], gatewaymac, timeslots: int):
        super(RandomCSMAScheduler, self).__init__(sensors, gatewaymac, timeslots)

    def next_schedule(self, observation=None) -> [CSMASchedule, CSMAControllerSchedule]:
        action_sensors = []
        action_controllers = []
        p_left = 1
        for i in range(len(self.sensors)):
            action_sensors.append([self.sensors[i], random.uniform(0, 1)])
            controller_p = random.uniform(0, p_left)
            p_left -= controller_p
            action_controllers.append([i, controller_p])
        random.shuffle(action_controllers)
        action_sensors.append([self.gatewaymac, random.uniform(0, 1)])
        self.sensor_schedule = CSMASchedule(action_sensors, self.timeslots)
        self.controller_schedule = CSMAControllerSchedule(action_controllers)
        return [self.sensor_schedule, self.controller_schedule]


def csma_encode(schedule: CSMASchedule) -> int:
    bytesize = 0
    for i in range(len(schedule.schedule)-1):
        bytesize += 7
    bytesize += 1
    return bytesize


def tdma_encode(schedule: TDMASchedule) -> int:
    """
    Computes the length in bytes of the given schedule. If the compressed option is set to True, a compression
    of the schedule is simulated.
    :param schedule: The schedule whose length is to be calculated.
    :param compressed: Determines, if the schedule should be compressed or not
    :return: The length of the schedule in number of bytes
    """
    bytesize = 1  # time byte at the end of the schedule
    for i in range((len(schedule.schedule)-1)):
        bytesize += 7
        # TODO: Change when schedule format is fixed
    return bytesize
