#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 ]]; then echo 'Usage: combine.sh PARTITION_ROOT PARTITIONS_FILE' >&2; exit 2; fi
root=$1
parts=$2
mkdir -p "$root/combined"
while IFS= read -r part; do
  [[ -f "$root/$part/summary.jsonl" ]]
  while IFS= read -r -d '' file; do
    target="$root/combined/${file##*/}"
    if [[ -e "$target" ]]; then
      [[ "$file" -ef "$target" ]] || cmp --silent "$file" "$target"
    else ln "$file" "$target"; fi
  done < <(find "$root/$part" -maxdepth 1 -name '*.jsonl.gz' -print0)
done < "$parts"
for name in summary.jsonl queries.jsonl audit-manifest.jsonl; do
  temporary=$(mktemp "$root/combined/.index.XXXXXX")
  while IFS= read -r part; do if [[ -f "$root/$part/$name" ]]; then cat "$root/$part/$name"; fi; done < "$parts" > "$temporary"
  if [[ "$name" == summary.jsonl ]]; then
    unique=$(mktemp "$root/combined/.unique.XXXXXX")
    duplicates=$(mktemp "$root/combined/.duplicates.XXXXXX")
    awk -v duplicates="$duplicates" 'seen[$0]++ {print > duplicates; next} {print}' "$temporary" > "$unique"
    mv "$duplicates" "$root/combined/redundant-summary-rows.jsonl"
    mv "$unique" "$temporary"
  fi
  if [[ -f "$root/combined/$name" ]]; then cmp --silent "$temporary" "$root/combined/$name"; rm "$temporary"; else mv "$temporary" "$root/combined/$name"; fi
done
