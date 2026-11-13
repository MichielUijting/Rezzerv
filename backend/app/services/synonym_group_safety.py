"""Pre-write guard for affected transitive central Catalogus synonym groups.

Only explicitly confirmed existing links and proposed NEW links are considered.
No household, receipt, or inventory reads/writes; no automatic merging.
"""
from collections import defaultdict
from itertools import combinations

from app.services.synonym_equivalence_review import proven_semantic_conflicts

MAX_GROUP_PRODUCTS = 200


def prospective_group_conflict(products, confirmed_links, new_links, pair_conflict):
    """Find a contradiction anywhere in the resulting affected connected group."""
    additions = {tuple(sorted(pair)) for pair in new_links}
    if not additions:
        return None
    graph = defaultdict(set)
    for first, second in set(confirmed_links) | additions:
        if first == second:
            return {"type": "same_article", "left_id": first, "right_id": second,
                    "detail": "Een artikel kan geen eigen synoniem zijn."}
        graph[first].add(second)
        graph[second].add(first)
    touched = {value for pair in additions for value in pair}
    visited = set()
    for root in sorted(touched):
        if root in visited:
            continue
        component = set()
        pending = [root]
        while pending:
            node = pending.pop()
            if node in component:
                continue
            component.add(node)
            pending.extend(sorted(graph[node] - component))
        visited.update(component)
        if len(component) > MAX_GROUP_PRODUCTS:
            return {"type": "group_limit", "left_id": root, "right_id": root,
                    "detail": "De synoniemgroep is te groot voor een veilige controle."}
        missing = sorted(component - products.keys())
        if missing:
            return {"type": "missing_article", "left_id": missing[0], "right_id": missing[0],
                    "detail": "Een artikel in de synoniemgroep is niet meer actief of geïdentificeerd."}
        for left_id, right_id in combinations(sorted(component), 2):
            left, right = products[left_id], products[right_id]
            identity_conflict = pair_conflict(left, right)
            if identity_conflict:
                return {"type": "transitive_" + identity_conflict["type"],
                        "left_id": left_id, "right_id": right_id,
                        "detail": identity_conflict["detail"]}
            semantic_conflicts = proven_semantic_conflicts(left, right)
            if semantic_conflicts:
                return {"type": "transitive_semantic_conflict",
                        "left_id": left_id, "right_id": right_id,
                        "detail": "; ".join(semantic_conflicts)}
    return None
