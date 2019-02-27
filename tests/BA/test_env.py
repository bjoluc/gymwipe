from gymwipe.baSimulation import BAEnvironment
import pytest
import logging
from gymwipe.simtools import SimMan

from ..fixtures import simman


def test_env_creation(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.baSimulation.BAEnvironment')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    #caplog.set_level(logging.DEBUG, logger='gymwipe.networking.simple_stack')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.control.paper_scheduler')

    BAEnvironment.initialize()
    #SimMan.runSimulation(0.1)
    while not BAEnvironment.is_done:
        SimMan.runSimulation(0.1)
    assert False
