from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

import gym
import numpy as np
from gym import error, spaces, utils
from gym.utils import seeding

from gymwipe.networking.messages import Packet, Transmittable
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

    MAX_ASSIGN_DURATION = 20 # * ASSIGNMENT_DURATION_FACTOR time slots

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
    An :class:`Interpreter` is an instance that observes the system's behavior
    by sniffing the packets received by the RRM's physical layer and infers
    observations and rewards for a channel assignment learning agent. Thus, RRM
    and learning agent can be used in any domain with only swapping the
    interpreter.

    This class serves as an abstract base class for all :class:`Interpreter`
    implementations.

    When implementing an interpreter, the following three methods have to be
    overridden:

        * :meth:`onPacketReceived`
        * :meth:`getReward`
        * :meth:`getObservation`

    The following methods provide default implementations that you might also
    want to override depending on your use case:

        * :meth:`reset`
        * :meth:`onChannelAssignment`
        * :meth:`getDone`
        * :meth:`getInfo`
    """

    @abstractmethod
    def onPacketReceived(self, senderIndex: int, receiverIndex: int, payload: Transmittable):
        """
        Is invoked whenever the RRM receives a packet that is not addressed to
        it.

        Args:
            senderIndex: The device index of the received packet's sender (as in
                the gym environment's action space)
            receiverIndex: The device index of the received packet's receiver
                (as in the gym environment's action space)
            payload: The received packet's payload
        """
    
    def onChannelAssignment(self, deviceIndex: int, duration: int):
        """
        Is invoked whenever the RRM assigns the channel.

        Args:
            deviceIndex: The index (as in the gym environment's action space) of
                the device that the channel is assigned to.
            duration: The duration of the assignment in multiples of
                :attr:`~gymwipe.networking.stack.TIME_SLOT_LENGTH`
        """

    @abstractmethod
    def getReward(self) -> float:
        """
        Returns a reward that depends on the last channel assignment.
        """

    @abstractmethod
    def getObservation(self) -> Any:
        """
        Returns an observation of the system's state.
        """
    
    def getDone(self) -> bool:
        """
        Returns whether an episode has ended.

        Note:
            Reinforcement learning problems do not have to be split into
            episodes. In this case, you do not have to override the default
            implementation as it always returns ``False``.
        """
        return False

    def getInfo(self) -> Dict:
        """
        Returns a :class:`dict` providing additional information on the
        environment's state that may be useful for debugging but is not allowed
        to be used by a learning agent.
        """
        return {}

    def getFeedback(self) -> Tuple[Any, float, bool, Dict]:
        """
        You may want to call this at the end of a channel assignment to get
        feedback for your learning agent. The return values are ordered like
        they need to be returned by the :meth:`step` method of a gym
        environment.

        Returns:
            A 4-tuple with the results of :meth:`getObservation`,
            :meth:`getReward`, :meth:`getDone`, and :meth:`getInfo`
        """
        return self.getObservation(), self.getReward(), self.getDone(), self.getInfo()
    
    def reset(self):
        """
        This method is invoked when the environment is reset – override it with
        your initialization tasks if you feel like it.
        """
