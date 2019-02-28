
import logging
import time
import numpy as np
from gymwipe.baSimulation.constants import Configuration
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.state_space_plants import StateSpacePlant
from gymwipe.simtools import SimTimePrepender, SimMan, Notifier
from gymwipe.networking.MyDevices import SimpleSensor, SimpleActuator, Gateway
import matplotlib.pyplot as plt

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
savestring = ""
episode_results_save = None
loss_save = None
plants_save = None

config: Configuration = None


def reset():
    logger.debug("environment resetted", sender="environment")


def done(msg):
    avgloss = msg
    loss_save.write("{}".format(avgloss))
    plt.plot(range(1, config.episodes + 1), avgloss)
    plt.xlabel('Episode')
    plt.ylabel('Empiricial Average Loss')
    picstr = "average_loss_" + savestring + ".png"
    plt.savefig(picstr)
    plt.close()
    logger.debug("Simulation is done, loss array is %s", avgloss.__str__(), sender="environment")
    if config.show_inputs_and_outputs is True:
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            outputs = sensor.outputs
            inputs = sensor.inputs
            logger.debug("data for sensor %d is %s", i, outputs.__str__(), sender="environment")
            plt.plot(range(0, len(outputs)), outputs)
            plt.xlabel('timestep')
            plt.ylabel('sensed output')
            sensorstr = "Sensor_" + str(i) + "_" + savestring + ".png"
            plt.savefig(sensorstr)
            plt.close()
            plt.plot(range(0, len(outputs)), outputs)
            plt.xlabel('timestep')
            plt.ylabel('input')
            sensorstr = "Actuator_" + str(i) + "_" + savestring + ".png"
            plt.savefig(sensorstr)
            plt.close()
    episode_results_save.close()
    loss_save.close()

    global is_done
    is_done = True


def episode_done(info):
    episode_results_save.write("episode {} finished. Duration: {:.3} mean loss: {:.2}\n".format(info[0],
                                                                                                info[1],
                                                                                                info[2]))
    print("episode {} finished. Duration: {:.3} mean loss: {:.2}\n".format(info[0], info[1], info[2]))
    logger.debug("episode %d finished. Duration: %f, mean loss: %f", info[0], info[1], info[2], sender="environment")


episode_done_event = Notifier("episode done")
episode_done_event.subscribeCallback(episode_done)
reset_event = Notifier("reset environment")
reset_event.subscribeCallback(reset)
done_event = Notifier("simulation done")
done_event.subscribeCallback(done)


def initialize(configuration: Configuration):
    """
    Initializes the simulation environment. Creates plants, their sensors, actuators and controllers and initializes
    the gateway. The parameters like the amount of plants, used protocol and scheduler, schedule length (for TDMA
    ) are defined in the module :mod:`~gymwipe.baSimulation.constants`
    """
    global savestring
    savestring = "scheduler_{}_protocol_{}_plants_{}_length_{}_seed_{}_{}.txt".format(configuration.scheduler_type,
                                                                                  configuration.protocol_type,
                                                                                  configuration.num_plants,
                                                                                  configuration.schedule_length,
                                                                                  configuration.seed,
                                                                                  int(time.time()))
    global episode_results_save
    episode_results_save = open("results_" + savestring, "w")
    global loss_save
    loss_save = open("episode_loss_" + savestring, "w")
    global plants_save
    plants_save = open("plant_structure_" + savestring, "w")
    global config
    config = configuration

    frequency_band = FrequencyBand([FsplAttenuation])
    np.random.seed(configuration.seed)
    for i in range(configuration.num_plants):
        if i+1 > configuration.num_instable_plants:
            plant = StateSpacePlant(2, 1,
                                    configuration.plant_sample_time,
                                    marginally_stable=True,
                                    name="Plant" + i.__str__())
        else:
            plant = StateSpacePlant(2, 1,
                                    configuration.plant_sample_time,
                                    marginally_stable=False,
                                    name="Plant" + i.__str__())
        plants.append(plant)
        controller = plant.generate_controller()
        controllers.append(controller)
        plantstr = "Plant {}: \nA:\n {} \nB:\n{} \ncontrol: {}\n".format(i, plant.a, plant.b, controller)
        plants_save.write(plantstr)
        sensor = SimpleSensor("Sensor " + i.__str__(), round(np.random.uniform(0.0, 3), 2),
                              round(np.random.uniform(0.0, 3), 2),
                              frequency_band, plant,configuration)
        sensors.append(sensor)
        sensormacs.append(sensor.mac)
        actuator = SimpleActuator("Actuator" + i.__str__(), round(np.random.uniform(0.0, 3), 2),
                                  round(np.random.uniform(0.0, 3), 2),
                                  frequency_band, plant, configuration)
        actuators.append(actuator)
        actuatormacs.append(actuator.mac)

    gateway = Gateway(sensormacs, actuatormacs, controllers, plants, "Gateway", round(np.random.uniform(0.0, 3), 2),
                      round(np.random.uniform(0.0, 3), 2), frequency_band, reset_event, done_event,
                      episode_done_event, configuration)
    plants_save.close()


if __name__ == "__main__":
    initialize()
    while not done:
        SimMan.runSimulation(config.timeslot_length*10)
    episode_results_save.close()
