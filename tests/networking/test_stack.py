import logging
from math import log10
from typing import Iterable, List

import pytest
from pytest_mock import mocker

from gymwipe.devices import Device
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.construction import Port
from gymwipe.networking.messages import (FakeTransmittable, Message, Packet,
                                         SimpleMacHeader,
                                         SimpleTransportHeader, StackMessages,
                                         Transmittable)
from gymwipe.networking.physical import BpskMcs, FrequencyBand
from gymwipe.networking.stack import (TIME_SLOT_LENGTH, SimpleMac, SimplePhy,
                                      SimpleRrmMac)
from gymwipe.simtools import SimMan


class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class CollectorPort(Port):
    """A subclass of Port that stores received and sent objects in lists"""
    def __init__(self, name: str):
        super(CollectorPort, self).__init__(name)
        self.inputHistory = []
        self.outputHistory = []
        self.input.addCallback(self.inputSaver)
        self.output.addCallback(self.outputSaver)
    
    def inputSaver(self, obj):
        self.inputHistory.append(obj)
    
    def outputSaver(self, obj):
        self.outputHistory.append(obj)

@pytest.fixture
def simple_phy():
    # initialize SimPy environment
    SimMan.initEnvironment()

    # create a wireless frequency band with FSPL attenuation
    frequencyBand = FrequencyBand([FsplAttenuation])

    # create two network devices
    device1 = Device("1", 0, 0)
    device2 = Device("2", 1, 1)

    # create the SimplePhy network stack layers
    device1Phy = SimplePhy("Phy", device1, frequencyBand)
    device2Phy = SimplePhy("Phy", device2, frequencyBand)
    
    setup = dotdict()
    setup.frequencyBand = frequencyBand
    setup.device1 = device1
    setup.device2 = device2
    setup.device1Phy = device1Phy
    setup.device2Phy = device2Phy
    return setup

def test_simple_phy(caplog, mocker, simple_phy):
    caplog.set_level(logging.INFO, logger='gymwipe.networking.construction')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.core')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.physical')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.stack')
    caplog.set_level(logging.INFO, logger='gymwipe.simtools')

    setup = simple_phy
    frequencyBand = setup.frequencyBand
    senderPhy = setup.device1Phy
    receiverPhy = setup.device2Phy

    # create a mocked port for capturing receiver Phy output
    receiverCallbackMock = mocker.Mock()
    receiverPort = Port("Receiver Stack", receiverCallbackMock)
    receiverPhy.ports["mac"].connectOutputTo(receiverPort.input)

    # create something transmittable
    packet = Packet(FakeTransmittable(8), FakeTransmittable(128))

    def sending():
        # the frequency band should be unused yet
        assert len(frequencyBand.getActiveTransmissions()) == 0

        # setup the message to the physical layer
        MCS = BpskMcs(frequencyBand.spec)
        POWER = 0.0 # dBm
        cmd = Message(StackMessages.SEND, {"packet": packet, "power": POWER, "mcs": MCS})

        # send the message to the physical layer
        senderPhy.ports["mac"].send(cmd)

        # wait 8 payload bits
        yield SimMan.timeout(8/MCS.dataRate)

        # assertions for the transmission
        transmissions = frequencyBand.getActiveTransmissions()
        assert len(transmissions) == 1
        t = transmissions[0]
        # check the correctness of the transmission created
        assert t.packet == packet
        assert t.power == POWER
        assert t.mcsHeader == MCS
        assert t.mcsPayload == MCS

        power = receiverPhy._receivedPower

        # wait another 64 bits
        yield SimMan.timeout(64/MCS.dataRate)

        # move device 2
        setup.device2.position.x = 2

        yield SimMan.timeout(16/MCS.dataRate)

        assert receiverPhy._receivedPower < power

        yield SimMan.timeout(1)
        assert len(frequencyBand.getActiveTransmissions()) == 0
    
    def receiving():
        yield SimMan.timeout(4)
        receiverCallbackMock.assert_called_with(packet)
    
    SimMan.process(sending())
    SimMan.process(receiving())
    SimMan.runSimulation(200)

