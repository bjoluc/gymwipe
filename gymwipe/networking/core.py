"""
Core components for networking simulation
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple
from math import sqrt, log10
from simpy import Event
from gymwipe.networking.messages import Packet
from gymwipe.simtools import SimMan, SimTimePrepender

logger = SimTimePrepender(logging.getLogger(__name__))

class Position:
    """
    A simple class for representing 2-dimensional positions, stored as two float values.
    """

    def __init__(self, x: float, y: float):
        """
        Args:
            x: The distance to a fixed origin in x direction, measured in meters
            y: The distance to a fixed origin in y direction, measured in meters
        """
        self.x = x
        self.y = y
    
    def __eq__(self, p):
        return p.x == self.x & p.y == self.y
    
    def distanceTo(self, p: 'Position') -> float:
        """
        Returns the euclidean distance of this :class:`Position` to `p`, measured in meters.

        Args:
            p: The :class:`Position` to calculate the distance to
        """
        return sqrt((self.x - p.x)**2 + (self.y - p.y)**2)
    
    def __str__(self):
        return "Position({},{})".format(self.x, self.y)

class NetworkDevice:
    """

    """

    def __init__(self, name: str, position: Position):
        self._name = name
        self._position = position
    
    def __str__(self):
        return "NetworkDevice('{}')".format(self.name)
    
    @property
    def position(self):
        """Position: The device's physical position"""
        return self._position
    
    @position.setter
    def setPosition(self, position):
        self._position = position
    
    @property
    def name(self) -> str:
        """str: The device name (for debugging and plotting)"""
        return self._name
