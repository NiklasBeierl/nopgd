__all__ = ["SnapshotPagingData", "PageTypes", "PagingEntry", "EntriesView", "PageView", "PagesView", "Snapshot"]

from abc import *
from enum import IntEnum
from functools import cached_property
import mmap
import struct
from typing import *

from pydantic import BaseModel

from paging_detection import PAGING_STRUCTURE_SIZE, PAGING_ENTRY_SIZE
from paging_detection.utils import get_full_class_name


class PageTypes(IntEnum):
    def __add__(self, other) -> "PageTypes":
        return self.__class__(self.value + other)

    def __radd__(self, other) -> "PageTypes":
        return self.__class__(self.value + other)

    def __sub__(self, other) -> "PageTypes":
        return self.__class__(self.value - other)

    def __rsub__(self, other) -> "PageTypes":
        return self.__class__(other - self.value)


PageTypes_T = TypeVar("PageTypes_T", bound=PageTypes)


class PagingEntry(ABC, Generic[PageTypes_T]):
    def __init__(self, value: int):
        self.value: int = value

    @property
    def target(self) -> int:
        raise NotImplementedError

    @property
    def present(self) -> bool:
        raise NotImplementedError

    def is_valid(self, page_type: PageTypes_T) -> bool:
        raise NotImplementedError

    def target_is_data(self, assumed_type: PageTypes_T) -> bool:
        raise NotImplementedError


PagingEntry_T = TypeVar("PagingEntry_T", bound=PagingEntry)


class EntriesView(Generic[PagingEntry_T]):
    def __init__(self, snapshot: "Snapshot", page_offset: int):
        self.snapshot: "Snapshot" = snapshot
        self.page_offset: int = page_offset
        self._present_keys = None

    def __getitem__(self, entry_offset: int) -> PagingEntry_T:
        if entry_offset % 8 != 0:
            raise KeyError

        offset = self.page_offset + entry_offset
        (value,) = struct.unpack("<Q", self.snapshot.mmap[offset : offset + PAGING_ENTRY_SIZE])
        return self.snapshot.paging_entry_cls(value=value)

    def __len__(self):
        return len(self.keys())

    def keys(self, present_only=True) -> Union[range, List[int]]:
        all_offsets = range(0, PAGING_STRUCTURE_SIZE, PAGING_ENTRY_SIZE)
        if not present_only:
            return all_offsets

        if not (present_keys := self._present_keys):
            present_keys = [offset for offset in all_offsets if self[offset].present]
            self._present_keys = present_keys

        return present_keys

    def __iter__(self):
        return iter(self.keys())

    def values(self, present_only=True) -> Iterable[PagingEntry_T]:
        return (self[offset] for offset in self.keys(present_only=present_only))

    def items(self, present_only=True) -> Iterable[Tuple[int, PagingEntry_T]]:
        return ((offset, self[offset]) for offset in self.keys(present_only=present_only))


EntriesView_T = TypeVar("EntriesView_T", bound=EntriesView)


class PageView(Generic[EntriesView_T, PageTypes_T]):
    def __init__(self, snapshot: "Snapshot", offset: int):
        self.snapshot: "Snapshot" = snapshot
        self.offset: int = offset

    @property
    def designations(self) -> Set[PageTypes_T]:
        return self.snapshot.designations[self.offset]

    @designations.setter
    def designations(self, value):
        self.snapshot.designations[self.offset] = value

    @cached_property
    def entries(self) -> EntriesView_T:
        return self.snapshot.entries_view_cls(self.snapshot, self.offset)


PageView_T = TypeVar("PageView_T", bound=PageView)


class PagesView(Generic[PageView_T]):
    def __init__(self, snapshot: "Snapshot"):
        self.snapshot = snapshot
        self.pages: Dict[int, PageView] = {}

    def __getitem__(self, item: int) -> PageView_T:
        if item % PAGING_STRUCTURE_SIZE != 0:
            raise KeyError
        if view := self.pages.get(item):
            return view
        else:
            pv = self.snapshot.page_view_cls(self.snapshot, item)
            self.pages[item] = pv
            return pv

    def __len__(self) -> int:
        return len(self.snapshot.designations)

    def keys(self) -> Iterable[int]:
        return self.snapshot.designations.keys()

    def __iter__(self):
        return iter(self.keys())

    def values(self) -> Iterable[PageView_T]:
        for offset in self.snapshot.designations:
            yield self[offset]

    def items(self) -> Iterable[Tuple[int, PageView_T]]:
        for offset in self.snapshot.designations:
            yield offset, self[offset]


PagesView_T = TypeVar("PagesView_T", bound=PagesView)


class Snapshot(ABC, Generic[PagesView_T]):
    @property
    @abstractmethod
    def paging_entry_cls(self) -> ClassVar[Type[PagingEntry]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def page_types_cls(self) -> ClassVar[Type[PagingEntry]]:
        raise NotImplementedError

    page_view_cls: ClassVar[Type[PageView]] = PageView
    entries_view_cls: ClassVar[Type[EntriesView]] = EntriesView
    pages_view_cls: ClassVar[Type[PagesView]] = PagesView

    """
    def __init_subclass__(cls, **kwargs):
        if not hasattr(cls, "paging_entry_cls"):
            raise NotImplementedError("You must set paging_entry_cls when inheriting form Snapshot")
        if not hasattr(cls, "page_types_cls"):
            raise NotImplementedError("You must set page_types_cls when inheriting form Snapshot")
    """

    def __init__(self, snapshot_data: "SnapshotPagingData"):
        self.snapshot = snapshot_data
        self.designations = snapshot_data.designations
        self.path = snapshot_data.path

    @cached_property
    def mmap(self):
        with open(self.path) as f:
            return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    @cached_property
    def pages(self) -> PagesView_T:
        return self.pages_view_cls(self)

    @property
    def size(self) -> int:
        return len(self.mmap)


class SnapshotPagingData(BaseModel, Generic[PageTypes_T]):
    snapshot_cls: str = get_full_class_name(Snapshot)
    pages_view_cls: Optional[str] = get_full_class_name(PagesView)
    page_view_cls: Optional[str] = get_full_class_name(PageView)
    entries_view_cls: Optional[str] = get_full_class_name(EntriesView)
    paging_entry_cls: Optional[str]
    page_types_cls: Optional[str]
    path: str
    designations: Dict[int, PageTypes_T]
