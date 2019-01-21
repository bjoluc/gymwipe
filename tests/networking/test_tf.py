import logging

from gymwipe.control.scheduler import (DQNTDMAScheduler,
                                       RoundRobinTDMAScheduler, Scheduler,
                                       TDMASchedule,TDMAEncode, DQNCSMAScheduler)

def test_tf(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')

    scheduler = DQNCSMAScheduler(None, 3)
    scheduler.nextSchedule(None)