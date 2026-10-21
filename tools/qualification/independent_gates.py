#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import types
import zipfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

import qualify
import artifact


APPROVED_MANIFEST_SHA256 = "9aa2f50dd3c38129a70f4ed042f2b7ae5a90d4234def40d70520aad13f36b3fc"
APPROVED_MANIFEST_REVISION = "2f5eb2d40df2d8549bb45f137e9f6b2c258e6ada"
MANIFEST_PATH = "tools/qualification/full-suite-manifest.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
LANE_GATES = frozenset(("staged-artifacts", "staged-consumer", "numerical-parity",
                        "physical-correctness", "unchanged-java-corpus",
                        "java-source-compatibility", "duplicate-provider"))
GLOBAL_GATES = frozenset(("migration-journeys", "performance-resource",
                          "publication-contract", "independent-review"))
PRODUCER_SCOPED_GATES = frozenset(("unchanged-java-corpus", "java-source-compatibility",
                                   "migration-journeys", "performance-resource",
                                   "independent-review"))
APPROVED_POLICY = {
    "tools/numerical/fixtures.json": "3086e982d8a4915634bd62d50dbfa0bf4f6e8cc0070a7a16d1f4bede9764d48a",
    "tools/numerical/compare.py": "4a6b4646683389aca643551b5672ca94d2f1e6dd49adad1c4684472b2b97348d",
    "tools/numerical/physical.py": "98ff243a02eece8a47a4faeda06385696174b2b10836e4e1315d6a13e22ee5ba",
    "tools/numerical/weld-pulley-physical-declaration.json": "9794a4ef64c93f6ff76afb03d98784b27be68fe413256362abf1a3f84cf96368",
    "tools/numerical/weld-pulley-physical-manifest.json": "5531b263fbd5a7684db0ea9fbef167c8d8772104949ce01ba4de7606498aecab",
    "tools/numerical/weld_pulley_quality.py": "f8c7cb7449b5d007e5c7dabb20e08deda93974b3cd8a4bedf0cd96f1640c2c87",
}
HISTORICAL_COMPARATOR_SHA256 = "6e9abe839c74ac9be1e8507e4a693b0414e70063f878481c94ab136c7ec89f4f"
APPROVED_COMPARATOR_REVISIONS = (
    "f0349a0d29f91879fc52286899f39e042c8523f6",
    "168fbfcdabd68cfb9317310958d6be7f52b38f05",
)
HISTORICAL_FIXTURE_SHA256 = "658f3216584a9842b9d9826767521f6bca1a9df0ed006b447a72a47d4915065c"
CURRENT_FIXTURE_REVISION = "b22ea2ddeb6c68242e688e9c9aa3214c4a8b495b"
APPROVED_MIGRATION = {
    "tools/migration/journeys.py": "f5111af3f263691446eae984904232d26a1d9392d6fa26881225bf8c9079b9b9",
    "tools/migration/validate_scene.py": "fa50bf08f0af86c173a4ec8775c4b6febb4b4c98099afd5dcb872ce97639ce6e",
    "tools/migration/validate_plain.py": "7fac38d996ff369c95d44a944050439df54f715924b825406136b7591d5b3f38",
}
MIGRATION_DEPENDENCIES = {
    "annotations-13.0.jar": "ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478",
    "kotlin-stdlib-2.4.20.jar": "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f",
}
REVIEWED_FULL_CI_REVISION = "00d2f949fd485287b737e905808bfb65be942733"
REVIEWED_FULL_CI_SHA256 = "f8e0bda794d141b1418b76ccd712306b9c9f1d587446fe79fcb4697b57885ad7"
NUMERICAL_SOURCE_HASH_METHOD = "SHA-256 of git archive --format=tar HEAD"
PROSPECTIVE_CASE_COUNT = 318
PROSPECTIVE_BRIDGE_METHODS = (
    "captureGeometry", "captureFreeMotion", "captureDefaultContacts",
    "captureConfigured30Repeat1", "captureConfigured30Repeat2",
    "captureConfigured60Repeat1", "captureConfigured60Repeat2",
    "captureConfigured120Repeat1", "captureConfigured120Repeat2",
    "captureJoints", "captureJointBooleanModes", "captureJointNumericModes",
    "captureAngleFailure", "captureCcd", "captureLongMotion")
JOINT_PHYSICAL_CASES = ("weld-spring-equal", "pulley-taut")
JOINT_PHYSICAL_STEPS = 36000
PROSPECTIVE_HISTORICAL_POLICY_REVISION = "7213238591db1611da86cdec075978190ca6d52f"
PROSPECTIVE_HISTORICAL_POLICY_SHA256 = "5c8e2ca48a2128b99b2f52188f0f556c3dad3030bde00975bc80d2a25b0c74bb"
PROSPECTIVE_PREVIOUS_POLICY_REVISION = "e038c334caa07a1547b86839f5d467c5f73ec708"
PROSPECTIVE_PREVIOUS_POLICY_SHA256 = "1b80b7c198d510ab16784348661053a4bde6507548f5ec12d4a460287ec7b484"
PROSPECTIVE_POLICY_REVISION = "83914cfc86f3add09ea65c89dc5b3e6035f709a0"
PROSPECTIVE_POLICY_PATH = "tools/numerical/portable/prospective_policy_catalog.json"
PROSPECTIVE_POLICY_SHA256 = "fab269814476a5a0c1d65f268f6c4177bb942ea8e7cdf1ea5ab8d4d9dcd2e160"
PROSPECTIVE_CHECKER_REVISION = "82e8a46448d4d6107e69de28cfa9df183292baf3"
PROSPECTIVE_REPRESENTED_CHECKER_REVISION = "2bd0d70f36b521949641a5404bdb3fa5890f61d3"
PROSPECTIVE_BRIDGE_CHECKER_REVISION = "6040b40265975b9091db430d79269cb5ea3d9868"
PROSPECTIVE_ASSEMBLED_CHECKER_REVISION = "b22ea2ddeb6c68242e688e9c9aa3214c4a8b495b"
APPROVED_PROSPECTIVE_CHECKERS = {
    "prospective_compare.py": "5ab8be61c17565d1feb4a23ceb588981f12d9e69213e0af97425a5f2a50f0ed9",
    "cases.py": "273c8246850d6995f0b3db1dac2d6f52d1c3154af1deaa48fbde25dc41f184c1",
    "orthogonality.py": "946bea6b9662a8f6e763ee9ce19374fa2b0b822a16a8e74ec355603576a5a15e",
    "reference_diagnostic.py": "f3e40a4671c8e07d5d0071f11818f9235d7a0f4a8ddfd784cb01604b0bb4b967",
    "receipt.py": "36c6c18255274195f58e4361e91d5fd7a5fc77eb9d5df01acc4abc0d36c75b0c",
}
APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS = {
    **APPROVED_PROSPECTIVE_CHECKERS,
    "prospective_compare.py": "f38b85d2e661182e6a5c3bef538f8127188197ee661c67dd1137c6e7c1d5f9d3",
}
APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS = {
    **APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS,
    "prospective_compare.py": "469c23f619b5b37ab79fc75d7b73328aae122d712104bbe094cf2357eda1cd07",
}
APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS = {
    **APPROVED_PROSPECTIVE_CHECKERS,
    "prospective_compare.py": "2f7743fed70ec9403492f84e880a286368a5f4c9f06f32c62996c91da837dd4f",
}
APPROVED_PROSPECTIVE_POLICY_CHECKERS = {
    **APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS,
    "cases.py": "d1613dfbd5f40adffabb960466010c22006261d8cf60f4711b49d8755c80e02c",
    "orthogonality.py": "a7fce390f154a9c044f20fb27803d104798cd6800bf8d757cc5ba9b862390644",
    "reference_diagnostic.py": "5d87eb26d11dabacc7caa0842a129d62d6e8f661a4b079c3383af309e7c6ef22",
}
P2_CLASS_LOAD_REVISION = "5b750850277a6e9d494483dc5fa2791b6d292233"
P2_NUMERICAL_ARCHIVE_OWNER_REVISION = "7641de9f0e544a8a29d5d583b91d0fb40029115b"
P2_NUMERICAL_ARCHIVE_REVISION = "4f2c7abb2cebd528515b7a5a0fd1497fd5511c86"
P2_CANONICAL_ARCHIVE_OWNER_REVISION = "606e6734613fc90677d3c30cabbf01c6a2e17ae4"
P2_CANONICAL_ARCHIVE_ASSEMBLY_REVISION = "48638f5acca9bf97532ce575809cf5e8472c93f7"
P2_ORIGINAL_OBJECT_OWNER_REVISION = "081b7c0be3bf92ffee28668538e61e2fade24081"
P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION = "8163c24141e49fea7570ffd139fc9a3ad6aca077"
P2_CURRENT_ASSEMBLY_REVISION = "24726f1f9e5c6c5cdad8dff3ea4e932265edd1c4"
P2_EDBC_ASSEMBLY_REVISION = "edbcfa5e219dd08b49a1fcef879dd5d458c23b1e"
P2_NATIVE_02C_ASSEMBLY_REVISION = "02cbc0a989e4d4b02a5305e8bf6d737251336ec8"
P2_DIRECT_WASM_22EFD_ASSEMBLY_REVISION = "22efd65082287ccbda2700c69899ba404b61602a"
P2_OPERATION_ASSEMBLY_REVISION = "0a8c7d74a2194c3e3b7428dddc273376dc854a0d"
P2_COMBINED_ASSEMBLY_REVISION = "3212df564682e95b33b4bd59b248733b5b34b219"
P2_ARITHMETIC_ASSEMBLY_REVISION = "a8273834c52b20d9e4b4ca732af7c7160b910d8f"
P2_ARITHMETIC_COVERAGE_ASSEMBLY_REVISION = "d981bdd2e6d915554f8fae1ea9b2c2a41cfcc7b0"
P2_PORTABLE_PROVIDER_ASSEMBLY_REVISION = "fac06d5240f8b030bfd9c5960d7784fa1a50c4f2"
P2_DYNAMIC_CLASS_ASSEMBLY_REVISION = "41926bd3d14a472f809c2e5693e6e774fb502ddc"
P2_GENERIC_CLASS_ASSEMBLY_REVISION = "fc576e69703b6757d7306be720a9834a59e81af6"
P2_D3D6_SOURCE_REVISION = "d3d6d554450060c8785209a6380535a33d87bfb4"
P2_BOOLEAN_JDI_HELPER_REVISION = "341276fd55ea23c35fabab4a859f520dd5831429"
P2_BOOLEAN_JDI_SOURCE_REVISION = "2a2c4b797b8adcdf3c03ee8475366ba2cfd9b16e"
P2_BOOLEAN_JDI_FINAL_SOURCE_REVISION = "1ef6554b4edb4e6066f5ae16ee64dbeda131d568"
P2_BOOLEAN_JDI_FINAL_ASSEMBLY_REVISION = "990910f697dbb8c183793796d0aca7a16c520815"
P2_ROTATION_PREMISE_SOURCE_REVISION = "a7fb17a65f936f4224e2a38a7481f2d698f2d155"
APPROVED_P2_PRODUCERS = {
    "actual_arithmetic.py": "5f02723e84401f612f4b7a1c72d7686b651e486e5153180ff80e2ec512faa1bf",
    "baseline_capture.py": "e4b4977da095744c3478ad6607a3281e4224f1ef83417c13dc88a51c9108bf34",
    "capture_actual.py": "68080114fe5e9f68d97514a8605e167a5e47328d36948cd239c1d4ca74ab6158",
    "rotation_oracle.py": "a95e4fba5883728dfe936c752daacd5a1fe0bb484dff4b14ddc9935b4a322ac6",
    "run.py": "fd584dee2d88f60d5e3c8abd4b8d040c70365a9024d690d0ba307e039addd233",
}
APPROVED_P2_CURRENT_PRODUCERS = {
    **APPROVED_P2_PRODUCERS,
    "baseline_capture.py": "0d61d0f942b6f0f977b028f47df183bcbd2f2d25add9300a787a30535f917847",
}
APPROVED_P2_EDBC_PRODUCERS = {
    **APPROVED_P2_CURRENT_PRODUCERS,
    "run.py": "4dd1f9eed602ae9cf3485fa64962edc3c541d087d9269dd5acd10ed1e22c1a97",
}
APPROVED_P2_NATIVE_02C_PRODUCERS = {
    **APPROVED_P2_EDBC_PRODUCERS,
    "run.py": "750273c0417ff633db79243e2b4df929104f6012b54f667168c176b450dea8cd",
}
APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS = {
    **APPROVED_P2_NATIVE_02C_PRODUCERS,
    "run.py": "7a52d41dcb96238402beee7cfc381ccb87b8ffd96ef247d602d92037bd073051",
}
APPROVED_P2_OPERATION_PRODUCERS = {
    **APPROVED_P2_NATIVE_02C_PRODUCERS,
    "actual_arithmetic.py": "d4ea004cd0056b85845b1a281e9caf386536c3707aa6a702258c720080656d5a",
    "capture_actual.py": "d27b6d615ab8425aa050933ea57b46cd6ff7b8e489f9ccbf2fa064cd7e6717f8",
    "rotation_oracle.py": "a765c8ab4ffda48df651ec0df923f3cfeff9de7a734c78155963ea851d489a3e",
}
APPROVED_P2_COMBINED_PRODUCERS = {
    **APPROVED_P2_OPERATION_PRODUCERS,
    "run.py": "7a52d41dcb96238402beee7cfc381ccb87b8ffd96ef247d602d92037bd073051",
}
APPROVED_P2_ARITHMETIC_PRODUCERS = {
    **APPROVED_P2_COMBINED_PRODUCERS,
    "actual_arithmetic.py": "dd3685fc1cf463682be36edf206ed78829333f53434a345bc3260927d7e27fdc",
    "rotation_oracle.py": "acb766b819eb314c65932e7357ac07314c93dcdd9acfd3ce48eb6c38a4ad1edd",
}
APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS = {
    **APPROVED_P2_ARITHMETIC_PRODUCERS,
    "rotation_oracle.py": "cf3b0906edb69b08cb24fb2be9a741ffacd3229a8ab466598887005d71109a47",
}
APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS = {
    **APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS,
    "actual_arithmetic.py": "e2e01e3c10de4e06c86365661821cb9c1ee6985b8944098683bd1f6039c8652b",
}
APPROVED_P2_DYNAMIC_CLASS_PRODUCERS = {
    **APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS,
    "actual_arithmetic.py": "e1732c31c7c3c290c81e379848b865b3b6968c63ebbc9d1dd03a6b6049fc7aa7",
}
APPROVED_P2_GENERIC_CLASS_PRODUCERS = {
    **APPROVED_P2_DYNAMIC_CLASS_PRODUCERS,
    "actual_arithmetic.py": "83454c14e4e72412f11acdeb15bc4c405c3bc651df542319e9ac3e94bf76fa4b",
}
P2_D3D6_PRODUCERS = {
    **APPROVED_P2_GENERIC_CLASS_PRODUCERS,
    "actual_arithmetic.py": "3d9f88a972e64f6d8ef5ae856091f6d35d49bb02d6a36774c4d84ecd8db6663c",
    "capture_actual.py": "9615eda6953125fa8fef0b991e4b4763c1db054625a587cdd2dac563874de265",
    "rotation_oracle.py": "0e7d89680e5fdac765b83a3c625c1e041b2c2e38a974492461fae150c8f46e9a",
}
P2_BOOLEAN_JDI_PRODUCERS = {
    **P2_D3D6_PRODUCERS,
    "actual_arithmetic.py": "6d1d478637b9645e6c007a2e5ce3def044742030698aefb3d792080a2be984c0",
    "capture_actual.py": "8f07d4d00877e1f57c74e75d99b052adb60c9f98c8b70f08691b8e533962106e",
}
P2_BOOLEAN_JDI_DEPENDENCIES = {
    "tools/numerical/portable/build.gradle.kts":
        "3d49cad9fd9205073f880cc20185856b2994c67e2e360cec64772d1e152a71f0",
    "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java":
        "bd83b069d0eea15872b916024b2c5fd9af553a1f0bb9b91b534932491155921f",
    "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py":
        "e041836cd3caf0ee0cfa847d66b718d9f10786ee9a914d85ebd4faac77e5dec7",
    "tools/numerical/portable/boolean_rotation_jdi/loaded_code.py":
        "1cc52a98ec4d93ad199f82831758bb61ae962f13da47f594a290f010a62087be",
    "tools/numerical/portable/boolean_rotation_jdi/source_guard.py":
        "5c44941dbe31ba0e2c196a53ed8fdfcd990aa51096661345e39731d54b132180",
    "tools/numerical/portable/boolean_rotation_jdi/witness.py":
        "dd7edfa3e0120520e4fd2fb2125e4f438cc73f0dbb08d70cb20ef0beddcb82a6",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/Transform.kt":
        "ec22ca59049bbe090f381f133a43d7e1e72b3b220960ec751c3f278b7b280747",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/collision/CollisionBody.kt":
        "71690455e111fbc3076885ef5a968a66e32616b334afdf428d8f9e56e74b0174",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/AbstractPhysicsBody.kt":
        "569979aee3583bf61d11dcffed236901257e606b207011c52f417e2ce1513719",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/RevoluteJoint.kt":
        "8be0bf63a1b2940a2570bd814040aaa1d6058862a1419528d02ed5c0f2748e58",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/AbstractPairedBodyJoint.kt":
        "90a4dc4bdf28e6ea785af699f5f40acd80afba86bf0e2a40a88ca03f8962d17f",
    "tools/numerical/portable/src/jvmTest/kotlin/portable/RevoluteLimitsFalseCaptureTest.kt":
        "d7a8467eb390a4c0db1544472fdb092420933470c879880f23ac64c2e43ff881",
}
P2_BOOLEAN_JDI_FINAL_PRODUCERS = {
    **P2_BOOLEAN_JDI_PRODUCERS,
    "actual_arithmetic.py": "2c3b33719c03ff2e57ac1eb6739bb248a554ed4efbf4b1e5fa59244e411b54d2",
    "capture_actual.py": "b3a867bfaf835bd41f998c93823375ec1e08b9ee4b2de8d2c52010447c28e5cc",
}
P2_BOOLEAN_JDI_FINAL_DEPENDENCIES = {
    **P2_BOOLEAN_JDI_DEPENDENCIES,
    "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java":
        "70990e22075d2c34bc6c03a194291ece66de13c11926494042b93d511f75c712",
    "tools/numerical/portable/boolean_rotation_jdi/jdi_bridge.py":
        "bc6662c300718d82af7eb7b13e089780a8caf41bb43694a90767044c0cda13cb",
    "tools/numerical/portable/boolean_rotation_jdi/loaded_code.py":
        "d76aeb947911108c29fc27b53ec2dced6648c160a78017eaf595a6d41fdb3235",
    "tools/numerical/portable/boolean_rotation_jdi/EndpointControl.java":
        "d32c7dbeb06c3c73f739faf8869ef485b13f853151369cea1d40cdefe6b948dd",
}
P2_ROTATION_PREMISE_PRODUCERS = {
    **P2_BOOLEAN_JDI_FINAL_PRODUCERS,
    "actual_arithmetic.py": "c5582c1062780019d47766e73d9af6536f636e66fc3ec593673eb2870db351f3",
    "capture_actual.py": "7842f3232b861485a63b1b1440e9b09f45c1bd66fe6f3d07e66dc05944b58a53",
    "rotation_oracle.py": "28642216813d88e9b6dc03e7006b83b992056297a113daf15218a7e641e3af14",
}
P2_ROTATION_PREMISE_DEPENDENCIES = {
    **P2_BOOLEAN_JDI_FINAL_DEPENDENCIES,
    "tools/numerical/portable/external_rotation_binding.py":
        "448a1e1e94a4d9929ca07f212545b45f3d2db120f66d05b374fe8914dbfa6a41",
    "tools/numerical/portable/src/jvmTest/kotlin/portable/RotationPremiseFixtureTest.kt":
        "ea960ab2a11aa5175c18cd14d13b59e96d285b28d1784a024a89ac207a479390",
}
APPROVED_P2_LOCAL_PRODUCERS = dict(P2_ROTATION_PREMISE_PRODUCERS)
APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS = {
    **APPROVED_P2_PRODUCERS,
    "baseline_capture.py": "b7bb228bde030d7fd6949ae3e7ca743a92060b436797835c6e4f7e12d779ad6c",
    "capture_actual.py": "aa95aa348dc0d78cab30afaf5f4ea4b64d36ab5e3d1e3e0aa35a12a6c6f44e0e",
    "run.py": "d789ab13f68c81c8351a6b91450adf91a7961327f93fbb6969a5ead7de7cf2d0",
}
APPROVED_P2_ORIGINAL_OBJECT_OWNER_PRODUCERS = {
    **APPROVED_P2_PRODUCERS,
    "actual_arithmetic.py": "b96043c57a918dabe8425961b02aff930a704e592c32baffc5645b94b84ce835",
}
APPROVED_P2_PRE_ARITHMETIC_PRODUCERS = {
    **APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS,
    "actual_arithmetic.py": "b96043c57a918dabe8425961b02aff930a704e592c32baffc5645b94b84ce835",
}
APPROVED_P2_CLASS_LOAD_PRODUCERS = {
    **APPROVED_P2_PRE_ARITHMETIC_PRODUCERS,
    "baseline_capture.py": "914e775309ffaa2ae4ea1690a22f83c055f422d7579e334e27d2fdf03d4e5a8f",
    "capture_actual.py": "2366b83a3314c72d208d49642609734536ae212c65db23025a7431dc636363b0",
    "run.py": "2bd20f332a15621b10f634dee7cf3551310e0dbe8b6465f4c55d7e5a5d420d7e",
}
APPROVED_P2_OWNER_CANONICAL_PRODUCERS = {
    **APPROVED_P2_CLASS_LOAD_PRODUCERS,
    "actual_arithmetic.py": "5f02723e84401f612f4b7a1c72d7686b651e486e5153180ff80e2ec512faa1bf",
}
APPROVED_P2_HISTORICAL_PRODUCERS = {
    **APPROVED_P2_CLASS_LOAD_PRODUCERS,
    "actual_arithmetic.py": "e51e768c7d2c9075b9e1900b2bf3ad0fdacbda42bb3eb0d6f52f49492b546675",
}
ROTATION_ORACLE_REVISION = "8b2959fbffb96486f6dcb1aef90fdbacf1e8a1cb"
ROTATION_ORACLE_SHA256 = "29de6401ef9253bee669714fdf31bade9291b4ee77d2aacaa34d62907f1bc238"
ROTATION_ORACLE_PATH = "tools/numerical/portable/rotation_oracle.py"
APPROVED_NOMINAL = {"tools/numerical/candidate/nominal_zero.py":
                    "8c54194ac8fa0b20e24db1e4eb6d072686fda5c4ecd0ee3c79abd45d686b7bc4"}
