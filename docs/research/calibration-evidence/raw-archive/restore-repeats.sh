#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
cd "$root/canonical"
sha256sum -c ../repeat-a/trace-sha256.txt
sha256sum -c ../repeat-b/trace-sha256.txt
cd "$root"
mkdir restored-a restored-b
for repeat in a b; do
 cp "repeat-$repeat"/*.jsonl "restored-$repeat/"
 for file in canonical/*.jsonl.gz; do ln "$file" "restored-$repeat/${file##*/}"; done
 (cd "restored-$repeat"; sha256sum -c "../repeat-$repeat/trace-sha256.txt")
done
