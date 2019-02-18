import logging

from gymwipe.control.scheduler import (RoundRobinTDMAScheduler, Scheduler,
                                       TDMASchedule, tdma_encode)
from gymwipe.control.paper_scheduler import MyDQNTDMAScheduler, MyDQNCSMAScheduler


def test_tf(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')

    scheduler = MyDQNCSMAScheduler(None, 3)
    scheduler.next_schedule(None)