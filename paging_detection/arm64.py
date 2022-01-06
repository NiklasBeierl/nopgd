from interfaces import *


class ARM64PageTypes(PageTypes):
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


class ARM64PagingEntry(PagingEntry[ARM64PageTypes]):
    @property
    def present(self) -> bool:
        return bool(self.value & 1)

    @property
    def target(self) -> int:
        return self.value

    def is_valid(self, page_type: ARM64PageTypes) -> bool:
        return True

    def target_is_data(self, assumed_type: ARM64PageTypes) -> bool:
        if assumed_type == ARM64PageTypes.L4:
            return True
        return False


ARM64PageView = PageView[ARM64PagingEntry, ARM64PageTypes]
ARM64PagesView = PagesView[ARM64PageView]


class ARM64Snapshot(Snapshot[ARM64PageView]):
    paging_entry_cls = ARM64PagingEntry
    page_types_cls = ARM64PageTypes
