from gymwipe.baSimulation import BAEnivronment
import numpy as np
import pytest
import logging
from gymwipe.simtools import SimMan

from ..fixtures import simman


def test_env_creation(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.baSimulation.BA')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')

    BAEnivronment.initialize()
    #SimMan.runSimulation(0.01)
    assert False
