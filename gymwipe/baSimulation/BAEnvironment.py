import os
import gc
import logging
import time
import numpy as np
import random
from gymwipe.control.scheduler import RoundRobinTDMAScheduler

from gymwipe.baSimulation.constants import Configuration, SchedulerType, ProtocolType
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_layers import SensorMac, ActuatorMac, GatewayMac
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.state_space_plants import StateSpacePlant
from gymwipe.simtools import SimTimePrepender, SimMan, Notifier
from gymwipe.networking.MyDevices import SimpleSensor, SimpleActuator, Gateway, Control, MyInterpreter
import matplotlib.pyplot as plt

logger = SimTimePrepender(logging.getLogger(__name__))

savepath = 'simulationresults/'
folder = ""
plants = []
controllers = []
sensors = []
sensormacs = []
actuators = []
actuatormacs = []
gateway: Gateway = None
is_done = False
savestring = ""
episode_results_save = None
loss_save = None
plants_save = None
config: Configuration = None
duration = 0.0


def reset():
    logger.debug("environment resetted", sender="environment")


def done(msg):
    avgloss = msg
    total_average = sum(msg)/len(msg)
    loss_save.write("{}".format(avgloss))
    episode_results_save.write("Simulation done. Total duration: {:.3} Total average loss: {:.3}".format(duration,
                                                                                                         total_average))
    plt.plot(range(1, config.episodes + 1), avgloss)
    plt.xlabel('Episode')
    plt.ylabel('Empiricial Average Loss')
    picstr = os.path.join(savepath, folder, "average_loss_" + savestring + ".png")
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
            sensorstr = os.path.join(savepath, folder, "Sensoroutputs/Sensor_" + str(i) + "_" + savestring + ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()
            plt.plot(range(0, len(inputs)), inputs)
            plt.xlabel('timestep')
            plt.ylabel('input')
            sensorstr = os.path.join(savepath, folder, "Actuatorinputs/Actuator_" + str(i) + "_" + savestring + ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()

    if config.show_error_rates is True:
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            mac: SensorMac = sensor._mac
            error = mac.error_rates
            logger.debug("error rated for sensor %d is %s", i, error.__str__(), sender="environment")
            plt.plot(range(0, len(error)), error)
            plt.xlabel('received schedule')
            plt.ylabel('error rate')
            sensorstr = os.path.join(savepath, folder, "Sensorerror/Sensor_" + str(i) + "_errorrate_" + savestring +
                                     ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()

            actuator: SimpleActuator = actuators[i]
            mac: ActuatorMac = actuator._mac
            error_schedule = mac.error_rates_schedule
            error_control = mac.error_rates_control
            plt.plot(range(0, len(error_schedule)), error_schedule)
            plt.xlabel('received schedule')
            plt.ylabel('error rate')
            actuatorstr = os.path.join(savepath, folder,
                                       "Actuatorerror/Actuator_" + str(i) + "_schedule_errorrate_" + savestring + ".png")
            os.makedirs(os.path.dirname(actuatorstr), exist_ok=True)
            plt.savefig(actuatorstr)
            plt.close()
            plt.plot(range(0, len(error_control)), error_control)
            plt.xlabel('received control message')
            plt.ylabel('error rate')
            actuatorstr = os.path.join(savepath, folder,
                                       "Actuatorerror/Actuator_" + str(i) + "_control_errorrate_" + savestring + ".png")
            os.makedirs(os.path.dirname(actuatorstr), exist_ok=True)
            plt.savefig(actuatorstr)
            plt.close()

    if config.show_assigned_p_values is True and config.protocol_type == ProtocolType.CSMA:
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            mac: SensorMac = sensor._mac
            ps = mac.assigned_ps
            plt.plot(range(0, len(ps)), ps)
            plt.xlabel('received schedule')
            plt.ylabel('assigned p')
            sensorstr = os.path.join(savepath, folder, "Sensor_p_values/Sensor_" + str(i) + "_p_values_" + savestring +
                                     ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()

        gatewaymac: GatewayMac = gateway._mac
        ps = gatewaymac.assigned_ps
        plt.plot(range(0, len(ps)), ps)
        plt.xlabel('received schedule')
        plt.ylabel('assigned p')
        sensorstr = os.path.join(savepath, folder, "Gateway_p_values/gateway_p_values_" + savestring +
                                 ".png")
        os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
        plt.savefig(sensorstr)
        plt.close()

    if config.show_statistics is True:
        gateway_arrived_acks = gateway.received_ack_amount
        gateway_arrived_data = gateway.received_data_amount
        gateway_send_controls = gateway.send_control_amount
        gateway_send_schedules = gateway.send_schedule_amount
        complete_name = os.path.join(savepath, folder, "statistics_" + savestring)
        os.makedirs(os.path.dirname(complete_name), exist_ok=True)
        statistics_save = open(complete_name, "w")
        statistics_save.write("GATEWAY\nMac Adresse: {}\ngesendete Schedules: {}\nerhaltene Sensordaten: \n".format(
            gateway.mac,
            gateway_send_schedules))
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensordata = gateway_arrived_data[sensor.mac]
            statistics_save.write("\tSensor {}: {}\n".format(gateway.macToDeviceIndexDict[sensor.mac], sensordata))
        statistics_save.write("gesendete Controls und erhaltene Acknowledgements: \n")
        for i in range(len(actuators)):
            actuator: SimpleActuator = actuators[i]
            actuatoracks = gateway_arrived_acks[actuator.mac]
            gatewaycontrols = gateway_send_controls[actuator.mac]
            if gatewaycontrols is not 0:
                statistics_save.write("\tActuator {}: gesendet: {} erhalten: {} ({}%)\n".format(
                    gateway.macToDeviceIndexDict[actuator.mac],
                    gatewaycontrols,
                    actuatoracks,
                    round(actuatoracks/gatewaycontrols*100)))
            else:
                statistics_save.write("\tActuator {}: gesendet: {} erhalten: {}\n".format(
                    gateway.macToDeviceIndexDict[actuator.mac],
                    gatewaycontrols,
                    actuatoracks))
        statistics_save.write("\n")
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensormaclayer: SensorMac = sensor._mac
            received_schedules = sensormaclayer.received_schedule_count
            send_data = sensormaclayer.send_data_count
            statistics_save.write("SENSOR {}\nMac Adresse: {}\nerhaltene Schedules: {} ({} %)\ngesendete Daten: {}\n".format(
                gateway.macToDeviceIndexDict[sensor.mac],
                sensor.mac,
                received_schedules,
                round(received_schedules/gateway_send_schedules * 100),
                send_data))
            statistics_save.write("\n")
        for i in range(len(actuators)):
            actuator: SimpleActuator = actuators[i]
            actuatormaclayer: ActuatorMac = actuator._mac
            received_schedules = actuatormaclayer.schedule_received_count
            received_controls = actuatormaclayer.control_received_count
            send_acks = actuatormaclayer.ack_send_count
            statistics_save.write("ACTUATOR {}\nMac Adresse: {}\nerhaltene Schedules: "
                                  "{} ({} %)\nerhaltene Controls: {}\ngesendete Acknowledgements: {}\n\n".format(
                gateway.macToDeviceIndexDict[actuator.mac],
                actuator.mac,
                received_schedules,
                round(received_schedules / gateway_send_schedules * 100),
                received_controls,
                send_acks))
        statistics_save.close()
    # episode_results_save.close()
    loss_save.close()
    gc.collect()

    global is_done
    is_done = True


def reset_env():
    global plants
    plants = []
    global controllers
    controllers = []
    global sensors
    sensors = []
    global sensormacs
    sensormacs = []
    global actuators
    actuators = []
    global actuatormacs
    actuatormacs = []
    global gateway
    gateway = None
    global is_done
    is_done = False
    gc.collect()
    global duration
    duration = 0.0


def episode_done(info):
    global gateway
    if config.scheduler_type == SchedulerType.ROUNDROBIN:
        for i in range(len(plants)):
            plant: StateSpacePlant = plants[i]
            plant.reset()
        gateway.simulatedSlot = 0
        gateway.control.reset()
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensor.reset()

        gateway.interpreter = MyInterpreter(config)
        gateway.interpreter.gateway = gateway

        gateway.scheduler = RoundRobinTDMAScheduler(list(gateway.deviceIndexToMacDict.values()),
                                                    gateway.sensor_macs,
                                                    gateway.actuator_macs,
                                                    config.schedule_length)
    elif config.scheduler_type == SchedulerType.DQN:
        for i in range(len(plants)):
            plant: StateSpacePlant = plants[i]
            plant.reset()

        gateway.simulatedSlot = 0
        gateway.control.reset()
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensor.reset()

        gateway.interpreter = MyInterpreter(config)
        gateway.interpreter.gateway = gateway

    elif config.scheduler_type == SchedulerType.RANDOM:
        for i in range(len(plants)):
            plant: StateSpacePlant = plants[i]
            plant.reset()
        gateway.simulatedSlot = 0
        gateway.control.reset()
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensor.reset()

        gateway.interpreter = MyInterpreter(config)
        gateway.interpreter.gateway = gateway
    episode_results_save.write("episode {} finished. Duration: {:.3} mean loss: {:.2}\n".format(info[0],
                                                                                                info[1],
                                                                                                info[2]))
    global duration
    duration += info[1]
    print("episode {} finished. Duration: {:.3} mean loss: {:.2}\n".format(info[0], info[1], info[2]))
    logger.debug("episode %d finished. Duration: %f, mean loss: %f", info[0], info[1], info[2], sender="environment")
    gc.collect()


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
    SimMan.init()
    timestamp = int(time.time())
    global savestring
    global folder
    folder = "{}/{}/{}/".format(configuration.protocol_type.name, configuration.scheduler_type.name, timestamp)
    savestring = "{}_{}_plants_{}_length_{}_seed_{}_episodes_{}_horizon_{}_{}.txt".format(
        configuration.scheduler_type.name,
        configuration.protocol_type.name,
        configuration.num_plants,
        configuration.schedule_length,
        configuration.seed,
        configuration.episodes,
        configuration.horizon,
        timestamp)
    global episode_results_save
    complete_name = os.path.join(savepath, folder, "results_" + savestring)
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    episode_results_save = open(complete_name, "w")

    global loss_save
    complete_name = os.path.join(savepath, folder, "episode_loss_" + savestring)
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    loss_save = open(complete_name, "w")

    global plants_save
    complete_name = os.path.join(savepath, folder, "plant_structure_" + savestring)
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    plants_save = open(complete_name, "w")

    complete_name = os.path.join(savepath, folder, "configuration_" + savestring)
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    config_save = open(complete_name, "w")

    global config
    config = configuration
    configstr = "{}\n{}\ntimeslot length: {}\nepisodes: {}\nhorizon: {}\nplant sample time: {}\nsensor sample time: {}\nkalman reset: {}" \
                "\nnum plants: {}\nnum instable plants: {}\nschedule length: {}\nseed: {}".format(
        config.protocol_type.name,
        config.scheduler_type.name,
        config.timeslot_length,
        config.episodes,
        config.horizon,
        config.plant_sample_time,
        config.sensor_sample_time,
        config.kalman_reset,
        config.num_plants,
        config.num_instable_plants,
        config.schedule_length,
        config.seed)

    config_save.write(configstr)
    config_save.close()
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
                              frequency_band, plant, configuration)
        sensors.append(sensor)
        sensormacs.append(sensor.mac)
        actuator = SimpleActuator("Actuator" + i.__str__(), round(np.random.uniform(0.0, 3), 2),
                                  round(np.random.uniform(0.0, 3), 2),
                                  frequency_band, plant, configuration)
        actuators.append(actuator)
        actuatormacs.append(actuator.mac)

    global gateway
    gateway = Gateway(sensormacs, actuatormacs, controllers, plants, "Gateway", round(np.random.uniform(0.0, 3), 2),
                      round(np.random.uniform(0.0, 3), 2), frequency_band, reset_event, done_event,
                      episode_done_event, configuration)
    plants_save.close()
    np.random.seed()
    gc.collect()


if __name__ == "__main__":
    initialize()
    while not done:
        SimMan.runSimulation(config.timeslot_length*10)
    episode_results_save.close()
