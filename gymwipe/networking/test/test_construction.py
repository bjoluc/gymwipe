import pytest
from pytest_mock import mocker
from gymwipe.networking.construction import Gate, Module

# Note: When mocking member functions of a class:
# Disable pylint warnings due to dynamically added member functions (assert_called_with) by # pylint: disable=E1101

def test_ports(mocker):
    # Create mocking functions for message transfer testing
    g1_receive = mocker.Mock()
    g2_receive = mocker.Mock()

    # Create two gates and connect them bidirectionally
    g1 = Gate(g1_receive)
    assert g1.input._onSendCallables == {g1_receive}

    g2 = Gate(g2_receive)
    assert g2.input._onSendCallables == {g2_receive}

    g1.connectOutputTo(g2.input)
    assert g1._output._onSendCallables == {g2.input.send}

    g2.connectOutputTo(g1.input)
    assert g2._output._onSendCallables == {g1.input.send}

    # Test message sending
    msg1 = 'test message 1'
    msg2 = 'test message 2'

    g1._output.send(msg1)
    g2_receive.assert_called_with(msg1)

    g2._output.send(msg2)
    g1_receive.assert_called_with(msg2)

def test_modules(mocker):
    m = Module('test module')
    assert m.getName() == 'test module'

    g1, g2 = (Gate(), Gate())
    m._addGate('gate 1', g1)
    m._addGate('gate 2', g2)
    assert m.gates['gate 1'] == g1
    assert m.gates['gate 2'] == g2
    assert m.gates == {'gate 1': g1, 'gate 2': g2}

    m1, m2 = (Module('module 1'), Module('module 2'))
    m._addSubModule('sub module 1', m1)
    m._addSubModule('sub module 2', m2)
    assert m._subModules['sub module 1'] == m1
    assert m._subModules['sub module 2'] == m2
    assert m._subModules == {'sub module 1': m1, 'sub module 2': m2}
