import pytest, logging
from pytest_mock import mocker
from gymwipe.networking.construction import Gate, Port, Module, PortListener
from gymwipe.simtools import SimMan

# Note: When mocking member functions of a class:
# Disable pylint warnings due to dynamically added member functions (assert_called_with) by # pylint: disable=E1101

def test_ports(mocker):
    # Create mocking functions for message transfer testing
    g1_receive = mocker.Mock()
    g2_receive = mocker.Mock()

    # Create two gates and connect them bidirectionally
    g1 = Port("g1", g1_receive)
    assert g1.input._onSendCallables == {g1_receive}

    g2 = Port("g2", g2_receive)
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

    g1, g2 = (Port("g1"), Port("g2"))
    m._addPort('gate 1', g1)
    m._addPort('gate 2', g2)
    assert m.ports['gate 1'] == g1
    assert m.ports['gate 2'] == g2
    assert m.ports == {'gate 1': g1, 'gate 2': g2}

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
            self._addPort("a")
            self._addPort("b")
            self.msgReceivedCount = {"a": 0, "b": 0}
            self.msgVal = None
            SimMan.process(self.process("a", "b"))
            SimMan.process(self.process("b", "a"))
        
        def process(self, fromPort: str, toPort: str):
            while(True):
                # Listen on port fromPort and proxy messages
                print("TestModule " + self.name + " gate " + fromPort + " waiting for message")

                msg = yield self.ports[fromPort].nReceives.event

                print("TestModule " + self.name + " gate " + fromPort + " received message " + str(msg))
                self.msgVal = msg
                self.msgReceivedCount[fromPort] += 1
                msg += 1
                yield SimMan.env.timeout(1) # wait 1 time step before sending

                # change the direction every 10 times a message has been passed
                if msg % 10 == 0:
                    self.ports[fromPort].output.send(msg)
                else:
                    self.ports[toPort].output.send(msg)
    
    m1 = TestModule("1")
    m2 = TestModule("2")

    m1.ports["b"].biConnectWith(m2.ports["b"])
    m2.ports["a"].biConnectWith(m1.ports["a"])

    def simulation():
        # send the test message (a zero)
        print("sending message")
        m1.ports["a"].input.send(1)

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

class MyModule(Module):
    @PortListener.setup
    def __init__(self, name: str):
        super(MyModule, self).__init__(name)
        self._addPort("a")
        self._addPort("b")
        self.logs = [[] for _ in range(4)]

    @PortListener("a", queued=False)
    def aListener(self, message):
        self.logs[0].append(message)
    
    @PortListener("a", queued=True) # queued should have no effect here
    def aListenerQueued(self, message):
        self.logs[1].append(message)

    @PortListener("b", queued=False)
    def bListener(self, message):
        self.logs[2].append(message)
        yield SimMan.timeout(10)
    
    @PortListener("b", queued=True)
    def bListenerQueued(self, message):
        self.logs[3].append(message)
        yield SimMan.timeout(10)

def test_gate_listener_method(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    # Create two identical modules in order to check for side effects
    # due to PortListener objects being used twice
    modules = MyModule("Test1"), MyModule("Test2")

    for i in range(3):
        for module in modules:
            # pass a message to port a
            module.ports["a"].input.send("msg" + str(i))
            for j in range(1):
                # All messages passed yet should have been received (and thus logged),
                # regardless of the queued flag.
                assert module.logs[j] == ["msg" + str(n) for n in range(i+1)]

def test_gate_listener_generator(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.construction')
    SimMan.initEnvironment()

    # Checking side effects by using two identical modules again
    modules = MyModule("Test1"), MyModule("Test2")

    def main():
        for i in range(3):
            for module in modules:
                module.ports["b"].input.send("msg" + str(i))
                yield SimMan.timeout(1)

    SimMan.process(main())
    SimMan.runSimulation(40)

    for module in modules:
        # Non-queued PortListener should only have received the first message,
        # since receiving takes 10 time units and the send interval is 1 time unit.
        assert module.logs[2] == ["msg0"]
        
        # Queued PortListener should have received all messages.
        assert module.logs[3] == ["msg" + str(n) for n in range(3)]
