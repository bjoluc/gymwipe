import itertools
import logging
import random
from collections import deque
from enum import Enum

import numpy as np
import tensorflow as tf
from keras.layers import Dense
from keras.models import Sequential
from keras.optimizers import Adam

from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class Schedule():
    """
        A framework for schedule classes. A implemented schedule will produce and contain the specific schedule for a scheduling descision taken by a scheduler
    """
    def __init__(self, action):
        self.action = action # Action output from Scheduler
        self.schedule = []
        self.string = ""


    def getString(self):
        raise NotImplementedError



class Scheduler():
    """
        A framework for a Scheduler class, which will produce channel allocation schedules
    """
    def __init__(self, devices, timeslots: int):
        """
        Args:
            devices: a list of MAC adresses which should be considered while producing a schedule
            int timeslots: the number of timeslots for which scheduling descisions should be taken
        """
        self.devices = devices # list of sensor/controller mac adresses
        self.schedule = None # current schedule
        self.timeslots = timeslots # 
    

    def nextSchedule(self, input) -> Schedule:
        """
            produces the next schedule, possibly given information about the system's state. Raises a NotImplementedError if not overridden by a subclass

            Args:
                input: a representation of the observed state
        """
        raise NotImplementedError

class RoundRobinTDMAScheduler(Scheduler):
    """
    A Round Robin Scheduler producing a TDMA Schedule
    """
    def __init__(self, devices: [], sensors: [], actuators: [], timeslots: int):
        super(RoundRobinTDMAScheduler,self).__init__(devices, timeslots)
        self.sensors = sensors
        self.actuators = actuators
        self.nextDevice = 0 # position in device list of the first device in the next schedule
        self.wasActuator = False
        
    def nextSchedule(self, input = None):
        action = []
        for i in range(self.timeslots):
            if(self.devices[self.nextDevice] in self.actuators):
                if self.wasActuator == True:
                    action.append([self.devices[self.nextDevice], 0])
                    self.wasActuator = False
                else:   
                    action.append([self.devices[self.nextDevice], 1])
                    self.wasActuator = True
            else:
                action.append([self.devices[self.nextDevice],0])
            if self.wasActuator == False:
                if self.nextDevice == (len(self.devices) -1):
                    self.nextDevice = 0
                else:
                    self.nextDevice += 1
            
        logger.debug("new schedule generated", sender=self)    
        self.schedule = TDMASchedule(action)
        return self.schedule

class DQNTDMAScheduler(Scheduler):
    """
        A DQN Scheduler producing a TDMA Schedule
    """
    def __init__(self, devices: {}, sensors: [], actuators: [], timeslots: int):
        super(DQNTDMAScheduler,self).__init__(devices, timeslots)
        self.sensors = sensors
        self.actuators = actuators

        self.batch_size = 32  # mini-batch size
        self.memory = deque(maxlen=20000)   # replay memory
        self.alpha = 0.95              # discount rate
        self.epsilon = 1                  # exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.999
        self.learning_rate = np.exp(-4)
        self.c = 100        # how many steps to fix target Q
        
        self.inputsize = 3* len(self.sensors) + 2* len(self.actuators) + self.timeslots
        self.actionset = list(itertools.combinations_with_replacement(self.devices,self.timeslots))
        self.actionsize = len(self.actionset)
        self.string = ', '.join(map(str, self.actionset))
        logger.debug("actionset: " + self.string, sender=self)

        self.model = self._buildModel()
        self.targetModel = self._buildModel()
        logger.debug("initialzed. statetsize : " + self.inputsize.__str__() + " actionsize: " + self.actionsize.__str__(), sender=self)

    def _buildModel(self):
        model = Sequential()
        model.add(Dense(1024, input_dim=self.inputsize, activation='relu'))
        model.add(Dense(1024, activation='relu'))
        model.add(Dense(self.actionsize, activation='linear'))
        model.compile(loss='mean_squared_error', optimizer=Adam(lr=self.learning_rate, decay=.001))

        return model

    def update_target_model(self):
        # copy weights from model to target_model
        self.targetModel.set_weights(self.model.get_weights())

    def remember(self, state, action, reward, next_state):
        self.memory.append((state, action, reward, next_state))

    def load(self, name):
        self.model.load_weights(name)

    def save(self, name):
        self.model.save_weights(name)

    def act(self, state):
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.actionsize)
        act_values = self.model.predict(state)
        return np.argmax(act_values[0])  # returns action

    def nextSchedule(self, input):
        return None

class DQNCSMAScheduler(Scheduler):
    """
        A DQN Scheduler producing a CSMA Schedule
    """
    def __init__(self, devices, timeslots: int):
        super(DQNCSMAScheduler,self).__init__(devices, timeslots)
        self. result = 0

    def nextSchedule(self, input):
        x = tf.Variable(3, name ="x")
        y = tf.Variable(4, name = "y")

        f = x*x*y +y +2
        with tf.Session() as sess:
            x.initializer.run()
            y.initializer.run()
            self.result = f.eval()

        logger.debug("Computation result:" + self.result.__str__(), sender = self)    
        return None





class TDMASchedule(Schedule):
    """
        A TDMA Schedule implementation. In every timeslot one single device will be allowed to send. 
        If multiple consecutive timeslots are assigned to the same device, 
        the device won't be written down a second time but the time in the next line will be increased 
        by the amount of the consecutive timeslots
    """
    def __init__(self, action):
        super(TDMASchedule, self).__init__(action)
        lastAction = None
        for i in range(len(self.action)):            
            if self.action[i] != lastAction:
                self.schedule.append((i+1).__str__() + " " + self.action[i][0].__str__() + " "+
                                     self.action[i][1].__str__() + " 1")
            lastAction = self.action[i]
        self.schedule.append((len(action)+1).__str__())
        self.string = " ".join(self.schedule)
        logger.debug("Schedule created. Content: " + self.string, sender=self)

    def getString(self):
        return self.string

    def getNextRelevantTimespan(self, MACadress, lastStep):

        schedulelist = self.string.split(" ")
        for i in range(len(schedulelist)):
            if schedulelist[(i % 4) - 1] == 0:
                if schedulelist[i] == MACadress:
                    if schedulelist[i-1] > lastStep:
                        logger.debug("relevant span for %s is %d to %d", MACadress, schedulelist[i-1],
                                     schedulelist[i+3], sender=self)
                        return [schedulelist[i-1], schedulelist[i+3]]
        return None

    def getEndTime(self) -> int:
        schedulelist = self.string.split(" ")
        return int(schedulelist[len(schedulelist)-1])


class CSMASchedule():
    pass


def CSMAEncode(schedule : CSMASchedule, compressed: bool) -> int:
    return 0

def TDMAEncode(schedule: TDMASchedule, compressed:bool) -> int:
    bytesize = 1 #endbyte
    if compressed==False:
        for i in range((len(schedule.schedule)-1)):
            bytesize += 7
        return bytesize
    else:
        alreadyIn = []
        alreadyInTime = []
        for i in range((len(schedule.action))):
            if schedule.action[i][0] in alreadyIn:
                bytesize +=3
                logger.debug("mac already in Schedule: %s" ,schedule.action[i][0]  , sender = "TDMAEncode")
            else:
                logger.debug("mac not yet in schedule: %s", schedule.action[i][0], sender="TDMAEncode")
                bytesize +=7
                alreadyIn.append(schedule.action[i][0])
                alreadyInTime.append(i+1)
        return bytesize
