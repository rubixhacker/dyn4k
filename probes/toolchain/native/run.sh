#!/usr/bin/env bash
set -euo pipefail
probe_root=/tmp/dyn4k-native-source
export KONAN_DATA_DIR="$probe_root/data"
compiler="$probe_root/kotlin-native-prebuilt-linux-x86_64-2.4.20/bin/konanc"
x64root="$KONAN_DATA_DIR/dependencies/x86_64-unknown-linux-gnu-gcc-8.3.0-glibc-2.19-kernel-4.9-2/x86_64-unknown-linux-gnu/sysroot"
armroot="$KONAN_DATA_DIR/dependencies/aarch64-unknown-linux-gnu-gcc-8.3.0-glibc-2.25-kernel-4.9-2/aarch64-unknown-linux-gnu/sysroot"
"$compiler" -version
uname -r
ldd --version | sed -n 1p
"$probe_root/probe.kexe"
"$x64root/lib/ld-linux-x86-64.so.2" --library-path "$x64root/lib:$x64root/usr/lib" "$probe_root/probe.kexe"
"$KONAN_DATA_DIR/dependencies/qemu-aarch64-static-5.1.0-linux-2/qemu-aarch64" -L "$armroot" "$probe_root/probe-arm64.kexe"
readelf -n "$x64root/lib/libc.so.6"
readelf -n "$armroot/lib/libc.so.6"
readelf -l "$probe_root/probe.kexe" | rg interpreter
readelf -l "$probe_root/probe-arm64.kexe" | rg interpreter
