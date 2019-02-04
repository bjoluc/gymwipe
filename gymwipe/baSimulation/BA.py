import logging

from gymwipe.simtools import SimTimePrepender

from gymwipe.networking.messages import StackMessageTypes
logger = SimTimePrepender(logging.getLogger(__name__))
TIMESLOT_LENGTH = 0.01
EPISODES = 200  # number of episodes
T = 500  # horizon length
SCHEDULER = 1
"""
1: Round Robin
2: My DQN
3: paper DQN
"""
PROTOCOL = 1
"""
1: TDMA
2: CSMA
"""


class Environment:
    def __init__(self):
        self.no_feedback_control_loops = 6
        self.sensors: [] = None
        self.actuators: [] = None
        self.controllers: [] = None

        self.param_seed = 61




class Evaluator:
    def __init__(self, gateway_mac, sensor_macs:[], actuator_macs: []):
        pass

    def schedule_results(self):
        pass

    def episode_results(self, ave_cost, ave_reward, episode, duration):
        pass



def reset():
    pass

if __name__ == "__main__":

    # train model
    episodes = 200  # number of episodes
    T = 500  # horizon length


