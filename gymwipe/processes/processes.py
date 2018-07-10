"""
"""
from typing import Any
from abc import ABC, abstractmethod

class PlantObserver(ABC):
    """
    A baseclass for objects to be notified on changes of a PlantObservable object.
    """

    @abstractmethod
    def notify(self, caller: 'PlantObservable', key: str, value: Any):
        """
        Is called by changes of any PlantObservable object this PlantObserver is registered at.

        Args:
            caller: The PlantObservable calling this method
            key: The key of the PlantObservable's value that changed
            value: The key's new value
        """
        pass


class PlantObservable:
    """
    A base class to be extended by Plant objects. Implements an observer pattern for keys and values.
    """

    def __init__(self):
        self._observers = set()
    
    def addObserver(self, o: PlantObserver):
        """
        Adds the PlantObserver to the set of this PlantObservable's observers.

        Args:
            o: The PlantObserver to be added
        """
        self._observers.add(o)
    
    def _notifyObservers(self, key: str, value: Any):
        """
        Notifies all Observers added via the addObserver method about the change of `key` to `value`.

        Args:
            key: The key of the value that changed
            value: The new value stored as `key`
        """
        for o in self._observers:
            o.notify(self, key, value)


class Plant(PlantObservable):
    """
    A simple key value store for physical plant state implementing PlantObservable.
    """

    def __init__(self, name: str):
        """
        Args:
            name: The plant's name, for logging and debugging
        """
        super(Plant, self).__init__()
        self._name = name
        self._values = {}
    
    def setValue(self, key: str, value: Any) -> None:
        """
        Stores `value` indexed by `key`.
        """
        self._values[key] = value
        self._notifyObservers(key, value)
    
    def getValue(self, key: str) -> Any:
        """
        Returns the value indexed by `key` or ``None`` if the key does not exist.
        """
        return self._values.get(key)
    