PRODUCER_MANIFEST_PATHS = {
    "unchanged-java-corpus": ("full-ci/lane-manifest.json",),
    "java-source-compatibility": ("full-ci/lane-manifest.json",),
    "migration-journeys": ("evidence/summary.json",),
    "performance-resource": ("evidence/candidate-identity-at-pilot.json",),
    "independent-review": ("standards.json", "spec.json"),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_approved_manifest(repository):
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{APPROVED_MANIFEST_REVISION}:{MANIFEST_PATH}"], stderr=subprocess.PIPE)
    manifest = json.loads(raw)
    if digest(manifest) != APPROVED_MANIFEST_SHA256:
        raise ValueError("approved complete-suite manifest changed")
    return manifest


def _result(gate, status, reason, **details):
    return {"gate": gate, "status": status, "reason": reason, **details}


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(path):
    value = json.loads(path.read_text(), object_pairs_hook=_strict_object,
                       parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    if not qualify.finite_json(value):
        raise ValueError(f"non-finite raw JSON observation: {path}")
    return value


def _file_path(root, relative):
    _file_path_name(relative)
    path = root.joinpath(*relative.split("/"))
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"raw archive file is missing or symbolic: {relative}")
    return path


def _archive_paths(root):
    return set(_archive_scan(root))


def _archive_identity(path):
    path = Path(path)
    state = path.lstat()
    attributes = getattr(state, "st_file_attributes", None)
    if (path.is_symlink() or path.is_junction()
            or (attributes is not None and attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
        raise ValueError(f"symbolic or reparse archive path: {path}")
    if os.name == "nt" and attributes is None:
        raise ValueError(f"Windows archive reparse status is unavailable: {path}")
    if type(state.st_ino) is not int or state.st_ino <= 0 or state.st_dev is None:
        raise ValueError(f"archive file identity is unavailable: {path}")
    if stat.S_ISREG(state.st_mode) and state.st_nlink != 1:
        raise ValueError(f"hardlinked archive file: {path}")
    if not stat.S_ISREG(state.st_mode) and not stat.S_ISDIR(state.st_mode):
        raise ValueError(f"nonregular archive path: {path}")
    return (state.st_dev, state.st_ino, state.st_mode, state.st_nlink,
            state.st_size, state.st_mtime_ns, state.st_ctime_ns, attributes)


def _archive_stable_identity(identity):
    return (*identity[:6], identity[7])


def _archive_ancestor_identity(identity):
    return (identity[0], identity[1], identity[2], identity[7])


def _archive_ancestor_handle_identity(state):
    return (state.st_dev, state.st_ino, state.st_mode,
            getattr(state, "st_file_attributes", None))


def _archive_handle_identity(state):
    return (state.st_dev, state.st_ino, state.st_mode, state.st_nlink,
            state.st_size, state.st_mtime_ns,
            getattr(state, "st_file_attributes", None))


@contextmanager
def _archive_directory(path, parent=None, name=None, ancestors=None):
    if os.name == "nt":
        from safari_windows_file import LockedDirectory
        with (LockedDirectory(path, resolve_root=False) if parent is None
              else parent.child(name)) as directory:
            yield directory
        return
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise ValueError("archive directory safe open is unavailable")
    descriptors = []
    try:
        if parent is None:
            current = Path(path.anchor)
            parts = [(current, current)]
            for part in path.parts[1:]:
                current = current / part
                parts.append((part, current))
        else:
            parts = [(name, path)]
        for target, current in parts:
            options = {"dir_fd": descriptors[-1]} if descriptors else (
                {"dir_fd": parent} if parent is not None else {})
            descriptor = os.open(target, os.O_RDONLY | directory_flag | nofollow,
                                 **options)
            descriptors.append(descriptor)
            if ancestors is not None:
                opened = os.fstat(descriptor)
                expected = ancestors[current]
                if current == path:
                    valid = _archive_handle_identity(opened) == _archive_stable_identity(expected)
                else:
                    valid = (_archive_ancestor_handle_identity(opened)
                             == _archive_ancestor_identity(expected))
                if not valid:
                    raise ValueError(f"archive ancestor changed during scan: {current}")
        yield descriptors[-1]
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _archive_scan(root):
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts or not root.is_dir():
        raise ValueError(f"archive path is absent or relative: {root}")
    ancestors = {path: _archive_identity(path) for path in (root, *root.parents)}
    for path, identity in ancestors.items():
        if not stat.S_ISDIR(identity[2]):
            raise ValueError(f"archive ancestor is not a directory: {path}")
    identities = {root: ancestors[root]}
    directory_members = {}
    files = {}
    seen = set()

    def visit(base, directory):
        with os.scandir(directory.path if os.name == "nt" else directory) as entries:
            members = list(entries)
        directory_members[base] = sorted(entry.name for entry in members)
        for entry in members:
            name = entry.name
            path = base / name
            relative = path.relative_to(root).as_posix()
            _file_path_name(relative)
            key = os.path.normcase(relative)
            if key in seen:
                raise ValueError(f"duplicate archive path: {relative}")
            seen.add(key)
            before = _archive_identity(path)
            identities[path] = before
            if stat.S_ISDIR(before[2]):
                with _archive_directory(path, directory, name) as child:
                    if os.name == "nt":
                        opened = _archive_identity(path)
                        if opened != before:
                            raise ValueError(f"archive directory identity changed: {relative}")
                    elif _archive_handle_identity(os.fstat(child)) != _archive_stable_identity(before):
                        raise ValueError(f"archive directory identity changed: {relative}")
                    visit(path, child)
                continue
            if os.name == "nt":
                handle = directory.open_file(name)
            else:
                handle = os.open(name, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                                 | os.O_NOFOLLOW, dir_fd=directory)
            try:
                opened = os.fstat(handle)
                if _archive_handle_identity(opened) != _archive_stable_identity(before):
                    raise ValueError(f"archive file identity changed: {relative}")
                sha = hashlib.sha256()
                while chunk := os.read(handle, 1024 * 1024):
                    sha.update(chunk)
                os.lseek(handle, 0, os.SEEK_SET)
                repeat = hashlib.sha256()
                while chunk := os.read(handle, 1024 * 1024):
                    repeat.update(chunk)
                if repeat.digest() != sha.digest():
                    raise ValueError(f"archive file changed during read: {relative}")
                closed = os.fstat(handle)
                if (_archive_handle_identity(closed) != _archive_handle_identity(opened)
                        or closed.st_ctime_ns != opened.st_ctime_ns):
                    raise ValueError(f"archive file changed during read: {relative}")
            finally:
                os.close(handle)
            if _archive_identity(path) != before:
                raise ValueError(f"archive file identity changed: {relative}")
            files[relative] = {"sha256": sha.hexdigest(), "mtime_ns": before[5],
                               "dev": before[0], "ino": before[1],
                               "nlink": before[3], "size": before[4],
                               "ctime_ns": before[6]}

    with _archive_directory(root, ancestors=ancestors) as directory:
        if os.name == "nt":
            for path, before in ancestors.items():
                if _archive_ancestor_identity(_archive_identity(path)) != _archive_ancestor_identity(before):
                    raise ValueError(f"archive ancestor changed during scan: {path}")
        elif _archive_handle_identity(os.fstat(directory)) != _archive_stable_identity(ancestors[root]):
            raise ValueError(f"archive root identity changed during scan: {root}")
        visit(root, directory)
        for path, before in identities.items():
            if _archive_identity(path) != before:
                raise ValueError(f"archive entry changed during scan: {path}")
        checked_ancestors = {**ancestors, **identities}
        for path, listed in directory_members.items():
            with _archive_directory(path, ancestors=checked_ancestors) as checked:
                with os.scandir(checked.path if os.name == "nt" else checked) as entries:
                    current_members = sorted(entry.name for entry in entries)
            if current_members != listed or _archive_identity(path) != identities[path]:
                raise ValueError(f"archive entry changed during scan: {path}")
        for path, before in ancestors.items():
            current = _archive_identity(path)
            expected = before if path == root else _archive_ancestor_identity(before)
            actual = current if path == root else _archive_ancestor_identity(current)
            if actual != expected:
                raise ValueError(f"archive ancestor changed during scan: {path}")
    return files


def _file_path_name(relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or "\n" in relative or "\r" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))
            or ":" in relative.split("/")[0]):
        raise ValueError(f"unsafe archive path: {relative}")


def _inventory(root, receipt):
    files = receipt.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("raw file inventory is missing")
    process = receipt.get("process")
    if not isinstance(process, dict):
        raise ValueError("raw process receipt is missing")
    started, finished = process.get("started_ns"), process.get("finished_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started):
        raise ValueError("raw process execution window is invalid")
    seen = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("raw file inventory entry is invalid")
        relative = item.get("path")
        if relative == "receipt.json":
            raise ValueError("receipt cannot inventory itself")
        path = _file_path(root, relative)
        if relative in seen:
            raise ValueError(f"duplicate archive path: {relative}")
        seen.add(relative)
        if (not SHA64.fullmatch(str(item.get("sha256", "")))
                or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]):
            raise ValueError(f"raw file hash differs: {relative}")
        mtime = item.get("mtime_ns")
        if type(mtime) is not int or not started <= mtime <= finished:
            raise ValueError(f"raw file timestamp differs from execution: {relative}")
        if path.stat().st_mtime_ns != mtime:
            raise ValueError(f"raw file filesystem timestamp differs: {relative}")
    actual = _archive_paths(root)
    if actual != seen | {"receipt.json"}:
        raise ValueError("archive has unlisted, missing, or duplicate files")
    return digest({"receipt": receipt, "files": sorted(files, key=lambda item: item["path"])})


def archive_digest(root):
    root = Path(root)
    paths = _archive_scan(root)
    if "receipt.json" not in paths:
        raise ValueError("raw receipt is absent")
    return digest([{"path": name, "sha256": paths[name]["sha256"],
                    "mtime_ns": paths[name]["mtime_ns"]}
                   for name in sorted(paths)])


def consumer_contract(manifest, lane_id):
    lane = manifest["lanes"][lane_id]
    scopes = set(lane["case_scopes"])
    cases = [item for item in manifest["cases"] if item["scope"] in scopes]
    if not cases or len({item["id"] for item in cases}) != len(cases):
        raise ValueError("approved staged consumer case contract is empty or duplicated")
    return {"target": lane["target"], "runtime": lane["runtime"],
            "version": lane["version"], "configuration": lane["configuration"],
            "cases": cases}


def _proven_ancestor(repository, revision, candidate_sha, label):
    prefix = ["git", "--no-replace-objects", "-C", str(repository)]
    shallow = subprocess.run(prefix + ["rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True, check=False)
    if shallow.returncode or shallow.stderr.strip() or shallow.stdout.strip() != "false":
        raise ValueError(f"{label} revision ancestry is unavailable")
    graft_path = subprocess.run(prefix + ["rev-parse", "--git-path", "info/grafts"],
                                capture_output=True, text=True, check=False)
    if graft_path.returncode or graft_path.stderr.strip() or not graft_path.stdout.strip():
        raise ValueError(f"{label} revision ancestry is unavailable")
    grafts = Path(graft_path.stdout.strip())
    if not grafts.is_absolute():
        grafts = Path(repository) / grafts
    if grafts.is_file() and grafts.stat().st_size:
        raise ValueError(f"{label} revision ancestry is unavailable")
    history = subprocess.run(prefix + ["rev-list", "--missing=print", candidate_sha],
                             capture_output=True, text=True, check=False)
    if (history.returncode or history.stderr.strip()
            or any(line.startswith("?") for line in history.stdout.splitlines())):
        raise ValueError(f"{label} revision ancestry is unavailable")
    checked = subprocess.run(prefix + ["merge-base", "--is-ancestor", revision,
                                       candidate_sha],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             check=False)
    if checked.returncode not in (0, 1) or checked.stderr:
        raise ValueError(f"{label} revision ancestry is unavailable")
    return checked.returncode == 0


def _policy_binding(repository, candidate_sha):
    fixture = "tools/numerical/fixtures.json"
    checker = "tools/numerical/compare.py"
    approved = _source_binding(repository, candidate_sha,
                               {path: value for path, value in APPROVED_POLICY.items()
                                if path not in (fixture, checker)},
                               "numerical approved policy/checker")
    local_checker = Path(__file__).resolve().parents[2] / checker
    if hashlib.sha256(local_checker.read_bytes()).hexdigest() != APPROVED_POLICY[checker]:
        raise ValueError(f"numerical approved policy/checker blob differs: {checker}")
    committed_checker = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:{checker}"], stderr=subprocess.PIPE)
    lineage = [_proven_ancestor(repository, revision, candidate_sha,
                                "numerical comparator")
               for revision in APPROVED_COMPARATOR_REVISIONS]
    expected_checker = (APPROVED_POLICY[checker] if any(lineage)
                        else HISTORICAL_COMPARATOR_SHA256)
    checker_digest = hashlib.sha256(committed_checker).hexdigest()
    if checker_digest != expected_checker:
        raise ValueError(f"numerical approved policy/checker blob differs: {checker}")
    local = Path(__file__).resolve().parents[2] / fixture
    committed = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:{fixture}"], stderr=subprocess.PIPE)
    candidate_digest = hashlib.sha256(committed).hexdigest()
    changed = _proven_ancestor(repository, CURRENT_FIXTURE_REVISION, candidate_sha,
                               "numerical fixture")
    expected_digest = (APPROVED_POLICY[fixture] if changed
                       else HISTORICAL_FIXTURE_SHA256)
    if (hashlib.sha256(local.read_bytes()).hexdigest() != APPROVED_POLICY[fixture]
            or candidate_digest != expected_digest):
        raise ValueError(f"numerical approved policy/checker blob differs: {fixture}")
    return {**approved, checker: checker_digest, fixture: candidate_digest}


def verified_numerical_source_sha256(repository, candidate_sha):
    if not isinstance(candidate_sha, str) or not SHA40.fullmatch(candidate_sha):
        raise ValueError("numerical source requires an exact candidate commit")
    archive = subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "--no-replace-objects",
         "-C", str(repository), "archive",
         "--format=tar", candidate_sha], stderr=subprocess.PIPE)
    return hashlib.sha256(archive).hexdigest()


def _prospective_policy_version(repository, candidate_sha):
    for revision, digest in (
            (PROSPECTIVE_POLICY_REVISION, PROSPECTIVE_POLICY_SHA256),
            (PROSPECTIVE_PREVIOUS_POLICY_REVISION, PROSPECTIVE_PREVIOUS_POLICY_SHA256),
            (PROSPECTIVE_HISTORICAL_POLICY_REVISION, PROSPECTIVE_HISTORICAL_POLICY_SHA256)):
        checked = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repository), "merge-base",
             "--is-ancestor", revision, candidate_sha],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if checked.returncode == 0:
            return revision, digest
        if checked.returncode != 1:
            raise ValueError("prospective policy revision ancestry is unavailable")
    return PROSPECTIVE_HISTORICAL_POLICY_REVISION, PROSPECTIVE_HISTORICAL_POLICY_SHA256


@lru_cache(maxsize=8)
def approved_prospective_catalog(repository, candidate_sha=None):
    revision, expected_sha = ((PROSPECTIVE_POLICY_REVISION, PROSPECTIVE_POLICY_SHA256)
                              if candidate_sha is None else
                              _prospective_policy_version(repository, candidate_sha))
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{revision}:{PROSPECTIVE_POLICY_PATH}"],
        stderr=subprocess.PIPE)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("adopted prospective policy catalog differs")
    catalog = json.loads(raw, object_pairs_hook=_strict_object)
    cases = catalog.get("cases")
    if (not isinstance(cases, dict) or len(cases) != PROSPECTIVE_CASE_COUNT
            or any(not isinstance(name, str) or not name for name in cases)):
        raise ValueError("adopted prospective case inventory differs")
    return catalog


def approved_prospective_cases(repository):
    return tuple(sorted(approved_prospective_catalog(str(repository))["cases"]))


