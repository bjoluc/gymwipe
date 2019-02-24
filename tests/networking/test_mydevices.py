import logging
import gymwipe.baSimulation.constants as c
import numpy as np
import pytest
from gymwipe.networking.MyDevices import Gateway, SimpleSensor, SimpleActuator
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.state_space_plants import StateSpacePlant
from gymwipe.simtools import SimMan

from ..fixtures import simman


def test_gateway(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')

    sensors = []
    sensorAddr = []
    plants = []
    controllers = []
    actuators = []
    actuatormacs = []

    frequency_band = FrequencyBand([FsplAttenuation])

    for i in range(c.NUM_PLANTS):
        np.random.seed(c.POSITION_SEED)
        plant = StateSpacePlant(2, 1, c.PLANT_SAMPLE_TIME, name="Plant" + i.__str__())
        plants.append(plant)
        controller = plant.generate_controller()
        controllers.append(controller)
        sensor = SimpleSensor("Sensor " + i.__str__(), round(np.random.uniform(0.0, 5.0), 2),
                              round(np.random.uniform(0.0, 5.0), 2),
                              frequency_band, plant)
        sensors.append(sensor)
        sensorAddr.append(sensor.mac)
        actuator = SimpleActuator("Actuator" + i.__str__(), round(np.random.uniform(0.0, 5.0), 2),
                                  round(np.random.uniform(0.0, 5.0), 2),
                                  frequency_band, plant)
        actuators.append(actuator)
        actuatormacs.append(actuator.mac)

    Gateway(sensorAddr, actuatormacs, controllers, plants, "Gateway", 0, 0, frequency_band, 3, None, None, None)
    SimMan.runSimulation(0.5)

    assert False


def test_sensor(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    sensors = []
    plants = []
    controllers = []
    frequency_band = FrequencyBand([FsplAttenuation])
    for i in range(c.NUM_PLANTS):
        np.random.seed(c.POSITION_SEED)
        plant = StateSpacePlant(2, 1, c.PLANT_SAMPLE_TIME, name="Plant" + i.__str__())
        plants.append(plant)
        controller = plant.generate_controller()
        controllers.append(controller)
        sensor = SimpleSensor("Sensor " + i.__str__(), round(np.random.uniform(0.0, 5.0), 2),
                              round(np.random.uniform(0.0, 5.0), 2),
                              frequency_band, plant)
        sensors.append(sensor)

    SimMan.runSimulation(0.005)
    assert False
