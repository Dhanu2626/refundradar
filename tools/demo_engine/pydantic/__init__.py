"""A stand-in for pydantic, for the live demo only (tools/demo_engine/bridge.py).

refundradar.webapp describes its requests with BaseModel. Here that means:
fields come from the class annotations, defaults are copied, and each value
given must fit its annotation (str, int, None, and lists, tuples and unions of
them) or the request is refused. Nothing is coerced; the demo page sends
exactly these types.
"""

import copy
import inspect
import types
import typing


class ValidationError(ValueError):
    pass


def _fits(value, kind) -> bool:
    if kind is type(None):
        return value is None
    origin, args = typing.get_origin(kind), typing.get_args(kind)
    if origin in (types.UnionType, typing.Union):
        return any(_fits(value, a) for a in args)
    if origin is list:
        return isinstance(value, list) and all(_fits(v, args[0]) for v in value)
    if origin is tuple:
        return (isinstance(value, (list, tuple)) and len(value) == len(args)
                and all(_fits(v, a) for v, a in zip(value, args)))
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def _shaped(value, kind):
    """JSON has no tuples: a list of pairs arrives as a list of lists."""
    args = typing.get_args(kind)
    if typing.get_origin(kind) is list and args and typing.get_origin(args[0]) is tuple:
        return [tuple(v) for v in value]
    return value


class BaseModel:
    def __init__(self, **data):
        fields = {}
        for klass in reversed(type(self).__mro__):
            if klass is not object:
                fields.update(inspect.get_annotations(klass))
        for name, kind in fields.items():
            if name in data:
                if not _fits(data[name], kind):
                    raise ValidationError(f"{name}: {data[name]!r} is not a valid value")
                setattr(self, name, _shaped(data[name], kind))
            elif hasattr(type(self), name):
                setattr(self, name, copy.deepcopy(getattr(type(self), name)))
            else:
                raise ValidationError(f"{name}: this field is required")