def _prospective_checker_binding(repository, candidate_sha):
    source_dir = "tools/numerical/portable"
    def descends_from(revision):
        checked = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repository), "merge-base",
             "--is-ancestor", revision, candidate_sha],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if checked.returncode not in (0, 1):
            raise ValueError("prospective checker revision ancestry is unavailable")
        return checked.returncode == 0

    if descends_from(PROSPECTIVE_REPRESENTED_CHECKER_REVISION):
        approved = APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS
    elif descends_from(PROSPECTIVE_CHECKER_REVISION):
        committed_comparator = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate_sha}:{source_dir}/prospective_compare.py"],
            stderr=subprocess.PIPE)
        comparator_sha256 = hashlib.sha256(committed_comparator).hexdigest()
        approved = (APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS
                    if comparator_sha256 == APPROVED_PROSPECTIVE_SIGNED_ZERO_CHECKERS[
                        "prospective_compare.py"] else APPROVED_PROSPECTIVE_CHECKERS)
    elif descends_from(PROSPECTIVE_BRIDGE_CHECKER_REVISION):
        approved = APPROVED_PROSPECTIVE_CHECKERS
    elif descends_from(PROSPECTIVE_ASSEMBLED_CHECKER_REVISION):
        approved = APPROVED_PROSPECTIVE_ASSEMBLED_CHECKERS
    elif descends_from(PROSPECTIVE_HISTORICAL_POLICY_REVISION):
        approved = APPROVED_PROSPECTIVE_POLICY_CHECKERS
    else:
        raise ValueError("prospective checker candidate predates approved revisions")
    for filename, current in APPROVED_PROSPECTIVE_REPRESENTED_CHECKERS.items():
        relative = f"{source_dir}/{filename}"
        local = Path(__file__).resolve().parents[2] / relative
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate_sha}:{relative}"], stderr=subprocess.PIPE)
        if (hashlib.sha256(local.read_bytes()).hexdigest() != current
                or hashlib.sha256(committed).hexdigest() != approved[filename]):
            raise ValueError(f"prospective policy/checker blob differs: {relative}")
    catalog = f"{source_dir}/prospective_policy_catalog.json"
    committed = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:{catalog}"], stderr=subprocess.PIPE)
    _, catalog_sha256 = _prospective_policy_version(repository, candidate_sha)
    if (hashlib.sha256(committed).hexdigest() != catalog_sha256
            or hashlib.sha256((Path(__file__).resolve().parents[2] / catalog).read_bytes()).hexdigest()
            != PROSPECTIVE_POLICY_SHA256):
        raise ValueError(f"prospective policy/checker blob differs: {catalog}")
    return {f"{source_dir}/{name}": value for name, value in approved.items()} | {
        catalog: catalog_sha256}


def _missing_numerical_subgates(repository):
    cases = {case: {"rule": "NOT_RUN", "arithmetic": "NOT_RUN", "status": "NOT_RUN"}
             for case in approved_prospective_cases(str(repository))}
    return {"frozen-traces": {"status": "NOT_RUN", "required_cases": 14},
            "prospective-rule-arithmetic": {
                "status": "NOT_RUN", "required_cases": PROSPECTIVE_CASE_COUNT,
                "reason": "318 per-case rule comparisons and target arithmetic audits are absent",
                "reference_diagnostic": (
                    "historical b22ea2ddeb6c68242e688e9c9aa3214c4a8b495b 318-case "
                    "self-check with checker SHA-256 "
                    "2f7743fed70ec9403492f84e880a286368a5f4c9f06f32c62996c91da837dd4f: "
                    "41 failed derived rules, 4 unpassed premises, "
                    "1 failed physical; current checker 75-case geometry replay: "
                    "12 unpassed premises; current 318-case self-check NOT_RUN"),
                "cases": cases}}


def _missing_physical_profiles():
    return {"default-sleep-wake": {"candidate_status": "NOT_RUN",
                                   "approved_reference_status": "FAILED_125847_OF_126000"},
            "configured-sleep-wake": {"candidate_status": "NOT_RUN",
                                      "approved_reference_status": "PASSED"},
            "weld-pulley": {"candidate_status": "NOT_RUN",
                            "required_cases": len(JOINT_PHYSICAL_CASES),
                            "steps_per_case": JOINT_PHYSICAL_STEPS,
                            "approved_reference_status": "PASSED_BASELINE_ONLY",
                            "legacy_pulley_diagnostic": "39 old-reference samples exceeded the 0.005 m solver tolerance; observed maximum extension 0.1208278904872957 m",
                            "reason": "candidate Weld and Pulley physical traces are absent"},
            "nominal": {"candidate_status": "NOT_RUN",
                        "reason": "candidate nominal physical quality evidence is absent"}}


def _source_binding(repository, candidate_sha, approved_paths, label, local_approved=None):
    if local_approved is None:
        local_approved = approved_paths
    for relative, approved in approved_paths.items():
        local = Path(__file__).resolve().parents[2] / relative
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate_sha}:{relative}"],
            stderr=subprocess.PIPE)
        if (hashlib.sha256(local.read_bytes()).hexdigest() != local_approved[relative]
                or hashlib.sha256(committed).hexdigest() != approved):
            raise ValueError(f"{label} blob differs: {relative}")
    return dict(approved_paths)


def _p2_producer_binding(repository, candidate_sha):
    def descends_from(revision):
        checked = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repository), "merge-base",
             "--is-ancestor", revision, candidate_sha],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if checked.returncode not in (0, 1):
            raise ValueError("reviewed P2 raw producer revision ancestry is unavailable")
        return checked.returncode == 0

    if not descends_from(PROSPECTIVE_CHECKER_REVISION):
        raise ValueError("candidate predates reviewed P2 raw producer revision")
    rotation_premise = descends_from(P2_ROTATION_PREMISE_SOURCE_REVISION)
    boolean_jdi_final = descends_from(P2_BOOLEAN_JDI_FINAL_SOURCE_REVISION)
    boolean_jdi = descends_from(P2_BOOLEAN_JDI_SOURCE_REVISION)
    if rotation_premise:
        approved = P2_ROTATION_PREMISE_PRODUCERS
    elif boolean_jdi_final:
        approved = P2_BOOLEAN_JDI_FINAL_PRODUCERS
    elif boolean_jdi:
        approved = P2_BOOLEAN_JDI_PRODUCERS
    elif descends_from(P2_BOOLEAN_JDI_HELPER_REVISION):
        raise ValueError("candidate has incomplete Boolean JDI producer lineage")
    elif descends_from(P2_D3D6_SOURCE_REVISION):
        approved = P2_D3D6_PRODUCERS
    elif descends_from(P2_GENERIC_CLASS_ASSEMBLY_REVISION):
        approved = APPROVED_P2_GENERIC_CLASS_PRODUCERS
    elif descends_from(P2_DYNAMIC_CLASS_ASSEMBLY_REVISION):
        approved = APPROVED_P2_DYNAMIC_CLASS_PRODUCERS
    elif descends_from(P2_PORTABLE_PROVIDER_ASSEMBLY_REVISION):
        approved = APPROVED_P2_PORTABLE_PROVIDER_PRODUCERS
    elif descends_from(P2_ARITHMETIC_COVERAGE_ASSEMBLY_REVISION):
        approved = APPROVED_P2_ARITHMETIC_COVERAGE_PRODUCERS
    elif descends_from(P2_ARITHMETIC_ASSEMBLY_REVISION):
        approved = APPROVED_P2_ARITHMETIC_PRODUCERS
    elif descends_from(P2_COMBINED_ASSEMBLY_REVISION):
        approved = APPROVED_P2_COMBINED_PRODUCERS
    elif descends_from(P2_DIRECT_WASM_22EFD_ASSEMBLY_REVISION):
        approved = APPROVED_P2_DIRECT_WASM_22EFD_PRODUCERS
    elif descends_from(P2_OPERATION_ASSEMBLY_REVISION):
        approved = APPROVED_P2_OPERATION_PRODUCERS
    elif descends_from(P2_NATIVE_02C_ASSEMBLY_REVISION):
        approved = APPROVED_P2_NATIVE_02C_PRODUCERS
    elif descends_from(P2_EDBC_ASSEMBLY_REVISION):
        approved = APPROVED_P2_EDBC_PRODUCERS
    elif descends_from(P2_CURRENT_ASSEMBLY_REVISION):
        approved = APPROVED_P2_CURRENT_PRODUCERS
    elif descends_from(P2_ORIGINAL_OBJECT_ASSEMBLY_REVISION):
        approved = APPROVED_P2_PRODUCERS
    elif descends_from(P2_ORIGINAL_OBJECT_OWNER_REVISION):
        approved = APPROVED_P2_ORIGINAL_OBJECT_OWNER_PRODUCERS
    elif descends_from(P2_CANONICAL_ARCHIVE_ASSEMBLY_REVISION):
        approved = APPROVED_P2_PRE_ORIGINAL_OBJECT_PRODUCERS
    elif descends_from(P2_CANONICAL_ARCHIVE_OWNER_REVISION):
        approved = APPROVED_P2_OWNER_CANONICAL_PRODUCERS
    elif (descends_from(P2_NUMERICAL_ARCHIVE_REVISION)
          or descends_from(P2_NUMERICAL_ARCHIVE_OWNER_REVISION)):
        approved = APPROVED_P2_PRE_ARITHMETIC_PRODUCERS
    elif descends_from(P2_CLASS_LOAD_REVISION):
        approved = APPROVED_P2_CLASS_LOAD_PRODUCERS
    else:
        approved = APPROVED_P2_HISTORICAL_PRODUCERS
    source_dir = "tools/numerical/portable"
    for name, local_approved in APPROVED_P2_LOCAL_PRODUCERS.items():
        relative = f"{source_dir}/{name}"
        local = Path(__file__).resolve().parents[2] / relative
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate_sha}:{relative}"], stderr=subprocess.PIPE)
        if (hashlib.sha256(local.read_bytes()).hexdigest() != local_approved
                or hashlib.sha256(committed).hexdigest() != approved[name]):
            raise ValueError(f"reviewed P2 raw producer blob differs: {relative}")
    if rotation_premise:
        _source_binding(repository, candidate_sha, P2_ROTATION_PREMISE_DEPENDENCIES,
                        "rotation premise producer")
    elif boolean_jdi_final:
        _source_binding(repository, candidate_sha, P2_BOOLEAN_JDI_FINAL_DEPENDENCIES,
                        "Boolean JDI final producer",
                        local_approved=P2_ROTATION_PREMISE_DEPENDENCIES)
    elif boolean_jdi:
        _source_binding(repository, candidate_sha, P2_BOOLEAN_JDI_DEPENDENCIES,
                        "Boolean JDI producer",
                        local_approved=P2_ROTATION_PREMISE_DEPENDENCIES)
    return dict(approved)


def _numerical_modules(directory):
    compare_spec = importlib.util.spec_from_file_location(
        "dyn4k_approved_compare", directory / "compare.py")
    compare = importlib.util.module_from_spec(compare_spec)
    compare_spec.loader.exec_module(compare)
    previous = sys.modules.get("compare")
    sys.modules["compare"] = compare
    try:
        physical_spec = importlib.util.spec_from_file_location(
            "dyn4k_approved_physical", directory / "physical.py")
        physical = importlib.util.module_from_spec(physical_spec)
        physical_spec.loader.exec_module(physical)
    finally:
        if previous is None:
            del sys.modules["compare"]
        else:
            sys.modules["compare"] = previous
    return compare, physical


def _joint_quality_module(directory):
    compare, _ = _numerical_modules(directory)
    previous = sys.modules.get("compare")
    sys.modules["compare"] = compare
    try:
        specification = importlib.util.spec_from_file_location(
            "dyn4k_approved_joint_quality", directory / "weld_pulley_quality.py")
        quality = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(quality)
    finally:
        if previous is None:
            del sys.modules["compare"]
        else:
            sys.modules["compare"] = previous
    return quality


def _nominal_module(directory):
    compare, _ = _numerical_modules(directory)
    previous = sys.modules.get("compare")
    sys.modules["compare"] = compare
    try:
        specification = importlib.util.spec_from_file_location(
            "dyn4k_approved_nominal", directory / "candidate/nominal_zero.py")
        nominal = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(nominal)
    finally:
        if previous is None:
            del sys.modules["compare"]
        else:
            sys.modules["compare"] = previous
    return nominal


def verify_nominal_physical_case(root, receipt, candidate_sha,
                                 expected_artifact_hashes, source_sha, repository):
    row = receipt.get("nominal_physical_case")
    if row is None:
        return {"candidate_status": "NOT_RUN", "approved_reference_status": "PASSED_BASELINE_ONLY",
                "reason": "36,000-step nominal capture is absent"}
    if not isinstance(row, dict) or set(row) != {
            "key", "reference", "candidate", "capture_receipt"} or row["key"] != "nominal-free-motion":
        raise ValueError("nominal physical case identity or raw paths differ")
    _source_binding(repository, candidate_sha, APPROVED_NOMINAL,
                    "nominal physical validator")
    directory = Path(__file__).resolve().parents[1] / "numerical"
    nominal = _nominal_module(directory)
    fixture = nominal.compare.load_fixture("nominal-free-motion")
    reference = _file_path(root, row["reference"])
    candidate = _file_path(root, row["candidate"])
    capture = _file_path(root, row["capture_receipt"])
    outcome = nominal.compare_pair(
        fixture, reference, candidate, capture, source_sha,
        expected_artifact_hashes["dyn4k-core"], candidate_sha)
    status = outcome["status"]
    if status == "PASSED":
        observed = outcome["nominal_positive_zero"]["candidate"]
        timestep = outcome["nominal_timestep"]["candidate"]
        if (observed != {"states": 36000, "positive_zero_checks": 216000}
                or timestep != {"timestep_callbacks": 108001,
                                "exact_timestep_checks": 540005}):
            raise ValueError("nominal 36,000-step physical audit counts differ")
    return {"candidate_status": "PASSED" if status == "PASSED" else
            "FAILED" if status == "FAILED" else "NOT_RUN",
            "approved_reference_status": "PASSED_BASELINE_ONLY",
            "states": 36000, "callbacks": 108001,
            "reason": outcome.get("reason", outcome.get("unpassed_channels", []))}


def physical_status(profiles):
    required = ("default-sleep-wake", "configured-sleep-wake", "weld-pulley", "nominal")
    statuses = [profiles[name]["candidate_status"] for name in required]
    if any(status not in ("PASSED", "FAILED", "NOT_RUN") for status in statuses):
        raise ValueError("physical profile status differs")
    return "FAILED" if "FAILED" in statuses else "PASSED" if all(
        status == "PASSED" for status in statuses) else "NOT_RUN"


def verify_joint_physical_cases(root, receipt, candidate_sha,
                                expected_artifact_hashes, source_sha, repository=None):
    directory = Path(__file__).resolve().parents[1] / "numerical"
    repository = Path(repository) if repository is not None else Path(__file__).resolve().parents[2]
    declaration = _json(directory / "weld-pulley-physical-declaration.json")
    manifest = _json(directory / "weld-pulley-physical-manifest.json")
    quality = _joint_quality_module(directory)
    rows = receipt.get("joint_physical_cases")
    if rows is None:
        raise ValueError("36,000-step candidate Weld and Pulley traces are absent")
    if (not isinstance(rows, list) or len(rows) != len(JOINT_PHYSICAL_CASES)
            or {row.get("case") for row in rows if isinstance(row, dict)}
            != set(JOINT_PHYSICAL_CASES)):
        raise ValueError("candidate Weld/Pulley case identities or counts differ")
    capture_source = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:tools/numerical/candidate/physical/WeldPulleyPhysicalCapture.java"],
        stderr=subprocess.PIPE)
    capture_sha = hashlib.sha256(capture_source).hexdigest()
    build_config = hashlib.sha256()
    for filename in ("settings.gradle.kts", "build.gradle.kts"):
        content = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate_sha}:tools/numerical/candidate/{filename}"],
            stderr=subprocess.PIPE)
        build_config.update(filename.encode() + b"\0" + str(len(content)).encode()
                            + b"\0" + content)
    expected_artifact_path = str(Path("build/staging-repository") /
                                 qualify.target_binary_path("dyn4k-core", "jvm"))
    if (declaration.get("steps_per_case") != JOINT_PHYSICAL_STEPS
            or set(manifest.get("cases", {})) != set(JOINT_PHYSICAL_CASES)):
        raise ValueError("approved Weld/Pulley declaration or case set differs")
    failures = {}
    for row in rows:
        case = row["case"]
        reference = directory / "references" / manifest["cases"][case]["file"]
        baseline = quality.audit_quality(declaration, manifest, case, reference)
        if baseline["status"] != "PHYSICAL_PASSED":
            raise ValueError(f"{case} approved baseline physical archive differs")
        trace = _file_path(root, row.get("candidate"))
        capture = _json(_file_path(root, row.get("capture_receipt")))
        raw = trace.read_bytes()
        counts = manifest["cases"][case]["counts"]
        required_capture = {
            "candidate_commit": candidate_sha,
            "source_hash_method": NUMERICAL_SOURCE_HASH_METHOD,
            "source_sha256": source_sha,
            "artifact_sha256": expected_artifact_hashes["dyn4k-core"],
            "artifact_path": expected_artifact_path,
            "capture_sha256": capture_sha,
            "build_config_sha256": build_config.hexdigest(),
            "trace_sha256": hashlib.sha256(raw).hexdigest(),
            "reference_trace_sha256": manifest["cases"][case]["gzip_sha256"],
            "expected_counts": counts, "executed_counts": counts, "skipped": 0}
        if any(capture.get(key) != value for key, value in required_capture.items()):
            raise ValueError(f"{case} candidate physical capture identity or counts differ")
        if (not isinstance(capture.get("runtime"), dict)
                or not all(isinstance(value, str) and value
                           for value in capture["runtime"].values())
                or not isinstance(capture.get("physical"), dict)
                or capture["physical"].get("case") != case
                or capture["physical"].get("counts") != counts):
            raise ValueError(f"{case} candidate physical producer manifest is incomplete")
        records = iter(_numerical_modules(directory)[0].records(trace))
        try:
            _, header = next(records)
        except StopIteration as error:
            raise ValueError(f"{case} candidate physical trace is empty") from error
        if header != {"kind": "inputs", "case": case,
                       "declaration_sha256": manifest["declaration_sha256"],
                       "capture_sha256": capture_sha,
                       "source_revision": candidate_sha,
                       "jar_sha256": expected_artifact_hashes["dyn4k-core"],
                       "step_seconds": declaration["step_seconds"],
                       "steps": JOINT_PHYSICAL_STEPS}:
            raise ValueError(f"{case} candidate physical input or source identity differs")
        failed = {metric: 0 for metric in declaration["cases"][case]["metrics"]}
        for step in range(1, JOINT_PHYSICAL_STEPS + 1):
            for order, callback in enumerate(quality.CALLBACKS):
                try:
                    _, event = next(records)
                except StopIteration as error:
                    raise ValueError(f"{case} missing callback at step {step}") from error
                if event != {"kind": "event", "step": step, "order": order,
                             "callback": callback}:
                    raise ValueError(f"{case} callback identity or order differs")
            try:
                _, state = next(records)
            except StopIteration as error:
                raise ValueError(f"{case} missing state at step {step}") from error
            if state.keys() != {"kind", "step", "state"} or state["kind"] != "state" or state["step"] != step:
                raise ValueError(f"{case} state identity or order differs")
            metrics = quality.weld(state["state"]) if case == "weld-spring-equal" else quality.pulley(state["state"])
            for metric, (lower, upper) in metrics.items():
                ceiling = quality.limit(declaration, case, metric)
                if lower <= ceiling < upper:
                    raise ValueError(f"{case} physical metric straddles approved limit")
                if lower > ceiling:
                    failed[metric] += 1
        if next(records, None) is not None:
            raise ValueError(f"{case} candidate physical trace has extra records")
        failures[case] = failed
    return {"candidate_status": "FAILED" if any(any(row.values()) for row in failures.values()) else "PASSED",
            "required_cases": 2, "steps_per_case": JOINT_PHYSICAL_STEPS,
            "approved_reference_status": "PASSED_BASELINE_ONLY",
            "legacy_pulley_diagnostic": "39 old-reference samples exceeded the 0.005 m solver tolerance; observed maximum extension 0.1208278904872957 m",
            "failures": failures}


@lru_cache(maxsize=4)
def _approved_rotation_oracle(repository):
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{ROTATION_ORACLE_REVISION}:{ROTATION_ORACLE_PATH}"], stderr=subprocess.PIPE)
    if hashlib.sha256(raw).hexdigest() != ROTATION_ORACLE_SHA256:
        raise ValueError("approved arithmetic oracle blob differs")
    return ROTATION_ORACLE_SHA256


