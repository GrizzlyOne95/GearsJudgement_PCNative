"""Redirect UE3 imports without embedding or redistributing package content.

The package-probe manifest records each fixed-size FObjectImport entry.  This
tool replaces one import record with an already-existing compatible import
record from the same package.  It never changes table sizes, export payloads,
or source files, and it refuses to overwrite its output.

Use this only when the replacement object has the same native type and the
redirect is appropriate for the diagnostic being performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable


IMPORT_RECORD = struct.Struct("<iiiiiii")


class RedirectError(ValueError):
    """Raised when a manifest, package, or replacement is unsafe to use."""


def _load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("byte_order") != "little":
        raise RedirectError("only little-endian packages are supported")
    if not isinstance(manifest.get("names"), list):
        raise RedirectError("manifest has no name table")
    if not isinstance(manifest.get("imports"), list) or not manifest["imports"]:
        raise RedirectError("manifest has no import table")
    return manifest


def _import_bounds(manifest: dict, package_size: int) -> tuple[int, int]:
    validation = manifest.get("layout_validation") or {}
    imports_end = validation.get("imports_end")
    expected_end = validation.get("expected_imports_end")
    if not isinstance(imports_end, int) or imports_end != expected_end:
        raise RedirectError("manifest import layout is not exact")
    imports_start = imports_end - len(manifest["imports"]) * IMPORT_RECORD.size
    if imports_start < 0 or imports_end > package_size:
        raise RedirectError("manifest import table is outside the package")
    return imports_start, imports_end


def _record_at(blob: bytes | bytearray, imports_start: int, index: int) -> bytes:
    offset = imports_start + index * IMPORT_RECORD.size
    return bytes(blob[offset : offset + IMPORT_RECORD.size])


def _validate_record(
    blob: bytes | bytearray, manifest: dict, imports_start: int, entry: dict
) -> bytes:
    index = entry.get("index")
    if not isinstance(index, int) or not 0 <= index < len(manifest["imports"]):
        raise RedirectError(f"invalid manifest import index: {index!r}")
    record = _record_at(blob, imports_start, index)
    if len(record) != IMPORT_RECORD.size:
        raise RedirectError(f"truncated import record at index {index}")
    (
        class_package_index,
        class_package_number,
        class_name_index,
        class_name_number,
        outer_index,
        object_name_index,
        object_name_number,
    ) = IMPORT_RECORD.unpack(record)
    names = manifest["names"]
    for name_index in (class_package_index, class_name_index, object_name_index):
        if not 0 <= name_index < len(names):
            raise RedirectError(f"import {index} has invalid name index {name_index}")
    if class_package_number or class_name_number or object_name_number:
        raise RedirectError(f"numbered FNames are not supported at import {index}")
    decoded = (
        names[class_package_index]["name"],
        names[class_name_index]["name"],
        outer_index,
        names[object_name_index]["name"],
    )
    expected = (
        entry.get("class_package"),
        entry.get("class_name"),
        entry.get("outer_index"),
        entry.get("object_name"),
    )
    if decoded != expected:
        raise RedirectError(
            f"package does not match manifest at import {index}: "
            f"decoded={decoded!r} expected={expected!r}"
        )
    return record


def _path_map(manifest: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for entry in manifest["imports"]:
        path = entry.get("object_path")
        if not isinstance(path, str) or not path:
            raise RedirectError(f"import {entry.get('index')} has no object path")
        if path in result:
            raise RedirectError(f"duplicate import object path: {path}")
        result[path] = entry
    return result


def redirect_imports(
    manifest_path: Path,
    package_path: Path,
    output_path: Path,
    replacements: Iterable[tuple[str, str]],
) -> list[tuple[int, str, int, str]]:
    """Apply import redirects and return their index/path report."""

    manifest = _load_manifest(manifest_path)
    blob = bytearray(package_path.read_bytes())
    imports_start, _ = _import_bounds(manifest, len(blob))
    by_path = _path_map(manifest)
    original = bytes(blob)
    report: list[tuple[int, str, int, str]] = []
    seen_sources: set[str] = set()

    for source_path, target_path in replacements:
        if source_path in seen_sources:
            raise RedirectError(f"duplicate replacement source: {source_path}")
        seen_sources.add(source_path)
        if source_path == target_path:
            raise RedirectError(f"source and target are identical: {source_path}")
        try:
            source = by_path[source_path]
        except KeyError as exc:
            raise RedirectError(f"source import was not found: {source_path}") from exc
        try:
            target = by_path[target_path]
        except KeyError as exc:
            raise RedirectError(f"target import was not found: {target_path}") from exc

        source_type = (source.get("class_package"), source.get("class_name"))
        target_type = (target.get("class_package"), target.get("class_name"))
        if source_type != target_type:
            raise RedirectError(
                f"incompatible import classes for {source_path}: "
                f"{source_type!r} != {target_type!r}"
            )

        _validate_record(original, manifest, imports_start, source)
        target_record = _validate_record(original, manifest, imports_start, target)
        source_index = source["index"]
        target_index = target["index"]
        source_offset = imports_start + source_index * IMPORT_RECORD.size
        blob[source_offset : source_offset + IMPORT_RECORD.size] = target_record
        report.append((source_index, source_path, target_index, target_path))

    if not report:
        raise RedirectError("at least one --replace mapping is required")
    if output_path.exists():
        raise RedirectError(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        raise RedirectError(f"output directory does not exist: {output_path.parent}")

    with output_path.open("xb") as handle:
        handle.write(blob)
    return report


def _replacement(value: str) -> tuple[str, str]:
    source, separator, target = value.partition("=")
    if not separator or not source or not target:
        raise argparse.ArgumentTypeError("expected FROM_OBJECT_PATH=TO_OBJECT_PATH")
    return source, target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Redirect fixed-size UE3 imports to compatible imports already in a package."
    )
    parser.add_argument("manifest", type=Path, help="package-probe manifest for the input")
    parser.add_argument("package", type=Path, help="little-endian input package")
    parser.add_argument("output", type=Path, help="new package path (must not exist)")
    parser.add_argument(
        "--replace",
        action="append",
        type=_replacement,
        default=[],
        metavar="FROM=TO",
        help="replace one import record; may be specified more than once",
    )
    args = parser.parse_args()
    try:
        report = redirect_imports(args.manifest, args.package, args.output, args.replace)
    except (OSError, RedirectError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    for source_index, source_path, target_index, target_path in report:
        print(f"import {source_index}: {source_path} -> import {target_index}: {target_path}")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest().upper()
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes, SHA-256 {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
