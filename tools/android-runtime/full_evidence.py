import re

from evidence import parse_instrumentation, validate_lane
from optimized_evidence import (_directives, _has_broad_namespace_keep,
                                _parse_class_spec, EFFECTIVE_KEEP_DIRECTIVES)


UMBRELLA = "io.github.rubixhacker.dyn4k.full.FullJourneyTest#allInstalledCases"
PROTECTED = ("org.dyn4j.", "io.github.rubixhacker.dyn4k.")
X86_DEXOPT_TOKENS = ["class", "org.dyn4j.geometry.Matrix22", "{", "public", "double",
                     "normMax", "(", ")", ";", "}"]


def validate_full_process_log(log, package):
    escaped = re.escape(package)
    started = re.findall(
        rf"(?m)\bActivityManager: Start proc (\d+):{escaped}/\S+ for added application {escaped}$",
        log)
    finished = re.findall(
        rf"(?m)\bActivityManager: Killing (\d+):{escaped}/\S+ \(adj \d+\): "
        rf"stop {escaped} due to finished inst$", log)
    if len(started) != 1 or finished != started:
        raise ValueError("instrumentation process identity or normal shutdown missing")
    return started[0]


def validate_full_installed(raw, expected_cases, process_exit_code):
    if not expected_cases:
        raise ValueError("full installed case list empty")
    result = parse_instrumentation(raw)
    validate_lane(result, set(expected_cases), {UMBRELLA}, process_exit_code)
    if result["portable"]["passed"] != len(expected_cases):
        raise ValueError("installed case count differs")
    return result


def validate_full_keep_scope(configuration, allowed_test_classes):
    if _has_broad_namespace_keep(configuration):
        raise ValueError("full optimized route has a broad keep rule")
    dexopt_member_count = 0
    for name, tokens in _directives(configuration):
        if name == "keepclassmembers" and tokens[:2] == X86_DEXOPT_TOKENS[:2]:
            dexopt_member_count += 1
            if tokens != X86_DEXOPT_TOKENS or dexopt_member_count != 1:
                raise ValueError("full optimized route has an unexpected Matrix22 member keep")
            continue
        if name not in EFFECTIVE_KEEP_DIRECTIVES:
            continue
        selectors, _, _, _ = _parse_class_spec(name, tokens)
        for selector in selectors:
            if selector.startswith(PROTECTED) and not (
                    selector in allowed_test_classes or
                    selector.startswith("io.github.rubixhacker.dyn4k.full.")):
                raise ValueError(f"engine or facade class kept outside full test entries: {selector}")
    if dexopt_member_count != 1:
        raise ValueError("full optimized route has a missing Matrix22 member keep")


def validate_full_r8(configuration, mapping, usage, debug_dex, release_dex,
                     allowed_test_classes=frozenset(), minimum_transformed=10):
    validate_full_keep_scope(configuration, allowed_test_classes)
    removed_engine = {match.group(1) for match in re.finditer(
        r"(?m)^(org\.dyn4j\.[\w.$]+)(?::)?$", usage)
        if match.group(1) not in allowed_test_classes and not match.group(1).endswith("Test")}
    if not mapping.strip() or not removed_engine:
        raise ValueError("full R8 mapping or usage is empty")
    if not debug_dex or not release_dex or len(release_dex) >= len(debug_dex):
        raise ValueError("full optimized DEX class inventory did not shrink")
    transformed = {}
    for original, target in re.findall(r"(?m)^(org\.dyn4j\.[\w.$]+) -> ([^:\s]+):$", mapping):
        if target == original or target.startswith("R8$$REMOVED$$CLASS$$"):
            continue
        descriptor = "L" + target.replace(".", "/") + ";"
        if descriptor not in release_dex:
            raise ValueError(f"mapped engine class absent from release DEX: {original}")
        if "L" + original.replace(".", "/") + ";" in debug_dex:
            transformed[original] = target
    if len(transformed) < minimum_transformed:
        raise ValueError(f"too few transformed engine classes: {len(transformed)}")
    return {"transformed_engine_classes": transformed,
            "removed_engine_classes": len(removed_engine),
            "debug_dex_classes": len(debug_dex), "release_dex_classes": len(release_dex)}