@lru_cache(maxsize=4)
def _rotation_oracle_module(repository):
    raw = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{ROTATION_ORACLE_REVISION}:{ROTATION_ORACLE_PATH}"], stderr=subprocess.PIPE)
    if hashlib.sha256(raw).hexdigest() != ROTATION_ORACLE_SHA256:
        raise ValueError("approved arithmetic oracle blob differs")
    module = types.ModuleType("dyn4k_approved_rotation_oracle")
    exec(compile(raw, ROTATION_ORACLE_PATH, "exec"), module.__dict__)
    return module


def _replay_target_arithmetic(root, oracle, identity, repository, payload, payload_bytes,
                              candidate_trace, catalog):
    required = {"binding", "binding_sha256", "receipt", "receipt_sha256",
                "target_source", "target_source_sha256", "target_source_git_path",
                "artifact", "artifact_sha256"}
    if not isinstance(oracle, dict) or set(oracle) != required:
        raise ValueError("prospective arithmetic oracle raw contract is incomplete")
    raw = {}
    for name in ("binding", "receipt", "target_source", "artifact"):
        raw[name] = _file_path(root, oracle[name]).read_bytes()
        if hashlib.sha256(raw[name]).hexdigest() != oracle[name + "_sha256"]:
            raise ValueError(f"prospective arithmetic oracle {name} differs")
    if oracle["artifact_sha256"] != identity["artifact_sha256"]:
        raise ValueError("prospective arithmetic oracle artifact differs from independent audit")
    _file_path_name(oracle["target_source_git_path"])
    committed_source = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{identity['candidate_commit']}:{oracle['target_source_git_path']}"],
        stderr=subprocess.PIPE)
    if committed_source != raw["target_source"]:
        raise ValueError("prospective arithmetic target source differs from candidate Git")
    if candidate_trace is None or catalog is None:
        raise ValueError("prospective arithmetic oracle lacks bound candidate trace or policy")
    compare, _ = _numerical_modules(Path(__file__).resolve().parents[1] / "numerical")
    records = [row for _, row in compare.records(candidate_trace)]
    if not records or records[0].get("kind") != "inputs":
        raise ValueError("prospective arithmetic trace header is absent")
    states = {row["step"]: row["state"] for row in records if row.get("kind") == "state"}
    case_id = identity["case_id"]
    reviewed = _rotation_oracle_module(str(repository)).verify_rotation_arithmetic(
        payload, {"id": case_id, "steps": catalog["cases"][case_id]["steps"]},
        records[0], states, catalog["rotation_caps"][case_id],
        binding=json.loads(raw["binding"], object_pairs_hook=_strict_object),
        trace_bytes=candidate_trace.read_bytes(), payload_bytes=payload_bytes,
        receipt_bytes=raw["receipt"], artifact_bytes=raw["artifact"],
        source_bytes=raw["target_source"])
    if reviewed.get("status", "").startswith("FAILED"):
        raise ValueError("prospective arithmetic oracle rejected raw operations: "
                         + reviewed.get("reason", reviewed["status"]))
    return "PASSED" if (reviewed.get("status") == "PASSED_ARITHMETIC"
                        and reviewed.get("qualification") == "PASSED") else "NOT_RUN"


def _target_arithmetic_evidence(root, audit, identity, repository,
                                candidate_trace=None, catalog=None):
    required = (set(identity) | {"schema", "oracle_revision", "oracle_sha256",
                                 "target_payload", "target_payload_sha256",
                                 "process_receipt", "process_receipt_sha256"})
    if (not isinstance(audit, dict) or set(audit) not in (required, required | {"oracle"})
            or audit.get("schema") != "target-arithmetic-evidence/1"
            or any(audit.get(key) != value for key, value in identity.items())):
        raise ValueError("prospective arithmetic producer manifest is incomplete or misbound")
    if (audit["oracle_revision"] != ROTATION_ORACLE_REVISION
            or audit["oracle_sha256"] != _approved_rotation_oracle(str(repository))):
        raise ValueError("approved arithmetic oracle identity differs")
    for key in ("target_payload", "process_receipt"):
        path = _file_path(root, audit[key])
        if hashlib.sha256(path.read_bytes()).hexdigest() != audit[key + "_sha256"]:
            raise ValueError(f"prospective arithmetic raw {key} differs")
    payload = _json(_file_path(root, audit["target_payload"]))
    process = _json(_file_path(root, audit["process_receipt"]))
    if (not isinstance(payload, dict) or payload.get("case_id") != identity["case_id"]
            or not ((isinstance(payload.get("runtime"), str) and payload["runtime"]
                     and isinstance(payload.get("operations"), list) and payload["operations"])
                    or (payload.get("schema") == "portable-rotation-audit/1"
                        and isinstance(payload.get("calls"), list)))):
        raise ValueError("prospective arithmetic target payload is incomplete")
    if (not isinstance(process, dict)
            or set(process) != {"command", "exit_code", "started_ns", "finished_ns",
                                "stdout", "stdout_sha256"}
            or not isinstance(process["command"], list) or not process["command"]
            or not all(isinstance(arg, str) and arg for arg in process["command"])
            or Path(process["command"][0]).name.lower() not in {"java", "node", "wasmtime",
                                                                  "adb", "xcrun", "gradlew", "gradle"}
            or type(process["exit_code"]) is not int or process["exit_code"] != 0
            or type(process["started_ns"]) is not int
            or type(process["finished_ns"]) is not int
            or process["started_ns"] <= 0
            or process["finished_ns"] < process["started_ns"]):
        raise ValueError("prospective arithmetic target process is incomplete")
    stdout = _file_path(root, process["stdout"]).read_bytes()
    if (hashlib.sha256(stdout).hexdigest() != process["stdout_sha256"]
            or f"ARITHMETIC_CASE={identity['case_id']}" not in stdout.decode().splitlines()):
        raise ValueError("prospective arithmetic target output differs")
    if "oracle" in audit:
        return _replay_target_arithmetic(root, audit["oracle"], identity, repository,
                                         payload, _file_path(root, audit["target_payload"]).read_bytes(),
                                         candidate_trace, catalog)
    return "NOT_RUN"


def _prospective_case_status(rule, arithmetic):
    if rule.startswith("FAILED") or arithmetic.startswith("FAILED"):
        return "FAILED"
    if rule != "PASSED_NUMERICAL_POLICY":
        return "NOT_RUN"
    return "PASSED" if arithmetic == "PASSED" else "NOT_RUN"


def _p2_scope(scope, candidate_sha, source_sha256, artifact_sha256, root):
    required = {"candidate_sha", "target", "runtime", "runtime_identity",
                "artifact_hashes", "source_sha256", "baseline_attestation_path",
                "baseline_attestation_sha256"}
    if not isinstance(scope, dict):
        raise IncompleteEvidence("independent numerical P2 JVM scope is missing")
    missing = required - set(scope)
    if missing:
        raise IncompleteEvidence("independent numerical P2 scope field is missing: "
                                 + ", ".join(sorted(missing)))
    if (set(scope) != required or scope["candidate_sha"] != candidate_sha
            or scope["target"] != "jvm" or scope["runtime"] != "Java"
            or not SHA64.fullmatch(str(scope["runtime_identity"]))
            or scope["source_sha256"] != source_sha256
            or not isinstance(scope["artifact_hashes"], dict)
            or set(scope["artifact_hashes"]) != set(qualify.MODULES)
            or scope["artifact_hashes"]["dyn4k-core"] != artifact_sha256
            or any(not SHA64.fullmatch(str(value)) for value in
                   scope["artifact_hashes"].values())
            or not SHA64.fullmatch(str(scope["baseline_attestation_sha256"]))):
        raise ValueError("independent numerical P2 source, JVM artifact, or attestation scope differs")
    sidecar = Path(scope["baseline_attestation_path"])
    if (not sidecar.is_absolute() or not sidecar.is_file() or sidecar.is_symlink()
            or sidecar.resolve().is_relative_to(root.resolve())):
        raise IncompleteEvidence("external numerical baseline attestation file is absent")
    if hashlib.sha256(sidecar.read_bytes()).hexdigest() != scope["baseline_attestation_sha256"]:
        raise ValueError("external numerical baseline attestation differs from independent audit")
    return sidecar


def _p2_runtime_identity(proof):
    required = {"host", "os", "machine", "device", "executable",
                "executable_sha256", "version", "method_executions",
                "dependency_sha256", "method_process_sha256"}
    if (not isinstance(proof, dict) or set(proof) != required
            or proof["host"] != "jvm" or proof["device"] is not False
            or proof["method_executions"] != 15
            or any(not isinstance(proof[key], str) or not proof[key]
                   for key in ("os", "machine", "executable", "version"))
            or not Path(proof["executable"]).is_absolute()
            or 'version "21.' not in proof["version"]
            or any(not SHA64.fullmatch(str(proof[key])) for key in
                   ("executable_sha256", "dependency_sha256",
                    "method_process_sha256"))):
        raise ValueError("reviewed P2 candidate runtime/process proof is incomplete")
    return digest({"schema": "reviewed-p2-runtime/1", "runtime": proof})


def _p2_directory(root, relative):
    _file_path_name(relative)
    directory = root.joinpath(*relative.split("/"))
    if not directory.is_dir() or directory.is_symlink():
        raise IncompleteEvidence(f"prospective raw directory is missing: {relative}")
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"prospective raw directory escapes archive: {relative}")
    return directory


def _p2_summary(summary, expected, methods, case_methods):
    rows = summary.get("results") if isinstance(summary, dict) else None
    evidence = summary.get("operation_evidence") if isinstance(summary, dict) else None
    if (not isinstance(rows, list) or len(rows) != PROSPECTIVE_CASE_COUNT
            or not isinstance(evidence, dict) or set(evidence) != set(methods)
            or not isinstance(case_methods, dict) or set(case_methods) != set(expected)
            or summary.get("operation_binding") != "VERIFIED_ARITHMETIC_BINDING"):
        raise ValueError("reviewed P2 verifier omitted raw operation or case coverage")
    identities = [row.get("id") for row in rows if isinstance(row, dict)]
    if identities != list(expected):
        raise ValueError("reviewed P2 comparison case identities or order differ")
    cases = {}
    for row in rows:
        case_id = row["id"]
        method = row.get("operation_method")
        if (method != case_methods[case_id] or method not in evidence or
                row.get("operation_receipt_sha256") != evidence[method].get("receipt_sha256") or
                not SHA64.fullmatch(str(row["operation_receipt_sha256"]))):
            raise ValueError(f"reviewed P2 operation method or receipt differs: {case_id}")
        rule = row.get("status")
        arithmetic = ("PASSED" if row.get("target_arithmetic") ==
                      "PASSED_BOUND_OPERATION_EVIDENCE" else "NOT_RUN")
        if not isinstance(rule, str):
            raise ValueError(f"reviewed P2 policy status is absent: {case_id}")
        status = _prospective_case_status(rule, arithmetic)
        if status == "PASSED" and row.get("qualification") != "PASSED_CASE_POLICY":
            raise ValueError(f"reviewed P2 policy qualification differs: {case_id}")
        cases[case_id] = {"rule": rule, "arithmetic": arithmetic,
                          "status": status, "method": method,
                          "receipt_sha256": row["operation_receipt_sha256"]}
    overall = ("FAILED" if any(item["status"] == "FAILED" for item in cases.values()) else
               "PASSED" if all(item["status"] == "PASSED" for item in cases.values()) else
               "NOT_RUN")
    return {"status": overall, "required_cases": PROSPECTIVE_CASE_COUNT,
            "methods_verified": len(evidence), "cases": cases,
            "reason": "reviewed P2 raw arithmetic and adopted case policy replayed"}


def _verify_p2_host(root, bridge, sidecar, repository, candidate_sha,
                    source_sha256, artifact_sha256):
    _prospective_checker_binding(repository, candidate_sha)
    _p2_producer_binding(repository, candidate_sha)
    baseline = _p2_directory(root, bridge["baseline"])
    candidate = _p2_directory(root, bridge["candidate"])
    arithmetic = _p2_directory(root, bridge["arithmetic"])
    if not (candidate / "jvm").is_dir():
        raise IncompleteEvidence("prospective JVM candidate lane is missing")
    portable = Path(__file__).resolve().parents[1] / "numerical/portable"
    previous = sys.dont_write_bytecode
    modules = ("prospective_compare", "actual_arithmetic", "baseline_capture", "run",
               "cases", "orthogonality", "reference_diagnostic", "receipt",
               "rotation_oracle")
    prior = {name: sys.modules.pop(name, None) for name in modules}
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(portable))
    try:
        from prospective_compare import compare_host
        from cases import declared_cases
        from actual_arithmetic import expected_case_ids
        frozen = {case["id"] for case in declared_cases()} - set(approved_prospective_cases(str(repository)))
        case_order = [case["id"] for case in declared_cases() if case["id"] not in frozen]
        case_methods = {case_id: method for method, ids in expected_case_ids().items()
                        for case_id in ids if case_id not in frozen}
        with tempfile.TemporaryDirectory(prefix="dyn4k-p2-replay-") as temporary:
            copied = Path(temporary)
            shutil.copytree(candidate, copied / "candidate")
            shutil.copytree(arithmetic, copied / "arithmetic")
            summary = compare_host(baseline, copied / "candidate/jvm", frozen,
                                   baseline_attestation=sidecar,
                                   arithmetic_captures=copied / "arithmetic")
            verified_runtime = _json(copied / "candidate/jvm/receipt.json").get("runtime")
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = previous
        for name in modules:
            sys.modules.pop(name, None)
            if prior[name] is not None:
                sys.modules[name] = prior[name]
    if (summary.get("candidate_source_sha256") != source_sha256
            or summary.get("candidate_artifact_sha256", {}).get("target") != artifact_sha256
            or summary.get("baseline_attestation_sha256") !=
            hashlib.sha256(sidecar.read_bytes()).hexdigest()):
        raise ValueError("reviewed P2 comparison source, artifact, or baseline differs")
    return summary, case_order, case_methods, _p2_runtime_identity(verified_runtime)


def verify_pending_prospective_bridge(root, receipt, repository, candidate_sha,
                                      artifact_sha256, source_sha256, scope=None):
    bridge = receipt.get("prospective_bridge")
    if (not isinstance(bridge, dict) or not {"inventory", "inventory_sha256"} <= set(bridge)
            or set(bridge) - {"inventory", "inventory_sha256", "baseline", "candidate",
                              "arithmetic"}):
        raise ValueError("prospective bridge inventory is missing or malformed")
    raw = _file_path(root, bridge["inventory"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != bridge["inventory_sha256"]:
        raise ValueError("prospective bridge inventory differs")
    inventory = _json(_file_path(root, bridge["inventory"]))
    if (not isinstance(inventory, dict)
            or set(inventory) != {"schema", "candidate_sha", "source_sha256",
                                  "artifact_sha256", "case_ids", "methods",
                                  "baseline_attestation_sha256"}
            or inventory["schema"] != "prospective-arithmetic-bridge/1"
            or inventory["candidate_sha"] != candidate_sha
            or inventory["source_sha256"] != source_sha256
            or inventory["artifact_sha256"] != artifact_sha256
            or inventory["case_ids"] != list(approved_prospective_cases(str(repository)))
            or not SHA64.fullmatch(str(inventory["baseline_attestation_sha256"]))
            or not isinstance(inventory["methods"], list)
            or [item.get("method") for item in inventory["methods"]
                if isinstance(item, dict)] != list(PROSPECTIVE_BRIDGE_METHODS)):
        raise ValueError("prospective bridge case, method, source, or artifact identity differs")
    paths = set()
    for item in inventory["methods"]:
        if not isinstance(item, dict) or set(item) != {"method", "receipt", "sha256"}:
            raise ValueError("prospective bridge method receipt is malformed")
        path = item["receipt"]
        if path in paths:
            raise ValueError("prospective bridge method receipt path is duplicated")
        paths.add(path)
        data = _file_path(root, path).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("prospective bridge method receipt differs")
        method_receipt = _json(_file_path(root, path))
        if (method_receipt.get("schema") != "portable-arithmetic-capture-receipt/3"
                or method_receipt.get("method") != item["method"]
                or method_receipt.get("candidate_commit") != candidate_sha
                or method_receipt.get("source_archive_sha256") != source_sha256
                or method_receipt.get("artifact_sha256") != artifact_sha256):
            raise ValueError(f"prospective bridge method is misbound: {item['method']}")
    if scope is None:
        return {"status": "NOT_RUN", "required_cases": PROSPECTIVE_CASE_COUNT,
                "transport_receipts": len(paths),
                "reason": "independent numerical P2 JVM scope and external baseline attestation are absent"}
    missing = {"baseline", "candidate", "arithmetic"} - set(bridge)
    if missing:
        raise IncompleteEvidence("prospective bridge raw archive field is missing: "
                                 + ", ".join(sorted(missing)))
    sidecar = _p2_scope(scope, candidate_sha, source_sha256, artifact_sha256, root)
    if inventory["baseline_attestation_sha256"] != scope["baseline_attestation_sha256"]:
        raise ValueError("prospective bridge baseline attestation differs from independent audit")
    summary, case_order, case_methods, runtime_identity = _verify_p2_host(
        root, bridge, sidecar, repository, candidate_sha, source_sha256, artifact_sha256)
    if runtime_identity != scope["runtime_identity"]:
        raise ValueError("reviewed P2 runtime identity differs from independent audit")
    if summary.get("candidate_artifact_sha256", {}).get("metadata") != \
            scope["artifact_hashes"]["dyn4k"]:
        raise ValueError("reviewed P2 metadata JAR differs from independent JVM audit")
    if set(case_order) != set(inventory["case_ids"]):
        raise ValueError("reviewed P2 source method/case inventory differs from bridge")
    result = _p2_summary(summary, case_order, PROSPECTIVE_BRIDGE_METHODS, case_methods)
    result["runtime_identity"] = runtime_identity
    return result


def verify_prospective_case_subgates(root, receipt, repository, candidate_sha,
                                     expected_artifact_hashes, source_sha):
    catalog = approved_prospective_catalog(str(repository), candidate_sha)
    expected = set(catalog["cases"])
    rows = receipt.get("prospective_cases")
    if (not isinstance(rows, list) or len(rows) != PROSPECTIVE_CASE_COUNT
            or {row.get("id") for row in rows if isinstance(row, dict)} != expected):
        raise ValueError("318 prospective rule/arithmetic raw case identities are missing or duplicated")
    _, catalog_sha256 = _prospective_policy_version(repository, candidate_sha)
    if receipt.get("prospective_catalog_sha256") != catalog_sha256:
        raise ValueError("adopted prospective catalog identity differs")
    approved_export = _prospective_checker_binding(repository, candidate_sha)
    for relative in ("tools/numerical/compare.py", "tools/numerical/fixtures.json"):
        committed = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repository), "show",
             f"{candidate_sha}:{relative}"], stderr=subprocess.PIPE)
        approved_export[relative] = hashlib.sha256(committed).hexdigest()
    portable = "tools/numerical/portable"
    archive = subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "--no-replace-objects",
         "-C", str(repository), "archive", candidate_sha,
         portable, "tools/numerical/compare.py", "tools/numerical/fixtures.json"],
        stderr=subprocess.PIPE)
    with tempfile.TemporaryDirectory(prefix="dyn4k-prospective-checker-") as temporary:
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(temporary, filter="data")
        for relative, expected_sha in approved_export.items():
            exported = Path(temporary) / relative
            if (not exported.is_file() or exported.is_symlink()
                    or hashlib.sha256(exported.read_bytes()).hexdigest() != expected_sha):
                raise ValueError(f"prospective exported checker differs: {relative}")
        package_path = str(Path(temporary) / portable)
        names = ("prospective_compare", "cases", "orthogonality", "reference_diagnostic",
                 "receipt", "compare")
        prior = {name: sys.modules.get(name) for name in names}
        previous_bytecode = sys.dont_write_bytecode
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, package_path)
        try:
            import prospective_compare
            declared = {case["id"]: case for case in prospective_compare.declared_cases()
                        if case["id"] in expected}
            if set(declared) != expected:
                raise ValueError("prospective executable case declarations differ")
            cases = {}
            for row in rows:
                case_id = row["id"]
                if set(row) != {"id", "reference", "candidate", "capture_receipt", "arithmetic_audit"}:
                    raise ValueError(f"{case_id} prospective raw fields differ")
                reference = _file_path(root, row["reference"])
                candidate = _file_path(root, row["candidate"])
                capture = _json(_file_path(root, row["capture_receipt"]))
                arithmetic = _json(_file_path(root, row["arithmetic_audit"]))
                required = {"case_id": case_id, "candidate_commit": candidate_sha,
                            "source_hash_method": NUMERICAL_SOURCE_HASH_METHOD,
                            "source_sha256": source_sha,
                            "artifact_sha256": expected_artifact_hashes["dyn4k-core"],
                            "trace_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                            "expected_steps": declared[case_id]["steps"],
                            "executed_steps": declared[case_id]["steps"], "skipped": 0}
                if any(capture.get(key) != value for key, value in required.items()):
                    raise ValueError(f"{case_id} prospective capture source, artifact, or step identity differs")
                if (arithmetic.get("case_id") != case_id
                        or arithmetic.get("candidate_commit") != candidate_sha
                        or arithmetic.get("trace_sha256") != required["trace_sha256"]):
                    raise ValueError(f"{case_id} target arithmetic raw audit identity differs")
                arithmetic_status = _target_arithmetic_evidence(
                    root, arithmetic,
                    {"case_id": case_id, "candidate_commit": candidate_sha,
                     "source_sha256": source_sha,
                     "artifact_sha256": expected_artifact_hashes["dyn4k-core"],
                     "trace_sha256": required["trace_sha256"]}, repository,
                    candidate, catalog)
                prospective_compare.verify_reference_inventory(reference, case_id, catalog)
                compared = prospective_compare.compare_policy_case(
                    reference, candidate, declared[case_id], catalog)
                rule = compared["status"]
                cases[case_id] = {"rule": rule,
                                  "arithmetic": arithmetic_status,
                                  "status": _prospective_case_status(rule, arithmetic_status)}
            overall = ("FAILED" if any(item["status"] == "FAILED" for item in cases.values()) else
                       "PASSED" if all(item["status"] == "PASSED" for item in cases.values()) else "NOT_RUN")
            return {"status": overall,
                    "required_cases": PROSPECTIVE_CASE_COUNT,
                    "reason": ("all adopted rule and arithmetic cases verified" if overall == "PASSED" else
                               "target arithmetic audits remain unqualified or incomplete"),
                    "cases": cases}
        finally:
            sys.path.pop(0)
            source_parent = str(Path(temporary) / "tools/numerical")
            if source_parent in sys.path:
                sys.path.remove(source_parent)
            sys.dont_write_bytecode = previous_bytecode
            for name in names:
                sys.modules.pop(name, None)
                if prior[name] is not None:
                    sys.modules[name] = prior[name]


