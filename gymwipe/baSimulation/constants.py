from enum import Enum


class ConfigType(Enum):
    """
    An enumeration of scheduler types to be used for the environment's configuration
    """
    unspecified = 0
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8
    I = 9
    J = 10
    K = 11
    L = 12
    M = 13
    N = 14
    O = 15
    P = 16
    Q = 17
    R = 18
    S = 19
    T = 20
    U = 21
    V = 22
    W = 23
    X = 24
    Y = 25
    Z = 26
    Z_ = 27


current_episode = 0


class SchedulerType(Enum):
    """
    An enumeration of scheduler types to be used for the environment's configuration
    """
    RANDOM = 0
    ROUNDROBIN = 1
    MYDQN = 2
    DQN = 3
    GREEDYWAIT = 4
    GREEDYERROR = 5
    FIXEDDQN = 6


class ProtocolType(Enum):
    """
    An enumeration of protocol types to be used for the environment's configuration
    """
    TDMA = 0
    CSMA = 1


class RewardType(Enum):
    """
    An enumeration of protocol types to be used for the environment's configuration
    """
    GoalEstimatedStateError = 0
    EstimationError = 1
    GoalRealStateError = 2


class Configuration:
    def __init__(self,
                 config_type: ConfigType,
                 scheduler_type: SchedulerType,
                 protocol_type: ProtocolType,
                 max_distance: float = 3,
                 min_distance: float = 0.7,
                 timeslot_length: float = 0.01,
                 episodes: int = 200,
                 horizon: int = 500,
                 num_plants: int = 2,
                 num_instable_plants: int = 0,
                 schedule_length: int = 2,
                 show_inputs_and_outputs: bool = True,
                 show_error_rates: bool = True,
                 kalman_reset: bool = True,
                 show_statistics: bool = True,
                 show_assigned_p_values: bool = True,
                 simulate: bool = True,
                 simulation_horizon: int = 150,
                 long_simulation_horizon: int = 1000,
                 seed: int = 42,
                 reward=RewardType.GoalRealStateError,
                 simulation_rounds: int = 16):
        self.max_distance = max_distance
        self.min_distance = min_distance
        self.scheduler_type = scheduler_type
        self.protocol_type = protocol_type
        if config_type == ConfigType.unspecified:
            self.num_plants = num_plants
            if num_plants >= num_instable_plants:
                self.num_instable_plants = num_instable_plants
            else:
                self.num_instable_plants = num_plants
            self.schedule_length = schedule_length

        if config_type == ConfigType.A:
            self.num_plants = 2
            self.num_instable_plants = 0
            self.schedule_length = 2

        if config_type == ConfigType.B:
            self.num_plants = 2
            self.num_instable_plants = 1
            self.schedule_length = 2

        if config_type == ConfigType.C:
            self.num_plants = 2
            self.num_instable_plants = 2
            self.schedule_length = 2

        if config_type == ConfigType.D:
            self.num_plants = 4
            self.num_instable_plants = 0
            self.schedule_length = 2

        if config_type == ConfigType.E:
            self.num_plants = 4
            self.num_instable_plants = 2
            self.schedule_length = 2

        if config_type == ConfigType.F:
            self.num_plants = 6
            self.num_instable_plants = 0
            self.schedule_length = 2

        if config_type == ConfigType.G:
            self.num_plants = 6
            self.num_instable_plants = 2
            self.schedule_length = 2

        if config_type == ConfigType.H:
            self.num_plants = 8
            self.num_instable_plants = 0
            self.schedule_length = 2

        if config_type == ConfigType.I:
            self.num_plants = 8
            self.num_instable_plants = 3
            self.schedule_length = 2

        if config_type == ConfigType.J:
            self.num_plants = 2
            self.num_instable_plants = 0
            self.schedule_length = 4

        if config_type == ConfigType.K:
            self.num_plants = 2
            self.num_instable_plants = 1
            self.schedule_length = 4

        if config_type == ConfigType.L:
            self.num_plants = 2
            self.num_instable_plants = 2
            self.schedule_length = 4

        if config_type == ConfigType.M:
            self.num_plants = 4
            self.num_instable_plants = 0
            self.schedule_length = 4

        if config_type == ConfigType.N:
            self.num_plants = 4
            self.num_instable_plants = 2
            self.schedule_length = 4

        if config_type == ConfigType.O:
            self.num_plants = 6
            self.num_instable_plants = 0
            self.schedule_length = 4

        if config_type == ConfigType.P:
            self.num_plants = 6
            self.num_instable_plants = 2
            self.schedule_length = 4

        if config_type == ConfigType.Q:
            self.num_plants = 8
            self.num_instable_plants = 0
            self.schedule_length = 4

        if config_type == ConfigType.R:
            self.num_plants = 8
            self.num_instable_plants = 3
            self.schedule_length = 4

        if config_type == ConfigType.S:
            self.num_plants = 4
            self.num_instable_plants = 0
            self.schedule_length = 6

        if config_type == ConfigType.T:
            self.num_plants = 4
            self.num_instable_plants = 1
            self.schedule_length = 6

        if config_type == ConfigType.U:
            self.num_plants = 4
            self.num_instable_plants = 2
            self.schedule_length = 6

        if config_type == ConfigType.V:
            self.num_plants = 6
            self.num_instable_plants = 0
            self.schedule_length = 6

        if config_type == ConfigType.W:
            self.num_plants = 6
            self.num_instable_plants = 2
            self.schedule_length = 6

        if config_type == ConfigType.X:
            self.num_plants = 6
            self.num_instable_plants = 3
            self.schedule_length = 6

        if config_type == ConfigType.Y:
            self.num_plants = 8
            self.num_instable_plants = 0
            self.schedule_length = 6

        if config_type == ConfigType.Z:
            self.num_plants = 8
            self.num_instable_plants = 2
            self.schedule_length = 6

        if config_type == ConfigType.Z_:
            self.num_plants = 8
            self.num_instable_plants = 4
            self.schedule_length = 6
        self.episodes = episodes
        self.horizon = horizon
        if scheduler_type == SchedulerType.DQN or scheduler_type == SchedulerType.MYDQN or scheduler_type == SchedulerType.FIXEDDQN:
            self.train = True
        else:
            self.train = False
        self.long_simulation_horizon = long_simulation_horizon
        self.timeslot_length = timeslot_length
        self.simulation_rounds = simulation_rounds
        self.plant_sample_time = self.timeslot_length + self.timeslot_length*self.schedule_length
        self.sample_to_timeslot_ratio = (self.timeslot_length*self.schedule_length + self.timeslot_length)/self.plant_sample_time
        self.sensor_sample_time = self.plant_sample_time
        self.show_inputs_and_outputs = show_inputs_and_outputs
        self.show_error_rates = show_error_rates
        self.kalman_reset = kalman_reset
        self.simulate = simulate
        self.simulation_horizon = simulation_horizon
        self.show_statistics = show_statistics
        self.show_assigned_p_values = show_assigned_p_values
        self.seed = seed
        self.reward = reward
        self.config_type = config_type






