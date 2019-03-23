from gymwipe.baSimulation import BAEnvironment

from gymwipe.baSimulation.constants import Configuration, SchedulerType, ProtocolType
from gymwipe.simtools import SimMan


def env_creation():
    # caplog.set_level(logging.DEBUG, logger='gymwipe.baSimulation.BAEnvironment')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.plants.state_space_plants')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.networking.MyDevices')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.networking.mac_layers')

    # caplog.set_level(logging.DEBUG, logger='gymwipe.networking.simple_stack')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.control.paper_scheduler')
    # caplog.set_level(logging.DEBUG, logger='gymwipe.control.scheduler')



    used_configs = dqn_config
    for i in range(len(used_configs)):
        config = used_configs[i]
        BAEnvironment.initialize(config)
        while not BAEnvironment.is_done:
            SimMan.runSimulation(0.01)
        BAEnvironment.reset_env()


if __name__ == "__main__":
    env_creation()