def _producer_scope(gate, candidate_sha, scopes):
    scope = scopes.get(gate) if isinstance(scopes, dict) else None
    required_fields = {"candidate_sha", "target", "runtime", "runtime_identity",
                       "artifact_hashes"}
    extra = ({"producer_manifest_hashes", "verifier_sha256", "policy_sha256"}
             if gate == "performance-resource" else {"producer_manifest_hashes"})
    if (not isinstance(scope, dict) or not required_fields <= set(scope)
            or set(scope) - required_fields - extra):
        raise ValueError(f"{gate} independent producing artifact/runtime scope is missing")
    if "producer_manifest_hashes" not in scope:
        raise ValueError(f"{gate} independently pinned producer manifest is missing")
    if scope["candidate_sha"] != candidate_sha:
        raise ValueError(f"{gate} producing source commit differs from exact candidate")
    expected_target = "source" if gate == "independent-review" else "jvm"
    expected_runtime = "codex" if gate == "independent-review" else "Java"
    if (scope["target"] != expected_target or scope["runtime"] != expected_runtime
            or not isinstance(scope["runtime_identity"], str)
            or not scope["runtime_identity"]):
        raise ValueError(f"{gate} producing target or runtime identity differs")
    hashes = scope["artifact_hashes"]
    required = (set() if gate == "independent-review" else
                {"dyn4k-core"} if gate == "migration-journeys" else
                set(qualify.MODULES))
    if (not isinstance(hashes, dict) or set(hashes) != required
            or any(not SHA64.fullmatch(str(value)) for value in hashes.values())):
        raise ValueError(f"{gate} producing artifact hashes are incomplete")
    manifests = scope["producer_manifest_hashes"]
    accepted_paths = ({frozenset(PRODUCER_MANIFEST_PATHS[gate]),
                       frozenset({"evidence/archive.json"})}
                      if gate == "performance-resource" else
                      {frozenset(PRODUCER_MANIFEST_PATHS[gate])})
    if (not isinstance(manifests, dict)
            or frozenset(manifests) not in accepted_paths
            or any(not SHA64.fullmatch(str(value)) for value in manifests.values())):
        raise ValueError(f"{gate} independently pinned producer manifest is missing")
    if gate == "performance-resource" and "evidence/archive.json" in manifests:
        if any(not SHA64.fullmatch(str(scope.get(name, ""))) for name in
               ("verifier_sha256", "policy_sha256")):
            raise ValueError("sustained performance verifier or approved policy pin is missing")
    elif set(scope) - required_fields - {"producer_manifest_hashes"}:
        raise ValueError(f"{gate} unexpected producing verifier scope")
    return scope


def _producer_manifest_contract(root, gate, scope, candidate_sha):
    for relative, expected in scope["producer_manifest_hashes"].items():
        manifest_file = _file_path(root, relative)
        if hashlib.sha256(manifest_file.read_bytes()).hexdigest() != expected:
            raise ValueError(f"{gate} producer manifest differs from independent audit: {relative}")
        manifest = _json(manifest_file)
        if not isinstance(manifest, dict):
            raise ValueError(f"{gate} producer manifest is not an object: {relative}")
        source_field = ("candidate_commit" if gate == "migration-journeys" else
                        "source_commit" if gate == "performance-resource" else "candidate_sha")
        if manifest.get(source_field) != candidate_sha:
            raise ValueError(f"{gate} producer manifest source differs from exact candidate")
        if gate in ("unchanged-java-corpus", "java-source-compatibility"):
            if manifest.get("status") != "PASSED" or len(manifest.get("files", {})) != 24:
                raise ValueError("reviewed full_ci producer manifest is incomplete")
        elif gate == "migration-journeys":
            if (manifest.get("expected_cases") != 10 or manifest.get("passed_cases") != 10
                    or manifest.get("failed_cases") != 0
                    or manifest.get("unavailable_cases") != 0):
                raise ValueError("migration producer manifest omits ten journeys")
        elif gate == "independent-review":
            if manifest.get("review_kind") != Path(relative).stem:
                raise ValueError("independent review producer manifest kind differs")


def _binding(root, receipt, candidate_sha, lane_id, lane, repository,
             expected_artifact_hashes, expected_runtime_identity, gate,
             expected_producer_scopes):
    import full_klib_consumer

    klib_schema = (gate == "staged-consumer" and receipt.get("schema") == 2
                   and lane_id in full_klib_consumer.LOCAL_LANES)
    if (receipt.get("schema") != 1 and not klib_schema
            or receipt.get("candidate_sha") != candidate_sha):
        raise ValueError("raw candidate SHA differs")
    source_tree = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse", f"{candidate_sha}^{{tree}}"],
        text=True, stderr=subprocess.PIPE).strip()
    if receipt.get("source_tree") != source_tree:
        raise ValueError("raw Git source tree differs from exact candidate")
    if gate not in GLOBAL_GATES or receipt.get("lane") is not None:
        if receipt.get("lane") != lane_id:
            raise ValueError("raw lane differs")
        for key in ("target", "runtime", "version", "configuration"):
            if receipt.get(key) != lane.get(key):
                raise ValueError(f"raw {key} differs from selected lane")
        if gate not in PRODUCER_SCOPED_GATES and (
                not isinstance(expected_runtime_identity, str) or not expected_runtime_identity
                or receipt.get("runtime_identity") != expected_runtime_identity):
            raise ValueError("raw runtime identity differs from independent selection")
    if gate in PRODUCER_SCOPED_GATES:
        scope = _producer_scope(gate, candidate_sha, expected_producer_scopes)
        if (receipt.get("producer_scope") != scope
                or receipt.get("runtime_identity") != scope["runtime_identity"]):
            raise ValueError("raw producing artifact/runtime scope differs from independent selection")
        _producer_manifest_contract(root, gate, scope, candidate_sha)
        selected_hashes = scope["artifact_hashes"]
    else:
        if (not isinstance(expected_artifact_hashes, dict)
                or set(expected_artifact_hashes) != set(qualify.MODULES)
                or any(not SHA64.fullmatch(str(value)) for value in expected_artifact_hashes.values())):
            raise ValueError("independently audited target binary hashes are missing")
        selected_hashes = expected_artifact_hashes
    if receipt.get("artifact_hashes") != selected_hashes:
        raise ValueError("raw artifact hashes differ from independent staging audit")
    process = receipt.get("process")
    if (not isinstance(process, dict) or not isinstance(process.get("command"), list)
            or not process["command"] or not all(isinstance(arg, str) and arg for arg in process["command"])
            or type(process.get("exit_code")) is not int):
        raise ValueError("raw command or exit code is missing")
    for key in ("stdout", "stderr"):
        if key in process:
            _file_path(root, process[key])
    return process


def _process_proof(root, process, gate, lane_id, receipt=None):
    import full_klib_consumer

    command = process["command"]
    executable = Path(command[0]).name.lower()
    allowed = {"gradlew", "gradle", "adb", "xcrun", "node", "wasmtime",
               "podman", "python", "python3", "java", "javac", "codex"}
    if executable not in allowed:
        raise ValueError(f"raw {gate} command has no recognized execution launcher")
    if executable in {"python", "python3"} and not any(
            arg.endswith((".py", ".sh")) for arg in command[1:]):
        raise ValueError(f"raw {gate} Python command lacks an executable verifier")
    if gate in ("staged-consumer", "duplicate-provider", "staged-artifacts",
                "publication-contract"):
        if executable not in {"gradlew", "gradle", "adb", "xcrun", "node",
                              "wasmtime", "podman"}:
            raise ValueError(f"raw {gate} command does not launch a consumer or staging task")
        if "stdout" not in process:
            raise ValueError(f"raw {gate} process output is missing")
        output = _file_path(root, process["stdout"]).read_text()
        klib_v2 = (gate == "staged-consumer" and isinstance(receipt, dict)
                   and receipt.get("schema") == 2 and lane_id in command
                   and lane_id in full_klib_consumer.LOCAL_LANES)
        marker = f"QUALIFICATION_LANE={lane_id}"
        lines = output.splitlines()
        if klib_v2:
            lane_seen = any(line == marker or line.endswith(
                " [QUIET] [system.out] " + marker) or line ==
                "[QUIET] [system.out] " + marker for line in lines)
        else:
            lane_seen = marker in lines
        if not lane_seen:
            raise ValueError(f"raw {gate} output lacks exact lane execution marker")
        if executable in {"gradlew", "gradle"}:
            task_pattern = (r"(?m)^(?:[^\n]+ )?\[LIFECYCLE\] \[[^\]\n]+\] > Task :[^\s]+$"
                            if klib_v2 else r"(?m)^> Task :[^\s]+")
            if not re.search(task_pattern, output):
                raise ValueError(f"raw {gate} Gradle task output is absent")
            expected = "BUILD FAILED" if process["exit_code"] != 0 else "BUILD SUCCESSFUL"
            if expected not in output:
                raise ValueError(f"raw {gate} Gradle outcome is absent")
        elif "QUALIFICATION_PROCESS_EXIT=" + str(process["exit_code"]) not in output.splitlines():
            raise ValueError(f"raw {gate} runtime exit marker is absent")
    return executable


def _process_file_binding(root, process, relative, label):
    path = _file_path(root, relative)
    marker = f"QUALIFICATION_{label}_SHA256={hashlib.sha256(path.read_bytes()).hexdigest()}"
    output = _file_path(root, process["stdout"]).read_text()
    if not any(line == marker or line.endswith(" " + marker)
               for line in output.splitlines()):
        raise ValueError(f"raw process output does not bind {relative}")


def _duplicate_provider(root, receipt, process):
    graph_path = _file_path(root, receipt.get("provider_graph"))
    _process_file_binding(root, process, receipt["provider_graph"], "PROVIDER_GRAPH")
    graph = graph_path.read_text()
    try:
        qualify.check_providers(graph)
    except ValueError as error:
        if ("duplicate org.dyn4j provider" not in str(error)
                or process["exit_code"] == 0
                or "stderr" not in process
                or "duplicate org.dyn4j provider" not in
                _file_path(root, process["stderr"]).read_text()):
            raise ValueError("duplicate provider diagnostic or failure is absent") from error
    else:
        raise ValueError("both provider coordinates are absent from raw graph")
    if not any("dependenc" in arg.lower() or "provider" in arg.lower()
               for arg in process["command"][1:]):
        raise ValueError("raw command does not run provider dependency diagnosis")
    task = process["command"][-1].split(":")[-1]
    output = _file_path(root, process["stdout"]).read_text()
    if not any(line.startswith("> Task :") and line.split(":")[-1].split()[0] == task
               for line in output.splitlines()):
        raise ValueError("raw provider task output differs from executed command")
    return "raw provider graph, command output, and failing diagnostic agree"


def _external_unavailable(receipt, candidate_sha, lane_id, gate):
    reason = receipt.get("reason")
    if (receipt.get("schema") != 1 or receipt.get("candidate_sha") != candidate_sha
            or (gate not in GLOBAL_GATES and receipt.get("lane") != lane_id)
            or (receipt.get("lane") is not None and receipt.get("lane") != lane_id)
            or not isinstance(reason, str) or not reason.strip()
            or not isinstance(receipt.get("observed_by"), str)
            or not receipt["observed_by"].strip()
            or type(receipt.get("observed_at_ns")) is not int
            or receipt["observed_at_ns"] <= 0):
        raise ValueError("external unavailability observation is incomplete or misbound")
    return _result(gate, "UNAVAILABLE", reason,
                   observation_sha256=digest(receipt))


def _validated_all_target_hashes(hashes):
    targets = {row["target"] for row in qualify.matrix()}
    if (not isinstance(hashes, dict) or set(hashes) != targets
            or any(not isinstance(value, dict) or set(value) != set(qualify.MODULES)
                   or any(not SHA64.fullmatch(str(sha)) for sha in value.values())
                   for value in hashes.values())):
        raise ValueError("independently audited 21-target binary hash map is incomplete")
    return hashes


def _gate_artifact_hashes(gate, lane, lane_hashes, all_target_hashes):
    if lane["target"] == "jvm" and gate in ("staged-artifacts", "publication-contract"):
        if all_target_hashes is None:
            raise ValueError("independently audited 21-target binary hash map is missing")
        return _validated_all_target_hashes(all_target_hashes)["jvm"]
    return lane_hashes


def _staged_publication(root, candidate_sha, lane, expected_artifact_hashes,
                        repository, expected_all_target_hashes=None):
    staging = root / "staged"
    if not staging.is_dir() or staging.is_symlink():
        raise ValueError("full staged repository is missing")
    audit = qualify.audit_staging(staging, candidate_sha)
    if audit["status"] != "PASSED":
        raise ValueError("full staged publication audit failed: " + "; ".join(audit["errors"][:4]))
    license_bytes = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate_sha}:LICENSE.md"],
        stderr=subprocess.PIPE)
    for item in audit["artifacts"]:
        path = staging / item["path"]
        if "license" in path.name.lower() and path.suffix == ".md":
            if path.read_bytes() != license_bytes:
                raise ValueError(f"staged license differs from exact candidate: {item['path']}")
        elif path.suffix == ".jar" and "sources" not in path.name and "javadoc" not in path.name:
            with zipfile.ZipFile(path) as package:
                if package.read("META-INF/LICENSE.md") != license_bytes:
                    raise ValueError(f"embedded license differs from exact candidate: {item['path']}")
    if expected_all_target_hashes is not None:
        _validated_all_target_hashes(expected_all_target_hashes)
        if expected_all_target_hashes[lane["target"]] != expected_artifact_hashes:
            raise ValueError("selected target hashes differ from all-target audit")
        selected = expected_all_target_hashes
    else:
        selected = {lane["target"]: expected_artifact_hashes}
    for target, hashes in selected.items():
        for module in qualify.MODULES:
            binary = staging / qualify.target_binary_path(module, target)
            if not binary.is_file() or binary.is_symlink():
                raise ValueError(f"staged target binary is missing: {target}/{module}")
            if qualify.digest(binary) != hashes[module]:
                raise ValueError(f"staged target binary differs from independent audit: {target}/{module}")
    return f"full staged audit verified {len(audit['artifacts'])} publication files"


