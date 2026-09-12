#!/usr/bin/env python3
"""excli — Excalidraw library manager CLI."""

import argparse
import datetime
import json
import math
import os
import re
import sys
import time
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_USER = os.environ.get("USER", os.environ.get("LOGNAME", "user"))

DEFAULT_SETTINGS_PATH = Path(
    f"/Users/{_USER}/Library/Application Support/Code/User/settings.json"
)
DEFAULT_CONFIG_PATH = Path(f"/Users/{_USER}/.excli/config.json")
SEED_SETTINGS_PATH = Path("/Users/davek/Code/personio/.vscode/settings.json")

SETTINGS_KEY = "excalidraw.workspaceLibraryPath"
VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9._/ -]+$")
SETTINGS_RE = re.compile(r'("excalidraw\.workspaceLibraryPath"\s*:\s*)"[^"]*"')

# ---------------------------------------------------------------------------
# Debug / trace
# ---------------------------------------------------------------------------

_debug_enabled = False
_t0 = time.monotonic()


def _debug(msg: str) -> None:
    if not _debug_enabled:
        return
    elapsed = time.monotonic() - _t0
    frame = sys._getframe(1)
    loc = f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno} {frame.f_code.co_name}()"
    print(f"[debug +{elapsed:.3f}s] {loc} | {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Low-level utilities
# ---------------------------------------------------------------------------


def die(msg: str, code: int = 1) -> None:
    _debug(f"die() called with code={code}: {msg}")
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Config file
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> dict:
    """Load config.json, creating and seeding it if absent."""
    _debug(f"config path: {config_path}")
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            _debug(f"loaded config: {cfg}")
            return cfg
        except (json.JSONDecodeError, PermissionError) as e:
            _debug(f"config read error: {e}")
            print(f"Warning: could not read {config_path}: {e}", file=sys.stderr)
            return {}

    # First run — create the config directory and seed it
    _debug(f"config not found; seeding from {SEED_SETTINGS_PATH}")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    seed_value = str(SEED_SETTINGS_PATH) if SEED_SETTINGS_PATH.exists() else str(DEFAULT_SETTINGS_PATH)
    cfg: dict = {"settings_path": seed_value}
    try:
        config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print(f"[excli] Created config file: {config_path}", file=sys.stderr)
        print(f"[excli]   settings_path = {seed_value}", file=sys.stderr)
    except Exception as e:
        _debug(f"could not write config: {e}")
        print(f"Warning: could not write {config_path}: {e}", file=sys.stderr)
    return cfg


def effective_settings_path(args, cfg: dict) -> Path:
    """Resolve the settings.json path: CLI flag > config file > built-in default."""
    if getattr(args, "settings", None):
        p = Path(args.settings).resolve()
        _debug(f"settings path from --settings flag: {p}")
        return p
    if "settings_path" in cfg:
        p = Path(cfg["settings_path"]).expanduser().resolve()
        _debug(f"settings path from config file: {p}")
        return p
    _debug(f"settings path from built-in default: {DEFAULT_SETTINGS_PATH}")
    return DEFAULT_SETTINGS_PATH


def strip_path_part(path: Path, part: str) -> Path:
    """Return path reconstructed without the first matching part component."""
    parts = path.parts
    try:
        idx = parts.index(part)
    except ValueError:
        return path
    return Path(*parts[:idx], *parts[idx + 1:])


def atomic_write(path: Path, content: str) -> None:
    tmp = Path(str(path) + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def validate_name(name: str) -> str:
    """Strip .excalidrawlib suffix, validate chars, reject path traversal."""
    base = name.removesuffix(".excalidrawlib") if name.endswith(".excalidrawlib") else name
    if not base:
        die("library name cannot be empty")
    if ".." in base.split("/"):
        die("library name must not contain path traversal (..)")
    if not VALID_NAME_RE.match(base):
        die(
            f"library name contains invalid characters: {base!r}\n"
            "Allowed: a-z A-Z 0-9 . _ / - (space)"
        )
    return base + ".excalidrawlib"


# ---------------------------------------------------------------------------
# Settings.json helpers (JSONC-safe: raw string operations only)
# ---------------------------------------------------------------------------


def read_settings_raw(settings_path: Path) -> str:
    _debug(f"reading settings: {settings_path}")
    if not settings_path.exists():
        die(f"settings file not found: {settings_path}")
    try:
        content = settings_path.read_text(encoding="utf-8")
        _debug(f"settings read ok ({len(content)} bytes)")
        return content
    except PermissionError:
        die(f"permission denied reading settings file: {settings_path}")


def get_library_path_from_settings(settings_path: Path, auto_add: bool = True) -> Path:
    _debug(f"get_library_path_from_settings({settings_path}, auto_add={auto_add})")
    content = read_settings_raw(settings_path)
    m = SETTINGS_RE.search(content)
    if not m:
        if not auto_add:
            die(
                f"key '{SETTINGS_KEY}' not found in settings.json.\n"
                "Run 'excli add-library <name>' first, or use --library <path>."
            )
        # Insert the key with an empty value before the closing brace
        new_content = content.rstrip()
        if new_content.endswith("}"):
            insert = f',\n    "{SETTINGS_KEY}": ""\n}}'
            new_content = new_content[:-1].rstrip().rstrip(",") + insert
        else:
            die(f"settings.json does not end with '}}'; cannot auto-add {SETTINGS_KEY}")
        atomic_write(settings_path, new_content)
        return get_library_path_from_settings(settings_path, auto_add=False)
    value_match = re.search(r'"excalidraw\.workspaceLibraryPath"\s*:\s*"([^"]*)"', content)
    library_value = Path(value_match.group(1))
    _debug(f"raw library value from settings: {library_value!r}")
    library_path = lib_path_fix(settings_path, library_value)
    _debug(f"resolved library path: {library_path}")
    return library_path


def set_library_in_settings(settings_path: Path, new_value: str) -> None:
    get_library_path_from_settings(settings_path)
    content = read_settings_raw(settings_path)
    new_content, count = SETTINGS_RE.subn(r'\g<1>"' + new_value + '"', content)
    if count == 0:
        die(
            f"key '{SETTINGS_KEY}' not found in {settings_path}.\n"
            "Please add the key manually first, then use excli to manage it."
        )
    atomic_write(settings_path, new_content)
    print(f"Updated settings.json: at '{settings_path}'\n\n{' '*8}{SETTINGS_KEY:<44s} -> \"{new_value}\"")


# ---------------------------------------------------------------------------
# Library file helpers
# ---------------------------------------------------------------------------


def load_library(library_path: Path) -> dict:
    _debug(f"loading library: {library_path} (exists={library_path.exists()})")
    if not library_path.exists():
        die(f"library file not found: {library_path}")
    try:
        with library_path.open(encoding="utf-8") as f:
            data = json.load(f)
        _debug(f"library loaded: {len(data.get('libraryItems', []))} items")
    except json.JSONDecodeError as e:
        die(f"invalid JSON in library file {library_path}: {e}")
    except PermissionError:
        die(f"permission denied reading library file: {library_path}")
    if "libraryItems" not in data or not isinstance(data["libraryItems"], list):
        die(
            f"library file {library_path} is missing a 'libraryItems' array.\n"
            "Expected format: {\"type\": \"excalidrawlib\", ..., \"libraryItems\": [...]}"
        )
    return data


def save_library_file(library_path: Path, data: dict) -> None:
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    atomic_write(library_path, content)


def resolve_library_path(args, settings_path: Path) -> Path:
    if hasattr(args, "library") and args.library:
        p = Path(args.library).resolve()
        _debug(f"library path from --library flag: {p}")
        if not p.exists():
            die(f"library file not found: {p}")
        return p
    _debug("library path from settings.json")
    return get_library_path_from_settings(settings_path)


# ---------------------------------------------------------------------------
# Item spec parsers
# ---------------------------------------------------------------------------


def parse_item_spec(spec: str, max_item: int) -> list[int]:
    """
    Parse a 1-based item spec like "1,3-5,9" into a sorted list of 0-based indices.
    """
    indices = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        range_match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        single_match = re.fullmatch(r"(\d+)", part)
        if range_match:
            lo, hi = int(range_match.group(1)), int(range_match.group(2))
            if lo > hi:
                die(f"invalid range {lo}-{hi}: start must be <= end")
            indices.extend(range(lo, hi + 1))
        elif single_match:
            indices.append(int(single_match.group(1)))
        else:
            die(
                f"invalid item spec token: {part!r}\n"
                "Expected comma-separated 1-based indices or ranges, e.g. '1,3-5,9'"
            )
    out_of_range = [i for i in indices if i < 1 or i > max_item]
    if out_of_range:
        die(
            f"item indices out of range: {out_of_range}\n"
            f"Library has {max_item} items (1-{max_item})"
        )
    # Convert to 0-based, deduplicate, sort
    return sorted(set(i - 1 for i in indices))


def parse_move_spec(spec: str, max_row: int) -> tuple[int, int]:
    """
    Parse a move spec into (from_row, to_row), both 1-based.
    Accepts: "row 3 to row 1", "row 3 to 1", "3 to 1", "3->1"
    """
    s = spec.strip().lower()
    patterns = [
        r"row\s+(\d+)\s+to\s+row\s+(\d+)",
        r"row\s+(\d+)\s+to\s+(\d+)",
        r"(\d+)\s+to\s+(\d+)",
        r"(\d+)\s*->\s*(\d+)",
    ]
    for pat in patterns:
        m = re.fullmatch(pat, s)
        if m:
            from_row, to_row = int(m.group(1)), int(m.group(2))
            if from_row == to_row:
                die(f"source and destination rows are the same ({from_row}); nothing to do")
            for label, val in [("source", from_row), ("destination", to_row)]:
                if val < 1 or val > max_row:
                    die(
                        f"{label} row {val} out of range; "
                        f"library has {max_row} rows (1-{max_row})"
                    )
            return from_row, to_row
    die(
        f"cannot parse move spec: {spec!r}\n"
        "Expected formats: 'row 3 to row 1', '3 to 1', '3->1'"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_add_library(args, settings_path: Path) -> None:
    normalized = validate_name(args.name)
    set_library_in_settings(settings_path, normalized)
    print("\n[info] Library file status (the file may not exist yet — that is OK):")
    cmd_status(args, settings_path)


def cmd_add_field(args, settings_path: Path) -> None:
    get_library_path_from_settings(settings_path)
    lib_path = resolve_library_path(args, settings_path)
    library_path = strip_path_part(lib_path,'.vscode')
   
    data = load_library(library_path)
    items = data["libraryItems"]
    already_present = sum(1 for item in items if args.field_name in item)
    if already_present:
        print(
            f"Warning: field '{args.field_name}' already exists on "
            f"{already_present}/{len(items)} items; it will be overwritten.",
            file=sys.stderr,
        )
    for item in items:
        item[args.field_name] = args.field_value
    save_library_file(library_path, data)
    print(f"Added field '{args.field_name}' = {args.field_value!r} to {len(items)} items in {library_path}")


def cmd_edit_field(args, settings_path: Path) -> None:
    get_library_path_from_settings(settings_path)
    lib_path = resolve_library_path(args, settings_path)
    library_path = strip_path_part(lib_path,'.vscode')
    data = load_library(library_path)
    items = data["libraryItems"]
    modified = 0
    for item in items:
        if args.field_name in item:
            item[args.field_name] = args.field_value
            modified += 1
    if modified == 0:
        print(
            f"Warning: field '{args.field_name}' not found on any library item; no changes made.",
            file=sys.stderr,
        )
        return
    save_library_file(library_path, data)
    print(
        f"Updated field '{args.field_name}' = {args.field_value!r} "
        f"on {modified}/{len(items)} items in {library_path}"
    )


def cmd_rearrange_items(args, settings_path: Path) -> None:
    get_library_path_from_settings(settings_path)
    lib_path = resolve_library_path(args, settings_path)
    library_path = strip_path_part(lib_path,'.vscode')

    data = load_library(library_path)
    items = data["libraryItems"]
    n = len(items)
    if n == 0:
        die("library is empty; nothing to rearrange")
    max_row = math.ceil(n / 4)
    from_row, to_row = parse_move_spec(args.move_spec, max_row)

    from_start = (from_row - 1) * 4
    from_end = min(from_start + 4, n)
    to_start = (to_row - 1) * 4

    moved_items = items[from_start:from_end]
    remaining = items[:from_start] + items[from_end:]

    # Adjust insertion index for the gap left by removing the source slice
    if to_row > from_row:
        insert_at = to_start - len(moved_items)
    else:
        insert_at = to_start
    insert_at = max(0, min(insert_at, len(remaining)))

    data["libraryItems"] = remaining[:insert_at] + moved_items + remaining[insert_at:]
    save_library_file(library_path, data)
    print(
        f"Moved {len(moved_items)} item(s) from row {from_row} to row {to_row} in {library_path}"
    )


def cmd_remove_items(args, settings_path: Path) -> None:
    get_library_path_from_settings(settings_path)
    lib_path = resolve_library_path(args, settings_path)
    library_path = strip_path_part(lib_path,'.vscode')
    data = load_library(library_path)
    items = data["libraryItems"]
    n = len(items)
    if n == 0:
        die("library is empty; nothing to remove")
    indices = parse_item_spec(args.item_spec, n)
    for idx in reversed(indices):
        items.pop(idx)
    data["libraryItems"] = items
    save_library_file(library_path, data)
    print(
        f"Removed {len(indices)} item(s); library now has {len(items)} items in {library_path}"
    )


def lib_path_fix(settings_path: Path, library_value: Path|str) -> Path:
    lib_path = Path(library_value) if Path(library_value).is_absolute() else settings_path.parent / library_value
    return lib_path


def cmd_status(args, settings_path: Path) -> None:
    print(f"Settings path : {settings_path}")
    print(f"  exists      : {settings_path.exists()}")

    library_value: str | Path | None = None
    library_value_subdir: str | Path | None = None

    if settings_path.exists():
        content = read_settings_raw(settings_path)
        value_match = re.search(r'"excalidraw\.workspaceLibraryPath"\s*:\s*"([^"]*)"', content)
        if value_match:
            library_value = Path(f"{value_match.group(1)}")
            library_value_subdir = settings_path.parent / Path(f"{library_value.parts[0]}") if len(library_value.parts) > 1 else None
            print(f"\n{SETTINGS_KEY}\n  value       : {library_value}")
        else:
            print(f"\n{SETTINGS_KEY}\n  value       : (not set)")

        if library_value_subdir and library_value_subdir.exists():
            print(f"\nFiles in {library_value_subdir}:")
            for p in sorted(library_value_subdir.rglob("*")):
                if p.is_file():
                    print(f"  {p.relative_to(library_value_subdir)}")
    else:
        print(f"\n{SETTINGS_KEY}\n  value       : (settings file missing)")

    if library_value:
        lib_path = lib_path_fix(settings_path, library_value)
        lib_path = strip_path_part(lib_path,'.vscode')
        print(f"\nLibrary file  : {lib_path}")
        print(f"  exists      : {lib_path.exists()}")
        if lib_path.exists():
            stat = lib_path.stat()
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = stat.st_size / 1024
            print(f"  size        : {size_kb:.1f} KB")
            print(f"  modified    : {mtime}")
            try:
                with lib_path.open(encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("libraryItems", [])
                print(f"  libraryItems: {len(items)}")
                lib_type = data.get("type", "(unknown)")
                lib_version = data.get("version", "(unknown)")
                print(f"  type        : {lib_type}")
                print(f"  version     : {lib_version}")
            except (json.JSONDecodeError, PermissionError) as e:
                print(f"  (could not parse library: {e})")


def cmd_save_library(args, settings_path: Path) -> None:
    get_library_path_from_settings(settings_path)
    lib_path = resolve_library_path(args, settings_path)
    library_path = strip_path_part(lib_path,'.vscode')
    data = load_library(library_path)
    if args.filename:
        dest = Path(args.filename).resolve()
        save_library_file(dest, data)
        print(f"Saved library to {dest}")
    else:
        save_library_file(library_path, data)
        print(f"Saved library in-place to {library_path}")


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="excli",
        description="Manage Excalidraw library files (.excalidrawlib) from the CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  excli add-library dave
  excli modify-library add-field status published
  excli modify-library remove-items 1,3-5,9
  excli modify-library rearrange-items "row 3 to row 1"
  excli --settings /tmp/test-settings.json add-library work
  excli modify-library --library libraries/dave.excalidrawlib edit-field status unpublished
""",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=f"Path to excli config file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--settings",
        metavar="PATH",
        help=f"Path to VS Code settings.json (overrides config file; default: {DEFAULT_SETTINGS_PATH})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable trace logging and show full traceback on error",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # --- add-library ---
    p_add = subparsers.add_parser(
        "add-library",
        help="Set the active Excalidraw library in VS Code settings.json",
        description=(
            "Sets excalidraw.workspaceLibraryPath in VS Code settings.json "
            "to <name>.excalidrawlib. Equivalent to 'Load library' in the Excalidraw UI."
        ),
    )
    p_add.add_argument(
        "name",
        help="Base name of the .excalidrawlib file (extension optional), e.g. 'dave' or 'libraries/work'",
    )

    # --- modify-library ---
    p_mod = subparsers.add_parser(
        "modify-library",
        help="Modify items in the currently configured library file",
        description="Modify libraryItems in the configured .excalidrawlib file. Changes are saved immediately.",
    )
    p_mod.add_argument(
        "--library",
        metavar="PATH",
        help="Path to the library file to modify (overrides path from settings.json)",
    )
    mod_sub = p_mod.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    mod_sub.required = True

    p_af = mod_sub.add_parser(
        "add-field",
        help="Add a field to every item in libraryItems",
        description=(
            "Adds (or overwrites) <field_name> = <field_value> on every item "
            "in the library's libraryItems array."
        ),
    )
    p_af.add_argument("field_name", help="JSON field name to add, e.g. 'status'")
    p_af.add_argument("field_value", help="Value to set (stored as a string)")

    p_ef = mod_sub.add_parser(
        "edit-field",
        help="Edit field_value where field_name exists in libraryItems",
        description=(
            "Updates <field_name> to <field_value> on every item that already has "
            "that field. Items without the field are left unchanged."
        ),
    )
    p_ef.add_argument("field_name", help="JSON field name to edit")
    p_ef.add_argument("field_value", help="New value to set")

    p_ra = mod_sub.add_parser(
        "rearrange-items",
        help="Rearrange rows of library items (4 items per row)",
        description=(
            "Moves an entire row of library items to a new row position. "
            "Items display 4-per-row in the Excalidraw sidebar."
        ),
        epilog=(
            "Move spec formats:\n"
            "  'row 3 to row 1'   fully qualified\n"
            "  'row 3 to 1'       abbreviated\n"
            "  '3 to 1'           bare numbers\n"
            "  '3->1'             arrow notation\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_ra.add_argument(
        "move_spec",
        help="Move specification, e.g. 'row 3 to row 1' or '3->1'",
    )

    p_ri = mod_sub.add_parser(
        "remove-items",
        help="Remove library items by 1-based index",
        description=(
            "Removes items by their 1-based index. "
            "Supports ranges and comma-separated lists."
        ),
        epilog=(
            "Item spec examples:\n"
            "  '5'         remove item 5\n"
            "  '5-8'       remove items 5, 6, 7, 8\n"
            "  '1,5,9'     remove items 1, 5, and 9\n"
            "  '1,3-5,9'   mixed ranges and singles\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_ri.add_argument(
        "item_spec",
        help="1-based item indices, e.g. '5-8' or '1,3-5,9'",
    )

    # --- status ---
    subparsers.add_parser(
        "status",
        help="Show current settings path, configured library, and library metadata",
        description=(
            "Reports the settings.json path, the configured excalidraw.workspaceLibraryPath value, "
            "files in the settings directory, and library file metadata if the path resolves."
        ),
    )

    # --- save-library ---
    p_save = subparsers.add_parser(
        "save-library",
        help="Save the library (optionally to a new filename)",
        description=(
            "Saves the currently configured library. Without a filename, saves in-place. "
            "With a filename, saves to that path (useful for exporting a copy)."
        ),
    )
    p_save.add_argument(
        "--library",
        metavar="PATH",
        help="Source library file path (overrides path from settings.json)",
    )
    p_save.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Destination filename (default: save in-place)",
    )

    return parser


def main() -> None:
    global _debug_enabled

    parser = build_parser()
    args = parser.parse_args()

    if args.debug:
        _debug_enabled = True
        _debug(f"excli starting; args={vars(args)}")

    config_path = Path(args.config).expanduser().resolve() if args.config else DEFAULT_CONFIG_PATH
    _debug(f"config path: {config_path}")

    cfg = load_config(config_path)
    settings_path = effective_settings_path(args, cfg)
    _debug(f"effective settings_path: {settings_path}")

    try:
        if args.command == "add-library":
            cmd_add_library(args, settings_path)
        elif args.command == "status":
            cmd_status(args, settings_path)
        elif args.command == "save-library":
            cmd_save_library(args, settings_path)
        elif args.command == "modify-library":
            dispatch = {
                "add-field": cmd_add_field,
                "edit-field": cmd_edit_field,
                "rearrange-items": cmd_rearrange_items,
                "remove-items": cmd_remove_items,
            }
            dispatch[args.subcommand](args, settings_path)
    except SystemExit:
        raise
    except Exception as e:
        if args.debug:
            print(f"\n[debug] Unhandled exception: {type(e).__name__}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)
        die(f"unexpected error: {e}")


if __name__ == "__main__":
    main()
