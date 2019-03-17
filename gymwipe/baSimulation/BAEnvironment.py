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
timestamp = 0


def training_done(msg):
    if config.train:
        print("training done...")
        avgloss = msg
        total_average = sum(avgloss)/len(avgloss)
        loss_save.write("{}".format(avgloss))
        episode_results_save.write("Training done. Total duration: {:.3} Total average loss: {:.3}".format(duration,
                                                                                                             total_average))
        plt.plot(range(1, config.episodes + 1), avgloss)
        plt.xlabel('Episode')
        plt.ylabel('Empiricial Average Loss')
        picstr = os.path.join(savepath, folder, "average_loss_" + savestring + ".png")
        plt.savefig(picstr)
        plt.close()
        logger.debug("Training is done, loss array is %s", avgloss.__str__(), sender="environment")

    loss_save.close()
    gc.collect()
    if not config.simulate:
        global is_done
        is_done = True
    else:
        gateway.simulatedSlot = 0

        for i in range(len(plants)):
            plant: StateSpacePlant = plants[i]
            plant.reset()
        gateway.simulatedSlot = 0
        gateway.control.reset()

        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensor.reset()
            sensor.inputs = []
            sensor.outputs = []
            mac: SensorMac = sensor._mac
            mac.biterror_sums = []
            mac.error_rates = []
            mac.received_schedule_count = 0
            mac.send_data_count = 0
            mac.assigned_ps = []

        for i in range(len(actuators)):
            actuator: SimpleActuator = actuators[i]
            mac: ActuatorMac = actuator._mac
            mac.schedule_received_count = 0
            mac.control_received_count = 0
            mac.ack_send_count = 0
            mac.error_rates_schedule = []
            mac.biterror_sums_schedule = []
            mac.error_rates_control = []
            mac.biterror_sums_control = []

        gateway.interpreter = MyInterpreter(config)
        gateway.interpreter.gateway = gateway
        gateway.n_simulate.trigger()


