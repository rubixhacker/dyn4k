#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
failures=0
run_case() {
 expected=$1; shift
 "$@"
 status=$?
 printf 'exit=%s expected=%s\n' "$status" "$expected"
 [ "$status" -eq "$expected" ] || failures=$((failures + 1))
}
for mode in development production; do
 for v in 22.0.0 24.14.1 24.15.0 26.8.2; do
  runner=/tmp/dyn4k-web-probe/node-v${v}-linux-x64/bin/node
  for target in js wasmJs wasmWasi; do
   ext=mjs; out=kotlin; expected=0
   [ "$mode" = production ] && out=optimized
   if [ "$target" = js ]; then ext=js; out=kotlin; fi
   if [ "$target" = wasmWasi ] && { [ "$v" = 22.0.0 ] || [ "$v" = 24.14.1 ]; }; then expected=1; fi
   printf '\nNode %s target %s mode %s\n' "$v" "$target" "$mode"
   run_case "$expected" "$runner" "build/compileSync/$target/main/${mode}Executable/$out/web-floor-probe.$ext"
  done
 done
 out=kotlin; [ "$mode" = production ] && out=optimized
 artifact="build/compileSync/wasmWasi/main/${mode}Executable/$out/web-floor-probe.wasm"
 for v in 37.0.0 48.0.2; do
  runner=/tmp/dyn4k-web-probe/wasmtime-v${v}-x86_64-linux/wasmtime
  printf '\nWasmtime %s mode %s\n' "$v" "$mode"
  "$runner" --version
  expected=0; [ "$v" = 37.0.0 ] && expected=1
  run_case "$expected" "$runner" run "$artifact"
  run_case 0 "$runner" run -W gc=y -W exceptions=y -W function-references=y "$artifact"
 done
done
printf '\nUnexpected exit results: %s\n' "$failures"
[ "$failures" -eq 0 ]
