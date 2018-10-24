"""
Domain-independent utility functions
"""
from typing import Any


def ownerPrefix(ownerObject: Any) -> str:
    """
    Calls :meth:`__str__` on the `ownerObject` (if it is not ``None``) and
    returns the result concatenated with '.'.
    If the object is ``None``, an empty string will be returned.
    """
    if ownerObject is None:
        return ''
    return str(ownerObject) + '.'

def strAndRepr(obj: Any) -> str:
    """
    Returns "str (repr)" where str and repr are the result of `str(obj)` and
    `repr(obj)`.
    """
    return "{} ({})".format(str(obj), repr(obj))