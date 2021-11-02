# About
This is some experimental code to try and see whether x86 64bit long mode paging structures can be detected in raw memory.
The primary use-case would be analyzing memory snapshots for which the running kernel version is not known.
The core parts of the code are geared towards x86 but should be quite easy to adapt for similar architectures.
So far the entire approach was only evaluated for linux kernels, some heuristics are also linux specific, but should
hold across different version of linux.

# General Notes:
- Paging structures as well as paging entries are handled with dataclasses. (`nopgd.paging_detection.Snapshot`) 
  - They can be conveniently be (de)serialized to/from json.
  - In most cases these dataclasses are currently being swapped out for classes reading paging entries from the mmaped memory snapshot file "on demand". (`paging_detection.mmaped.MemMappedSnapshot`), the designations of pages are then stored in a `nopgd.paging_detection.mmaped.LightSnapshot`.
  - There is a tool for converting `Snapshot` json to `LightSnapshot` json in `./dev_utils`.
- Networkx is used to analyze the topology of the paging structures, graphs are stored as `.graphml`.
  - There are tools for viewing / analyzing `.graphml` files such as Gephi or Graphia.

# Data flow:
All of the python scripts use argparse. You can invoke them with `--help`.

### Get PML4 (PGD) addresses from your snapshot
Use the [`pslist_with_pgds.PsListWithPGDs`](volatility_plugins/pslist_with_pgds.py) Volatility3 plugin.
```bash
cd path/to/nosyms
vol -p volatility_plugins/ -f data/dump -r csv pslist_with_pgds.PsListWithPGDs > data/dump_pgds.csv
```
Note: You need a profile matching the linux kernel running in the snapshot.

### Extract known paging structures (Get the ground truth)
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

### Extract paging information for all pages 
```bash
cd path/to/nosyms/paging_detection
python3 extract_all_pages.py ../data/dump
```
Produces:
```
../data/dump_all_pages.json
../data/dump_all_pages.graphml
```

### Determine possible types for all pages (Prediction)
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
### (Optinally) apply additional filters
Point the script to the "all_pages_with_types" `.json` or `.graphml`, it will figure out the path of the other one automatically.
```bash
cd path/to/nosyms/paging_detection
python3 filters.py ../data/dump_all_pages_with_types.json
```
Produces:
```
../data/dump_all_pages_with_types_filtered.json
```

### Compare results
Point it to the "prediction" and "ground truth" `.json`.
It prints a table with accuracy stats.
```bash
cd path/to/nosyms/paging_detection
python3 analze_type_prediction.py ../data/dump_all_pages_with_types.json ../data/dump_known_pages.json
```