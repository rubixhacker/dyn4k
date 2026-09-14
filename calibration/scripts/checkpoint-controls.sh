#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 3 ]]; then echo 'Usage: checkpoint-controls.sh ORIGINAL_UPSTREAM_TRACES CHECKPOINT_TRACES NEW_EVIDENCE_DIRECTORY' >&2; exit 2; fi
original=$1
checkpoint=$2
out=$3
root=$(cd "$(dirname "$0")" && pwd)
mkdir "$out"
while IFS=$'\t' read -r new old; do
  gzip -cd "$original/$old" | jq -scS '.[0] | {settings,world,state}' > "$out/$new.original-input.json"
  gzip -cd "$checkpoint/$new" | jq -scS '.[0] | {settings,world,state}' > "$out/$new.checkpoint-input.json"
  cmp "$out/$new.original-input.json" "$out/$new.checkpoint-input.json"
  gzip -cd "$original/$old" | jq -scS '[.[] | select(.kind=="state") | .state]' > "$out/$new.original-states.json"
  count=$(jq 'length' "$out/$new.original-states.json")
  gzip -cd "$checkpoint/$new" | jq -scS --argjson count "$count" '[.[] | select(.kind=="state") | .state][:$count]' > "$out/$new.checkpoint-states.json"
  cmp "$out/$new.original-states.json" "$out/$new.checkpoint-states.json"
  printf '%s\t%s\t%s\t%s\n' "$new" "$old" "$count" 'EXACT_INPUT_AND_STATE_PREFIX_MATCH'
done < "$root/checkpoint-controls.tsv"
