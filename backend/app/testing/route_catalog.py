from __future__ import annotations

import argparse
import inspect
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from fastapi.routing import APIRoute

READ_METHODS = {"GET", "HEAD", "OPTIONS"}
IGNORED_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def classify_surface(path: str) -> str:
    if path.startswith("/api/testing/"):
        return "testing"
    if path.startswith("/api/admin/"):
        return "admin"
    if path.startswith("/api/dev/"):
        return "dev"
    return "production"


def classify_access(method: str) -> str:
    return "read" if method.upper() in READ_METHODS else "mutation"


def endpoint_source(endpoint: Any) -> tuple[str, str, str | None]:
    module = str(getattr(endpoint, "__module__", "") or "")
    name = str(getattr(endpoint, "__qualname__", None) or getattr(endpoint, "__name__", "") or "")
    source_file = inspect.getsourcefile(endpoint) or inspect.getfile(endpoint)
    normalized_source = str(Path(source_file).resolve()) if source_file else None
    return module, name, normalized_source


def route_signature(routes: Iterable[Any]) -> tuple[tuple[str, str, str], ...]:
    signature: list[tuple[str, str, str]] = []
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        endpoint = getattr(route, "endpoint", None)
        endpoint_name = str(getattr(endpoint, "__qualname__", None) or getattr(endpoint, "__name__", "") or "")
        for method in sorted(route.methods or []):
            signature.append((method.upper(), str(route.path), endpoint_name))
    return tuple(sorted(signature))


def wait_for_stable_routes(app: Any, *, timeout_seconds: float = 20.0, stable_polls: int = 5, interval_seconds: float = 0.25) -> None:
    deadline = time.monotonic() + timeout_seconds
    previous: tuple[tuple[str, str, str], ...] | None = None
    unchanged = 0
    while time.monotonic() < deadline:
        current = route_signature(app.routes)
        if current == previous and current:
            unchanged += 1
            if unchanged >= stable_polls:
                return
        else:
            previous = current
            unchanged = 0
        time.sleep(interval_seconds)
    raise RuntimeError("FastAPI-routeset werd niet tijdig stabiel")


def build_catalog(app: Any) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for route_index, route in enumerate(app.routes):
        if not isinstance(route, APIRoute):
            continue
        path = str(route.path)
        if path in IGNORED_PATHS:
            continue
        endpoint = getattr(route, "endpoint", None)
        module, endpoint_name, source_file = endpoint_source(endpoint)
        for method in sorted(route.methods or []):
            normalized_method = method.upper()
            entries.append(
                {
                    "method": normalized_method,
                    "path": path,
                    "endpoint": endpoint_name,
                    "module": module,
                    "source_file": source_file,
                    "surface": classify_surface(path),
                    "access": classify_access(normalized_method),
                    "route_index": route_index,
                    "name": str(getattr(route, "name", "") or ""),
                }
            )

    entries.sort(key=lambda item: (item["path"], item["method"], item["module"], item["endpoint"], item["route_index"]))

    method_path_routes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        method_path_routes[(entry["method"], entry["path"])].append(entry)

    duplicates = [
        {
            "method": method,
            "path": path,
            "registrations": [
                {
                    "module": item["module"],
                    "endpoint": item["endpoint"],
                    "route_index": item["route_index"],
                }
                for item in registrations
            ],
        }
        for (method, path), registrations in sorted(method_path_routes.items())
        if len(registrations) > 1
    ]

    summary = {
        "route_registrations": len(entries),
        "unique_method_paths": len(method_path_routes),
        "duplicates": len(duplicates),
        "by_surface": dict(sorted(Counter(item["surface"] for item in entries).items())),
        "by_access": dict(sorted(Counter(item["access"] for item in entries).items())),
        "mutation_by_surface": dict(
            sorted(Counter(item["surface"] for item in entries if item["access"] == "mutation").items())
        ),
    }
    return {"summary": summary, "duplicates": duplicates, "routes": entries}


def markdown_table(catalog: dict[str, Any]) -> str:
    summary = catalog["summary"]
    lines = [
        "# M2C2n FastAPI-routecatalogus",
        "",
        "> Gegenereerd uit de werkelijk geregistreerde `app.routes`; dit bestand niet handmatig onderhouden.",
        "",
        "## Samenvatting",
        "",
        f"- Routeregistraties: **{summary['route_registrations']}**",
        f"- Unieke methode-padcombinaties: **{summary['unique_method_paths']}**",
        f"- Dubbele methode-padregistraties: **{summary['duplicates']}**",
        f"- Leesregistraties: **{summary['by_access'].get('read', 0)}**",
        f"- Mutatieregistraties: **{summary['by_access'].get('mutation', 0)}**",
        "",
        "### Registraties per oppervlak",
        "",
    ]
    for surface, count in summary["by_surface"].items():
        mutation_count = summary["mutation_by_surface"].get(surface, 0)
        lines.append(f"- `{surface}`: **{count}** totaal, **{mutation_count}** muterend")

    lines.extend(["", "## Routes", "", "| Methode | Pad | Soort | Oppervlak | Endpoint | Module |", "|---|---|---|---|---|---|"])
    for item in catalog["routes"]:
        values = [
            item["method"],
            f"`{item['path']}`",
            item["access"],
            item["surface"],
            f"`{item['endpoint']}`",
            f"`{item['module']}`",
        ]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")

    lines.extend(["", "## Dubbele methode-padregistraties", ""])
    if not catalog["duplicates"]:
        lines.append("Geen dubbele methode-padregistraties gevonden.")
    else:
        for duplicate in catalog["duplicates"]:
            lines.append(f"### `{duplicate['method']} {duplicate['path']}`")
            lines.append("")
            for registration in duplicate["registrations"]:
                lines.append(
                    f"- `{registration['module']}.{registration['endpoint']}` (route-index {registration['route_index']})"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_catalog(output_dir: Path, catalog: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "M2C2N-ROUTE-CATALOG.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "M2C2N-ROUTE-CATALOG.md").write_text(markdown_table(catalog), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genereer de M2C2n FastAPI-routecatalogus")
    parser.add_argument("--output-dir", default="/tmp/m2c2n-route-catalog")
    parser.add_argument("--fail-on-duplicates", action="store_true")
    args = parser.parse_args()

    from app.main import app

    wait_for_stable_routes(app)
    catalog = build_catalog(app)
    write_catalog(Path(args.output_dir), catalog)

    summary = catalog["summary"]
    print(
        "M2C2N_ROUTE_CATALOG_GREEN "
        f"registrations={summary['route_registrations']} "
        f"unique_method_paths={summary['unique_method_paths']} "
        f"duplicates={summary['duplicates']} "
        f"mutations={summary['by_access'].get('mutation', 0)}"
    )
    if args.fail_on_duplicates and catalog["duplicates"]:
        raise SystemExit("Dubbele methode-padregistraties gevonden")


if __name__ == "__main__":
    main()
