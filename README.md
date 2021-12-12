# About

This is some experimental code to try and see whether x86 64bit long mode paging structures can be detected in raw
memory. The primary use-case would be analyzing memory snapshots for which the running kernel version is not known. The
core parts of the code are geared towards x86 but should be quite easy to adapt for similar architectures. So far the
entire approach was only evaluated for linux kernels, some heuristics are also linux specific, but should hold across
different version of linux.

## Data structures / File formats

This code uses two kinds of data structures to represent the "paging structure data" in a snapshot.

### Snapshot Objects / JSON Files

`MemMappedSnapshot` gives you OOP-style access to any 4kb page in a snapshot under the
assumption that it is a paging structure:

```python
from paging_detection.mmaped import SnapshotPagingData, MemMappedSnapshot
snapshot = MemMappedSnapshot(SnapshotPagingData(path=some_path, designations={}))
entry = snapshot.pages[4096].entries[16]
if entry.present:
    target_page = snapshot.pages[entry.target]
else:
    print("Entry is not present!")
```

You can store your assumptions about the "types" of a page as "designations":

```python
from paging_detection import PageTypes
snapshot.pages[4096].designations.add(PageTypes.PML4)  
```

To store designations, a dataclass (`paging_detection.mmaped.SnapshotPagingData`) is used. It also stores the path of the (raw) snapshot file and is easily saved as JSON...

```python
with open("snapshot-pages.json", "w") as f:
    f.write(snapshot.json())
```

... so you can pick up right where you left off...

```python
import json
with open("snapshot-pages.json") as f:
    snapshot = MemMappedSnapshot(SnapshotPagingData.validate(json.load(f)))
```

### Graphs / Graphml Files

The other datastructure used to represent paging data are graphs, specifically [networkx.MultiDiGraph](https://networkx.org/documentation/stable/reference/classes/multidigraph.html). The
advantages of this representation are:

- Graph operations provided by networkx
- The data is reduced to the parts chosen when constructing the graph from the snapshot.

These graphs are stored as `.graphml` files, in these files:

- A vertex represents a 4kb-page in memory
    - Its ID is the physical address of the corresponding page (as a string, because graphml does not allow `int`-IDs)
    - It may or may not be an actual paging structure
    - Depending on the purpose of the file, not all pages in memory get a node
- Vertices have properties (all optional):
    - `PML4`, `PDP`, `PD`, `PT`: `bool` Whether the page is considered to be a PML4, PDP, ...
    - `invalid_PML4`, `invalid_PDP`, ... : `int` How many entries would be considered "invalid" under the respective
      designation
        - "invalid" means they would cause an exception to be raised by an MMU if a translation attempt is made
    - `oob_PML4`, `oob_PDP`, ...: `int` How many entries would be considered "out of bounds" unt the respective
      designation
        - "oob" (out of bounds) means the entry would point to a paging structure outside the bounds of physical memory
- An edge represents an entry pointing from one page to another
    - Meaning that IF the source vertex is indeed a paging structure, it has a **present** entry pointing to the target
      vertex
- Edges have properties (all optional):
    - `offset`: The offset of the corresponding entry has within the paging structure (source node)

## Data flow:

At the moment the code here makes one long "pipeline" for processing a snapshot. All scripts here can be invoked with `--help` for more usage info.

### Steps:

#### Get PML4 (PGD) addresses from your snapshot (Get the ground truth)

Use the [`pslist_with_pgds.PsListWithPGDs`](volatility_plugins/pslist_with_pgds.py) Volatility3 plugin.
(Volatility3 needs to have access to [matching symbols](https://volatility3.readthedocs.io/en/latest/symbol-tables.html) for the kernel in the snapshot)
```bash
cd path/to/nosyms
vol -p volatility_plugins/ -f data/dump -r csv pslist_with_pgds.PsListWithPGDs > data/dump_pgds.csv
```

Note: You need a profile matching the linux kernel running in the snapshot.

#### Extract known paging structures (Get the ground truth)

Pass `--kpti` or `--no-kpti` according to whether the snapshot comes from a kernel with page table isolation.

```bash
cd path/to/nosyms/paging_detection
python3 extract_known_paging_structures.py --kpti ../data/dump ../data/dump_pgds.csv
```

Produces:

```
../data/dump_known_pages.json
../data/dump_known_pages.graphml
```

#### Extract graph considering all pages "potential paging structures".

```bash
cd path/to/nosyms/paging_detection
python3 extract_all_pages.py ../data/dump
```

Produces:

```
../data/dump_all_pages.json
../data/dump_all_pages.graphml
```

#### Determine possible types for all pages (Prediction)

Point the script to the "all_pages" `.json` or `.graphml`, it will figure out the path of the other one automatically.

```bash
cd path/to/nosyms/paging_detection
python3 determine_types.py ../data/dump_all_pages.json
```

Produces:

```
../data/dump_all_pages_with_types.json
../data/dump_all_pages_with_types.graphml
```

#### (Optionally) apply additional filters (linux specific)

Point the script to the "all_pages_with_types" `.json` or `.graphml`, it will figure out the path of the other one
automatically.

```bash
cd path/to/nosyms/paging_detection
python3 filters.py ../data/dump_all_pages_with_types.json
```

Produces:

```
../data/dump_all_pages_with_types_filtered.json
```

#### Compare results

Point it to the "prediction" and "ground truth" `.json`. It prints a table with accuracy stats.

```bash
cd path/to/nosyms/paging_detection
python3 analze_type_prediction.py ../data/dump_all_pages_with_types.json ../data/dump_known_pages.json
```
