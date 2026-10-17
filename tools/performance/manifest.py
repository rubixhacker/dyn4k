#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path


V1_MANIFEST_SHA256 = "18cca97bbf1fc939eda669efe2344bbfe06c416a735ca8cc5184d5ba2519176a"
V1_MANIFEST_FILE = Path(__file__).resolve().parents[2] / "docs/research/performance-manifest-v1.json"


TARGET_ROWS = {
    "jvm": ["java"],
    "android": ["android_jvm"],
    "js": ["chromium", "firefox", "safari", "node"],
    "wasmJs": ["chromium", "firefox", "safari", "node"],
    "wasmWasi": ["node", "wasmtime"],
    "linuxX64": ["linux_x64"],
    "linuxArm64": ["linux_arm64"],
    "mingwX64": ["windows_x64"],
    "macosArm64": ["macos_arm64"],
    "iosArm64": ["ios_device"],
    "iosSimulatorArm64": ["ios_simulator_arm64"],
    "iosX64": ["ios_simulator_x64"],
    "tvosArm64": ["tvos_device"],
    "tvosSimulatorArm64": ["tvos_simulator"],
    "watchosArm64": ["watchos_ilp32_device"],
    "watchosDeviceArm64": ["watchos_lp64_device"],
    "watchosSimulatorArm64": ["watchos_simulator"],
    "androidNativeArm32": ["android_arm32"],
    "androidNativeArm64": ["android_arm64"],
    "androidNativeX86": ["android_x86"],
    "androidNativeX64": ["android_x64"],
}

SIZES = {
    "separated": {"small": 100, "medium": 1000, "stress": 10000},
    "pile": {"small": 100, "medium": 500, "stress": 2000},
    "joint": {"small": 50, "medium": 250, "stress": 1000},
    "ccd": {"small": 25, "medium": 100, "stress": 500},
    "lifecycle": {"small": 100, "medium": 1000, "stress": 5000},
}

JOINT_MODES = {
    "Angle": ["free", "limits", "ratio"],
    "Distance": ["rigid", "limits", "spring", "spring_damper"],
    "Friction": ["friction"],
    "Motor": ["offset"],
    "Pin": ["spring", "spring_damper"],
    "Prismatic": ["free", "limits", "motor", "spring", "spring_damper"],
    "Pulley": ["taut", "ratio", "slack"],
    "Revolute": ["free", "limits", "motor"],
    "Weld": ["rigid", "limits", "spring", "spring_damper"],
    "Wheel": ["spring", "spring_damper", "limits", "motor"],
    "Mixed": ["all_types"],
}

JOINT_PARAMETERS = {
    "anchor_rectangle_m": [0.25, 0.25],
    "anchor_center_m": "(3*i,3)",
    "dynamic_center_m": "(3*i,2)",
    "paired_anchor_m": "(3*i,2.5)",
    "prismatic_wheel_axis": [1.0, 0.0],
    "angle_limit_rad": [-0.5, 0.5],
    "linear_limit_m": [-0.5, 0.5],
    "distance_limit_m": [0.8, 1.2],
    "ratio": 2.0,
    "spring_frequency_hz": 4.0,
    "spring_damping_ratio": 0.5,
    "motor_speed_rad_or_m_per_s": 1.0,
    "maximum_motor_force_n": 10.0,
    "maximum_motor_torque_nm": 10.0,
    "friction_maximum_force_n": 10.0,
    "friction_maximum_torque_nm": 10.0,
    "motor_linear_target_m": [0.0, 1.0],
    "motor_angular_target_rad": 0.25,
    "periodic_angular_impulse_kg_m2_per_s": 0.01,
    "pulley_anchors_m": "(3*i-1,5) and (3*i+1,5)",
    "mixed_default_modes": {"Angle": "free", "Distance": "rigid", "Friction": "friction", "Motor": "offset", "Pin": "spring", "Prismatic": "free", "Pulley": "taut", "Revolute": "free", "Weld": "rigid", "Wheel": "spring"},
}


def build_config(target):
    if target == "jvm":
        return "default Kotlin bytecode optimization"
    if target == "android":
        return "R8-optimized consumer application from single-variant AAR"
    if target in ("js", "wasmJs", "wasmWasi"):
        return "PRODUCTION linked output; Binaryen optimized for Wasm"
    return "Kotlin/Native -opt"


