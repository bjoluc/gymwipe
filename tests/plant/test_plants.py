import logging
import matplotlib.pyplot as plt
import pytest
from gymwipe.simtools import SimMan
from gymwipe.plants.state_space_plants import LinearInvertedPendulum, RCL
from scipy import signal as sg
import math

from ..fixtures import simman


def test_pendulum(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.core')
    pendulum = LinearInvertedPendulum(500, 1000, 9.81, 1)

    imp_response = pendulum.get_impulse_response(10000)
    assert False


def test_rcl(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.core')
    rcl = RCL(10, 10, 10)
    assert False