def _migration_journeys(root, candidate_sha, expected_artifact_hashes):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migration"))
    try:
        import journeys
        import validate_plain
        import validate_scene
        report = journeys.verify_evidence(root / "evidence")
    finally:
        sys.path.pop(0)
    if (report.get("candidate_commit") != candidate_sha or
            report.get("source_revision") != journeys.SAMPLE_REVISION or
            report.get("source_manifest_sha256") != journeys.SOURCE_MANIFEST_SHA256 or
            report.get("expected_cases") != 10 or report.get("passed_cases") != 10 or
            report.get("failed_cases") != 0 or report.get("unavailable_cases") != 0):
        raise ValueError("migration source, candidate, or ten journey counts differ")
    cases = report.get("cases")
    if (not isinstance(cases, list) or len(cases) != 10 or
            {(case.get("provider"), case.get("scene")) for case in cases}
            != {(provider, scene) for provider in journeys.PROVIDERS
                for scene in journeys.SCENES} or
            any(case.get("status") != "PASSED" for case in cases)):
        raise ValueError("migration journey identities or outcomes differ")
    source_manifest = _file_path(root, "evidence/sources.sha256").read_bytes()
    if hashlib.sha256(source_manifest).hexdigest() != journeys.SOURCE_MANIFEST_SHA256:
        raise ValueError("42 unchanged sample source identities differ from pinned manifest")
    source_rows = source_manifest.decode().splitlines()
    if len(source_rows) != 42 or len(set(source_rows)) != 42:
        raise ValueError("42 unchanged Java source records are incomplete")
    source_paths = []
    for row in source_rows:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+\.java)", row)
        if match is None:
            raise ValueError("unchanged Java source manifest row is invalid")
        source_paths.append(match[2])
        if hashlib.sha256(_file_path(root, "evidence/sources/" + match[2]).read_bytes()).hexdigest() != match[1]:
            raise ValueError(f"unchanged Java source bytes differ: {match[2]}")
    if source_paths != sorted(source_paths):
        raise ValueError("unchanged Java source manifest is not sorted")
    sample_check = _json(_file_path(root, "evidence/sample-check.json"))
    if (sample_check.get("status") != "PASSED" or sample_check.get("revision") != journeys.SAMPLE_REVISION
            or sample_check.get("java_source_count") != 42
            or sample_check.get("manifest_sha256") != journeys.SOURCE_MANIFEST_SHA256):
        raise ValueError("migration post-run sample check differs")
    for provider in journeys.PROVIDERS:
        compiled = _json(root / "evidence" / provider / "compile" / "compile.json")
        jar_hashes = dict(journeys.PINNED_JARS)
        if provider == "candidate":
            jar_hashes.pop("dyn4j-6.0.0.jar")
            jar_hashes[journeys.CANDIDATE_JAR] = expected_artifact_hashes["dyn4k-core"]
            jar_hashes.update(MIGRATION_DEPENDENCIES)
        if (not isinstance(compiled.get("artifacts"), list)
                or {item.get("name"): item.get("sha256") for item in compiled["artifacts"]
                    if isinstance(item, dict)} != jar_hashes
                or len(compiled["artifacts"]) != len(jar_hashes)):
            raise ValueError(f"{provider} resolved dependency inventory differs")
        for name, expected_hash in jar_hashes.items():
            binary = _file_path(root, f"evidence/resolved/{provider}/{name}")
            if hashlib.sha256(binary.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f"{provider} resolved dependency differs: {name}")
        if (compiled.get("status") != "PASSED" or compiled.get("exit_code") != 0
                or compiled.get("source_count") != 42
                or compiled.get("source_manifest_sha256") != journeys.SOURCE_MANIFEST_SHA256
                or not isinstance(compiled.get("command"), list)
                or Path(compiled["command"][0]).name != "javac"
                or "--release" not in compiled["command"]
                or "8" not in compiled["command"]
                or not all(any(arg.endswith(path) for arg in compiled["command"])
                           for path in source_paths)
                or not all(any(name in arg for arg in compiled["command"])
                           for name in jar_hashes)
                or not (root / "evidence" / provider / "compile" / "javac.log").is_file()):
            raise ValueError(f"{provider} unchanged Java compilation lacks raw success evidence")
        classes = list((root / "evidence" / provider / "compile" / "classes").rglob("*.class"))
        if (not classes or len(classes) != compiled.get("class_count")
                or any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0
                       or path.read_bytes()[:4] != b"\xca\xfe\xba\xbe" for path in classes)):
            raise ValueError(f"{provider} compiled class outputs differ")
        if not _file_path(root, f"evidence/{provider}/compile/javac-version.log").read_text().strip():
            raise ValueError(f"{provider} javac version output is missing")
        observer = _json(_file_path(root, f"evidence/{provider}/observer-build.json"))
        if (observer.get("status") != "PASSED" or observer.get("exit_code") != 0
                or len(observer.get("commands", [])) != 3
                or any(step.get("exit_code") != 0 for step in observer["commands"])):
            raise ValueError(f"{provider} observer build lacks raw command evidence")
    instrumentation = _file_path(root, "evidence/instrumentation/javassist-3.30.2-GA.jar")
    if hashlib.sha256(instrumentation.read_bytes()).hexdigest() != journeys.JAVASSIST_SHA256:
        raise ValueError("migration observer instrumentation differs from pinned JAR")
    for case in cases:
        for mode in ("plain", "observed"):
            observation = case.get(mode)
            if (not isinstance(observation, dict) or observation.get("status") != "PASSED"
                    or observation.get("exit_code") != 0):
                raise ValueError(f"{case['provider']} {case['scene']} {mode} did not execute")
            directory = root / "evidence" / case["provider"] / case["scene"] / mode
            invocation = _json(directory / "invocation.json")
            command = invocation.get("command")
            if (not isinstance(command, list) or command[:2] != ["podman", "run"]
                    or not any(arg.endswith("run-plain-scene.sh" if mode == "plain" else "run-scene.sh") for arg in command)
                    or case["scene"] not in command
                    or not _file_path(root, (directory / "container.log").relative_to(root).as_posix()).read_text().strip()):
                raise ValueError(f"{case['scene']} {mode} raw container invocation is missing")
            validation_name = "plain-validation.json" if mode == "plain" else "validation.json"
            validation = _json(directory / "evidence" / case["scene"] / validation_name)
            if validation != observation.get("validation"):
                raise ValueError(f"{case['scene']} {mode} raw validation differs from summary")
            if (validation.get("failed", validation.get("failed_checks")) != 0
                    or validation.get("unexecuted", validation.get("unexecuted_checks")) != 0
                    or validation.get("executed", validation.get("executed_checks", 0)) <= 0):
                raise ValueError(f"{case['scene']} {mode} raw validation has incomplete checks")
            evidence = directory / "evidence" / case["scene"]
            if mode == "plain":
                replay = validate_plain.validate(case["scene"], evidence)
            else:
                log_text = _file_path(root, (evidence / "observer.log").relative_to(root).as_posix()).read_text()
                input_text = _file_path(root, (evidence / "inputs.log").relative_to(root).as_posix()).read_text()
                samples, errors = [], []
                for number, line in enumerate(log_text.splitlines(), 1):
                    if line.startswith("OBS_JSON "):
                        try:
                            samples.append(json.loads(line[len("OBS_JSON "):]))
                        except (ValueError, TypeError) as error:
                            errors.append(f"line {number}: {error}")
                checks = validate_scene.checks_for(case["scene"], log_text, input_text, samples, errors)
                replay = {"scene": case["scene"], "expected_checks": len(checks),
                          "executed_checks": sum(item["status"] != "skipped" for item in checks),
                          "passed_checks": sum(item["status"] == "passed" for item in checks),
                          "failed_checks": sum(item["status"] == "failed" for item in checks),
                          "unexecuted_checks": sum(item["status"] == "skipped" for item in checks),
                          "samples": len(samples), "checks": checks, "parse_errors": errors}
            if replay != validation or replay.get("failed", replay.get("failed_checks")) != 0:
                raise ValueError(f"{case['scene']} {mode} raw scene, input, physics, or CCD evidence differs")
    candidate_jar = root / "evidence" / "resolved" / "candidate" / journeys.CANDIDATE_JAR
    if (not candidate_jar.is_file() or candidate_jar.is_symlink() or
            qualify.digest(candidate_jar) != expected_artifact_hashes["dyn4k-core"]):
        raise ValueError("migration candidate JAR differs from audited staged artifact")
    return "ten pinned migration journeys and raw evidence verified"


def _independent_review(root, candidate_sha, repository):
    reports = []
    sessions = set()
    for kind in ("standards", "spec"):
        report = _json(_file_path(root, f"{kind}.json"))
        session_path = _file_path(root, f"{kind}.jsonl")
        if (report.get("review_kind") != kind or report.get("candidate_sha") != candidate_sha
                or report.get("model") != "gpt-6-sol"):
            raise ValueError(f"{kind} review identity differs from final candidate")
        raw_session = session_path.read_text()
        messages = [json.loads(line, object_pairs_hook=_strict_object)
                    for line in raw_session.splitlines() if line]
        turn_models = {item.get("payload", {}).get("model") for item in messages
                       if item.get("type") == "turn_context"}
        session_ids = {item.get("payload", {}).get("id") for item in messages
                       if item.get("type") == "session_meta"}
        if turn_models != {"gpt-6-sol"} or len(session_ids) != 1:
            raise ValueError(f"{kind} raw session does not prove one Sol review")
        final_reviews = []
        observed_findings = []
        for item in messages:
            if item.get("type") != "response_item":
                continue
            payload = item.get("payload", {})
            if isinstance(payload.get("findings"), list):
                observed_findings.extend(payload["findings"])
            if payload.get("type") != "message" or payload.get("role") != "assistant":
                continue
            for part in payload.get("content", []):
                if part.get("type") != "output_text":
                    continue
                try:
                    value = json.loads(part.get("text", ""), object_pairs_hook=_strict_object)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict) and value.get("kind") == "independent-review-result":
                    final_reviews.append(value)
                elif isinstance(value, dict) and isinstance(value.get("findings"), list):
                    observed_findings.extend(value["findings"])
        if len(final_reviews) != 1:
            raise ValueError(f"{kind} raw final review output is absent or ambiguous")
        raw_review = final_reviews[0]
        if (raw_review.get("review_kind") != kind
                or raw_review.get("candidate_sha") != candidate_sha
                or raw_review.get("findings") != report.get("findings")
                or raw_review.get("verdict") != report.get("verdict")
                or raw_review.get("assessment") != report.get("assessment")
                or raw_review.get("reviewed_paths") != report.get("reviewed_paths")):
            raise ValueError(f"{kind} raw review findings differ from report or exact final head")
        required_paths = ({"AGENTS.md", "docs/agents/writing.md"} if kind == "standards"
                          else {"docs/specs/complete-port.md",
                                "docs/planning/acceptance-implementation.md"})
        reviewed_paths = raw_review.get("reviewed_paths")
        if (not isinstance(raw_review.get("assessment"), str)
                or len(raw_review["assessment"].strip()) < 40
                or not isinstance(reviewed_paths, list)
                or not required_paths <= set(reviewed_paths)
                or len(reviewed_paths) != len(set(reviewed_paths))):
            raise ValueError(f"{kind} raw review has no substantive standards or spec assessment")
        for path in reviewed_paths:
            _file_path_name(path)
            subprocess.check_output(["git", "--no-replace-objects", "-C", str(repository), "show",
                                     f"{candidate_sha}:{path}"], stderr=subprocess.PIPE)
        session_id = next(iter(session_ids))
        if report.get("session_id") != session_id or session_id in sessions:
            raise ValueError("independent reviews repeat or misstate session identity")
        sessions.add(session_id)
        findings = raw_review.get("findings")
        if not isinstance(findings, list):
            raise ValueError(f"{kind} actionable findings are missing")
        final_by_id = {finding.get("id"): finding for finding in findings
                       if isinstance(finding, dict)}
        for observed in observed_findings:
            if (not isinstance(observed, dict) or observed.get("id") not in final_by_id
                    or (observed.get("severity") is not None
                        and observed["severity"] != final_by_id[observed["id"]].get("severity"))):
                raise ValueError(f"{kind} raw actionable finding is absent from final review")
        ids = [finding.get("id") for finding in findings if isinstance(finding, dict)]
        if len(ids) != len(findings) or len(set(ids)) != len(ids):
            raise ValueError(f"{kind} finding identities are invalid")
        for finding in findings:
            if (not isinstance(finding.get("severity"), str)
                    or not isinstance(finding.get("description"), str)
                    or not finding["description"].strip()):
                raise ValueError(f"{kind} raw finding lacks actionable details")
            resolution = finding.get("resolution")
            if (not isinstance(resolution, dict)
                    or resolution.get("status") != "RESOLVED"
                    or resolution.get("candidate_sha") != candidate_sha
                    or not isinstance(resolution.get("evidence"), str)
                    or not resolution["evidence"].strip()):
                raise ValueError(f"{kind} actionable finding is unresolved")
            evidence = resolution["evidence"]
            _file_path_name(evidence)
            committed = subprocess.check_output(
                ["git", "--no-replace-objects", "-C", str(repository), "show", f"{candidate_sha}:{evidence}"],
                stderr=subprocess.PIPE)
            if hashlib.sha256(committed).hexdigest() != resolution.get("evidence_sha256"):
                raise ValueError(f"{kind} resolution evidence differs from exact final head")
        if raw_review.get("verdict") != "PASSED":
            raise ValueError(f"{kind} raw reviewer verdict is not PASSED")
        reports.append(report)
    return f"{len(reports)} distinct Sol reviews verified against final head"


def _bounded_bundle(root, candidate_sha, lane, expected_artifact_hashes, repository):
    manifest = json.loads(subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:tools/qualification/foundation-probes.json"],
        stderr=subprocess.PIPE))
    summary = artifact.verify_bundle(root, manifest, candidate_sha)
    route = summary["route"]
    target = "js" if route == "jsSafari" else route
    hashes = summary["artifact_hashes"]
    observed = hashes.get(target) if route == "ubuntu-host" else hashes
    if target != lane["target"] and route != "ubuntu-host":
        raise ValueError("bounded archive target differs from selected lane")
    if route == "ubuntu-host":
        observed = hashes.get(lane["target"])
    if observed != expected_artifact_hashes:
        raise ValueError("bounded archive artifacts differ from independent audit")
    return summary


def _staged_consumer(root, receipt, candidate_sha, lane_id, lane,
                     expected_artifact_hashes, repository, process, manifest):
    target = lane["target"]
    if target in ("js", "wasmJs", "wasmWasi"):
        suffix = {"js": "jsNode", "wasmJs": "wasmJsNode",
                  "wasmWasi": "wasmWasiNode"}[target]
    else:
        suffix = target
    group_id = f"consumer-{suffix}"
    foundation = json.loads(subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{candidate_sha}:tools/qualification/foundation-probes.json"],
        stderr=subprocess.PIPE))
    group = next((item for item in foundation["groups"] if item["id"] == group_id), None)
    foundation_route = (receipt.get("consumer_group") != "full-suite" and group is not None
                        and lane["runtime"] in ("Java", "Node.js", "Linux x64", "macOS ARM64", "Windows x64", "iOS simulator ARM64", "iOS simulator x64", "tvOS simulator ARM64", "watchOS simulator ARM64"))
    if foundation_route:
        if receipt.get("consumer_group") != group_id:
            raise ValueError("frozen staged consumer group differs")
        task = Path(group["report_pattern"]).parent.name
        if not any(arg.endswith(":" + task) or arg == task for arg in process["command"][1:]):
            raise ValueError("raw command does not execute exact consumer task")
        output = _file_path(root, process["stdout"]).read_text()
        if not any(line.startswith("> Task :") and line.split(":")[-1].split()[0] == task
                   for line in output.splitlines()):
            raise ValueError("raw consumer task output differs from executed command")
        expected = set(qualify.expected_probe_cases(foundation, group))
    else:
        contract = consumer_contract(manifest, lane_id)
        if (receipt.get("consumer_group") != "full-suite"
                or receipt.get("consumer_contract_sha256") != digest(contract)
                or lane_id not in process["command"]):
            raise ValueError("full staged consumer command or approved lane contract differs")
        expected = {item["id"] for item in contract["cases"]}
    graph = _file_path(root, receipt.get("provider_graph")).read_text()
    _process_file_binding(root, process, receipt["provider_graph"], "PROVIDER_GRAPH")
    providers = set(re.findall(r"io\.github\.rubixhacker:([^:\s]+):", graph))
    expected_providers = {qualify.target_publication_name(module, target)
                          for module in qualify.MODULES}
    if "org.dyn4j:dyn4j" in graph or not expected_providers <= providers:
        raise ValueError("external consumer provider graph is incomplete or duplicated")
    binaries = receipt.get("resolved_artifacts")
    if not isinstance(binaries, dict) or set(binaries) != set(qualify.MODULES):
        raise ValueError("both resolved external consumer binaries are required")
    for module, relative in binaries.items():
        _process_file_binding(root, process, relative,
                              "RESOLVED_" + module.upper().replace("-", "_"))
        if hashlib.sha256(_file_path(root, relative).read_bytes()).hexdigest() != expected_artifact_hashes[module]:
            raise ValueError(f"resolved external consumer artifact differs: {module}")
    reports = receipt.get("consumer_xml")
    if not isinstance(reports, list) or not reports or len(reports) != len(set(reports)):
        raise ValueError("raw staged consumer XML report paths are missing or duplicate")
    observed = []
    for relative in reports:
        _process_file_binding(root, process, relative, "CONSUMER_XML")
        suite = ET.fromstring(_file_path(root, relative).read_bytes())
        if suite.tag != "testsuite":
            raise ValueError("raw staged consumer XML root is not testsuite")
        cases = list(suite.iter("testcase"))
        counts = {name: sum(case.find(element) is not None for case in cases)
                  for name, element in (("failures", "failure"), ("errors", "error"),
                                        ("skipped", "skipped"))}
        counts["tests"] = len(cases)
        if (any(suite.get(name) is None or int(suite.get(name)) != count
                for name, count in counts.items()) or
                any(counts[name] for name in ("failures", "errors", "skipped"))):
            raise ValueError("staged consumer XML counts or outcomes differ")
        if not 0 <= float(suite.get("time", "nan")) < float("inf"):
            raise ValueError("staged consumer XML suite time is invalid")
        for case in cases:
            identity = ((case.get("classname"), case.get("name"))
                        if foundation_route else case.get("id"))
            if (not identity or not 0 <= float(case.get("time", "nan")) < float("inf")
                    or (foundation_route and not all(identity))):
                raise ValueError("staged consumer XML case identity or time is invalid")
            observed.append(identity)
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("staged consumer case identities or counts differ from frozen manifest")
    return (f"{len(observed)} raw external consumer cases and both resolved artifacts verified",
            not foundation_route)


def _java_full_ci(root, receipt, gate, candidate_sha, repository,
                  expected_artifact_hashes):
    if receipt.get("producer") != "reviewed-full-ci":
        raise ValueError(f"{gate} requires the reviewed full_ci raw archive contract")
    relative = receipt.get("full_ci_archive")
    _file_path_name(relative)
    archive = root / relative
    manifest_file = _file_path(root, f"{relative}/lane-manifest.json")
    manifest_sha = receipt.get("full_ci_manifest_sha256")
    if (not SHA64.fullmatch(str(manifest_sha))
            or hashlib.sha256(manifest_file.read_bytes()).hexdigest() != manifest_sha):
        raise ValueError("reviewed full_ci manifest differs from independently pinned receipt")
    verified_source = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "show",
         f"{REVIEWED_FULL_CI_REVISION}:tools/compatibility/full_ci.py"],
        stderr=subprocess.PIPE)
    if hashlib.sha256(verified_source).hexdigest() != REVIEWED_FULL_CI_SHA256:
        raise ValueError("reviewed full_ci verifier source differs")
    evidence = _json(_file_path(root, f"{relative}/result.json"))
    if evidence.get("archives", {}).get("staged_jvm_jar") != expected_artifact_hashes["dyn4k-core"]:
        raise ValueError("reviewed Java corpus core JAR differs from independent staging audit")
    corpus = evidence.get("corpus")
    routes = ({name: row for name, row in corpus.items()
               if re.fullmatch(r"(baseline|candidate|android)-javac(8|21)-java(8|21)", name)}
              if isinstance(corpus, dict) else {})
    if (len(routes) != 12 or any(not isinstance(row, dict)
                                  or row.get("cases") != 2385 for row in routes.values())):
        raise ValueError("reviewed Java producer manifest omits 2,385 expanded identities on 12 routes")
    resolved = receipt.get("resolved_artifacts")
    if (not isinstance(resolved, dict) or set(resolved) != set(qualify.MODULES)
            or any(hashlib.sha256(_file_path(root, path).read_bytes()).hexdigest()
                   != expected_artifact_hashes[module]
                   for module, path in resolved.items())):
        raise ValueError("Java corpus resolved publications differ from independent staging audit")
    with tempfile.TemporaryDirectory(prefix="dyn4k-reviewed-full-ci-") as temporary:
        source_archive = subprocess.check_output(
            ["git", "-c", "core.autocrlf=false", "--no-replace-objects",
             "-C", str(repository), "archive", REVIEWED_FULL_CI_REVISION,
             "tools/compatibility", "tools/baseline", "dyn4k-core/src/jvmConsumer/java"],
            stderr=subprocess.PIPE)
        with tarfile.open(fileobj=io.BytesIO(source_archive)) as package:
            package.extractall(temporary, filter="data")
        command = [sys.executable,
                   str(Path(temporary) / "tools/compatibility/full_ci.py"),
                   "verify", "--candidate-sha", candidate_sha,
                   "--output", str(archive.resolve()),
                   "--manifest-sha256", manifest_sha]
        checked = subprocess.run(command, capture_output=True, text=True,
                                 timeout=120, check=False)
    if checked.returncode != 0:
        raise ValueError("reviewed full_ci/strict raw verifier rejected archive: "
                         + checked.stdout[-1000:] + checked.stderr[-300:])
    verified = json.loads(checked.stdout, object_pairs_hook=_strict_object)
    if verified.get("status") != "PASSED" or verified.get("corpus_files") != 24:
        raise ValueError("reviewed full_ci/strict verifier did not pass full Java corpus")
    return ("2,385 unchanged Java cases across 12 compile/runtime routes and "
            "216-type strict source compatibility verified by reviewed full_ci")


