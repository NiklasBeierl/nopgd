from typing import *


def get_full_class_name(cls: Type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def import_class(cls: str) -> Type:
    mod_name, cls_name = cls.rsplit(".", maxsplit=1)
    mod = __import__(mod_name, fromlist=[mod_name])
    return getattr(mod, cls_name)
