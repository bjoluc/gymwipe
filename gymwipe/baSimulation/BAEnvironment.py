results_save = open("sensor_scheduling.txt", "w")
import logging
import numpy as np
from gymwipe.baSimulation import constants as c
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.state_space_plants import StateSpacePlant
from gymwipe.simtools import SimTimePrepender, SimMan, Notifier
from gymwipe.networking.MyDevices import SimpleSensor, SimpleActuator, Gateway

logger = SimTimePrepender(logging.getLogger(__name__))

plants = []
controllers = []
sensors = []
sensormacs = []
actuators = []
actuatormacs = []
gateway = None
SimMan.init()
is_done = False


def reset():
    logger.debug("environment resetted", sender="environment")


def done(msg):
    logger.debug("Simulation is done", sender="environment")
    global is_done
    is_done = True


def episode_done(info):
    results_save.write("episode {} finished. Duration: {:.3} mean loss: {:.2}\n".format(info[0], info[1], info[2]))
    logger.debug("episode %d finished. Duration: %f, mean loss: %f", info[0], info[1], info[2], sender="environment")


episode_done_event = Notifier("episode done")
episode_done_event.subscribeCallback(episode_done)
reset_event = Notifier("reset environment")
reset_event.subscribeCallback(reset)
done_event = Notifier("simulation done")
done_event.subscribeCallback(done)


def initialize():
    """
    Initializes the simulation environment. Creates plants, their sensors, actuators and controllers and initializes
    the gateway. The parameters like the amount of plants, used protocol and scheduler, schedule length (for TDMA
    ) are defined in the module :mod:`~gymwipe.baSimulation.constants`
    """

    frequency_band = FrequencyBand([FsplAttenuation])
    for i in range(c.NUM_PLANTS):
        np.random.seed(c.POSITION_SEED)
        if i+1 > c.INSTABLE_PLANTS:
            plant = StateSpacePlant(2, 1, c.PLANT_SAMPLE_TIME, name="Plant" + i.__str__())
        else:
            plant = StateSpacePlant(2,1, c.PLANT_SAMPLE_TIME, marginally_stable=False, name="Plant" + i.__str__())
        plants.append(plant)
        controller = plant.generate_controller()
        controllers.append(controller)
        sensor = SimpleSensor("Sensor " + i.__str__(), round(np.random.uniform(0.0, 5.0), 2),
                              round(np.random.uniform(0.0, 5.0), 2),
                              frequency_band, plant)
        sensors.append(sensor)
        sensormacs.append(sensor.mac)
        actuator = SimpleActuator("Actuator" + i.__str__(), round(np.random.uniform(0.0, 5.0), 2),
                                  round(np.random.uniform(0.0, 5.0), 2),
                                  frequency_band, plant)
        actuators.append(actuator)
        actuatormacs.append(actuator.mac)

    gateway = Gateway(sensormacs, actuatormacs, controllers, plants, "Gateway", round(np.random.uniform(0.0, 5.0), 2),
                      round(np.random.uniform(0.0, 5.0), 2), frequency_band, c.SCHEDULE_LENGTH, reset_event, done_event,
                      episode_done_event)


if __name__ == "__main__":
    initialize()
    while not done:
        SimMan.runSimulation(c.TIMESLOT_LENGTH*10)
    results_save.close()
