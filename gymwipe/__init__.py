from typing import Any

def ownerPrefix(ownerObject: Any):
    """
    Calls :meth:`__str__` on the `ownerObject` (if it is not ``None``) and
    returns the result concatenated with '.'.
    If the object is ``None``, an empty string will be returned.
    """
    if ownerObject is None:
        return ''
    return str(ownerObject) + '.'
    