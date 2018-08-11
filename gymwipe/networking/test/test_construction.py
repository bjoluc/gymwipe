import pytest, logging
from pytest_mock import mocker
from gymwipe.networking.construction import Port, Gate, Module
from gymwipe.simtools import SimMan

# Note: When mocking member functions of a class:
# Disable pylint warnings due to dynamically added member functions (assert_called_with) by # pylint: disable=E1101

def test_ports(mocker):
    # Create mocking functions for message transfer testing
    g1_receive = mocker.Mock()
    g2_receive = mocker.Mock()

    # Create two gates and connect them bidirectionally
    g1 = Gate("g1", g1_receive)
    assert g1.input._onSendCallables == {g1_receive}

    g2 = Gate("g2", g2_receive)
    assert g2.input._onSendCallables == {g2_receive}

    g1.connectOutputTo(g2.input)
    assert g1.output._onSendCallables == {g2.input.send}

    g2.connectOutputTo(g1.input)
    assert g2.output._onSendCallables == {g1.input.send}

    # Test message sending
    msg1 = 'test message 1'
    msg2 = 'test message 2'

    g1.output.send(msg1)
    g2_receive.assert_called_with(msg1)

    g2.output.send(msg2)
    g1_receive.assert_called_with(msg2)

def test_module_functions():
    m = Module('test module')
    assert m.name == 'test module'

    g1, g2 = (Gate("g1"), Gate("g2"))
    m._addGate('gate 1', g1)
    m._addGate('gate 2', g2)
    assert m.gates['gate 1'] == g1
    assert m.gates['gate 2'] == g2
    assert m.gates == {'gate 1': g1, 'gate 2': g2}

    m1, m2 = (Module('module 1'), Module('module 2'))
    m._addSubModule('sub module 1', m1)
    m._addSubModule('sub module 2', m2)
    assert m.subModules['sub module 1'] == m1
    assert m.subModules['sub module 2'] == m2
    assert m.subModules == {'sub module 1': m1, 'sub module 2': m2}

def test_module_simulation(caplog):
    # Connect two modules in a bidirectional cycle and let them pass around a message object in both directions
    #
    #      <----------------->
    # |----a-----|      |----a-----|
    # | module 1 |      | module 2 |
    # |----b-----|      |----b-----|
    #      <----------------->

    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    SimMan.initEnvironment()

    class TestModule(Module):
        def __init__(self, name):
            super(TestModule, self).__init__(name)
            self._addGate("a")
            self._addGate("b")
            self.msgReceivedCount = {"a": 0, "b": 0}
            self.msgVal = None
            SimMan.process(self.process("a", "b"))
            SimMan.process(self.process("b", "a"))
        
        def process(self, fromGate: str, toGate: str):
            while(True):
                # Listen on gate fromGate and proxy messages
                print("TestModule " + self.name + " port " + fromGate + " waiting for message")

                assert self.gates[fromGate].receivesMessage is not None

                msg = yield self.gates[fromGate].receivesMessage

                print("TestModule " + self.name + " port " + fromGate + " received message " + str(msg))
                self.msgVal = msg
                self.msgReceivedCount[fromGate] += 1
                msg += 1
                yield SimMan.env.timeout(1) # wait 1 time step before sending

                # change the direction every 10 times a message has been passed
                if msg % 10 == 0:
                    self.gates[fromGate].output.send(msg)
                else:
                    self.gates[toGate].output.send(msg)
    
    m1 = TestModule("1")
    m2 = TestModule("2")

    m1.gates["b"].biConnectWith(m2.gates["b"])
    m2.gates["a"].biConnectWith(m1.gates["a"])

    def simulation():
        # send the test message (a zero)
        print("sending message")
        m1.gates["a"].input.send(1)

        # wait 40 time units
        yield SimMan.timeout(20)
        assert m1.msgVal == 19
        assert m2.msgVal == 20
        yield SimMan.timeout(20)

        # assertions
        for m in [m1, m2]:
            for portName in ["a", "b"]:
                assert m.msgReceivedCount[portName] == 10
    
    SimMan.process(simulation())
    SimMan.runSimulation(50)
