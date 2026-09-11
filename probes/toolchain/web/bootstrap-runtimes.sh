#!/usr/bin/env bash
set -euo pipefail
root=/tmp/dyn4k-web-probe
mkdir -p "$root"
while read -r version digest; do
 file="node-${version}.tar.xz"
 curl --fail --location --retry 2 --max-time 180 "https://nodejs.org/dist/v${version}/node-v${version}-linux-x64.tar.xz" -o "$root/$file"
 printf '%s  %s\n' "$digest" "$root/$file" | sha256sum --check
 tar -xf "$root/$file" -C "$root"
done <<'VERSIONS'
22.0.0 9122e50f2642afd5f6078cafd1f52ede60fc464284384f05c18a04d13d07ae5a
24.14.1 84d38715d449447117d05c3e71acd78daa49d5b1bfa8aacf610303920c3322be
24.15.0 472655581fb851559730c48763e0c9d3bc25975c59d518003fc0849d3e4ba0f6
26.8.2 40e1d3225c1c9ae9a2671c98ecb9857e4d5555026394f348645676798840d5c5
VERSIONS
while read -r version digest; do
 file="wasmtime-${version}.tar.xz"
 curl --fail --location --retry 2 --max-time 180 "https://github.com/bytecodealliance/wasmtime/releases/download/v${version}/wasmtime-v${version}-x86_64-linux.tar.xz" -o "$root/$file"
 printf '%s  %s\n' "$digest" "$root/$file" | sha256sum --check
 tar -xf "$root/$file" -C "$root"
done <<'VERSIONS'
37.0.0 5d83e111f4de32d33c20a272628dd11a529bebeda4627eac51c2cae4ad69966e
48.0.2 f2b0ad1ce9253f2f9a38793c2c42cd1cba4e90b27dc40d685eaf723dc8438d94
VERSIONS
