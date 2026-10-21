import hashlib
from pathlib import Path


PINNED_FILES = {
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/Transform.kt":
        "ec22ca59049bbe090f381f133a43d7e1e72b3b220960ec751c3f278b7b280747",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/CollisionBody.kt":
        "71690455e111fbc3076885ef5a968a66e32616b334afdf428d8f9e56e74b0174",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/AbstractPhysicsBody.kt":
        "569979aee3583bf61d11dcffed236901257e606b207011c52f417e2ce1513719",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/RevoluteJoint.kt":
        "8be0bf63a1b2940a2570bd814040aaa1d6058862a1419528d02ed5c0f2748e58",
    "tools/numerical/portable/src/jvmTest/kotlin/portable/RevoluteLimitsFalseCaptureTest.kt":
        "d7a8467eb390a4c0db1544472fdb092420933470c879880f23ac64c2e43ff881",
}


def verify_source_schedule(root):
    root = Path(root)
    try:
        for path, digest in PINNED_FILES.items():
            if hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
                return {"status": "FAILED_SOURCE_SCHEDULE", "qualification": "UNPASSED",
                        "path": path}
    except OSError:
        return {"status": "FAILED_SOURCE_SCHEDULE", "qualification": "UNPASSED"}
    return {"status": "MATCHED_SOURCE_SCHEDULE", "qualification": "UNPASSED",
            "files": len(PINNED_FILES)}
