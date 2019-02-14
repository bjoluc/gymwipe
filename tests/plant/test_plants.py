import logging
import matplotlib.pyplot as plt
import pytest
from gymwipe.simtools import SimMan
from gymwipe.plants.state_space_plants import MatlabPendulum
from  gymwipe.plants.random_plants import RandomPlant2
from scipy import signal as sg
import os
from math import sin, cos, pi
import time

from ..fixtures import simman


def test_matlab(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    pendulum = MatlabPendulum(0.2, 1, 0.5, 9.81, 0.0001)
    pendulum.impulse()
    time.sleep(10)
    assert False


def test_state_computation(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    pendulum = MatlabPendulum(0.2, 1, 0.5, 9.81, 0.001)
    pendulum.set_motor_velocity(10.0, SimMan.now)
    SimMan.runSimulation(0.01) # 10 update times
    pendulum.update_state(SimMan.now)
    time.sleep(10)
    assert False


def test_random(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.random_plants')
    plant = RandomPlant2(1, 2, 1, 0.001)
    assert False