@pytest.fixture
def simple_mac(simple_phy):
    s = simple_phy
    s.rrm = Device("RRM", 2, 2)
    s.rrmPhy = SimplePhy("RrmPhy", s.rrm, s.frequencyBand)
    s.rrmMac = SimpleRrmMac("RrmMac", s.rrm, s.frequencyBand.spec)
    s.device1Mac = SimpleMac("Mac", s.device1, s.frequencyBand.spec, SimpleMac.newMacAddress())
    s.device2Mac = SimpleMac("Mac", s.device2, s.frequencyBand.spec, SimpleMac.newMacAddress())

    # inter-layer connections
    # put collector ports as proxies between each device's Phy and Mac layer
    s.dev1PhyProxy = CollectorPort("Dev1PhyProxy")
    s.dev2PhyProxy = CollectorPort("Dev2PhyProxy")

    # mac <-> phyProxy
    s.device1Phy.ports["mac"].biConnectProxy(s.dev1PhyProxy)
    s.device2Phy.ports["mac"].biConnectProxy(s.dev2PhyProxy)

    # phyProxy <-> phy
    s.dev1PhyProxy.biConnectWith(s.device1Mac.ports["phy"])
    s.dev2PhyProxy.biConnectWith(s.device2Mac.ports["phy"])

    s.rrmMac.ports["phy"].biConnectWith(s.rrmPhy.ports["mac"])

    return s

def do_not_test_simple_mac_then(caplog, simple_mac):
    # TODO Why does device 1 all the sudden fail to receive the first RRM packet?
    caplog.set_level(logging.INFO, logger='gymwipe.networking.construction')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.core')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.physical')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.stack')
    #caplog.set_level(logging.INFO, logger='gymwipe.simtools')

    s = simple_mac

    dev1Addr = s.device1Mac.addr
    dev2Addr = s.device2Mac.addr

    def sender(fromMacLayer: SimpleMac, toMacLayer: SimpleMac, payloads: Iterable):
        # send a bunch of packets from `fromMacLayer` to `toMacLayer`
        for p in payloads:
            packet = Packet(SimpleTransportHeader(fromMacLayer.addr, toMacLayer.addr), p)
            fromMacLayer.ports["transport"].send(packet)
            yield SimMan.timeout(1e-4)

    def receiver(macLayer: SimpleMac, receivedPacketsList: List[Packet]):
        # receive forever
        while True:
            receiveCmd = Message(StackMessages.RECEIVE, {"duration": 10})
            macLayer.ports["transport"].send(receiveCmd)
            result = yield receiveCmd.eProcessed
            if result is not None:
                receivedPacketsList.append(result)

    ASSIGN_TIME = 0.01
    ANNOUNCE_TIME = (13 + log10(ASSIGN_TIME/TIME_SLOT_LENGTH))*8 / s.rrmMac._announcementMcs.dataRate
    # 13 bytes header + log10(ASSIGN_TIME/TIME_SLOT_LENGTH) bytes payload

    def resourceManagement():
        # Assign the frequency band 5 times for each device
        previousCmd = None
        for i in range(10):
            if i % 2 == 0:
                dest = dev1Addr
            else:
                dest = dev2Addr
            cmd = Message(StackMessages.ASSIGN, {"duration": ASSIGN_TIME/TIME_SLOT_LENGTH, "dest": dest})
            s.rrmMac.ports["transport"].send(cmd)
            if previousCmd is not None:
                yield previousCmd.eProcessed
            previousCmd = cmd

    receivedPackets1, receivedPackets2 = [], []
    
    SimMan.process(sender(s.device1Mac, s.device2Mac, [Transmittable(i) for i in range(10)]))
    SimMan.process(sender(s.device2Mac, s.device1Mac, [Transmittable(i) for i in range(10,20)]))
    SimMan.process(receiver(s.device1Mac, receivedPackets1))
    SimMan.process(receiver(s.device2Mac, receivedPackets2))
    SimMan.process(resourceManagement())

    ROUND_TIME = ANNOUNCE_TIME + ASSIGN_TIME
    
    # After 1 assignment, device 2 should have received the first chunk of
    # packets. Highly depends on data rates, TIME_SLOT_LENGTH, and ASSIGN_TIME!
    SimMan.runSimulation(ROUND_TIME)
    assert len(receivedPackets2) == 4
    
    SimMan.runSimulation(ROUND_TIME)
    # Same for device 1
    assert len(receivedPackets1) == 4

    SimMan.runSimulation(ROUND_TIME)
    assert len(receivedPackets2) == 8
    
    SimMan.runSimulation(ROUND_TIME)
    assert len(receivedPackets1) == 8

    SimMan.runSimulation(6*ROUND_TIME)

    # Both devices should have received 10 packets
    assert len(receivedPackets1) == 10
    assert len(receivedPackets2) == 10
