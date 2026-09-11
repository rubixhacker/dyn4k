#!/usr/bin/env bash
set -euo pipefail
: "${JAVA_HOME:?Set JAVA_HOME to the selected JDK21 installation}"
"$JAVA_HOME/bin/java" -version
if ! "$JAVA_HOME/bin/java" -version 2>&1 | rg -q 'version "21[.]'; then
  printf "JDK21 is required\n" >&2
  exit 1
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
probe_root=$(mktemp -d /tmp/dyn4k-native-repro.XXXXXX)
export KONAN_DATA_DIR="$probe_root/data"
archive=kotlin-native-prebuilt-linux-x86_64-2.4.20.tar.gz
curl -fL "https://github.com/JetBrains/kotlin/releases/download/v2.4.20/$archive" -o "$probe_root/$archive"
printf '%s  %s\n' 32d33c15c4da668a8d47a0ce2aea95be2c2cf8f5d1d65f6f4ed3697e4686dc7f "$probe_root/$archive" | sha256sum --check -
tar -xzf "$probe_root/$archive" -C "$probe_root"
compiler="$probe_root/kotlin-native-prebuilt-linux-x86_64-2.4.20/bin/konanc"
"$compiler" -version
for mode in debug optimized; do
  flags=(-g)
  if [[ "$mode" == optimized ]]; then flags=(-opt); fi
  for target in linux_x64 linux_arm64; do
    "$compiler" "$source_dir/Probe.kt" -target "$target" "${flags[@]}" -o "$probe_root/$target-$mode"
    readelf -W --version-info "$probe_root/$target-$mode.kexe" > "$probe_root/$target-$mode.elf.txt"
  done
  "$probe_root/linux_x64-$mode.kexe"
  x64root="$KONAN_DATA_DIR/dependencies/x86_64-unknown-linux-gnu-gcc-8.3.0-glibc-2.19-kernel-4.9-2/x86_64-unknown-linux-gnu/sysroot"
  "$x64root/lib/ld-linux-x86-64.so.2" --library-path "$x64root/lib:$x64root/usr/lib" "$probe_root/linux_x64-$mode.kexe"
  armroot="$KONAN_DATA_DIR/dependencies/aarch64-unknown-linux-gnu-gcc-8.3.0-glibc-2.25-kernel-4.9-2/aarch64-unknown-linux-gnu/sysroot"
  "$KONAN_DATA_DIR/dependencies/qemu-aarch64-static-5.1.0-linux-2/qemu-aarch64" -L "$armroot" "$probe_root/linux_arm64-$mode.kexe"
done
sha256sum "$probe_root"/*.kexe
printf 'Artifacts: %s\n' "$probe_root"
