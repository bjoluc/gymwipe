import logging

import pytest

from gymwipe.baSimulation.BA import TIMESLOT_LENGTH
from gymwipe.devices import Device
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_headers import NCSMacHeader
from gymwipe.networking.mac_layers import (ActuatorMacTDMA, GatewayMac,
                                           SensorMacTDMA, newUniqueMacAddress)
from gymwipe.networking.messages import Packet, Transmittable, Message, StackMessageTypes
from gymwipe.networking.physical import FrequencyBand
from gymwipe.control.scheduler import TDMASchedule

from gymwipe.networking.simple_stack import SimplePhy
from typing import Iterable
from gymwipe.simtools import SimMan


from ..fixtures import simman


class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


@pytest.fixture
def my_mac(simple_phy):
    s = simple_phy
    s.rrm = Device("RRM", 2, 2)
    s.rrmPhy = SimplePhy("RrmPhy", s.rrm, s.frequencyBand)
    s.rrmMac = GatewayMac("RrmMac", s.rrm, s.frequencyBand.spec, newUniqueMacAddress())
    s.device1Mac = SensorMacTDMA("Mac", s.device1, s.frequencyBand.spec, newUniqueMacAddress())
    s.device2Mac = SensorMacTDMA("Mac", s.device2, s.frequencyBand.spec, newUniqueMacAddress())

    s.device1Mac.ports["phy"].biConnectWith(s.device1Phy.ports["mac"])
    s.device2Mac.ports["phy"].biConnectWith(s.device2Phy.ports["mac"])
    s.rrmMac.ports["phy"].biConnectWith(s.rrmPhy.ports["mac"])

    return s


def test_sensormac(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_headers')
    sensor1 = Device("Sensor1", 0, 0)
    actuator1 = Device("Actuator1", 1, 1)
    mac1 = newUniqueMacAddress()
    mac2 = newUniqueMacAddress()
    sensor1_mac = SensorMacTDMA("Sensor1MacLayer", sensor1, FrequencyBand([FsplAttenuation]).spec, mac1)
    controller1_mac = ActuatorMacTDMA("Actuator1MacLayer", actuator1, FrequencyBand([FsplAttenuation]).spec, mac2)

    message_type = bytearray(1)
    message_type[0] = 0  # schedule
    packet = Packet(NCSMacHeader(bytes(message_type), mac2, mac1), Transmittable(TDMASchedule([[mac1, 0], [mac2, 0]])),
                    Transmittable(5))
    message_type[0] = 1  # sensor data
    packet2 = Packet(NCSMacHeader(bytes(message_type), mac1, mac2),  Transmittable("Test"))
    packet3 = Packet(NCSMacHeader(bytes(message_type), mac1, mac1),  Transmittable("Test"))

    sensor1_mac.gates["phyIn"].send(packet)
    controller1_mac.gates["phyIn"].send(packet2)  # should appear as relevant
    controller1_mac.gates["phyIn"].send(packet3)  # should appear as irrelevant
    assert False


def test_actuator_mac_sending(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    actuator1 = Device("Actuator1", 1, 1)
    mac1 = newUniqueMacAddress()
    actuator1_mac = ActuatorMacTDMA("Actuator1MacLayer", actuator1, FrequencyBand([FsplAttenuation]).spec, mac1)

    gateway = Device("Gateway", 0, 0)
    mac2 = newUniqueMacAddress()
    gateway_mac = GatewayMac("GW_mac_layer", gateway, FrequencyBand([FsplAttenuation]), mac2)

    ctrlCmd = Message(
        StackMessageTypes.SENDCONTROL, {
            "control": 5,
            "receiver": mac1
        }
    )
    gateway_mac.gates["networkIn"].send(ctrlCmd)
    SimMan.runSimulation(1)
    assert False


def test_actuator_mac(caplog, simman):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    actuator1 = Device("Actuator1", 1, 1)
    mac1 = newUniqueMacAddress()
    actuator1_mac = ActuatorMacTDMA("Actuator1MacLayer", actuator1, FrequencyBand([FsplAttenuation]).spec, mac1)
    mac2 = newUniqueMacAddress()

    controlsendingtype = bytearray(1)
    controlsendingtype[0] = 2
    packet = Packet(NCSMacHeader(type=controlsendingtype, sourceMAC=mac2, destMAC=mac1), Transmittable("Test"))
    actuator1_mac.gates["phyIn"].send(packet)

    assert False


def test_sending(caplog, my_mac):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.simple_stack')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    s = my_mac
    sen1address = s.device1Mac.addr
    sen2address = s.device2Mac.addr

    def sender(from_mac_layer: GatewayMac, payloads: Iterable):
        # send a bunch of schedules
        for p in payloads:
            clock = SimMan.now
            send_cmd = Message(
                StackMessageTypes.SEND, {
                    "schedule": p,
                    "clock": clock
                }
            )
            from_mac_layer.gates["networkIn"].send(send_cmd)
            yield send_cmd.eProcessed
            time = SimMan.now
            endslot = p.get_end_time()
            endtime = time + (endslot * TIMESLOT_LENGTH)
            yield SimMan.timeoutUntil(endtime)

    def receiver(mac_layer: SensorMacTDMA):
        # receive forever
        i = 1
        while True:
            send_cmd = Message(StackMessageTypes.SEND, {"state": i})
            mac_layer.gates["networkIn"].send(send_cmd)
            yield send_cmd.eProcessed
            i += 1

    SimMan.process(sender(s.rrmMac, [TDMASchedule([[sen1address, 0], [sen2address, 0]]) for i in range(10)]))
    SimMan.process(receiver(s.device1Mac))
    SimMan.process(receiver(s.device2Mac))

    ROUND_TIME = 1
    SimMan.runSimulation(ROUND_TIME)
    assert False

