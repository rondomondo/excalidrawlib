# jq cheatsheet — excalidrawlib files

## Inspect structure

```bash
# Top-level keys
cat library | jq 'keys'

# Count library items
cat library | jq '.libraryItems | length'

# See the full structure of the first item
cat library | jq '.libraryItems[0]'

# See all item statuses
cat library | jq '[.libraryItems[].status] | unique'

# Count elements per library item
cat library | jq '[.libraryItems[] | {elements: (.elements | length)}]'

# List all element types used across all items
cat library | jq '[.libraryItems[].elements[].type] | unique'
```

## Explore items

```bash
# Preview first item's elements (just type and id)
cat library | jq '.libraryItems[0].elements[] | {type, id}'

# Find items that contain a specific element type (e.g. "text")
cat library | jq '.libraryItems[] | select(.elements[].type == "text")'

# Count items by status
cat library | jq '.libraryItems | group_by(.status) | map({status: .[0].status, count: length})'
```

## Extract a subset

```bash
# Extract first 10 items into a new file (preserves wrapper)
cat library | jq '.libraryItems |= .[:10]' > library.small

# Extract items 10–20
cat library | jq '.libraryItems |= .[10:20]' > library.slice

# Extract only "published" items
cat library | jq '.libraryItems |= map(select(.status == "published"))' > library.published
```

## Edit items

```bash
# Set all items to "published"
cat library | jq '.libraryItems[].status = "published"' > library.out

# Remove a field from all elements
cat library | jq '.libraryItems[].elements[] |= del(.versionNonce)' > library.out

# Add a field to every library item
cat library | jq '.libraryItems[] |= . + {tag: "mine"}' > library.out
```

## Validate / diff

```bash
# Pretty-print for readability
cat library | jq '.' | less

# Compact output (for diffs or piping)
cat library | jq -c '.libraryItems[]'

# Compare item counts between two files
jq '.libraryItems | length' library library.small
```
