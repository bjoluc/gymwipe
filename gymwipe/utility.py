"""
Domain-independent utility functions
"""
from typing import Any


def ownerPrefix(ownerObject: Any) -> str:
    """
    Calls :meth:`__repr__` on the `ownerObject` (if it is not ``None``) and
    returns the result concatenated with '.'.
    If the object is ``None``, an empty string will be returned.
    """
    if ownerObject is None:
        return ''
    return repr(ownerObject) + '.'

def strAndRepr(obj: Any) -> str:
    """
    Returns "str (repr)" where str and repr are the result of `str(obj)` and
    `repr(obj)`.
    """
    return "{} ({})".format(str(obj), repr(obj))