def _numerical_entries(root, receipt, candidate_sha, expected_artifact_hashes, repository,
                       physical_only=False, prospective_scope=None):
    numerical_dir = Path(__file__).resolve().parents[1] / "numerical"
    compare, physical = _numerical_modules(numerical_dir)
    catalog = _json(numerical_dir / "fixtures.json")
    selected = {item["key"] for item in catalog["fixtures"]
                if not physical_only or "physical_phase_ceilings_m" in compare.load_fixture(item["key"])}
    entries = receipt.get("fixtures")
    if not isinstance(entries, list) or {item.get("key") for item in entries
                                         if isinstance(item, dict)} != selected or len(entries) != len(selected):
        raise ValueError("frozen numerical fixture identities or counts differ")
    source_sha = verified_numerical_source_sha256(repository, candidate_sha)
    physical_profiles = {
        "default-sleep-wake": {"states": 0, "failures": 0,
                               "approved_reference_status": "FAILED_125847_OF_126000"},
        "configured-sleep-wake": {"states": 0, "failures": 0,
                                  "approved_reference_status": "PASSED_BASELINE_ONLY"}}
    for item in entries:
        fixture = compare.load_fixture(item["key"])
        reference = _file_path(root, item.get("reference"))
        candidate = _file_path(root, item.get("candidate"))
        capture = _file_path(root, item.get("capture_receipt"))
        if _json(capture).get("source_hash_method") != NUMERICAL_SOURCE_HASH_METHOD:
            raise ValueError(f"{item['key']} numerical producer source digest method differs")
        result = compare.compare(fixture, reference, candidate, capture,
                                 source_sha, expected_artifact_hashes["dyn4k-core"],
                                 candidate_sha)
        if result["status"] == "UNPASSED" and not physical_only:
            raise IncompleteEvidence(
                f"{item['key']} has unapproved comparison channels: {result['unpassed_channels']}")
        if result["status"] not in (("PASSED", "UNPASSED") if physical_only else ("PASSED",)):
            raise ValueError(f"{item['key']} numerical comparison {result['status']}: {result.get('reason', result.get('unpassed_channels'))}")
        if physical_only:
            phases = physical.phases_for_fixture(fixture)
            states = 0
            failed = 0
            phase_index = 0
            for _, row in compare.records(candidate):
                if row["kind"] != "state":
                    continue
                while row["step"] > phases[phase_index][2]:
                    phase_index += 1
                ceiling = fixture["physical_phase_ceilings_m"][phases[phase_index][0]]
                if physical.depth_for_state(row["state"]) > physical.Fraction(str(ceiling)):
                    failed += 1
                states += 1
            if states != fixture["counts"]["state"]:
                raise ValueError(f"{item['key']} physical state count differs")
            physical_profiles[fixture["profile"]]["states"] += states
            physical_profiles[fixture["profile"]]["failures"] += failed
    if physical_only:
        physical_profiles["default-sleep-wake"]["candidate_status"] = (
            "FAILED" if physical_profiles["default-sleep-wake"]["failures"] else "PASSED")
        physical_profiles["configured-sleep-wake"]["candidate_status"] = (
            "FAILED" if physical_profiles["configured-sleep-wake"]["failures"] else "PASSED")
        physical_profiles["weld-pulley"] = verify_joint_physical_cases(
            root, receipt, candidate_sha, expected_artifact_hashes, source_sha, repository)
        physical_profiles["nominal"] = verify_nominal_physical_case(
            root, receipt, candidate_sha, expected_artifact_hashes, source_sha, repository)
        return physical_profiles
    subgates = _missing_numerical_subgates(repository)
    subgates["frozen-traces"] = {"status": "PASSED", "required_cases": len(entries)}
    if "prospective_bridge" in receipt:
        if "prospective_cases" in receipt:
            raise ValueError("prospective bridge and per-case arithmetic routes are ambiguous")
        p2_artifact = (prospective_scope.get("artifact_hashes", {}).get("dyn4k-core")
                       if isinstance(prospective_scope, dict) else None)
        subgates["prospective-rule-arithmetic"] = verify_pending_prospective_bridge(
            root, receipt, repository, candidate_sha,
            p2_artifact or expected_artifact_hashes["dyn4k-core"], source_sha,
            prospective_scope)
    else:
        subgates["prospective-rule-arithmetic"] = verify_prospective_case_subgates(
            root, receipt, repository, candidate_sha, expected_artifact_hashes, source_sha)
    return subgates


class IncompleteEvidence(Exception):
    pass


def _performance_resource(root, candidate_sha, expected_artifact_hashes,
                          scope=None, repository=None, trusted_key=None):
    scope = scope or {}
    manifests = scope.get("producer_manifest_hashes", {})
    if "evidence/archive.json" in manifests:
        if trusted_key is None:
            raise IncompleteEvidence("sustained performance external trusted key is absent")
        if not Path(trusted_key).is_file():
            raise IncompleteEvidence("sustained performance external trusted key is absent")
        key_path = Path(trusted_key).resolve(strict=True)
        if key_path.is_relative_to(Path(root).resolve()) or len(key_path.read_bytes()) < 32:
            raise ValueError("sustained performance trusted key is inside archive or too short")
        repository = Path(repository)
        index = _json(root / "evidence/archive.json")
        if index.get("route") != "sustained-raw-v1" or index.get("source_commit") != candidate_sha:
            raise ValueError("sustained performance route or candidate differs")
        jvm = index.get("artifacts", {}).get("jvm.java", {})
        for module, key in (("dyn4k-core", "core"), ("dyn4k", "kotlin")):
            if jvm.get(key, {}).get("sha256") != expected_artifact_hashes[module]:
                raise ValueError(f"sustained performance producing {module} JAR differs")
        checked = ("tools/performance/sustained_archive.py",
                   "tools/performance/manifest.py", "tools/performance/measure.py",
                   "tools/performance/analyze.py", "tools/performance/candidate_runner.py",
                   "tools/performance/stress_monitor.py",
                   "docs/research/performance-manifest-v1.json")
        for relative in checked:
            local = repository / relative
            if not local.is_file():
                raise IncompleteEvidence(f"sustained performance producer source is not assembled: {relative}")
            try:
                committed = subprocess.check_output(
                    ["git", "--no-replace-objects", "-C", str(repository), "show",
                     f"{candidate_sha}:{relative}"], stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as error:
                raise IncompleteEvidence(
                    f"sustained performance producer source is not present at candidate: {relative}") from error
            if local.read_bytes() != committed:
                raise ValueError(f"sustained performance verifier source differs: {relative}")
            if relative.endswith("sustained_archive.py") and hashlib.sha256(committed).hexdigest() != scope["verifier_sha256"]:
                raise ValueError("sustained performance independently approved verifier differs")
            if relative.endswith("performance-manifest-v1.json") and hashlib.sha256(committed).hexdigest() != scope["policy_sha256"]:
                raise ValueError("sustained performance independently approved policy differs")
        with tempfile.TemporaryDirectory(prefix="dyn4k-sustained-verify-") as temporary:
            copied = Path(temporary) / "evidence"
            shutil.copytree(root / "evidence", copied)
            checked_process = subprocess.run(
                [sys.executable, str(repository / checked[0]), "verify", "--archive", str(copied),
                 "--trusted-key", str(key_path), "--expected-source-commit", candidate_sha],
                cwd=repository, text=True, capture_output=True, timeout=3600,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        if checked_process.returncode != 0:
            try:
                failure = json.loads(checked_process.stdout, object_pairs_hook=_strict_object)
                reason = str(failure.get("reason", "raw verifier failed"))
            except ValueError:
                reason = "raw verifier returned malformed output"
            if "unpassed policy" in reason or "unavailable" in reason:
                raise IncompleteEvidence("sustained performance " + reason)
            raise ValueError("sustained performance raw verifier rejected archive: " + reason)
        verified = json.loads(checked_process.stdout, object_pairs_hook=_strict_object)
        if verified.get("qualification") != "passed" or verified.get("source_commit") != candidate_sha:
            raise ValueError("sustained performance verifier did not qualify exact candidate")
        return "independently pinned sustained performance archive verified"
    performance_dir = Path(__file__).resolve().parents[1] / "performance"
    sys.path.insert(0, str(performance_dir))
    try:
        import verify_candidate_archive
        raw = verify_candidate_archive.audit_raw_archive(root / "evidence")
        identity = _json(root / "evidence" / "candidate-identity-at-pilot.json")
        if identity.get("source_commit") != candidate_sha:
            raise ValueError("performance raw identity differs from exact candidate")
        observed_hashes = identity.get("sha256")
        if not isinstance(observed_hashes, dict):
            raise ValueError("performance producing JVM binary inventory is missing")
        for module in qualify.MODULES:
            matching = [value for path, value in observed_hashes.items()
                        if path.endswith(f"/{module}-jvm-0.1.0-alpha.1.jar")]
            if matching != [expected_artifact_hashes[module]]:
                raise ValueError(f"performance producing {module} JAR differs from independent audit")
        if raw.get("archive_audit") != "raw_hashes_verified":
            raise ValueError("performance raw archive audit did not verify")
        try:
            qualified = verify_candidate_archive.verify(root / "evidence")
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            raise IncompleteEvidence(f"performance reference environment is unverified: {error}") from error
        if qualified.get("qualification") != "passed":
            raise IncompleteEvidence("performance raw records verified; qualification remains unpassed")
        return "sustained performance archive and reference environment verified"
    finally:
        sys.path.pop(0)


def evaluate(manifest, candidate_sha, lane_id, archives, repository,
             expected_artifact_hashes=None, expected_runtime_identity=None,
             expected_archive_digests=None, expected_all_target_hashes=None,
             expected_producer_scopes=None, expected_performance_key=None,
             expected_signed_lane=None):
    repository = Path(repository)
    if digest(manifest) != APPROVED_MANIFEST_SHA256:
        raise ValueError("manifest differs from independently approved complete suite")
    if not isinstance(candidate_sha, str) or not SHA40.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be an exact commit")
    actual = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repository), "rev-parse", "--verify",
         f"{candidate_sha}^{{commit}}"], text=True, stderr=subprocess.PIPE).strip()
    if actual != candidate_sha:
        raise ValueError("candidate SHA does not identify the requested commit")
    lane = manifest["lanes"].get(lane_id)
    if not isinstance(lane, dict):
        raise ValueError("lane is absent from approved manifest")
    required = lane.get("required_gates")
    if (not isinstance(required, list) or not set(required) <= LANE_GATES
            or len(required) != len(set(required))
            or set(manifest.get("global_gates", [])) != GLOBAL_GATES):
        raise ValueError("approved gate routes are incomplete or duplicated")
    names = list(required) + list(manifest["global_gates"])
    if not isinstance(archives, dict) or set(archives) - set(names):
        raise ValueError("archive map has an unknown or inapplicable gate")
    gates = {}
    if expected_archive_digests is None:
        expected_archive_digests = {}
    if not isinstance(expected_archive_digests, dict) or set(expected_archive_digests) - set(names):
        raise ValueError("independent archive digest map has an unknown gate")
    if expected_producer_scopes is None:
        expected_producer_scopes = {}
    if (not isinstance(expected_producer_scopes, dict)
            or set(expected_producer_scopes) - (set(names) &
                (PRODUCER_SCOPED_GATES | {"numerical-parity"}))):
        raise ValueError("independent producing scope map has an unknown gate")
    for gate in names:
        gates[gate] = evaluate_gate(gate, archives.get(gate), candidate_sha,
                                    lane_id, lane, repository,
                                    expected_artifact_hashes,
                                    expected_runtime_identity,
                                    expected_archive_digests.get(gate),
                                    expected_all_target_hashes, manifest,
                                    expected_producer_scopes, expected_performance_key,
                                    expected_signed_lane)
    statuses = {item["status"] for item in gates.values()}
    status = next((state for state in ("FAILED", "UNAVAILABLE", "NOT_RUN")
                   if state in statuses), "PASSED")
    result = {"schema": 1, "kind": "independent-gate-verification",
              "candidate_sha": candidate_sha, "lane": lane_id,
              "manifest_sha256": digest(manifest),
              "approved_numerical_blobs": dict(APPROVED_POLICY),
              "approved_nominal_blobs": dict(APPROVED_NOMINAL),
              "approved_migration_blobs": dict(APPROVED_MIGRATION),
              "reviewed_full_ci_revision": REVIEWED_FULL_CI_REVISION,
              "expected_artifact_hashes": expected_artifact_hashes,
              "expected_all_target_hashes": expected_all_target_hashes,
              "expected_producer_scopes": expected_producer_scopes,
              "expected_archive_digests": expected_archive_digests,
              "expected_runtime_identity": expected_runtime_identity,
              "expected_performance_key_sha256": (
                  hashlib.sha256(Path(expected_performance_key).read_bytes()).hexdigest()
                  if expected_performance_key is not None
                  and Path(expected_performance_key).is_file() else None),
              "gates": gates, "status": status}
    result["result_sha256"] = digest(result)
    return result


def evaluate_assembly(manifest, candidate_sha, lane_inputs, repository,
                      expected_all_target_hashes=None, expected_performance_key=None):
    if digest(manifest) != APPROVED_MANIFEST_SHA256:
        raise ValueError("assembly manifest differs from approved complete suite")
    if not isinstance(lane_inputs, dict) or set(lane_inputs) != set(manifest["lanes"]):
        raise ValueError("assembly requires all 112 approved lane inputs")
    if expected_all_target_hashes is not None:
        _validated_all_target_hashes(expected_all_target_hashes)
    results = {}
    selected_cases = {}
    adapter = {}
    globals_seen = {}
    allowed = {"archives", "expected_artifact_hashes", "expected_runtime_identity",
               "expected_archive_digests", "expected_producer_scopes"}
    for lane_id in manifest["lanes"]:
        supplied = lane_inputs[lane_id]
        if not isinstance(supplied, dict) or not set(supplied) <= allowed:
            raise ValueError(f"assembly lane input differs: {lane_id}")
        hashes = supplied.get("expected_artifact_hashes")
        if hashes is not None and (not isinstance(hashes, dict)
                                   or set(hashes) != set(qualify.MODULES)
                                   or any(not SHA64.fullmatch(str(value))
                                          for value in hashes.values())):
            raise ValueError(f"assembly artifact hashes are invalid: {lane_id}")
        contract = consumer_contract(manifest, lane_id)
        selected_cases[lane_id] = len(contract["cases"])
        result = evaluate(
            manifest, candidate_sha, lane_id, supplied.get("archives", {}), repository,
            hashes, supplied.get("expected_runtime_identity"),
            supplied.get("expected_archive_digests"), expected_all_target_hashes,
            supplied.get("expected_producer_scopes"), expected_performance_key)
        if result["result_sha256"] != digest({key: value for key, value in result.items()
                                              if key != "result_sha256"}):
            raise ValueError("assembly lane result digest differs")
        results[lane_id] = result
        for gate in manifest["global_gates"]:
            gate_result = result["gates"][gate]
            identity = (gate_result["status"], gate_result.get("archive_sha256"))
            if gate in globals_seen and globals_seen[gate] != identity:
                raise ValueError(f"assembly global gate differs across lanes: {gate}")
            globals_seen[gate] = identity
        if result["status"] == "PASSED":
            if result["gates"]["staged-consumer"].get("complete_selected_suite") is not True:
                raise ValueError("assembly lacks complete selected-suite case ingestion")
            gate_results = {}
            for gate, gate_result in result["gates"].items():
                receipt_hash = result["expected_archive_digests"].get(gate)
                if gate_result["status"] != "PASSED" or not SHA64.fullmatch(str(receipt_hash)):
                    raise ValueError(f"assembly gate receipt is unbound: {gate}")
                gate_results[gate] = {"status": "PASSED", "receipt_sha256": receipt_hash}
            adapter[lane_id] = {
                "case_results": [{"id": case["id"], "status": "PASSED"}
                                 for case in contract["cases"]],
                "expected": selected_cases[lane_id], "executed": selected_cases[lane_id],
                "failures": 0, "skipped": 0, "consumer": "PASSED",
                "gate_results": gate_results,
                "independent_result_sha256": result["result_sha256"]}
    statuses = {result["status"] for result in results.values()}
    status = next((state for state in ("FAILED", "UNAVAILABLE", "NOT_RUN")
                   if state in statuses), "PASSED")
    assembled = {"schema": 1, "kind": "independent-gate-assembly",
                 "candidate_sha": candidate_sha, "manifest_sha256": digest(manifest),
                 "required_lanes": len(results), "selected_cases": selected_cases,
                 "lane_results": results, "qualify_adapter": adapter, "status": status}
    assembled["result_sha256"] = digest(assembled)
    return assembled


def _evaluate_signed_full_consumer(gate, root, candidate_sha, lane_id, repository,
                                   hashes, runtime, expected_digest, signed_lane, family):
    import full_signed_routes

    _archive_paths(root)
    if family == "wasm-node":
        import full_wasm_node_consumer
        measured = full_wasm_node_consumer.archive_digest(root)
    else:
        measured = archive_digest(root)
    if not SHA64.fullmatch(str(expected_digest or "")) or measured != expected_digest:
        raise ValueError("independently signed archive digest differs")
    receipt = _json(_file_path(root, "receipt.json"))
    if not isinstance(receipt, dict):
        raise ValueError("dedicated producer receipt is invalid")
    if receipt.get("status") == "UNAVAILABLE":
        if _archive_paths(root) != {"receipt.json"}:
            raise ValueError("unavailability receipt has unexpected raw files")
        if signed_lane.get("expected_unavailability") != receipt:
            raise ValueError("unavailability is not independently audited")
        observation = _external_unavailable(receipt, candidate_sha, lane_id, gate)
        return _result(gate, "UNAVAILABLE", observation["reason"],
                       archive_sha256=expected_digest,
                       observation_sha256=observation["observation_sha256"])
    if receipt.get("status") == "NOT_RUN":
        if signed_lane.get("expected_not_run") != receipt:
            raise ValueError("unexecuted producer attempt is not independently audited")
        return _result(gate, "NOT_RUN", "independently audited producer did not execute",
                       archive_sha256=expected_digest)
    if receipt.get("status") != "PASSED":
        raise ValueError("dedicated producer did not report a passing execution")
    if family == "browser":
        import full_browser_consumer

        has_http_producer = b"DYN4K_BROWSER_HTTP_ARCHIVE" in full_browser_consumer.original(
            repository, candidate_sha, full_browser_consumer.REPORTER)
        has_cdp_producer = b"DYN4K_BROWSER_CDP_ARCHIVE" in full_browser_consumer.original(
            repository, candidate_sha, "tools/qualification/full_browser_consumer.py")
        producer = full_browser_consumer.original(
            repository, candidate_sha, "tools/qualification/full_browser_consumer.py")
        has_bidi_producer = b"DYN4K_BROWSER_BIDI_ARCHIVE" in producer
        has_minimum_worker = b"DYN4K_BROWSER_FIREFOX_MINIMUM_SW" in producer
        has_safari_producer = b'SAFARI_WORKER = ' in producer
        _, browser_family, browser_role, _ = lane_id.split(":")
        chromium = browser_family == "Chromium"
        firefox_current = browser_family == "Firefox" and browser_role == "current"
        firefox_minimum = browser_family == "Firefox" and browser_role == "minimum"
        safari = browser_family == "Safari"
        schema = receipt.get("schema")
        if (type(schema) is not int or not (
                schema == 5 and has_http_producer and (
                    firefox_current and has_bidi_producer
                    or firefox_minimum and has_bidi_producer and has_minimum_worker
                        and has_safari_producer
                    or safari and has_safari_producer)
                or schema == 4 and has_http_producer and has_cdp_producer and chromium
                or schema == 3 and has_http_producer
                    and not (chromium and has_cdp_producer)
                    and not (firefox_current and has_bidi_producer)
                    and not (firefox_minimum and has_minimum_worker)
                    and not (safari and has_safari_producer)
                or schema == 2 and not has_http_producer)):
            raise ValueError("browser receipt schema differs from exact producer source")
        public = full_signed_routes.verify_browser(
            repository, candidate_sha, lane_id, root, signed_lane,
            hashes, runtime, expected_digest)
        if schema in (3, 4):
            _browser_consumption_witness(root, receipt, signed_lane)
    else:
        public = full_signed_routes.verify(repository, candidate_sha, lane_id, root,
                                           signed_lane, hashes, runtime, expected_digest)
    expected_public = {"status": "PASSED", "lane": lane_id,
                       "selected_cases": 2523, "archive_sha256": expected_digest,
                       "candidate_sha": candidate_sha}
    if family == "native-host" and receipt.get("schema") == 3:
        expected_public.update({"artifact_hash_provenance": "audited",
                                "complete_selected_suite": True})
    if public != expected_public:
        raise ValueError("signed full consumer public result differs from selected gate")
    return _result(gate, "PASSED", f"{family} public full consumer verified",
                   archive_sha256=expected_digest, complete_selected_suite=True,
                   selected_cases=2523, public_verification=public)


