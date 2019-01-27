import logging

from gymwipe.control.scheduler import (MyDQNTDMAScheduler,
                                       RoundRobinTDMAScheduler, Scheduler,
                                       TDMASchedule, tdma_encode, MyDQNCSMAScheduler)

def test_tf(caplog):
    caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')

    scheduler = MyDQNCSMAScheduler(None, 3)
    scheduler.next_schedule(None)