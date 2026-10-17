#!/usr/bin/env bash
set -euo pipefail

destination=$1
revision=058bf6d982a0fb89b54050f929f6ea9dae53b714
if [[ ! -d "$destination/.git" ]]; then
    mkdir -p "$(dirname "$destination")"
    git clone --quiet https://github.com/dyn4j/dyn4j.git "$destination"
fi
actual=$(git -C "$destination" rev-parse HEAD)
if [[ "$actual" != "$revision" ]]; then
    git -C "$destination" checkout --quiet --detach "$revision"
fi
actual=$(git -C "$destination" rev-parse HEAD)
if [[ "$actual" != "$revision" ]]; then
    printf 'Pinned upstream revision mismatch: %s\n' "$actual" >&2
    exit 1
fi
printf 'Pinned upstream tests: %s\n' "$actual"
