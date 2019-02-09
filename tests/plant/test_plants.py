import logging
import matplotlib.pyplot as plt
import pytest
from gymwipe.simtools import SimMan
from gymwipe.plants.state_space_plants import MatlabPendulum
from scipy import signal as sg
import os
from math import sin, cos, pi
import time

from ..fixtures import simman


def test_pendulum(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.core')
    pendulum = LinearInvertedPendulum(100, 500, 9.81, 0.3)

    imp_response = pendulum.get_impulse_response(10000)
    assert False


def test_rcl(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.core')
    rcl = RCL(10, 10, 10)
    assert False


def test_matlab(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    pendulum = MatlabPendulum(0.2, 1, 0.5, 9.81, 0.0001)
    pendulum.impulse()
    time.sleep(10)
    assert False
