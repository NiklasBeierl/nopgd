import mmap
from functools import cached_property
import struct
from typing import Dict, Set, Iterable, Tuple, Union, List

from pydantic import BaseModel

from paging_detection import PageTypes, PAGING_STRUCTURE_SIZE, PAGING_ENTRY_SIZE, PagingEntry, Snapshot as FullSnapshot


class LightSnapshot(BaseModel):
    path: str
    designations: Dict[int, Set[PageTypes]]

    @classmethod
    def from_full_snapshot(cls, snapshot: FullSnapshot):
        designations = {offset: page.designations for offset, page in snapshot.pages.items()}
        return cls(path=snapshot.path, designations=designations)


class EntriesView:
    def __init__(self, snapshot, page_offset: int):
        self.snapshot = snapshot
        self.page_offset: int = page_offset
        self._present_keys = None

    def __getitem__(self, entry_offset: int) -> PagingEntry:
        if entry_offset % 8 != 0:
            raise KeyError

        offset = self.page_offset + entry_offset
        (value,) = struct.unpack("<Q", self.snapshot.mmap[offset : offset + PAGING_ENTRY_SIZE])
        return PagingEntry(value=value)

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

    def values(self, present_only=True) -> Iterable[PagingEntry]:
        return (self[offset] for offset in self.keys(present_only=present_only))

    def items(self, present_only=True) -> Iterable[Tuple[int, PagingEntry]]:
        return ((offset, self[offset]) for offset in self.keys(present_only=present_only))


class PageView:
    def __init__(self, snapshot, offset):
        self.snapshot = snapshot
        self.offset = offset

    @property
    def designations(self):
        return self.snapshot.designations[self.offset]

    @cached_property
    def entries(self):
        return EntriesView(self.snapshot, self.offset)


class PagesView:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.pages: Dict[int, PageView] = {}

    def __getitem__(self, item: int) -> PageView:
        if item % PAGING_STRUCTURE_SIZE != 0:
            raise KeyError
        if view := self.pages.get(item):
            return view
        else:
            pv = PageView(self.snapshot, item)
            self.pages[item] = pv
            return pv

    def __len__(self):
        return len(self.snapshot.designations)

    def keys(self) -> Iterable[int]:
        return self.snapshot.designations.keys()

    def __iter__(self):
        return iter(self.keys())

    def values(self) -> Iterable[PageView]:
        for offset in self.snapshot.designations:
            yield self[offset]

    def items(self) -> Iterable[Tuple[int, PageView]]:
        for offset in self.snapshot.designations:
            yield offset, self[offset]


class MemMappedSnapshot:
    def __init__(self, snapshot: LightSnapshot):
        self.snapshot = snapshot
        self.designations = snapshot.designations
        self.path = snapshot.path

    @cached_property
    def mmap(self):
        with open(self.path) as f:
            return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    @cached_property
    def pages(self):
        return PagesView(self)

    def json(self):
        return self.snapshot.json()
