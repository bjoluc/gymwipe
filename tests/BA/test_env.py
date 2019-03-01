from gymwipe.baSimulation import BAEnvironment
import pytest
import logging

from gymwipe.baSimulation.constants import Configuration, SchedulerType, ProtocolType
from gymwipe.simtools import SimMan

from ..fixtures import simman


def test_env_creation(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.baSimulation.BAEnvironment')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    # caplog.set_level(logging.DEBUG, logger='gymwipe.networking.simple_stack')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.control.paper_scheduler')

    configs = [Configuration(SchedulerType.ROUNDROBIN,
                             ProtocolType.TDMA,
                             timeslot_length=0.01,
                             episodes=3,
                             horizon=50,
                             plant_sample_time=0.01,
                             sensor_sample_time=0.01,
                             num_plants=5,
                             num_instable_plants=0,
                             schedule_length=2,
                             show_inputs_and_outputs=False,
                             seed=40),
               Configuration(SchedulerType.DQN,
                             ProtocolType.TDMA,
                             timeslot_length=0.01,
                             episodes=1,
                             horizon=50,
                             plant_sample_time=0.01,
                             sensor_sample_time=0.01,
                             num_plants=5,
                             num_instable_plants=0,
                             schedule_length=2,
                             show_inputs_and_outputs=True,
                             seed=40)
               ]

    for i in range(len(configs)):
        config = configs[i]
        BAEnvironment.initialize(config)
        while not BAEnvironment.is_done:
            SimMan.runSimulation(0.01)
        BAEnvironment.reset_env()
