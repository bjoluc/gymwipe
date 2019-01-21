import logging

from gymwipe.devices import Device
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_headers import NCSMacHeader
from gymwipe.networking.mac_layers import (ActuatorMacTDMA, GatewayMac,
                                           SensorMac, newUniqueMacAddress)
from gymwipe.networking.messages import Packet, Transmittable, Message, StackMessageTypes
from gymwipe.networking.physical import FrequencyBand
from gymwipe.networking.MyDevices import SimpleSensor, Gateway
from gymwipe.control.scheduler import TDMAEncode

from ..fixtures import simman


def test_sensormac(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_headers')
    sensor1 = Device("Sensor1", 0, 0)
    actuator1 = Device("Actuator1",1,1)
    mac1 = newUniqueMacAddress()
    mac2 = newUniqueMacAddress()
    sensor1Mac = SensorMac("Sensor1MacLayer", sensor1, FrequencyBand([FsplAttenuation]).spec, mac1)
    controller1Mac = ActuatorMacTDMA("Actuator1MacLayer", actuator1, FrequencyBand([FsplAttenuation]).spec, mac2)

    type = bytearray(1)
    type[0] = 0
    packet = Packet(NCSMacHeader(bytes(type), mac2, mac1), Transmittable("Test"))
    type[0] = 1
    packet2 = Packet(NCSMacHeader(bytes(type), mac1, mac2), Transmittable("Test2"))
    packet3 = Packet(NCSMacHeader(bytes(type), mac1, mac1), Transmittable("Test3"))

    sensor1Mac.gates["phyIn"].send(packet)
    controller1Mac.gates["phyIn"].send(packet2) # should appear as relevant
    controller1Mac.gates["phyIn"].send(packet3) # should appear as irrelevant
    assert sensor1Mac.name == "Sensor1MacLayer"

def test_sending(caplog, simman):
    caplog.set_level(logging.INFO, logger='gymwipe.networking.construction')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.core')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.physical')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.stack')
    caplog.set_level(logging.INFO, logger='gymwipe.simtools')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_headers')

    sensor1 = SimpleSensor("Sensor1", 0,0, FrequencyBand([FsplAttenuation]), None, 5)
    gateway = Gateway("roundrobinTDMA",[sensor1.mac],[], "Gateway", 1, 1, FrequencyBand([FsplAttenuation]), 3)

    type = bytearray(1)
    type[0] = 1
    schedule = gateway.scheduler.nextSchedule()
    sendCmd = Message(StackMessageTypes.SEND, {"schedule": schedule})
    gateway._mac.gates["networkIn"].send(sendCmd)
    assert False

