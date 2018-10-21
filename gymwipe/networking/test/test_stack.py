import logging
from typing import Iterable, List

import pytest
from pytest_mock import mocker

from gymwipe.devices import Device
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.construction import Gate
from gymwipe.networking.messages import (FakeTransmittable, Packet, Signal,
                                         SimpleMacHeader,
                                         SimpleTransportHeader, StackSignals,
                                         Transmittable)
from gymwipe.networking.physical import Channel
from gymwipe.networking.stack import SimpleMac, SimplePhy, SimpleRrmMac
from gymwipe.simtools import SimMan


class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class CollectorGate(Gate):
    """A subclass of Gate that stores received and sent objects in lists"""
    def __init__(self, name: str):
        super(CollectorGate, self).__init__(name)
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

    # create a wireless channel with FSPL attenuation
    channel = Channel([FsplAttenuation])

    # create two network devices
    device1 = Device("1", 0, 0)
    device2 = Device("2", 6, 5)

    # create the SimplePhy network stack layers
    device1Phy = SimplePhy("Phy", device1, channel)
    device2Phy = SimplePhy("Phy", device2, channel)
    
    setup = dotdict()
    setup.channel = channel
    setup.device1 = device1
    setup.device2 = device2
    setup.device1Phy = device1Phy
    setup.device2Phy = device2Phy
    return setup

def test_simple_phy(caplog, mocker, simple_phy):
    #caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.networking.core')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.stack')
    caplog.set_level(logging.INFO, logger='gymwipe.networking.physical')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.simtools')

    setup = simple_phy
    channel = setup.channel
    senderPhy = setup.device1Phy
    receiverPhy = setup.device2Phy

    # create a mocked gate for capturing receiver Phy output
    receiverCallbackMock = mocker.Mock()
    receiverGate = Gate("Receiver Stack", receiverCallbackMock)
    receiverPhy.gates["mac"].connectOutputTo(receiverGate.input)

    # create something transmittable
    packet = Packet(FakeTransmittable(8), FakeTransmittable(128))

    def sending():
        # the channel should be unused yet
        assert len(channel.getActiveTransmissions()) == 0

        # setup the message to the physical layer
        BITRATE = 1e6  # 1 Mb/s
        POWER = -20.0 # dBm
        cmd = Signal(StackSignals.SEND, {"packet": packet, "power": POWER, "bitrate": BITRATE})

        # send the message to the physical layer
        senderPhy.gates["mac"].send(cmd)

        # wait 8 bits
        yield SimMan.timeout(8/BITRATE)

        # assertions for the transmission
        transmissions = channel.getActiveTransmissions()
        assert len(transmissions) == 1
        t = transmissions[0]
        # check the correctness of the transmission created
        assert t.packet == packet
        assert t.power == POWER
        assert t.bitrateHeader == BITRATE
        assert t.bitratePayload == BITRATE

        power = receiverPhy._receivedPower

        # wait another 64 bits
        yield SimMan.timeout(64/BITRATE)

        # move device 2
        setup.device2.position.x = 50

        yield SimMan.timeout(16/BITRATE)

        assert receiverPhy._receivedPower < power

        yield SimMan.timeout(1)
        assert len(channel.getActiveTransmissions()) == 0
    
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
    s.rrmPhy = SimplePhy("RrmPhy", s.rrm, s.channel)
    s.rrmMac = SimpleRrmMac("RrmMac", s.rrm)
    s.device1Mac = SimpleMac("Mac", s.device1, SimpleMac.newMacAddress())
    s.device2Mac = SimpleMac("Mac", s.device2, SimpleMac.newMacAddress())

    # inter-layer connections
    # put collector gates as proxies between each device's Phy and Mac layer
    s.dev1PhyProxy = CollectorGate("Dev1PhyProxy")
    s.dev2PhyProxy = CollectorGate("Dev2PhyProxy")

    # mac <-> phyProxy
    s.device1Phy.gates["mac"].biConnectProxy(s.dev1PhyProxy)
    s.device2Phy.gates["mac"].biConnectProxy(s.dev2PhyProxy)

    # phyProxy <-> phy
    s.dev1PhyProxy.biConnectWith(s.device1Mac.gates["phy"])
    s.dev2PhyProxy.biConnectWith(s.device2Mac.gates["phy"])

    s.rrmMac.gates["phy"].biConnectWith(s.rrmPhy.gates["mac"])

    return s

def test_simple_mac(caplog, simple_mac):
    #caplog.set_level(logging.DEBUG, logger='gymwipe.simtools')
    #caplog.set_level(logging.INFO, logger='gymwipe.networking.construction')
    #caplog.set_level(logging.DEBUG, logger='gymwipe.networking.core')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.stack')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.physical')

    s = simple_mac

    dev1Addr = s.device1Mac.addr
    dev2Addr = s.device2Mac.addr

    def sender(fromMacLayer: SimpleMac, toMacLayer: SimpleMac, payloads: Iterable):
        # send a bunch of packets from `fromMacLayer` to `toMacLayer`
        for p in payloads:
            packet = Packet(SimpleTransportHeader(fromMacLayer.addr, toMacLayer.addr), p)
            fromMacLayer.gates["transport"].send(packet)
            yield SimMan.timeout(1)

    def receiver(macLayer: SimpleMac, receivedPacketsList: List[Packet]):
        # receive forever
        while True:
            receiveCmd = Signal(StackSignals.RECEIVE, {"duration": 10000})
            macLayer.gates["transport"].send(receiveCmd)
            result = yield receiveCmd.eProcessed
            receivedPacketsList.append(result)

    
    def resourceManagement():
        # assign the channel 5 times for each device
        previousCmd = None
        for i in range(10):
            if i % 2 == 0:
                dest = dev1Addr
            else:
                dest = dev2Addr
            cmd = Signal(StackSignals.ASSIGN, {"duration": 50, "dest": dest})
            SimMan.timeout(1)
            s.rrmMac.gates["transport"].send(cmd)
            if previousCmd is not None:
                yield previousCmd.eProcessed
            previousCmd = cmd

    receivedPackets1, receivedPackets2 = [], []
    
    SimMan.process(sender(s.device1Mac, s.device2Mac, [Transmittable(i) for i in range(10)]))
    SimMan.process(sender(s.device2Mac, s.device1Mac, [Transmittable(i) for i in range(10,20)]))
    SimMan.process(receiver(s.device1Mac, receivedPackets1))
    SimMan.process(receiver(s.device2Mac, receivedPackets2))
    SimMan.process(resourceManagement())
    SimMan.runSimulation(2000)

    # assertions
    # both devices should have received 10 packets
    assert len(receivedPackets1) == 10
    assert len(receivedPackets2) == 10

    # TODO add detailed assertions throughout the test
