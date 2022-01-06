from paging_detection.utils import import_class
from paging_detection.interfaces import *

CLASS_ATTRIBUTES = ["pages_view_cls", "page_view_cls", "entries_view_cls", "page_types_cls", "paging_entry_cls"]


def snapshot_from_paging_data(data: SnapshotPagingData) -> Snapshot:
    _Snapshot = import_class(data.snapshot_cls)
    if any(getattr(data, c) for c in CLASS_ATTRIBUTES):

        class DynamicallyGeneratedSnapshot(_Snapshot):
            for c in CLASS_ATTRIBUTES:
                if cls_name := getattr(data, c):
                    locals()[c] = import_class(cls_name)

        _Snapshot = DynamicallyGeneratedSnapshot

    return _Snapshot(data)


from paging_detection.arm64 import *
from paging_detection.utils import get_full_class_name

t = SnapshotPagingData(
    path="../data_dump/ubuntu-21.10-server-cloudimg-arm64-512-idle.raw",
    designations={},
    snapshot_cls=get_full_class_name(ARM64Snapshot),
    pages_view_cls=None,
    page_view_cls=None,
    entries_view_cls=None,
    paging_entry_cls=None,
    page_types_cls=None,
)

t2 = SnapshotPagingData(
    path="../data_dump/ubuntu-21.10-server-cloudimg-arm64-512-idle.raw",
    designations={},
    paging_entry_cls=get_full_class_name(ARM64PagingEntry),
    page_types_cls=get_full_class_name(ARM64PageTypes),
)

snapshot = snapshot_from_paging_data(t)
snapshot2 = snapshot_from_paging_data(t2)
print("Done")
