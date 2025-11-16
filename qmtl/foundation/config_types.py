from __future__ import annotations

from collections.abc import Mapping as ABCMapping, Sequence as ABCSequence
from typing import Any, Callable, Dict, Mapping, Sequence, get_args, get_origin


def _describe_collection(args: tuple[Any, ...], label: str) -> str:
    inner = _type_description(args[0]) if args else "any"
    return f"{label}[{inner}]"


def _describe_mapping(args: tuple[Any, ...]) -> str:
    key_desc = _type_description(args[0]) if args else "any"
    value_desc = _type_description(args[1]) if len(args) > 1 else "any"
    return f"mapping[{key_desc}, {value_desc}]"


def _describe_tuple(args: tuple[Any, ...]) -> str:
    if not args:
        return "tuple"
    if len(args) == 2 and args[1] is Ellipsis:
        return f"tuple[{_type_description(args[0])}]"
    inner_desc = ", ".join(_type_description(arg) for arg in args)
    return f"tuple[{inner_desc}]"


_TYPE_DESCRIPTION_HANDLERS: Dict[Any, Callable[[tuple[Any, ...]], str]] = {
    list: lambda args: _describe_collection(args, "list"),
    Sequence: lambda args: _describe_collection(args, "sequence"),
    ABCSequence: lambda args: _describe_collection(args, "sequence"),
    set: lambda args: _describe_collection(args, "set"),
    tuple: lambda args: _describe_tuple(args),
    Mapping: _describe_mapping,
    ABCMapping: _describe_mapping,
    dict: _describe_mapping,
}


def _describe_leaf(annotation: Any) -> str:
    if annotation is type(None):  # pragma: no cover - explicit None type
        return "null"
    return getattr(annotation, "__name__", str(annotation))


def _type_description(annotation: Any) -> str:
    if annotation is Any:
        return "any"
    origin = get_origin(annotation)
    if origin is None:
        return _describe_leaf(annotation)
    args = get_args(annotation)
    handler = _TYPE_DESCRIPTION_HANDLERS.get(origin)
    if handler is not None:
        return handler(args)
    return " | ".join(_type_description(arg) for arg in args)


def _inner_type_names(values: Sequence[Any]) -> str:
    inner = {type(item).__name__ for item in values}
    return ",".join(sorted(inner)) or "unknown"


_VALUE_TYPE_CHECKS: tuple[tuple[type, Callable[[Any], str]], ...] = (
    (list, lambda value: f"list[{_inner_type_names(value)}]"),
    (tuple, lambda _value: "tuple"),
    (set, lambda value: f"set[{_inner_type_names(value)}]"),
    (dict, lambda _value: "mapping"),
)


def _value_type_name(value: Any) -> str:
    if value is None:
        return "null"
    for type_, formatter in _VALUE_TYPE_CHECKS:
        if isinstance(value, type_):
            return formatter(value)
    return type(value).__name__


def _type_matches(value: Any, annotation: Any) -> bool:
    if annotation is Any:
        return True

    origin = get_origin(annotation)
    if origin is None:
        return _matches_without_origin(value, annotation)

    args = get_args(annotation)
    handler = _GENERIC_TYPE_HANDLERS.get(origin)
    if handler is not None:
        return handler(value, args)

    return any(_type_matches(value, option) for option in args)


def _matches_without_origin(value: Any, annotation: Any) -> bool:
    if annotation is type(None):
        return value is None
    if isinstance(annotation, type):
        return isinstance(value, annotation)
    return True


def _matches_list(value: Any, args: tuple[Any, ...]) -> bool:
    if not isinstance(value, list):
        return False
    inner = args[0] if args else Any
    return all(_type_matches(item, inner) for item in value)


def _matches_tuple(value: Any, args: tuple[Any, ...]) -> bool:
    if not isinstance(value, tuple):
        return False
    if not args:
        return True
    if _is_variadic_tuple(args):
        return all(_type_matches(item, args[0]) for item in value)
    if len(value) != len(args):
        return False
    return _tuple_items_match(value, args)


def _is_variadic_tuple(args: tuple[Any, ...]) -> bool:
    return len(args) == 2 and args[1] is Ellipsis


def _tuple_items_match(values: tuple[Any, ...], expected: tuple[Any, ...]) -> bool:
    return all(_type_matches(item, target) for item, target in zip(values, expected))


def _matches_set(value: Any, args: tuple[Any, ...]) -> bool:
    if not isinstance(value, set):
        return False
    inner = args[0] if args else Any
    return all(_type_matches(item, inner) for item in value)


def _matches_mapping(value: Any, args: tuple[Any, ...]) -> bool:
    if not isinstance(value, dict):
        return False
    key_type = args[0] if args else Any
    value_type = args[1] if len(args) > 1 else Any
    return all(
        _type_matches(k, key_type) and _type_matches(v, value_type)
        for k, v in value.items()
    )


def _matches_sequence(value: Any, args: tuple[Any, ...]) -> bool:
    if isinstance(value, (str, bytes)) or not isinstance(value, ABCSequence):
        return False
    inner = args[0] if args else Any
    return all(_type_matches(item, inner) for item in value)


_GENERIC_TYPE_HANDLERS: Dict[Any, Callable[[Any, tuple[Any, ...]], bool]] = {
    list: _matches_list,
    Sequence: _matches_sequence,
    ABCSequence: _matches_sequence,
    tuple: _matches_tuple,
    set: _matches_set,
    dict: _matches_mapping,
    Mapping: _matches_mapping,
    ABCMapping: _matches_mapping,
}
