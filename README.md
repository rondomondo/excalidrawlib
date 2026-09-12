# excli — Excalidraw Library Manager CLI

A Python CLI for managing [Excalidraw](https://excalidraw.com/) library files (`.excalidrawlib`) from the terminal. Designed to work alongside the [Excalidraw VS Code extension](https://marketplace.visualstudio.com/items?itemName=pomdtr.excalidraw-editor).

---

## What it does

The Excalidraw VS Code extension loads a personal shape library from a `.excalidrawlib` file on disk, configured via `excalidraw.workspaceLibraryPath` in `settings.json`. `excli` lets you:

- Switch the active library without touching the UI
- Add, edit, and remove items in a library file
- Reorder rows of items (the sidebar displays 4 items per row)
- Inspect library metadata

---

## Requirements

- Python 3.10+
- VS Code with the [Excalidraw extension](https://marketplace.visualstudio.com/items?itemName=pomdtr.excalidraw-editor)

---

## Installation

```bash
git clone <repo>
cd excalidrawlib
chmod +x excli.py
# Optionally symlink onto your PATH
ln -s "$PWD/excli.py" /usr/local/bin/excli
```

---

## Configuration

On first run, `excli` creates `~/.excli/config.json` and seeds it with the path to `settings.json`. You can edit this file directly:

```json
{
  "settings_path": "/Users/dave/Code/myproject/.vscode/settings.json"
}
```

### Resolution order for `settings.json`

| Priority | Source |
|----------|--------|
| 1 | `--settings PATH` flag |
| 2 | `settings_path` in `~/.excli/config.json` |
| 3 | Built-in default: `~/Library/Application Support/Code/User/settings.json` |

### Global flags

```
--config PATH     Config file to use (default: ~/.excli/config.json)
--settings PATH   VS Code settings.json path (overrides config file)
--debug           Timestamped trace logging + full traceback on error
```

---

## Commands

### `status`

Show the currently configured settings file, library path, and library metadata.

```
excli status
```

```
Settings path : /Users/dave/Code/myproject/.vscode/settings.json
  exists      : True

excalidraw.workspaceLibraryPath
  value       : libraries/dave.excalidrawlib

Library file  : /Users/dave/Code/myproject/libraries/dave.excalidrawlib
  exists      : True
  size        : 2449.8 KB
  modified    : 2026-09-12 09:18:43
  libraryItems: 51
  type        : excalidrawlib
  version     : 2
```

---

### `add-library <name>`

Set `excalidraw.workspaceLibraryPath` in `settings.json` to `<name>.excalidrawlib`. Equivalent to clicking **Load library** in the Excalidraw UI. The extension picks up the change immediately — no restart needed.

```bash
excli add-library dave
excli add-library libraries/work        # subdirectory
excli add-library dave.excalidrawlib   # extension is stripped automatically
```

The library file does not need to exist yet — Excalidraw will create it when you save your first item.

**Name rules:** `a-z A-Z 0-9 . _ / - (space)` only. Path traversal (`..`) is rejected.

---

### `modify-library`

Modify `libraryItems` in the configured library file. All subcommands accept `--library PATH` to target a specific file instead of the one from `settings.json`.

```
excli modify-library [--library PATH] SUBCOMMAND
```

#### `add-field <field_name> <field_value>`

Add (or overwrite) a JSON field on **every** item in `libraryItems`.

```bash
excli modify-library add-field status published
excli modify-library add-field tag architecture
```

Warns if the field already exists on some items before overwriting.

#### `edit-field <field_name> <field_value>`

Update a field on items that already have it. Items without the field are left unchanged.

```bash
excli modify-library edit-field status unpublished
excli modify-library --library libraries/work.excalidrawlib edit-field tag infra
```

#### `remove-items <item_spec>`

Remove items by their **1-based index**. Accepts individual indices, ranges, and combinations.

```bash
excli modify-library remove-items 5          # remove item 5
excli modify-library remove-items 5-8        # remove items 5, 6, 7, 8
excli modify-library remove-items 1,5,9      # remove items 1, 5, and 9
excli modify-library remove-items 1,3-5,9   # mixed
```

Indices are validated against the library size before any changes are made.

#### `rearrange-items <move_spec>`

Move an entire **row** of items to a different row position. The Excalidraw sidebar displays items **4 per row**, so rows are groups of up to 4 consecutive items.

```bash
excli modify-library rearrange-items "row 3 to row 1"
excli modify-library rearrange-items "row 3 to 1"
excli modify-library rearrange-items "3 to 1"
excli modify-library rearrange-items "3->1"
```

All four formats are equivalent.

---

### `save-library [filename]`

Save the library. Without a filename, saves in-place (useful to normalise formatting). With a filename, exports a copy.

```bash
excli save-library                            # re-save in-place
excli save-library backup.excalidrawlib       # export a copy
excli save-library --library src.excalidrawlib dest.excalidrawlib
```

---

## Common workflows

### Switch between libraries

```bash
# Point VS Code at a different library file
excli add-library work
excli add-library dave
excli add-library libraries/client-x
```

### Tag all items and then update some

```bash
# Stamp everything as draft first
excli modify-library add-field status draft

# Then promote specific items to published
# (edit-field updates only items that already have the field)
excli modify-library edit-field status published
```

### Clean up a library

```bash
# See what's there
excli status

# Remove the last few items
excli modify-library remove-items 48-51

# Reorder: bring row 5 to the top
excli modify-library rearrange-items "5->1"
```

### Work with a specific file

```bash
# Any subcommand accepts --library to bypass settings.json
excli modify-library --library ~/exports/shared.excalidrawlib add-field org acme
excli modify-library --library ~/exports/shared.excalidrawlib remove-items 1,2
```

### Use a different settings file

```bash
# One-off override
excli --settings /tmp/test-settings.json status

# Or update config.json to make it the default
# ~/.excli/config.json:
# { "settings_path": "/Users/dave/Code/otherproject/.vscode/settings.json" }
```

---

## Debugging

`--debug` prints timestamped trace lines to stderr showing every decision point — config load, settings parse, library path resolution, item counts — and a full traceback on unhandled exceptions.

```bash
excli --debug status
```

```
[debug +0.013s] excli.py:648 main() | excli starting; args={'config': None, 'settings': None, ...}
[debug +0.013s] excli.py:651 main() | config path: /Users/dave/.excli/config.json
[debug +0.014s] excli.py:66  load_config() | config path: /Users/dave/.excli/config.json
[debug +0.016s] excli.py:100 effective_settings_path() | settings path from config file: ...
[debug +0.017s] excli.py:148 read_settings_raw() | reading settings: ... (107 bytes)
...
```

---

## `.excalidrawlib` file format

Library files are JSON with this structure:

```json
{
  "type": "excalidrawlib",
  "version": 2,
  "source": "https://excalidraw.com",
  "libraryItems": [
    {
      "id": "abc123",
      "status": "published",
      "elements": [ ... ]
    }
  ]
}
```

`excli` reads and writes only `libraryItems`. All other top-level fields are preserved as-is.

---

## jq reference

For ad-hoc inspection and transformation, `jq` pairs well with excli. See [`jq-excalidrawlib.md`](jq-excalidrawlib.md) for a full cheatsheet. Quick examples:

```bash
# Count items
jq '.libraryItems | length' libraries/dave.excalidrawlib

# List unique statuses
jq '[.libraryItems[].status] | unique' libraries/dave.excalidrawlib

# Extract items 10–20 into a new file
jq '.libraryItems |= .[10:20]' libraries/dave.excalidrawlib > slice.excalidrawlib
```

---

## File safety

All writes use an atomic temp-file + `os.replace()` pattern — a crash mid-write leaves the original intact.
