TIMESLOT_LENGTH = 0.002
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


if __name__ == "__main__":

    # train model
    episodes = 200  # number of episodes
    T = 500  # horizon length


