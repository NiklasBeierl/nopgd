from collections import defaultdict, Counter
from typing import Dict, List, DefaultDict, Tuple

import pandas as pd
import networkx as nx

from paging_detection import PagingStructure, PageTypes, PAGING_STRUCTURE_SIZE
from paging_detection.mmaped import SnapshotPagingData, MemMappedSnapshot
from paging_detection.graphs import color_graph, add_task_info


def read_paging_structures(dump_path: str, pgds: List[int]) -> MemMappedSnapshot:
    """
    Extract PagingStructure from memory. Consider every int in pgds to be an address of a PML4.
    :param mem: Memory
    :param pgds: List of physical pml4 addresses in mem
    :return: Dict mapping page address to instance of PagingStructure describing the underlying page
    """
    designations = {}
    snapshot = MemMappedSnapshot(SnapshotPagingData(path=dump_path, designations=designations))

    print("Extracting known paging structures.")
    last_progress = 0
    for i, pml4_addr in enumerate(sorted(pgds)):
        if (progress := 100 * i // len(pgds)) != last_progress and (progress % 5 == 0):
            print(f"{progress}%")
            last_progress = progress

        addresses = {pml4_addr}
        for page_type in PageTypes:
            next_addresses = set()  # Holds addresses of tables of the "next" table type by the end onf the iteration
            for addr in addresses:
                if not addr in snapshot.designations:
                    snapshot.designations[addr] = set()
                table = snapshot.pages[addr]
                if not page_type in table.designations:  # Did not consider this table as page_type yet
                    table.designations.add(page_type)
                    next_addresses |= {
                        entry.target
                        for entry in table.entries.values()
                        # PDEs and PDPEs can point to large pages, we do not want to confuse those for paging structures
                        if not entry.target_is_data(page_type) and entry.target < snapshot.size
                    }
            addresses = next_addresses

    return snapshot


def get_mapped_pages(pages: Dict[int, PagingStructure]) -> DefaultDict[int, bool]:
    """
    Determine which of the pages are mapped into any virtual address space.
    """
    is_mapped = defaultdict(lambda: False)
    for page in pages.values():
        for entry in page.entries.values():
            for designation in page.designations:
                if entry.target_is_data(designation):
                    is_mapped[entry.target] = True
    return is_mapped


def build_nx_graph(
    pages: Dict[int, PagingStructure], mem_size: int, data_page_nodes: bool = False
) -> Tuple[nx.MultiDiGraph, List[Tuple]]:
    """
    Build a networkx graph representing the paging structures in a snapshot.
    :param pages: Dict mapping physical address to paging structure.
    :param mem_size: Size of the memory snapshot, pages "outside" the physical memory will be ignored.
    :param data_page_nodes: Whether to add nodes for data pages, if False, last-level structures have an additional
    property "data_pages", indicating how many data pages they point to
    :return: The built graph and a list of out of bounds entries.
    """
    graph = nx.MultiDiGraph()
    out_of_bound_entries = []

    # Empty PML4s are not added during the loop below because they have neither in- nor outbound edges.
    graph.add_nodes_from(pages.keys())
    for offset, page in pages.items():
        graph.nodes[offset].update({t: (t in page.designations) for t in PageTypes})

    for page_offset, page in pages.items():
        for designation in page.designations:
            for entry_offset, entry in page.entries.items():
                if entry.target == 0:
                    continue
                if entry.target < mem_size:
                    if data_page_nodes or not entry.target_is_data(designation):
                        graph.add_edge(page_offset, entry.target, page_offset + entry_offset, offset=entry_offset)
                    else:
                        node = graph.nodes[page_offset]
                        node["data_pages"] = node.get("data_pages", 0) + 1
                # If the target is a data page, it may lie outside the snapshot (IOMem). Otherwise its an out-of-bounds
                # entry. In any case, it is not added as a node.
                elif not entry.target_is_data(designation):
                    out_of_bound_entries.append(
                        (str(designation), hex(page_offset), hex(entry_offset), hex(entry.target), hex(entry.value))
                    )

    return graph, out_of_bound_entries


def get_node_features(graph: nx.MultiDiGraph) -> pd.DataFrame:
    """
    Create a pandas dataframe with some useful stats for every node in a paging structures graph.
    """
    df = pd.DataFrame(data=[graph.nodes[node] for node in graph.nodes], index=graph.nodes)
    r_graph = graph.reverse()
    df["longest_inbound_path"] = [len(nx.dfs_successors(r_graph, source=node)) for node in r_graph.nodes]
    idx, deg = tuple(zip(*graph.in_degree))
    df["in_degree"] = pd.Series(data=deg, index=idx)
    idx, deg = tuple(zip(*graph.out_degree))
    # Note: Out degree will be 0 for pages in "training" data and 1 in "target" data
    df["out_degree"] = pd.Series(data=deg, index=idx)
    return df


dump_path = "../data_dump/nokaslr.raw"

if __name__ == "__main__":
    import argparse
    import pathlib

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dump_path",
        help="Path to snapshot. Output files will have the same name with _known_pages.[json|graphml] appended.",
        type=pathlib.Path,
    )
    parser.add_argument(
        "task_info",
        help="Path to .csv containing task info. Use the pslist_with_pgds.PsListWithPGDs Vol3 plugin.",
        type=pathlib.Path,
    )
    parser.add_argument(
        "--kpti", help="Whether the snapshot is from a kernel with KPTI enabled.", action=argparse.BooleanOptionalAction
    )

    args = parser.parse_args()
    dump_path = args.dump_path
    task_info_path = args.task_info

    out_pages = dump_path.with_stem(dump_path.stem + "_known_pages").with_suffix(".json")
    out_graph = out_pages.with_suffix(".graphml")
    out_oob_entries = dump_path.with_stem(dump_path.stem + "_out_of_bounds").with_suffix(".csv")

    task_info = pd.read_csv(task_info_path)

    phy_pgds = []
    if args.kpti:
        for kernel, user in task_info[["phy_pgd_kernel", "phy_pgd_user"]].itertuples(index=False):
            phy_pgds.extend([kernel, user])
    else:
        phy_pgds.extend(task_info["phy_pgd"])

    snapshot = read_paging_structures(str(dump_path), phy_pgds)

    print(f"Saving pages: {out_pages}")
    with open(out_pages, "w") as f:
        f.write(snapshot.snapshot.json())

    print("Building nx graph.")
    graph, out_of_bounds = build_nx_graph(snapshot.pages, snapshot.size)

    if out_of_bounds:
        print(f"There are {len(out_of_bounds)} out of bounds entries. Saving to csv: {out_oob_entries}")
        oob_df = pd.DataFrame(
            out_of_bounds,
            columns=[
                "page type",
                "page physical offset",
                "entry offset within page",
                "entry target page",
                "entry value",
            ],
        )
        oob_df.to_csv(out_oob_entries, index=False)

    print("Adding task info to PML4s in graph.")

    graph_cols = ["phy_pgd_kernel", "phy_pgd_user", "COMM"] if args.kpti else ["phy_pgd", "COMM"]
    graph = add_task_info(graph, task_info[graph_cols].itertuples(index=False))
    print("Adding colors to graph.")
    graph = color_graph(graph, snapshot.pages)

    print(f"Saving graph: {out_graph}")
    nx.readwrite.write_graphml(graph, out_graph)

    # Below is some exploratory code, you will need a debugger / add prints to access these values.

    node_data = get_node_features(graph)
    is_mapped = get_mapped_pages(snapshot.pages)
    total_mapped = sum(mapped and addr < snapshot.size for addr, mapped in is_mapped.items())
    # Approximate b.c. of large pages
    app_mapped_mem_perc = total_mapped / (snapshot.size / PAGING_STRUCTURE_SIZE)

    types_summary = Counter((is_mapped[addr], *page.designations) for addr, page in snapshot.pages.items())
    ambiguous_pages = sum(occ for desigs, occ in types_summary.items() if len(desigs) > 2)

print("Done.")
