import json
import struct
from pydantic import BaseModel, Field
from typing import Dict, Set, Iterable

from paging_detection import PagingEntry, PageTypes, PAGING_STRUCTURE_SIZE, PAGING_ENTRY_SIZE, ReadableMem
from paging_detection.mmaped import SnapshotPagingData


class PagingStructure(BaseModel):
    entries: Dict[int, PagingEntry]
    designations: Set[PageTypes] = Field(default_factory=set)

    @property
    def valid_pml4es(self) -> Dict[int, PagingEntry]:
        return {offset: entry for offset, entry in self.entries.items() if entry.valid_pml4e}

    @property
    def valid_pdpes(self) -> Dict[int, PagingEntry]:
        return {offset: entry for offset, entry in self.entries.items() if entry.valid_pdpe}

    @property
    def valid_pdes(self) -> Dict[int, PagingEntry]:
        return {offset: entry for offset, entry in self.entries.items() if entry.valid_pde}

    @property
    def valid_ptes(self) -> Dict[int, PagingEntry]:
        return self.entries

    def __getitem__(self, item):
        start = item.start
        end = item.stop or PAGING_STRUCTURE_SIZE
        entries = {
            offset: PagingEntry(value=entry.value) for offset, entry in self.entries.items() if start <= offset < end
        }
        return PagingStructure(entries=entries, designations=set(self.designations))

    @classmethod
    def from_mem(cls, mem: ReadableMem, designations: Iterable[PageTypes]) -> "PagingStructure":
        assert len(mem) == PAGING_STRUCTURE_SIZE
        entries = {}
        for offset in range(0, PAGING_STRUCTURE_SIZE, PAGING_ENTRY_SIZE):
            value = struct.unpack("<Q", mem[offset : offset + 8])[0]
            if value & 1:  # Only add present entries
                entries[offset] = PagingEntry(value=value)
        return cls(entries=entries, designations=set(designations))


# Legacy class
class Snapshot(BaseModel):
    path: str
    pages: Dict[int, PagingStructure]
    size: int


if __name__ == "__main__":
    import argparse
    import pathlib

    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to full snapshot json.", type=pathlib.Path)
    parser.add_argument("output", help="Output path.", type=pathlib.Path)
    args = parser.parse_args()

    with open(args.input) as f:
        input = Snapshot.validate(json.load(f))

    designations = {offset: page.designations for offset, page in input.pages.items()}
    output = SnapshotPagingData(path=input.path, designations=designations)

    with open(args.output, "w") as f:
        f.write(output.json())
