import logging

import pytest
from gymwipe.devices import Device
from gymwipe.networking.MyDevices import Gateway, SimpleSensor
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_layers import SensorMacTDMA, newUniqueMacAddress
from gymwipe.networking.messages import Message, StackMessageTypes
from gymwipe.networking.physical import FrequencyBand
from gymwipe.networking.simple_stack import SimplePhy
from gymwipe.plants.sliding_pendulum import SlidingPendulum
from gymwipe.simtools import SimMan

from ..fixtures import simman


def test_gateway(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    sensors = []
    sensorMACS = []
    sensorAddr = []
    frequencyBand = FrequencyBand([FsplAttenuation])

    def receiver(mac_layer: SensorMacTDMA):
        # receive forever
        i = 1
        while True:
            send_cmd = Message(StackMessageTypes.SEND, {"state": i})
            mac_layer.gates["networkIn"].send(send_cmd)
            yield send_cmd.eProcessed
            i += 1
    for i in range(5):
        device = Device(("Sensor1" + i.__str__()), (0.2 * i + 0.2), (0.2 * i + 0.2))
        phy = SimplePhy(("PHY1" + i.__str__()), device, frequencyBand)
        mac = SensorMacTDMA(("MAC1" + i.__str__()), device, frequencyBand.spec, newUniqueMacAddress())

        phy.ports["mac"].biConnectWith(mac.ports["phy"])
        sensors.append(device)
        sensorMACS.append(mac)
        sensorAddr.append(mac.addr)
        SimMan.process(receiver(mac))

    Gateway("roundrobinTDMA", sensorAddr, [], "Gateway", 0, 0, frequencyBand, 3)
    SimMan.runSimulation(0.5)

    assert False


def test_sensor(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    sensors = []
    sensorAddr = []
    frequencyBand = FrequencyBand([FsplAttenuation])

    for i in range(5):
        sensor = SimpleSensor("Sensor" + i.__str__(), i, frequencyBand, SlidingPendulum(), 0.005)
        sensors.append(sensor)
        sensorAddr.append(sensor.mac_address())

    Gateway("roundrobinTDMA", sensorAddr, [], "Gateway", 0, 0, frequencyBand, 3)
    SimMan.runSimulation(0.5)

    assert False