def _browser_consumption_witness(root, receipt, signed_lane):
    binding = signed_lane.get("expected_execution_witness")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("independently signed browser process witness is missing")
    path = Path(binding["path"])
    if (not path.is_absolute() or not path.is_file() or path.is_symlink()
            or path.resolve().is_relative_to(root.resolve())
            or not SHA64.fullmatch(str(binding["sha256"]))
            or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]):
        raise ValueError("independent browser process witness bytes differ")
    witness = json.loads(path.read_bytes(), object_pairs_hook=_strict_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(
                             ValueError(f"non-finite browser witness value: {value}")))
    if receipt.get("schema") == 4:
        import full_signed_routes

        full_signed_routes.browser_execution_witness(
            signed_lane, receipt.get("candidate_sha"), receipt.get("lane"),
            signed_lane.get("expected_archive_digests", {}).get("staged-consumer"),
            receipt.get("runtime_identity"), receipt.get("staged_hashes"),
            receipt.get("toolchain"), root)
    observed = witness.get("browser_consumption") if isinstance(witness, dict) else None
    if not isinstance(observed, dict) or set(observed) != {"core", "facade"}:
        raise ValueError("independent browser process consumption is missing")
    modules = receipt.get("modules")
    if not isinstance(modules, dict) or set(modules) != {"core", "facade"}:
        raise ValueError("browser producer process inventory differs")
    protocols = {"cdp"} if receipt.get("schema") == 4 else {
        "cdp", "bidi", "web-inspector"}
    for short in ("core", "facade"):
        process = modules[short]
        browser = observed[short]
        folder = root / short
        launches = [_strict_json_line(line) for line in
                    _file_path(root, f"{short}/browser-launches.jsonl").read_bytes().splitlines()]
        captured = _json(_file_path(root, f"{short}/http-responses.json"))
        if (not isinstance(process, dict) or not isinstance(browser, dict)
                or set(browser) != {"protocol", "clock", "browser_pid", "browser_sha256",
                                    "started_ns", "finished_ns", "responses"}
                or browser["protocol"] not in protocols
                or browser["clock"] != "unix-epoch-ns"
                or len(launches) != 1 or not isinstance(launches[0], dict)
                or type(browser["browser_pid"]) is not int or browser["browser_pid"] <= 0
                or browser["browser_pid"] != launches[0].get("pid")
                or browser["browser_sha256"] != launches[0].get("process_sha256")
                or browser["browser_sha256"] != receipt.get("toolchain", {}).get("browser_sha256")
                or type(browser["started_ns"]) is not int
                or type(browser["finished_ns"]) is not int
                or not process.get("started_ns", 0) <= browser["started_ns"]
                    <= browser["finished_ns"] <= process.get("finished_ns", 0)
                or not isinstance(captured, dict)
                or not isinstance(captured.get("responses"), list)
                or not isinstance(browser["responses"], list)
                or len(browser["responses"]) != len(captured["responses"])):
            raise ValueError("independent browser process observation differs")
        server = {item["url"]: item for item in captured["responses"]}
        if len(server) != len(captured["responses"]):
            raise ValueError("browser server response URLs are duplicated")
        cdp = None
        if receipt.get("schema") == 4:
            rows = [_strict_json_line(line) for line in
                    _file_path(root, f"{short}/chromium-cdp.jsonl").read_bytes().splitlines()]
            if not rows or not isinstance(rows[0], dict) or rows[0].get("kind") != "session":
                raise ValueError("archived Chromium CDP session is missing")
            if (rows[0].get("browser_pid") != browser["browser_pid"]
                    or rows[0].get("cdp_browser_pid") != browser["browser_pid"]
                    or type(rows[0].get("started_ns")) is not int
                    or not process["started_ns"] <= rows[0]["started_ns"] <= browser["finished_ns"]):
                raise ValueError("archived and independent Chromium process differ")
            cdp = {}
            for row in rows[1:]:
                from urllib.parse import urlsplit
                address = urlsplit(row.get("url", "")) if isinstance(row, dict) else None
                url = (address.path + ("?" + address.query if address.query else "")
                       if address else None)
                if (url in cdp or url not in server
                        or row.get("browser_pid") != browser["browser_pid"]
                        or row.get("target_id") != rows[0].get("target_id")
                        or any(type(row.get(key)) is not int for key in
                               ("request_ns", "response_ns", "finished_ns"))
                        or not browser["started_ns"] <= row["request_ns"] <= row["response_ns"]
                            <= row["finished_ns"] <= browser["finished_ns"]
                        or row.get("body_sha256") != server[url].get("sha256")
                        or row.get("body_size") != server[url].get("size")):
                    raise ValueError("archived Chromium CDP body or process differs")
                cdp[url] = row
            if set(cdp) != set(server):
                raise ValueError("archived Chromium CDP response inventory differs")
        seen = set()
        for item in browser["responses"]:
            if (not isinstance(item, dict)
                    or set(item) != {"url", "body_sha256", "size", "request_ns",
                                     "response_ns", "finished_ns"}
                    or type(item["url"]) is not str or item["url"] in seen
                    or item["url"] not in server
                    or item["body_sha256"] != server[item["url"]].get("sha256")
                    or item["size"] != server[item["url"]].get("size")
                    or type(server[item["url"]].get("started_ns")) is not int
                    or type(server[item["url"]].get("finished_ns")) is not int
                    or any(type(item[key]) is not int for key in
                           ("request_ns", "response_ns", "finished_ns"))
                    or not browser["started_ns"] <= item["request_ns"]
                        <= item["response_ns"] <= item["finished_ns"]
                        <= browser["finished_ns"]
                    or not item["request_ns"] <= server[item["url"]]["started_ns"]
                        <= item["response_ns"]
                    or not server[item["url"]]["started_ns"]
                        <= server[item["url"]]["finished_ns"] <= item["finished_ns"]):
                raise ValueError("independent browser response body or interval differs")
            if cdp is not None:
                row = cdp[item["url"]]
                if (item["body_sha256"] != row["body_sha256"]
                        or item["size"] != row["body_size"]
                        or row["request_ns"] > item["finished_ns"]
                        or item["request_ns"] > row["finished_ns"]
                        or not server[item["url"]]["started_ns"] <= row["response_ns"]
                        or not server[item["url"]]["finished_ns"] <= row["finished_ns"]):
                    raise ValueError("independent and archived Chromium body intervals differ")
            seen.add(item["url"])


def _strict_json_line(raw):
    return json.loads(raw, object_pairs_hook=_strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"non-finite browser launch value: {value}")))


def evaluate_gate(gate, archive, candidate_sha, lane_id, lane, repository,
                  expected_artifact_hashes, expected_runtime_identity,
                  expected_archive_digest=None, expected_all_target_hashes=None,
                  manifest=None, expected_producer_scopes=None,
                  expected_performance_key=None, expected_signed_lane=None):
    import full_browser_consumer

    if archive is None:
        if gate == "physical-correctness":
            return _result(gate, "NOT_RUN", "no raw candidate physical archive supplied",
                           profiles=_missing_physical_profiles())
        if gate == "numerical-parity":
            return _result(gate, "NOT_RUN", "no raw candidate numerical archive supplied",
                           subgates=_missing_numerical_subgates(repository))
        return _result(gate, "NOT_RUN", "no raw archive supplied")
    root = Path(archive)
    try:
        if not root.is_dir() or root.is_symlink():
            raise ValueError("raw archive directory is missing or symbolic")
        if (gate == "staged-consumer" and isinstance(manifest, dict)
                and len(manifest.get("lanes", {})) == 112):
            import full_signed_routes

            family = full_signed_routes.route_table(repository, manifest)[lane_id]
            if family == "browser":
                approved = load_approved_manifest(repository)
                if manifest != approved or lane != approved["lanes"][lane_id]:
                    raise ValueError("approved full browser lane or suite differs")
            if (family in {"wasm-node", "native-host", "android-native", "apple-device"}
                    or family == "browser" and _json(_file_path(root, "receipt.json")).get(
                        "schema") in (2, 3, 4, 5)):
                if expected_signed_lane is None:
                    if not (family == "android-native"
                            and full_signed_routes.PUBLIC_REPLAY_ACTIVE.get()):
                        raise ValueError("dedicated staged consumer requires independently signed lane")
                else:
                    return _evaluate_signed_full_consumer(
                        gate, root, candidate_sha, lane_id, repository,
                        expected_artifact_hashes, expected_runtime_identity,
                        expected_archive_digest, expected_signed_lane, family)
        if gate == "staged-consumer" and (root / "verification.json").is_file():
            _archive_paths(root)
            summary = _bounded_bundle(root, candidate_sha, lane,
                                      expected_artifact_hashes, repository)
            return _result(gate, "NOT_RUN",
                           "bounded staged consumer verified; full lane configuration and suite remain unexecuted",
                           bounded_executed=summary["executed"])
        receipt = _json(_file_path(root, "receipt.json"))
        if not isinstance(receipt, dict):
            raise ValueError("raw archive receipt is not an object")
        if receipt.get("status") == "UNAVAILABLE":
            if {path.name for path in root.iterdir()} != {"receipt.json"}:
                raise ValueError("unavailability receipt has unexpected raw files")
            if gate == "staged-consumer" and expected_signed_lane is not None:
                if (expected_signed_lane.get("expected_unavailability") != receipt
                        or not SHA64.fullmatch(str(expected_archive_digest or ""))
                        or archive_digest(root) != expected_archive_digest):
                    raise ValueError("unavailability is not independently audited")
            return _external_unavailable(receipt, candidate_sha, lane_id, gate)
        if receipt.get("status") == "PASSED":
            if not SHA64.fullmatch(str(expected_archive_digest or "")):
                raise ValueError("independent archive provenance digest is missing")
            if archive_digest(root) != expected_archive_digest:
                raise ValueError("independent archive provenance digest differs")
        if (gate == "staged-consumer" and lane_id in full_browser_consumer.LANES
                and ("consumer_contract_sha256" in receipt
                     or "browser_support_sha256" in receipt)):
            import full_browser_consumer

            if (candidate_sha not in full_browser_consumer.LEGACY_LOCK_CANDIDATES
                    or lane_id not in full_browser_consumer.LANES
                    or type(candidate_sha) is not str
                    or not SHA40.fullmatch(candidate_sha)
                    or type(receipt.get("schema")) is not int
                    or receipt["schema"] != 1 or receipt.get("status") != "PASSED"
                    or receipt.get("lane") != lane_id
                    or receipt.get("candidate_sha") != candidate_sha
                    or type(expected_runtime_identity) is not str
                    or not expected_runtime_identity
                    or receipt.get("runtime_identity") != expected_runtime_identity
                    or not isinstance(expected_artifact_hashes, dict)
                    or set(expected_artifact_hashes) != set(full_browser_consumer.MODULES)
                    or any(type(value) is not str or not SHA64.fullmatch(value)
                           for value in expected_artifact_hashes.values())):
                raise ValueError("selected full Chromium candidate, runtime, or artifacts differ")
            approved = load_approved_manifest(repository)
            if (manifest is not None and manifest != approved
                    or lane != approved["lanes"][lane_id]):
                raise ValueError("approved full Chromium lane contract differs")
            selected = consumer_contract(approved, lane_id)["cases"]
            browser_cases = full_browser_consumer.contract(repository, lane_id)["cases"]
            if (len(selected) != 2523
                    or [item["id"] for item in selected]
                    != [item["id"] for item in browser_cases]):
                raise ValueError("approved full Chromium case set differs")
            producer_path = "tools/qualification/full_browser_consumer.py"
            if (Path(full_browser_consumer.__file__).read_bytes()
                    != full_browser_consumer.original(repository, candidate_sha,
                                                      producer_path)):
                raise ValueError("public Chromium verifier differs from exact candidate")
            toolchain = receipt.get("toolchain")
            browser_path = toolchain.get("browser") if isinstance(toolchain, dict) else None
            if (type(browser_path) is not str or not
                    (Path(browser_path).is_absolute()
                     or (candidate_sha == full_browser_consumer.LEGACY_CANDIDATE_SHA
                         and PurePosixPath(browser_path).is_absolute()))):
                raise ValueError("selected live Chromium executable path is invalid")
            public = full_browser_consumer.verify(
                repository, candidate_sha, lane_id, root, expected_archive_digest,
                browser_path, expected_artifact_hashes)
            if public != {"status": "PASSED", "lane": lane_id,
                          "selected_cases": len(selected),
                          "archive_sha256": expected_archive_digest,
                          "candidate_sha": candidate_sha}:
                raise ValueError("public full Chromium replay differs from selected gate")
            return _result(gate, "PASSED", "full staged Chromium consumer replay verified",
                           archive_sha256=expected_archive_digest,
                           complete_selected_suite=True, selected_cases=len(selected))
        archive_sha = _inventory(root, receipt)
        gate_hashes = _gate_artifact_hashes(
            gate, lane, expected_artifact_hashes, expected_all_target_hashes)
        process = _binding(root, receipt, candidate_sha, lane_id, lane,
                           repository, gate_hashes,
                           expected_runtime_identity, gate, expected_producer_scopes)
        if receipt.get("status") not in ("PASSED", "FAILED", "NOT_RUN"):
            raise ValueError("reported gate status is invalid")
        if receipt["status"] == "NOT_RUN":
            return _result(gate, "NOT_RUN", "producer records no execution",
                           archive_sha256=archive_sha)
        if receipt["status"] == "FAILED":
            if process["exit_code"] == 0:
                raise ValueError("producer reports failure but raw process exited successfully")
            _process_proof(root, process, gate, lane_id, receipt)
            return _result(gate, "FAILED", f"raw command exited {process['exit_code']}",
                           archive_sha256=archive_sha)
        _process_proof(root, process, gate, lane_id, receipt)
        if gate == "duplicate-provider":
            reason = _duplicate_provider(root, receipt, process)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if process["exit_code"] != 0:
            return _result(gate, "FAILED", f"raw command exited {process['exit_code']}",
                           archive_sha256=archive_sha)
        if gate in ("staged-artifacts", "publication-contract"):
            if gate == "publication-contract" and expected_all_target_hashes is None:
                raise ValueError("independently audited 21-target binary hash map is missing")
            if gate == "publication-contract":
                _validated_all_target_hashes(expected_all_target_hashes)
            reason = _staged_publication(root, candidate_sha, lane,
                                         gate_hashes, repository,
                                         expected_all_target_hashes if gate == "publication-contract" else None)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "staged-consumer":
            reason, complete = _staged_consumer(
                root, receipt, candidate_sha, lane_id, lane,
                expected_artifact_hashes, repository, process, manifest)
            return _result(gate, "PASSED" if complete else "NOT_RUN", reason,
                           archive_sha256=archive_sha, complete_selected_suite=complete,
                           selected_cases=len(consumer_contract(manifest, lane_id)["cases"])
                           if complete else None)
        if gate in ("unchanged-java-corpus", "java-source-compatibility"):
            reason = _java_full_ci(root, receipt, gate, candidate_sha,
                                   repository, expected_producer_scopes[gate]["artifact_hashes"])
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "migration-journeys":
            _source_binding(repository, candidate_sha, APPROVED_MIGRATION,
                            "migration raw validator")
            reason = _migration_journeys(root, candidate_sha,
                                         expected_producer_scopes[gate]["artifact_hashes"])
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate in ("numerical-parity", "physical-correctness"):
            policy = _policy_binding(repository, candidate_sha)
            reason = _numerical_entries(
                root, receipt, candidate_sha, expected_artifact_hashes, repository,
                physical_only=gate == "physical-correctness",
                prospective_scope=(expected_producer_scopes or {}).get("numerical-parity")
                if gate == "numerical-parity" else None)
            if gate == "physical-correctness":
                status = physical_status(reason)
                return _result(gate, status,
                               "default, configured, nominal, and joint physical obligations are reported separately",
                               profiles=reason, archive_sha256=archive_sha, policy_sha256=policy)
            status = reason["prospective-rule-arithmetic"]["status"]
            return _result(gate, status,
                           "14 frozen traces and 318 prospective rule/arithmetic cases are separate obligations",
                           subgates=reason, archive_sha256=archive_sha,
                           policy_sha256=policy)
        if gate == "performance-resource":
            reason = _performance_resource(root, candidate_sha,
                                           expected_producer_scopes[gate]["artifact_hashes"],
                                           expected_producer_scopes[gate], repository,
                                           expected_performance_key)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        if gate == "independent-review":
            reason = _independent_review(root, candidate_sha, repository)
            return _result(gate, "PASSED", reason, archive_sha256=archive_sha)
        raise ValueError(f"unknown approved gate route: {gate}")
    except IncompleteEvidence as error:
        return _result(gate, "NOT_RUN", str(error))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError,
            json.JSONDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            zipfile.BadZipFile, ET.ParseError) as error:
        if gate == "numerical-parity":
            return _result(gate, "FAILED", str(error),
                           subgates=_missing_numerical_subgates(repository))
        return _result(gate, "FAILED", str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--lane")
    parser.add_argument("--assembly", type=Path)
    parser.add_argument("--repository", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archive", action="append", default=[], metavar="GATE=PATH")
    parser.add_argument("--expected-artifacts", type=Path)
    parser.add_argument("--expected-all-target-artifacts", type=Path)
    parser.add_argument("--expected-producer-scopes", type=Path)
    parser.add_argument("--expected-archive-digests", type=Path)
    parser.add_argument("--expected-runtime-identity")
    parser.add_argument("--expected-performance-key", type=Path)
    args = parser.parse_args(argv)
    manifest = (json.loads(args.manifest.read_text()) if args.manifest
                else load_approved_manifest(args.repository))
    archives = {}
    for value in args.archive:
        gate, separator, path = value.partition("=")
        if not separator or not path or gate in archives:
            parser.error("each --archive must be a unique GATE=PATH")
        archives[gate] = Path(path)
    hashes = json.loads(args.expected_artifacts.read_text()) if args.expected_artifacts else None
    all_hashes = (json.loads(args.expected_all_target_artifacts.read_text())
                  if args.expected_all_target_artifacts else None)
    producer_scopes = (json.loads(args.expected_producer_scopes.read_text())
                       if args.expected_producer_scopes else None)
    archive_digests = (json.loads(args.expected_archive_digests.read_text())
                       if args.expected_archive_digests else None)
    if args.assembly:
        if args.lane or archives:
            parser.error("--assembly cannot be combined with --lane or --archive")
        result = evaluate_assembly(
            manifest, args.candidate_sha, _json(args.assembly), args.repository,
            all_hashes, args.expected_performance_key)
    else:
        if not args.lane:
            parser.error("--lane is required without --assembly")
        result = evaluate(manifest, args.candidate_sha, args.lane, archives,
                          args.repository, hashes, args.expected_runtime_identity,
                          archive_digests, all_hashes, producer_scopes,
                          args.expected_performance_key)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
