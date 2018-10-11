"""
Gym environments based on the Simple network devices
"""

from typing import List

import gym
import numpy as np
from gym import error, spaces, utils
from gym.utils import seeding

from gymwipe.networking.attenuation_models import FSPLAttenuation
from gymwipe.networking.devices import SimpleNetworkDevice, SimpleRrmDevice
from gymwipe.networking.messages import (FakeTransmittable, Packet,
                                         Transmittable)
from gymwipe.networking.physical import Channel
from gymwipe.simtools import SimMan


class BaseEnv(gym.Env):
    """
    A subclass of the OpenAI gym environment that models the Radio Resource
    Manager channel assignment problem. It sets a channel and an action space
    (depending on the number of devices to be used for channel assignment).
    """
    metadata = {'render.modes': ['human']}

    def __init__(self, channel: Channel, deviceCount: int):
        """
        Args:
            channel: The physical channel to be used for the simulation
            deviceCount: The number of devices to be included in the
                environment's action space
        """
        self.channel = channel

        self.deviceCount = deviceCount
        self.action_space = spaces.Dict({
            "device": spaces.Discrete(deviceCount),
            "duration": spaces.Box(low=10,high=float('inf'))
        })

        self.seed()

    def seed(self, seed=None):
        """
        Sets the seed for this environment's random number generator and returns
        it in a single-item list.
        """
        self.np_random, seed = seeding.np_random(seed)
        return [seed]
    
    def render(self, mode='human', close=False):
        """
        Renders the environment to stdout.
        """

class SimpleTestEnv(BaseEnv):
    """
    An environment for testing reinforcement learning with three simple devices:

        *   Two network devices that send a configurable amount of data to each
            other
        *   A simple RRM that receives piggy-backed mac-layer queue lengths as
            rewards
    """

    class _senderDevice(SimpleNetworkDevice):
        
        def __init__(self, name: str, xPos: float, yPos: float, channel: Channel,
                        packetByteLength: int, packetInterval: int):
            super(SimpleTestEnv._senderDevice, self).__init__(name, xPos, yPos, channel)
            self.packetLength = packetByteLength
            self.packetInterval = packetInterval
            SimMan.process(self.senderProcess())

            self.destinationMac: bytes = None # to be set after construction
        
        def senderProcess(self):
            data = FakeTransmittable(self.packetLength)
            while True:
                self.send(data, self.destinationMac)
                yield SimMan.timeout(self.packetInterval)


    def __init__(self):
        channel = Channel(FSPLAttenuation)
        super(SimpleTestEnv, self).__init__(channel, deviceCount=2)

        # no observations in this environment
        self.observation_space = spaces.Box(0,0)

        self.senders: List[SimpleTestEnv._senderDevice] = None
        self.reset()

    def step(self, action):
        assert self.action_space.contains(action)

        reward = 0
        done = False
        observation = 0
        return observation, reward, done, {}

    def reset(self):
        """
        Resets the state of the environment and returns an initial observation.
        """
        SimMan.initEnvironment()

        self.senders = [
            SimpleTestEnv._senderDevice("Sender 1", 1, 1, self.channel, 8, 16),
            SimpleTestEnv._senderDevice("Sender 2", -1, -1, self.channel, 8, 8)
        ]

        observation = 0
        return observation

    def render(self, mode='human', close=False):
        pass