def development_config(target):
    if target == "jvm":
        return "Kotlin -Xno-optimize"
    if target == "android":
        return "debug consumer application from single-variant AAR"
    if target in ("js", "wasmJs", "wasmWasi"):
        return "DEVELOPMENT linked output"
    return "Kotlin/Native -g"


def minimum_policy(target, runtime):
    if target == "jvm": return "Java 8"
    if target == "android" or target.startswith("androidNative"): return "Android API 21"
    if target in ("js", "wasmJs"):
        return {"chromium": "Chromium 119", "firefox": "Firefox 120", "safari": "Safari 18.2", "node": "Node.js 22.0.0"}[runtime]
    if target == "wasmWasi":
        return "Node.js 24.15.0 without experimental Wasm flags" if runtime == "node" else "Wasmtime 37.0.0 with -W gc=y -W exceptions=y -W function-references=y"
    if target == "linuxX64": return "Linux kernel 4.9.156, glibc 2.19"
    if target == "linuxArm64": return "Linux kernel 4.9.156, glibc 2.25"
    if target == "mingwX64": return "Windows 10 1507, build family 10240"
    if target == "macosArm64": return "macOS 11 with deployment override"
    if target.startswith("ios"): return "iOS 15"
    if target.startswith("tvos"): return "tvOS 15"
    if target == "watchosDeviceArm64": return "watchOS 26"
    if target.startswith("watchos"): return "watchOS 8"
    raise ValueError(f"no minimum policy for {target}")


def gates(target, runtime):
    medium = not (target.startswith("tvos") or target.startswith("watchos"))
    return {"small": "absolute", "medium": "absolute" if medium else "report_only", "stress": "report_only"}


def rows():
    return [
        {
            "id": f"{target}.{runtime}",
            "target": target,
            "runtime_family": runtime,
            "optimized_build": build_config(target),
            "development_build": development_config(target),
            "minimum_policy": minimum_policy(target, runtime),
            "minimum_tested_patch": None,
            "current_tested_version": None,
            "size_assignment": gates(target, runtime),
            "representative_hardware": None,
            "runtime_version": None,
            "abi": None,
            "environment_status": "unavailable",
            "probe_status": "unvalidated",
            "blocker": "Pin and verify a compatible host or device, runtime, ABI, and probes before measurement.",
        }
        for target, runtimes in TARGET_ROWS.items()
        for runtime in runtimes
    ]


def scenarios():
    return [
        {
            "id": f"{family}.{variant}.{size}.{hz}hz.{api}",
            "family": family,
            "variant": variant,
            "size": size,
            "dynamic_bodies": count,
            "rate_hz": hz,
            "api": api,
        }
        for family, size_counts in SIZES.items()
        for variant in (
            [f"{joint.lower()}_{mode}" for joint, modes in JOINT_MODES.items() for mode in modes]
            if family == "joint"
            else (["settle", "wake", "replace"] if family == "lifecycle" else ["default"])
        )
        for size, count in size_counts.items()
        for hz in (30, 60, 120)
        for api in ("baseline", "direct_kotlin", "compatibility")
    ]


