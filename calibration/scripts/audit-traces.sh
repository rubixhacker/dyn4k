#!/usr/bin/env bash
set -euo pipefail
calibration_root=$(cd "$(dirname "$0")/.." && pwd)
audit_classes=$(mktemp -d "${TMPDIR:-/tmp}/dyn4k-audit.XXXXXX")
trap 'rm -rf "$audit_classes"' EXIT
javac -d "$audit_classes" "$calibration_root/src/Audit.java"
java -Xmx256m -cp "$audit_classes" Audit "$@"
