from gymwipe.baSimulation import BAEnvironment
import numpy as np
import pytest
import logging
from gymwipe.simtools import SimMan

from ..fixtures import simman


def test_env_creation(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.baSimulation.BA')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    BAEnvironment.initialize()
    SimMan.runSimulation(0.1)
    assert False
