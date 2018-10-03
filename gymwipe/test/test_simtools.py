import logging
from typing import Any

import pytest
from pytest_mock import mocker

from gymwipe.simtools import Notifier, SimMan


def getMockList(mocker, length: int):
    """ Returns a list of Mock callables """
    return [mocker.Mock() for _ in range(length)]

def test_notifier_callback(caplog, mocker):
    caplog.set_level(logging.DEBUG, logger='gymwipe.simtools')

    n = Notifier('myNotifier')
    value = "test1"

    # testing callback subscription and invocation
    callHistory = []
    callbackList = []
    for i in range(3, 0, -1):
        def callback(value, i=i): # force early binding for the i values
            callHistory.append((i, value))
            print(i)
        callbackList.append(callback)

    for priority, c in enumerate(callbackList):
        n.subscribeCallback(c, priority)

    n.trigger(value)

    assert callHistory == [(i, value) for i in range(1, 4)]
    
def makeLoggingProcess(timeoutLength: int):
    """
    Returns a generator function that logs the value it is
    initialized with and yields a timeout afterwards.
    """
    def loggingProcess(value: Any):
        loggingProcess.instanceCounter += 1
        loggingProcess.value = value
        yield SimMan.timeout(timeoutLength)
        loggingProcess.instanceCounter -= 1
    
    loggingProcess.value = None
    loggingProcess.instanceCounter = 0
    return loggingProcess

def test_notifier_simpy(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.simtools')

    n = Notifier("notifier")
    p1, p2, p3 = [makeLoggingProcess(10) for _ in range(3)]

    n.subscribeProcess(p1, blocking=False)
    n.subscribeProcess(p2, blocking=True, queued=False)
    n.subscribeProcess(p3, blocking=True, queued=True)

    def main():
        for i in range(1,4):
            n.trigger("msg" + str(i))
            yield SimMan.timeout(1)

    SimMan.process(main())
    SimMan.runSimulation(4)
    # After 4 time units:
    # Three instances of p1 should be running
    assert p1.instanceCounter == 3
    # and the last one should have been started with value "msg3".
    assert p1.value == "msg3"

    # One instance of each p2 and p3 should be running (others are blocked).
    assert p2.instanceCounter == 1
    assert p2.value == "msg1"
    assert p3.instanceCounter == 1
    assert p3.value == "msg1"

    SimMan.runSimulation(11)
    # After 15 time units:
    # All p1 instances should have finished.
    assert p1.instanceCounter == 0

    # The first p2 instance should have finished and no other p2 instance should be running.
    assert p2.instanceCounter == 0
    assert p2.value == "msg1"

    # The second p3 instance should be the only p3 instance at that time.
    assert p3.instanceCounter == 1
    assert p3.value == "msg2"

    SimMan.runSimulation(25)
    # In the end, even the last p3 instance should have finished
    assert p3.instanceCounter == 0
    assert p3.value == "msg3"
    # and no other p2 instance should have been run.
    assert p2.value == "msg1"
