"""Replay van reeds aangeleverd lokaal proef-4 rapport, zonder DB of netwerk.

Alleen voor ontwikkelvalidatie: geen persoonsgegevens of artikelexports naar Git.
"""

import collections
import sys
from pathlib import Path

from tools.inhuis_taxonomy_proof5_core import Matcher, load_references


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Gebruik: python -m tools.inhuis_taxonomy_proof5_replay PAD_PROEF4_RAPPORT")
    matcher = Matcher(*load_references())
    counts = collections.defaultdict(collections.Counter)
    sampled = collections.defaultdict(list)
    seen = set()
    for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith(("Catalogus | ", "Bonartikelen ED2 | ")):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 11:
            continue
        source, name, retailer = parts[:3]
        signature = (source, name, retailer, parts[3])
        # Identieke regels kunnen op verschillende bonnen voorkomen;
        # dit rapport bewaart de rijen precies zoals geprint.
        if signature in seen:
            pass
        seen.add(signature)
        result = matcher.match(name, retailer)
        counts[source][result["status"]] += 1
        if len(sampled[(source, result["status"])]) < 9:
            sampled[(source, result["status"])].append(
                (name, [category["pad"] for category in result["shopify"]][:2],
                 result["cbs_vergelijking"]))
    for source, counter in counts.items():
        print(source, "aantal", sum(counter.values()), dict(counter))
    print("KWALITEITSVOORBEELDEN (NIET OPGESLAGEN):")
    for (source, status), records in sorted(sampled.items()):
        print(source, status)
        for item in records:
            print("  ", item)


if __name__ == "__main__":
    main()
