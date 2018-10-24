from gym.envs.registration import register

from gymwipe.envs.counter_traffic import CounterTrafficEnv

register(
    id='CounterTraffic-v0',
    entry_point='gymwipe.envs:CounterTrafficEnv',
)
