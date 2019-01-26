import logging

from gymwipe.control.scheduler import (DQNTDMAScheduler,
                                       RoundRobinTDMAScheduler, Scheduler,
                                       TDMASchedule, tdma_encode)
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_layers import newUniqueMacAddress
from gymwipe.networking.MyDevices import Gateway,GatewayDevice
from gymwipe.networking.physical import FrequencyBand


def test_tdma(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')

    sched = TDMASchedule([["a", 1], ["b", 1], ["c", 1]])
    schedSame = TDMASchedule([["a", 1], ["a", 1], ["a", 1], ["b", 1], ["c", 1]])

    rrScheduler = RoundRobinTDMAScheduler(["a", "b", "c", "d"],["a", "b"], ["c", "d"], 3)
    assert rrScheduler.devices == ["a", "b", "c", "d"]
    assert rrScheduler.timeslots == 3
    rrScheduler.next_schedule()
    assert rrScheduler.schedule.get_string() == "1 a 0 1 2 b 0 1 3 c 1 1 4"
    rrScheduler.next_schedule()
    assert rrScheduler.schedule.get_string() == "1 c 0 1 2 d 1 1 3 d 0 1 4"
    rrScheduler.next_schedule()
    assert sched.get_string() == "1 a 1 1 2 b 1 1 3 c 1 1 4"
    assert schedSame.get_string() == "1 a 1 1 4 b 1 1 5 c 1 1 6"


def test_scheduler_creation(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    mac1 = newUniqueMacAddress()
    mac2 = newUniqueMacAddress()
    mac3 = newUniqueMacAddress()
    gateway = Gateway("roundrobinTDMA", [mac1, mac2], [mac3], "Gateway", 0, 0, FrequencyBand([FsplAttenuation]),5)
    assert len(gateway.deviceIndexToMacDict) == 3
    assert len(gateway.macToDeviceIndexDict) == 3
    assert len(gateway.sensors) == 2
    assert len(gateway.actuators) == 1
    assert isinstance(gateway.scheduler, RoundRobinTDMAScheduler)
    gateway2 = Gateway("DQNTDMAScheduler", [1, 2, 3], [4, 5, 6], "Gateway", 0, 0, FrequencyBand([FsplAttenuation]),5)
    assert isinstance(gateway2.scheduler, DQNTDMAScheduler)


def test_encoding(caplog):

    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    mac1 = newUniqueMacAddress()
    mac2 = newUniqueMacAddress()
    mac3 = newUniqueMacAddress()
    schedule = TDMASchedule([[mac1, 0], [mac2, 0], [mac3, 0], [mac1, 1]])
    assert tdma_encode(schedule, False) == 29
    assert tdma_encode(schedule, True) == 25



