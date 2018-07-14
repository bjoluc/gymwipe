import pytest, logging
from pytest_mock import mocker
from gymwipe.simtools import SimMan
from gymwipe.networking.core import NetworkDevice, Position, Channel, FSPLAttenuationProvider
from gymwipe.networking.construction import Gate
from gymwipe.networking.stack import SimplePhy
from gymwipe.networking.messages import Packet, Signal, PhySignals

def test_simple_phy(caplog, mocker):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.core')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.stack')
    SimMan.initEnvironment()

    # create a wireless channel with FSPL attenuation
    channel = Channel(FSPLAttenuationProvider())

    # create two network devices
    sender = NetworkDevice("Sender", Position(0,0))
    receiver = NetworkDevice("Receiver", Position(6,5))

    # create the SimplePhy network stack layers
    senderPhy = SimplePhy("Phy", sender, channel)
    receiverPhy = SimplePhy("Phy", receiver, channel)

    # create a mocked gate for captchering receiver Phy output
    receiverCallbackMock = mocker.Mock()
    receiverGate = Gate("Receiver Stack", receiverCallbackMock)
    receiverPhy.gates["mac"].connectOutputTo(receiverGate.input)

    # create a packet
    packet = Packet("Header2", Packet("Header1", "Payload"))

    def sending():
        # the channel should be unused yet
        assert len(channel.getActiveTransmissions(SimMan.now)) == 0

        # setup the message to the physical layer
        cmd = Signal(PhySignals.SEND, {"packet": packet, "power": -20, "bitrate": 16})

        # wait until the receiver is receiving
        yield SimMan.timeout(1)

        # send the message to the physical layer
        senderPhy.gates["mac"].input.send(cmd)

        # wait and assert
        yield SimMan.timeout(20)
        transmissions = channel.getActiveTransmissions(SimMan.now)
        assert len(transmissions) == 1
        t = transmissions[0]
        # check the correctness of the transmission created
        assert t.packet == packet
        assert t.power == -20
        assert t.bitrateHeader == 16
        assert t.bitratePayload == 16

        yield SimMan.timeout(100)
        assert len(channel.getActiveTransmissions(SimMan.now)) == 0
    
    def receiving():
        # setup the message to the physical layer
        cmd = Signal(PhySignals.RECEIVE, {"duration": 150})

        # send the message to the physical layer
        receiverPhy.gates["mac"].input.send(cmd)

        yield SimMan.timeout(150)

        receiverCallbackMock.assert_called_with(packet)

    SimMan.registerProcess(sending())
    SimMan.registerProcess(receiving())
    SimMan.runSimulation(200)
