import logging

from gymwipe.control.scheduler import (RoundRobinTDMAScheduler,
                                       TDMASchedule, CSMASchedule, csma_encode, tdma_encode)
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.mac_layers import newUniqueMacAddress
from gymwipe.networking.MyDevices import Gateway
from gymwipe.networking.physical import FrequencyBand

from ..fixtures import simman


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


def test_encoding(caplog, simman):

    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')
    caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    mac1 = newUniqueMacAddress()
    mac2 = newUniqueMacAddress()
    mac3 = newUniqueMacAddress()
    schedule_tdma = TDMASchedule([[mac1, 0], [mac2, 0], [mac3, 0], [mac1, 1]])
    schedule_csma = CSMASchedule([(mac1, 0.5), (mac2, 0.2), (mac3, 0.7)], 10)
    assert tdma_encode(schedule_tdma, False) == 29
    assert tdma_encode(schedule_tdma, True) == 25
    assert csma_encode(schedule_csma) == 22
    assert False







