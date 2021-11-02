import json

from paging_detection import Snapshot
from paging_detection.mmaped import LightSnapshot


if __name__ == "__main__":
    import argparse
    import pathlib

    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to full snapshot json.", type=pathlib.Path)
    parser.add_argument("output", help="Output path.", type=pathlib.Path)
    args = parser.parse_args()

    with open(args.input) as f:
        input = Snapshot.validate(json.load(f))

    output = LightSnapshot.from_full_snapshot(input)

    with open(args.output, "w") as f:
        f.write(output.json())
