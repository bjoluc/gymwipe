from abc import ABC, abstractmethod
from typing import List

import gym
import numpy as np
from gym import error, spaces, utils
from gym.utils import seeding

from gymwipe.networking.messages import Packet
from gymwipe.networking.physical import Channel
from gymwipe.simtools import SimMan


class BaseEnv(gym.Env):
    """
    A subclass of the OpenAI gym environment that models the Radio Resource
    Manager channel assignment problem. It sets a channel and an action space
    (depending on the number of devices to be used for channel assignment).

    The action space is a dict space of two discrete spaces: The device number
    and the assignment duration.
    """
    metadata = {'render.modes': ['human']}

    MAX_ASSIGN_DURATION = 40 # * ASSIGNMENT_DURATION_FACTOR time slots

    ASSIGNMENT_DURATION_FACTOR = 1000

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
            "duration": spaces.Discrete(self.MAX_ASSIGN_DURATION)
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

class Interpreter(ABC):
    """
    An abstract base class for interpreter implementations. An interpreter is an
    instance that observes the system's behavior by sniffing the packets
    received by the RRM's physical layer and infers both observations and
    rewards for a channel assignment learning agent. It is the only component in
    the networking system that is requires knowledge about the domain.
    """

    @abstractmethod
    def onPacketReceived(self, p: Packet):
        """
        Is invoked whenever the RRM receives a packet that is not addressed to
        it.

        Args:
            p: The packet that was received
        """
    
    def onChannelAssignment(self, duration: int, destination: bytes):
        """
        Is invoked whenever the RRM assigns the channel.

        Args:
            duration: The duration of the assignment in multiples of
                :attr:`~gymwipe.networking.stack.TIME_SLOT_LENGTH`
            destination: The MAC address of the device that the channel is
                assigned to.
        """

    @abstractmethod
    def getReward(self) -> float:
        """
        Returns a reward that ideally depends on the last channel assignment.
        """

    @abstractmethod
    def getObservation(self):
        """
        Returns an observation of the system's state.
        """
    
    def getDone(self):
        """
        Returns whether an episode has ended.

        Note:
            Reinforcement learning problems do not have to be split into
            episodes. In this case, you do not have to override the default
            implementation as it always returns ``False``.
        """
        return False