def manifest():
    return {
        "version": 1,
        "policy": "https://github.com/rubixhacker/dyn4k/issues/8#issuecomment-5674480273",
        "source_commit": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
        "baseline_jar_sha256": "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e",
        "baseline_source_archive_sha256": "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223",
        "targets": list(TARGET_ROWS),
        "runtime_rows": rows(),
        "families": SIZES,
        "joint_modes": JOINT_MODES,
        "joint_parameters": JOINT_PARAMETERS,
        "rates_hz": [30, 60, 120],
        "api_surfaces": ["baseline", "direct_kotlin", "compatibility"],
        "scenarios": scenarios(),
        "fixture": {
            "version": "performance-v1",
            "seed": 17017,
            "gravity_m_per_s2": [0.0, -9.8],
            "dynamic_shape": "circle radius 0.25 m, one fixture per body; density 1 kg/m^2, friction 0.5, restitution 0.0",
            "static_shape": "rectangles with density 1 kg/m^2, friction 0.5, restitution 0; floor width 200 m and thickness 1 m centered at (0,-0.5) m for pile and lifecycle",
            "separated": "Grid pitch 3 m, 32 columns, starting (-48,2) m; zero gravity; all bodies have velocity (0.75,0.0) m/s; wrap by deterministic translation at x=48 m.",
            "pile": "10 columns; circle centers at x=(column-4.5)*0.48 m and y=0.3+row*0.48 m; zero initial velocity; floor contact and gravity active.",
            "joint": "One dynamic circle and one static 0.25 m square anchor per mechanism at x=3*i m. Disable at-rest detection for the dynamic circles. Mixed rotates the ten types by index. Apply linear impulse (0.5,1.0) kg*m/s and angular impulse 0.01 kg*m^2/s to every dynamic body once per simulated second. Mode parameters are fixed in the harness.",
            "ccd": "Two static walls, width 0.5 m and height 20 m, centered at x=-10 and x=10 m. Bullet circles alternate direction at 18 m/s from x=+-8 m, y=0.5+(index%20)*0.45 m. Reset at crossing to maintain repeated CCD opportunities.",
            "lifecycle": "10-column pile with the same floor. Every tenth dynamic body has a distance joint to the floor at both centers. Settle has no imposed wake. Wake applies impulse (0.2,0.5) kg*m/s to every tenth body once per simulated second. Replace removes and recreates ceil(1% of bodies) once per simulated second, starting at (17017 + elapsed whole seconds) modulo body count, with the same indexed positions and constant body and joint counts. Removal includes fixture and joint cleanup.",
            "callback": "Contact begin/end counters, without logging in timed steps; record counts after each step.",
            "diagnostics": "After timed stepping, record aggregate absolute linear and angular speed each step. Count full broad-phase candidate pairs using detectIterator(true), and active contact pairs/points, on the first step of each simulated second and the final step. Use -1 for unsampled pair counts; never interpret it as zero.",
            "solver": "dyn4j 6.0.0 defaults; do not change iteration or sleep settings",
        },
        "budgets": {
            "jvm_vs_baseline": {"median_ratio_max": 1.10, "p99_ratio_max": 1.20, "compute_per_simulated_second_ratio_max": 1.10, "retained_heap_ratio_max": 1.10, "steady_allocation_ratio_max": 1.10, "construction_or_replacement_allocation_ratio_max": 1.15},
            "shim_vs_direct": {"median_ratio_max": 1.05, "total_compute_ratio_max": 1.05, "p99_ratio_max": 1.10, "adaptation_allocation_bytes_max": 0},
            "absolute_p99_seconds": {"30": "1/120", "60": "1/240", "120": "1/480"},
            "incremental_peak_mib": {"small": 16, "medium": 64},
            "mib_bytes": 1048576,
        },
        "sustained": {
            "measured_wall_seconds": 600,
            "fresh_process_repetitions": 3,
            "final_window_seconds": 60,
            "create_use_dispose_cycles": 100,
            "equal_simulated_duration": True,
            "paced_no_dropped_steps": True,
            "timing_and_memory_separate_processes": True,
            "warmup_outside_measurement": True,
        },
        "measurement_method": {
            "warmup": "Pace at intended cadence for at least 120 wall seconds. Use 30-second windows. The last three window medians must each be within 5% of their median. Reset the fixture after warm-up in the same process. If no convergence by 600 wall seconds, mark inconclusive.",
            "timer": "Monotonic nanoTime. Measure paired-call positive resolution and median/p99 overhead with 10,000 calls. Keep pauses inside measured step elapsed time. Do not subtract overhead from gate samples.",
            "sampling": "Store every step with mutation time, lateness, allocation, heap, RSS, awake bodies, contact starts and ends, and TOI events. Keep event-only full and final-minute latency distributions. No dropped steps or hidden invalid runs.",
            "noise": "Before candidate runs, obtain three fresh-process pairs of unchanged baseline at each reference environment and workload. Balance pair order. Use one-second paired blocks and 2,000 deterministic bootstrap draws, seed 17017. Retain each pair interval and its raw series.",
            "confidence": "The upper bound of a two-sided 95% block-bootstrap ratio interval must be at or below each relative limit. Evaluate each run and its final minute separately. A crossing interval is inconclusive.",
            "tail": "Report p99 only with its event count. If an event-only final-minute series has fewer than 100 events, use the full-run distribution for tail context and mark the final-minute tail inconclusive.",
            "plateau": "After warm-up, run 100 create/use/dispose cycles. Record post-collection live heap, resident process bytes, and collection count. Compare cycles 20-39 with 80-99; drift above 5% or absent reclamation is inconclusive or failing, pending probe attribution.",
            "run_order": "Use three fresh matched processes per API. Rotate the order baseline/direct/compatibility, direct/compatibility/baseline, compatibility/baseline/direct so each API occupies every position once. Retain the order and process identity.",
            "memory": "Profile allocation and memory in separate paced processes using the same event schedule as timing. Record construction allocation, post-collection retained heap with the world alive, and RSS from empty harness through construction, warm-up, and measurement. Count managed, native, and Wasm linear storage once. A process RSS delta is a diagnostic until attribution and reserved-memory overhead are validated.",
        },
        "qualification": "unpassed",
    }