def simulation_done(msg):
    global savestring
    global folder
    folder = "{}/{}/{}/Simulation/".format(config.protocol_type.name, config.scheduler_type.name, timestamp)
    savestring = "training_{}_{}_plants_{}_length_{}_seed_{}_episodes_{}_horizon_{}_{}".format(
        config.scheduler_type.name,
        config.protocol_type.name,
        config.num_plants,
        config.schedule_length,
        config.seed,
        config.episodes,
        config.horizon,
        timestamp)

    global loss_save

    complete_name = os.path.join(savepath, folder, "schedule_loss_" + savestring + ".txt")
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    loss_save = open(complete_name, "w")

    print("simulation done...")
    avgloss = msg
    total_average = sum(avgloss) / len(avgloss)
    loss_save.write("{}".format(avgloss))
    plt.plot(range(1, config.simulation_horizon + 1), avgloss)
    plt.xlabel('Schedule')
    plt.ylabel('Empiricial Loss')
    picstr = os.path.join(savepath, folder, "simulation_loss_" + savestring + ".png")
    plt.savefig(picstr)
    plt.close()
    logger.debug("Simulation is done, loss array is %s", avgloss.__str__(), sender="environment")

    loss_save.close()
    gc.collect()

    if config.show_inputs_and_outputs is True:
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            outputs = sensor.outputs
            inputs = sensor.inputs
            logger.debug("data for sensor %d is %s", i, outputs.__str__(), sender="environment")
            plt.plot(range(0, len(outputs)), outputs)
            plt.xlabel('timestep')
            plt.ylabel('sensed output')
            sensorstr = os.path.join(savepath, folder, "Sensoroutputs/Sensor_" + str(i) + "/" + savestring + ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()
            plt.plot(range(0, len(inputs)), inputs)
            plt.xlabel('timestep')
            plt.ylabel('input')
            sensorstr = os.path.join(savepath, folder, "Actuatorinputs/Actuator_" + str(i) + "/" + savestring + ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()

    if config.show_error_rates is True:
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            mac: SensorMac = sensor._mac
            error = mac.error_rates
            bits = mac.biterror_sums
            logger.debug("error rated for sensor %d is %s", i, error.__str__(), sender="environment")
            plt.plot(range(0, len(error)), error)
            plt.xlabel('received schedule')
            plt.ylabel('error rate')
            sensorstr = os.path.join(savepath, folder, "Sensorerror/Sensor_" + str(i) + "/errorrate_" + savestring +
                                     ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()

            # biterrors sensor
            plt.plot(range(0, len(bits)), bits)
            plt.xlabel('received schedule')
            plt.ylabel('# biterrors')
            sensorstr = os.path.join(savepath, folder, "Sensorerror/Sensor_" + str(i) + "/biterrors" + savestring +
                                     ".png")
            os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
            plt.savefig(sensorstr)
            plt.close()


            actuator: SimpleActuator = actuators[i]
            mac: ActuatorMac = actuator._mac
            error_schedule = mac.error_rates_schedule
            bits_schedule = mac.biterror_sums_schedule
            error_control = mac.error_rates_control
            bits_control = mac.biterror_sums_control

            plt.plot(range(0, len(error_schedule)), error_schedule)
            plt.xlabel('received schedule')
            plt.ylabel('error rate')
            actuatorstr = os.path.join(savepath, folder,
                                       "Actuatorerror/Actuator_" + str(i) + "/schedule_errorrate_" + savestring + ".png")
            os.makedirs(os.path.dirname(actuatorstr), exist_ok=True)
            plt.savefig(actuatorstr)
            plt.close()

            plt.plot(range(0, len(error_schedule)), error_schedule)
            plt.xlabel('received schedule')
            plt.ylabel('biterrors')
            actuatorstr = os.path.join(savepath, folder,
                                       "Actuatorerror/Actuator_" + str(
                                           i) + "/schedule_biterrors_" + savestring + ".png")
            os.makedirs(os.path.dirname(actuatorstr), exist_ok=True)
            plt.savefig(actuatorstr)
            plt.close()

            plt.plot(range(0, len(error_control)), error_control)
            plt.xlabel('received control message')
            plt.ylabel('error rate')
            actuatorstr = os.path.join(savepath, folder,
                                       "Actuatorerror/Actuator_" + str(i) + "/control_errorrate_" + savestring + ".png")
            os.makedirs(os.path.dirname(actuatorstr), exist_ok=True)
            plt.savefig(actuatorstr)
            plt.close()

            plt.plot(range(0, len(error_schedule)), error_schedule)
            plt.xlabel('received control message')
            plt.ylabel('biterrors')
            actuatorstr = os.path.join(savepath, folder,
                                       "Actuatorerror/Actuator_" + str(
                                           i) + "/control_biterrors_" + savestring + ".png")
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
            sensorstr = os.path.join(savepath, folder, "Sensor_p_values/Sensor_" + str(i) + "/p_values_" + savestring +
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

    if config.show_statistics is True and config.protocol_type == ProtocolType.TDMA:
        gateway_arrived_acks = gateway.received_ack_amount
        gateway_arrived_data = gateway.received_data_amount
        gateway_send_controls = gateway.send_control_amount
        gateway_send_schedules = gateway.send_schedule_amount

        complete_name = os.path.join(savepath, folder, "statistics_" + savestring + ".txt")
        os.makedirs(os.path.dirname(complete_name), exist_ok=True)
        statistics_save = open(complete_name, "w")
        statistics_save.write("Average Simulation Loss: {}\n".format(total_average))
        statistics_save.write("GATEWAY\nPosition: {}\nMac Adresse: {}\ngesendete Schedules: {}\nerhaltene Sensordaten: \n".format(
            (gateway.position.x, gateway.position.y),
            gateway.mac,
            gateway_send_schedules))
        chosen_count = gateway.chosen_devices
        for i in range(len(sensors)):
            sensor: SimpleSensor = sensors[i]
            sensordata = gateway_arrived_data[sensor.mac]
            wanted = chosen_count[sensor.mac]
            statistics_save.write("\tSensor {}:verlangt: {} erhalten: {} ({} %)\n".format(
                gateway.macToDeviceIndexDict[sensor.mac],
                wanted,
                sensordata,
                round(sensordata/wanted*100, 2)))
        statistics_save.write("gesendete Controls und erhaltene Acknowledgements: \n")
        for i in range(len(actuators)):
            actuator: SimpleActuator = actuators[i]
            actuatoracks = gateway_arrived_acks[actuator.mac]
            actuatormaclayer: ActuatorMac = actuator._mac
            gatewaycontrols = gateway_send_controls[actuator.mac]
            send_acks = actuatormaclayer.ack_send_count
            if gatewaycontrols is not 0:
                statistics_save.write("\tActuator {}: gesendet: {} erhalten: {} ({}% der vom Actuator gesendeten ACKs)\n".format(
                    gateway.macToDeviceIndexDict[actuator.mac],
                    gatewaycontrols,
                    actuatoracks,
                    round(actuatoracks/send_acks*100, 2)))
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
            wanted = chosen_count[sensor.mac]
            statistics_save.write("SENSOR {}\nPosition: {}\nMac Adresse: {}\nerhaltene Schedules: {} ({} %)\ngesendete Daten: {} ({} % der verlangten Daten)\n\n".format(
                gateway.macToDeviceIndexDict[sensor.mac],
                (sensor.position.x, sensor.position.y),
                sensor.mac,
                received_schedules,
                round(received_schedules/gateway_send_schedules * 100, 2),
                send_data,
                round(send_data/wanted*100, 2)))

        statistics_save.write("\n\n")
        for i in range(len(actuators)):
            actuator: SimpleActuator = actuators[i]
            actuatormaclayer: ActuatorMac = actuator._mac
            received_schedules = actuatormaclayer.schedule_received_count
            received_controls = actuatormaclayer.control_received_count
            send_acks = actuatormaclayer.ack_send_count
            send_controls = gateway_send_controls[actuator.mac]
            statistics_save.write("ACTUATOR {}\nPosition: {}\nMac Adresse: {}\nerhaltene Schedules: "
                                  "{} ({} %)\nerhaltene Controls: {} ({} %)\ngesendete Acknowledgements: {}\n\n".format(
                gateway.macToDeviceIndexDict[actuator.mac],
                (actuator.position.x, actuator.position.y),
                actuator.mac,
                received_schedules,
                round(received_schedules / gateway_send_schedules * 100,2),
                received_controls,
                round(received_controls/send_controls*100, 2),
                send_acks))

        statistics_save.write("\n\n")
        gateway_chosen_schedules = gateway.chosen_schedules
        sorted_keys = sorted(gateway_chosen_schedules, key=gateway_chosen_schedules.get, reverse=True)
        statistics_save.write("CHOSEN SCHEDULES\n")
        for i in range(len(sorted_keys)):
            key = sorted_keys[i]
            statistics_save.write("{} : {} ({}%)\n".format(key, gateway_chosen_schedules[key],
                                                           round(
                                                               gateway_chosen_schedules[key]/gateway_send_schedules*100
                                                               , 2)))

        statistics_save.write("\n\nCHOSEN DEVICES\n")

        devices = sorted(chosen_count, key=chosen_count.get, reverse=True)
        summe = 0
        for i in range(len(devices)):
            summe += chosen_count[devices[i]]

        names = []
        values = []
        for i in range(len(devices)):
            device_mac = devices[i]
            device_id = gateway.macToDeviceIndexDict[device_mac]
            count = chosen_count[device_mac]
            values.append(count/summe*100)
            if device_mac in gateway.sensor_macs:
                statistics_save.write("Sensor {}: {} ({}%)\n".format(device_id, count, round(count/summe*100, 2)))
                names.append("Sensor {}".format(device_id))
            if device_mac in gateway.actuator_macs:
                statistics_save.write("Actuator {}: {} ({}%)\n".format(device_id, count, round(count / summe * 100, 2)))
                names.append("Actuator {}".format(device_id))

        # chosen devices diagram
        index = np.arange(len(names))

        plt.bar(index, values, 0.35)
        plt.xlabel('Device')
        plt.ylabel('% chosen in schedule')
        plt.xticks(index, names)

        picstr = os.path.join(savepath, folder,
                                   "chosen_devices_" + savestring + ".png")
        os.makedirs(os.path.dirname(picstr), exist_ok=True)
        plt.savefig(picstr)
        plt.close()
        statistics_save.close()
    # episode_results_save.close()
    global is_done
    is_done = True
    gc.collect()


def reset_env():
    print("Environment resetted")
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

    if config.scheduler_type == SchedulerType.ROUNDROBIN:

        gateway.scheduler = RoundRobinTDMAScheduler(list(gateway.deviceIndexToMacDict.values()),
                                                    gateway.sensor_macs,
                                                    gateway.actuator_macs,
                                                    config.schedule_length)

    episode_results_save.write("episode {} finished. Duration: {:.3} mean loss: {:.2}\n".format(info[0],
                                                                                                info[1],
                                                                                                info[2]))
    global duration
    duration += info[1]
    print("episode {} finished. Duration: {:.3} mean loss: {:.2}".format(info[0], info[1], info[2]))
    logger.debug("episode %d finished. Duration: %f, mean loss: %f", info[0], info[1], info[2], sender="environment")
    gc.collect()


episode_done_event = Notifier("episode done")
episode_done_event.subscribeCallback(episode_done)
done_event = Notifier("simulation done")
done_event.subscribeCallback(training_done)
simulation_done_event = Notifier("simulation done")
simulation_done_event.subscribeCallback(simulation_done)


def generate_x_y(num_plants):
    def random_pos():
        return round(np.random.uniform(0.0, 3.7), 2), round(np.random.uniform(0.0, 3.7), 2)
    gateway_pos = random_pos()

    def next_pos():
        distance = 0.0
        position = 0.0, 0.0
        while distance < 1.6:
            position = random_pos()
            diff_x = abs(gateway_pos[0]-position[0])
            diff_y = abs(gateway_pos[1]-position[1])
            distance = min(diff_x, diff_y)
        return position

    coords = []
    for i in range(num_plants):
        coords.append((next_pos(), next_pos()))
    return gateway_pos, coords


def initialize(configuration: Configuration):
    """
    Initializes the simulation environment. Creates plants, their sensors, actuators and controllers and initializes
    the gateway. The parameters like the amount of plants, used protocol and scheduler, schedule length (for TDMA
    ) are defined in the module :mod:`~gymwipe.baSimulation.constants`
    """
    SimMan.init()
    print("initializing new environment...")
    global timestamp
    timestamp = int(time.time())
    global savestring
    global folder
    folder = "{}/{}/{}/Training/".format(configuration.protocol_type.name, configuration.scheduler_type.name, timestamp)
    savestring = "training_{}_{}_plants_{}_length_{}_seed_{}_episodes_{}_horizon_{}_{}".format(
        configuration.scheduler_type.name,
        configuration.protocol_type.name,
        configuration.num_plants,
        configuration.schedule_length,
        configuration.seed,
        configuration.episodes,
        configuration.horizon,
        timestamp)
    global episode_results_save
    complete_name = os.path.join(savepath, folder, "results_" + savestring + ".txt")
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    episode_results_save = open(complete_name, "w")

    global loss_save
    complete_name = os.path.join(savepath, folder, "episode_loss_" + savestring + ".txt")
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    loss_save = open(complete_name, "w")

    global plants_save
    complete_name = os.path.join(savepath, folder, "plant_structure_" + savestring + ".txt")
    os.makedirs(os.path.dirname(complete_name), exist_ok=True)
    plants_save = open(complete_name, "w")

    complete_name = os.path.join(savepath, folder, "configuration_" + savestring + ".txt")
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

    gatewaypos, coords = generate_x_y(config.num_plants)
    for i in range(configuration.num_plants):
        sensor_pos, actuator_pos = coords[i]
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
        sensor = SimpleSensor("Sensor " + i.__str__(), sensor_pos[0],
                              sensor_pos[1],
                              frequency_band, plant, configuration)
        sensors.append(sensor)
        sensormacs.append(sensor.mac)
        actuator = SimpleActuator("Actuator" + i.__str__(), actuator_pos[0],
                                  actuator_pos[1],
                                  frequency_band, plant, configuration)
        actuators.append(actuator)
        actuatormacs.append(actuator.mac)

    global gateway
    gateway = Gateway(sensormacs, actuatormacs, controllers, plants, "Gateway", gatewaypos[0],
                      gatewaypos[1], frequency_band, done_event,
                      episode_done_event, simulation_done_event, configuration)
    plants_save.close()

    plt.plot(gatewaypos[0], gatewaypos[1], 'o', color='b')
    for i in range(len(sensors)):
        sensor = sensors[i]
        actuator = actuators[i]
        x,y = (sensor.position.x, sensor.position.y)
        plt.plot(x, y, 'o', color='r')
        x, y = (actuator.position.x, actuator.position.y)
        plt.plot(x, y, 'o', color='g')

    sensorstr = os.path.join(savepath, folder, "devicepositions_" + savestring +
                             ".png")
    os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
    plt.savefig(sensorstr)
    plt.close()
    np.random.seed()
    gc.collect()


def env_creation():
    roundrobin_config = [Configuration(SchedulerType.ROUNDROBIN,
                                       ProtocolType.TDMA,
                                       timeslot_length=0.01,
                                       episodes=1,
                                       horizon=500,
                                       num_plants=3,
                                       num_instable_plants=1
                                       )]

    test = [Configuration(SchedulerType.DQN,
                          ProtocolType.TDMA,
                          timeslot_length=0.01,
                          episodes=5,
                          horizon=500,
                          num_plants=3,
                          num_instable_plants=1)]

    dqn_config = [Configuration(SchedulerType.DQN,
                                ProtocolType.TDMA,
                                timeslot_length=0.01,
                                episodes=20,
                                horizon=500,
                                plant_sample_time=0.01,
                                sensor_sample_time=0.01,
                                num_plants=2,
                                num_instable_plants=0,
                                schedule_length=2,
                                show_error_rates=False,
                                show_inputs_and_outputs=False,
                                kalman_reset=True,
                                show_statistics=True,
                                show_assigned_p_values=False,
                                seed=42)]

    used_configs = test
    for i in range(len(used_configs)):
        configur = used_configs[i]
        initialize(configur)
        while not is_done:
            SimMan.runSimulation(0.01)
        reset_env()


def compare():
    dqn = ""
    robin =""
    plt.plot(range(0, len(dqn)), dqn, label="DQN Scheduler")
    plt.plot(range(0, len(robin)), robin, label="Round Robin Scheduler")
    plt.xlabel('episode')
    plt.ylabel(' average episode loss')
    plt.legend()
    sensorstr = os.path.join(savepath, "Vergleich1.png")
    os.makedirs(os.path.dirname(sensorstr), exist_ok=True)
    plt.savefig(sensorstr)
    plt.close()


if __name__ == "__main__":
    env_creation()
    # compare()



