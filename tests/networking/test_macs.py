import logging

import pytest
from gymwipe.devices import Device
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_headers import NCSMacHeader
from gymwipe.networking.mac_layers import (ActuatorMacTDMA, GatewayMac,
                                           SensorMacTDMA, newUniqueMacAddress)
from gymwipe.networking.messages import Packet, Transmittable, Message, StackMessageTypes
from gymwipe.networking.physical import FrequencyBand
from gymwipe.control.scheduler import TDMASchedule

from gymwipe.networking.simple_stack import SimplePhy
from typing import Iterable, List
from gymwipe.simtools import SimMan
from gymwipe.baSimulation.BA import TIMESLOT_LENGTH

from ..fixtures import simman, simple_phy

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
    actuator1 = Device("Actuator1",1,1)
    mac1 = newUniqueMacAddress()
    mac2 = newUniqueMacAddress()
    sensor1Mac = SensorMacTDMA("Sensor1MacLayer", sensor1, FrequencyBand([FsplAttenuation]).spec, mac1)
    controller1Mac = ActuatorMacTDMA("Actuator1MacLayer", actuator1, FrequencyBand([FsplAttenuation]).spec, mac2)

    type = bytearray(1)
    type[0] = 0  # schedule
    packet = Packet(NCSMacHeader(bytes(type), mac2, mac1), Transmittable("Test"))
    type[0] = 1  # sensordata
    packet2 = Packet(NCSMacHeader(bytes(type), mac1, mac2), Transmittable("Test2"))
    packet3 = Packet(NCSMacHeader(bytes(type), mac1, mac1), Transmittable("Test3"))

    sensor1Mac.gates["phyIn"].send(packet)
    controller1Mac.gates["phyIn"].send(packet2)  # should appear as relevant
    controller1Mac.gates["phyIn"].send(packet3)  # should appear as irrelevant
    assert sensor1Mac.name == "Sensor1MacLayer"


def test_sending(caplog, my_mac):
    caplog.set_level(logging.INFO, logger='gymwipe.networking.construction')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.core')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.physical')
    caplog.set_level(logging.INFO, logger='gymwipe.simtools')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_headers')

    s= my_mac
    sen1addr = s.device1Mac.addr
    sen2addr = s.device2Mac.addr
    rrmaddr = s.rrmMac.addr

    def sender(fromMacLayer: GatewayMac, payloads: Iterable):
        # send a bunch of packets from `fromMacLayer` to `toMacLayer`
        for p in payloads:
            clock = SimMan.now
            sendCmd = Message(
                StackMessageTypes.SEND, {
                    "schedule": p,
                    "clock": clock
                }
            )
            fromMacLayer.gates["networkIn"].send(sendCmd)
            yield sendCmd.eProcessed
            time = SimMan.now
            endslot= p.getEndTime()
            endtime = time + (endslot * TIMESLOT_LENGTH)
            SimMan.timeoutUntil(endtime)

    def receiver(macLayer: SensorMacTDMA, receivedPacketsList: List[Packet]):
        # receive forever
        i = 1
        while True:
            sendCmd = Message(StackMessageTypes.SEND, {"state": i})
            macLayer.gates["networkIn"].send(sendCmd)
            receiveCmd = Message(StackMessageTypes.RECEIVE, {"duration": 10})
            macLayer.gates["networkIn"].send(receiveCmd)
            result = yield receiveCmd.eProcessed
            if result is not None:
                i += 1
                sendCmd = Message(StackMessageTypes.SEND, {"data": i})
                macLayer.gates["networkIn"].send(sendCmd)
                receivedPacketsList.append(result)

    receivedPackets1 = []

    SimMan.process(sender(s.rrmMac, [TDMASchedule([[sen1addr, 0], [sen2addr, 0]]) for i in range(10)]))
    SimMan.process(receiver(s.device1Mac, receivedPackets1))

    ROUND_TIME = 11
    SimMan.runSimulation(ROUND_TIME)
    assert len(receivedPackets1) == 10

