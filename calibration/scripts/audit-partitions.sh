#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
if [[ $# != 2 ]]; then echo 'Usage: audit-partitions.sh PARTITIONED_CAPTURE NEW_DERIVATIVE_ROOT' >&2; exit 2; fi
source=$1
destination=$2
mkdir "$destination"
export root source destination
xargs -d '\n' -P 2 -I '{}' bash -c '
  part=$1
  while [[ ! -d "$source/combined" ]] && ! { [[ -f "$source/$part.log" ]] && tail -1 "$source/$part.log" | rg -q "^JointCases attempted="; }; do sleep 5; done
  "$root/scripts/audit-traces.sh" --complete "$source/$part" "$destination/$part" > "$destination/$part.log" 2>&1
' _ '{}' < "$source/partitions.txt"
"$root/scripts/combine.sh" "$destination" "$source/partitions.txt"
