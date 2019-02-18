import logging

from gymwipe.simtools import SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))


class Schedule:
    """
        A framework for schedule classes. A implemented schedule will produce and contain the specific schedule for a scheduling descision taken by a scheduler
    """
    def __init__(self, action):
        self.action = action # Action output from Scheduler
        self.schedule = []
        self.string = ""

    def get_string(self):
        raise NotImplementedError

    def get_end_time(self):
        raise NotImplementedError


class Scheduler:
    """
        A framework for a Scheduler class, which will produce channel allocation schedules
    """
    def __init__(self, devices, timeslots: int):
        """
        Args:
            devices: a list of MAC adresses which should be considered while producing a schedule
            int timeslots: the number of timeslots for which scheduling decisions should be taken
        """
        self.devices = devices  # list of sensor/controller mac addresses
        self.schedule = None  # current schedule
        self.timeslots = timeslots  # length of schedule

    def next_schedule(self, observation, last_reward) -> Schedule:
        """
            produces the next schedule, possibly given information about the system's state. Raises a
            NotImplementedError if not overridden by a subclass

            Args:
                observation: a representation of the observed state
                last_reward: the reward for the previous produced schedule
        """
        raise NotImplementedError


class RoundRobinTDMAScheduler(Scheduler):
    """
    A Round Robin Scheduler producing a TDMA Schedule
    """
    def __init__(self, devices: [], sensors: [], actuators: [], timeslots: int):
        super(RoundRobinTDMAScheduler, self).__init__(devices, timeslots)
        self.sensors = sensors
        self.actuators = actuators
        self.nextDevice = 0 # position in device list of the first device in the next schedule
        self.wasActuator = False
        
    def next_schedule(self, observation=None, last_reward=None):
        action = []
        for i in range(self.timeslots):
            if self.devices[self.nextDevice] in self.actuators:
                if self.wasActuator:
                    action.append([self.devices[self.nextDevice], 0])
                    self.wasActuator = False
                else:   
                    action.append([self.devices[self.nextDevice], 1])
                    self.wasActuator = True
            else:
                action.append([self.devices[self.nextDevice], 0])
            if not self.wasActuator:
                if self.nextDevice == (len(self.devices) - 1):
                    self.nextDevice = 0
                else:
                    self.nextDevice += 1
            
        logger.debug("new schedule generated", sender="RoundRobinTDMAScheduler")
        self.schedule = TDMASchedule(action)
        return self.schedule

    def get_next_control_slot(self, last_control_slot) -> [int, str]:
        for i in range(len(self.schedule.schedule)-1):
            line = self.schedule.schedule[i]
            logger.debug("found line %s", line.__str__(), sender="RoundRobinTDMAScheduler")
            if line[1] in self.actuators:  # is control line
                if line[0] > last_control_slot:  # is next control line
                    return [line[0], line[1]]
        return None


class TDMAGreedyWaitingTime(Scheduler):
    def __init__(self, devices: [], sensors: [], actuators: [], timeslots: int):
        super(TDMAGreedyWaitingTime, self).__init__(devices, timeslots)

    def next_schedule(self, observation, last_reward) -> Schedule:
        pass


# class CSMAGreedyWaitingTime(Scheduler):
#   def __init__(self):
#      pass

    #def next_schedule(self, observation, last_reward) -> Schedule:
        #pass


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
                self.schedule.append(self.action[i][0].__str__() + " " + self.action[i][1].__str__())

            self.string = " ".join(self.schedule)
            logger.debug("CSMA Controller Schedule created. Content: " + self.string, sender="CSMA Schedule")
        else:
            logger.debug("p sum is higher than 1", sender=self)

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
            self.schedule.append(self.action[i][0].__str__() + " " + self.action[i][1].__str__())
        self.schedule.append(self.length.__str__())

        self.string = " ".join(self.schedule)
        logger.debug("CSMA Schedule created. Content: " + self.string, sender="CSMA Schedule")

    def get_my_p(self, addr):
        for i in range(len(self.schedule)):
            line = self.schedule[i].split(" ")
            if addr.__str__() == line[0]:
                return float(line[1])
        return 0

    def get_string(self):
        return self.string

    def get_end_time(self):
        return self.length


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
