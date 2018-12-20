"""
A Gym environment for frequency band assignments to a sensor and a controller in
the wireless networked control of an inverted pendulum
"""
from math import degrees
from typing import Dict, List

import gym
import numpy as np
from gym import error, spaces, utils
from gym.utils import seeding
from simpy.rt import RealtimeEnvironment

from gymwipe.control.inverted_pendulum import InvertedPendulumPidController
from gymwipe.envs.core import BaseEnv, Interpreter
from gymwipe.networking.attenuation_models import FsplAttenuation
from gymwipe.networking.devices import SimpleRrmDevice
from gymwipe.networking.messages import (FakeTransmittable, Packet,
                                         Transmittable)
from gymwipe.networking.physical import FrequencyBand
from gymwipe.plants.sliding_pendulum import (AngleSensor, SlidingPendulum,
                                             WagonActuator)
from gymwipe.simtools import SimMan


class InvertedPendulumInterpreter(Interpreter):

    def __init__(self, env: "InvertedPendulumEnv"):
        self._env = env
        self.reset()

    def onPacketReceived(self, senderIndex: int, receiverIndex: int,  payload: Transmittable):
        """
        No actions for received packets, as we read sensor angles directly
        from the plant object.
        """
        pass

    def onFrequencyBandAssignment(self, deviceIndex: int, duration: int):
        pass

    def getReward(self):
        """
        Reward is :math:`\\lvert 180 - \\alpha \\rvert` with :math:`\\alpha`
        being the pendulum angle. 
        """
        return float( abs(180 - degrees(self._env.plant.getAngle())) )

    def getObservation(self):
        return int(degrees(self._env.plant.getAngle()))
    
    def getDone(self):
        return False
    
    def getInfo(self):
        return {"Sensor angle": degrees(self._env.plant.getAngle())}

class InvertedPendulumEnv(BaseEnv):
    """
    An environment that allows an agent to assign a frequency band to a sliding
    pendulum's :class:`~gymwipe.plants.sliding_pendulum.AngleSensor` and an
    :class:`~gymwipe.control.inverted_pendulum.InvertedPendulumPidController`

    Note:
        This environment is yet untested!
    """

    def __init__(self):
        frequencyBand = FrequencyBand([FsplAttenuation])
        super(InvertedPendulumEnv, self).__init__(frequencyBand, deviceCount=2)

        # Observation depends on plant angle
        self.observation_space = spaces.Discrete(180)

        # Realtime environment for visualization
        SimMan.env = RealtimeEnvironment()

        # Setup plant and devices
        plant = SlidingPendulum(visualized=True)
        controller = InvertedPendulumPidController("Controller", 0, -1, frequencyBand)
        sensor = AngleSensor("Sensor", frequencyBand, plant, controller.macAddr, 0.001) # 1 ms sample interval
        controller.sensorAddr = sensor.macAddr
        actuator = WagonActuator("Actuator", frequencyBand, plant)
        controller.actuatorAddr = actuator.macAddr
        self.plant = plant
        self.sensor = sensor
        self.actuator = actuator
        self.controller = controller

        self.deviceIndexToMacDict = {
            0: sensor.macAddr,
            1: controller.macAddr
        }

        interpreter = InvertedPendulumInterpreter(self)
        self.rrm = SimpleRrmDevice("RRM", 0, 1, self.frequencyBand, self.deviceIndexToMacDict, interpreter)

    def reset(self):
        """
        Resets the state of the environment and returns an initial observation.
        """
        return self.rrm.interpreter.getObservation()
    
    def step(self, action):
        assert self.action_space.contains(action)
        deviceIndex = action["device"]
        duration = action["duration"] * self.ASSIGNMENT_DURATION_FACTOR

        # Assign the frequency band
        assignSignal = self.rrm.assignFrequencyBand(deviceIndex, duration)

        # Run the simulation until the assignment ends
        SimMan.runSimulation(assignSignal.eProcessed)

        # Return (observation, reward, done, info)
        return self.rrm.interpreter.getFeedback()

    def render(self, mode='human', close=False):
        pass
