import logging

import gym
import numpy as np

import gymwipe.envs


def test_counter_traffic_env(caplog):
    caplog.set_level(logging.INFO, logger='gymwipe.networking.construction')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.core')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.physical')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.simple_stack')
    caplog.set_level(logging.INFO, logger='gymwipe.simtools')

    # Get the environment and extract the number of actions.
    env = gym.make('CounterTraffic-v0')
    np.random.seed(123)
    env.seed(123)

    observation_center = env.COUNTER_BOUND

    # Give device 0 the frequency band for 3 time units (number depends on
    # env.ASSIGNMENT_DURATION_FACTOR) – it should have sent one packet then
    observation, reward, _, _ = env.step({"device": 0, "duration": 3})
    # should be enough for 2 packets to be sent
    assert observation - observation_center == 2
    assert reward == -2
    
    # Give device 1 the frequency band 4 times longer (it sends 3 packets per number),
    # thus one packet of the next number should have been sent afterwards
    observation, reward, _, _ = env.step({"device": 1, "duration": 12})
    assert observation - observation_center == 0
    assert reward == 2