def ccd_fixture_revision():
    return {
        "version": "performance-ccd-v2",
        "base_manifest_version": 1,
        "base_manifest_sha256": V1_MANIFEST_SHA256,
        "family": "ccd",
        "workload_ids": [item["id"] for item in scenarios() if item["family"] == "ccd"],
        "body_hash": {
            "algorithm": "zero_based_creation_index",
            "counter_scope": "each_fixture",
            "creation_order": ["left_wall", "right_wall", "bullet_circles_ascending_index"],
            "warmup": "fresh_fixture_resets_counter",
            "routes": ["baseline", "direct_kotlin", "compatibility"],
            "other_families": "unchanged",
        },
        "qualification": "unpassed",
    }


def validate_ccd_fixture_revision(value):
    if hashlib.sha256(V1_MANIFEST_FILE.read_bytes()).hexdigest() != V1_MANIFEST_SHA256:
        raise ValueError("base manifest hash differs")
    validate(json.loads(V1_MANIFEST_FILE.read_text()))
    if value != ccd_fixture_revision():
        raise ValueError("CCD fixture revision differs from the frozen rule")


def validate(value):
    if value.get("version") != 1:
        raise ValueError("unsupported manifest version")
    if value.get("targets") != list(TARGET_ROWS):
        raise ValueError("target list differs from approved scope")
    expected = rows()
    observed = value.get("runtime_rows", [])
    if len(observed) != 28 or [row.get("id") for row in observed] != [row["id"] for row in expected]:
        raise ValueError("runtime row list is incomplete or reordered")
    if value.get("families") != SIZES or value.get("joint_modes") != JOINT_MODES or value.get("joint_parameters") != JOINT_PARAMETERS:
        raise ValueError("workload sizes or joint modes differ")
    if value.get("scenarios") != scenarios():
        raise ValueError("workload scenario expansion differs")
    if value.get("budgets") != manifest()["budgets"] or value.get("sustained") != manifest()["sustained"] or value.get("measurement_method") != manifest()["measurement_method"]:
        raise ValueError("approved budget or sustained contract differs")
    for row, template in zip(observed, expected):
        for field in ("target", "runtime_family", "optimized_build", "development_build", "minimum_policy", "size_assignment"):
            if row.get(field) != template[field]:
                raise ValueError(f"runtime policy differs: {row['id']} / {field}")
        if row.get("environment_status") not in ("available", "unavailable"):
            raise ValueError(f"unknown environment status: {row['id']}")
        if row.get("environment_status") == "available" and not all(
            row.get(field) for field in ("representative_hardware", "runtime_version", "abi")
        ):
            raise ValueError(f"available row lacks identity: {row['id']}")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "emit-ccd-fixture":
        print(json.dumps(ccd_fixture_revision(), indent=2, sort_keys=True))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "validate-ccd-fixture":
        value = json.load(sys.stdin if sys.argv[2] == "-" else Path(sys.argv[2]).open())
        validate_ccd_fixture_revision(value)
        print("CCD fixture revision valid")
        return
    if len(sys.argv) == 2 and sys.argv[1] == "emit":
        print(json.dumps(manifest(), indent=2, sort_keys=True))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        value = json.load(sys.stdin if sys.argv[2] == "-" else Path(sys.argv[2]).open())
        validate(value)
        print("manifest valid")
        return
    raise SystemExit("usage: manifest.py emit | validate FILE_OR_DASH")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
