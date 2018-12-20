from gym.envs.registration import register

from gymwipe.envs.counter_traffic import CounterTrafficEnv
from gymwipe.envs.inverted_pendulum import InvertedPendulumEnv

register(
    id='CounterTraffic-v0',
    entry_point='gymwipe.envs:CounterTrafficEnv',
)

register(
    id='InvertedPendulum-v0',
    entry_point='gymwipe.envs:InvertedPendulumEnv',
)
