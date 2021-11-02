from typing import Dict

import networkx as nx

from paging_detection import PagingStructure, max_page_addr, PageTypes, PAGING_STRUCTURE_SIZE
from paging_detection.mmaped import LightSnapshot, MemMappedSnapshot


def build_nx_graph(pages: Dict[int, PagingStructure], max_paddr: int) -> nx.MultiDiGraph:
    """
    Build a networkx graph representing pages and their (hypothetical) paging entries in a snapshot.
    :param pages: Dict mapping physical address to pages
    :return: The resulting graph
    """
    graph = nx.MultiDiGraph()
    # Allows nx to avoid mem reallocation for the nodes.
    # Adds "disconnected" pages to avoid key errors.
    graph.add_nodes_from(pages.keys())

    print("Building nx graph.")
    last_prog = 0
    for page_offset, page in pages.items():
        if ((prog := int(100 * page_offset / snap_size)) != last_prog) and (prog % 5) == 0:
            last_prog = prog
            print(f"{prog} % done.")
        for entry_offset, entry in page.entries.items():
            if entry.target <= max_paddr:
                graph.add_edge(page_offset, entry.target, entry_offset)

    return graph


if __name__ == "__main__":
    import argparse
    import pathlib

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "in_file",
        help="Path to snapshot. Output files will have the same name with .json and .graphml as suffix.",
        type=pathlib.Path,
    )
    args = parser.parse_args()
    dump_path = args.in_file
    if dump_path.suffix in {".json", ".graphml"}:
        raise ValueError(f"Snapshot has {dump_path.suffix} as extension and would be overwritten by outputs.")
    out_pages_path = dump_path.with_stem(dump_path.stem + "_all_pages").with_suffix(".json")
    out_graph_path = out_pages_path.with_suffix(".graphml")

    snap_size = dump_path.stat().st_size

    # snapshot.pages.items() only iterates over pages for which designations are stored.
    dummy_desigs = {offset: set() for offset in range(0, snap_size, PAGING_STRUCTURE_SIZE)}
    snapshot = MemMappedSnapshot(LightSnapshot(path=str(dump_path), designations=dummy_desigs))

    pages = snapshot.pages
    max_paddr = max_page_addr(snap_size)

    full_graph = build_nx_graph(pages, max_paddr=max_paddr)

    last_prog = 0
    print("Counting oob entries and invalid entries.")
    for page_offset, page in pages.items():
        if ((prog := int(100 * page_offset / snap_size)) != last_prog) and (prog % 5) == 0:
            last_prog = prog
            print(f"{prog} % done.")
        node = full_graph.nodes[page_offset]

        for page_type in PageTypes:
            # oob entries point to a paging structure outside of the memories bounds.
            # Note that a entries pointing to a data page (bit7 set or PT entry) are never "out of bounds"
            node[f"invalid_{page_type}"] = 0
            # Invalid entries violate constraints.
            # E.g. a PD entry with bit7 set pointing to an address which is not 2mb aligned.
            node[f"oob_{page_type}"] = 0

        for entry in page.entries.values():
            for page_type in PageTypes:
                if not entry.is_valid(page_type):
                    node[f"invalid_{page_type}"] += 1
                if entry.target > max_paddr and not entry.target_is_data(page_type):
                    node[f"oob_{page_type}"] += 1

    print(f"Saving graph: {out_graph_path}")
    nx.readwrite.write_graphml(full_graph, out_graph_path)

    print(f"Saving pages: {out_pages_path}")
    with open(out_pages_path, "w") as f:
        f.write(snapshot.json())

    print("Done")
