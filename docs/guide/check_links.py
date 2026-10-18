#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
FILES = (ROOT / "README.md", ROOT / "docs/guide/migration.md")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
REQUIRED_GUIDE_CLAIMS = {
    "compound assignment binding": "rebind that variable to the returned vector",
    "named mutation identity": "`add`, `subtract`, `multiply`, and `divide` change the existing vector",
    "named Java module": "defines module `org.dyn4j`",
    "module exports": "exports all 17 `org.dyn4j` packages",
    "provider descriptor source": "[provider descriptor](https://github.com/rubixhacker/dyn4k/blob/578b8207ba19dcf633a56adbe293e3cd78b5e861/dyn4k-core/src/jvmModule/java/module-info.java)",
    "named consumer fixture": "module dyn4k.migration.probe",
    "named consumer source links": "[module descriptor](../../tools/compatibility/fixtures/named_module/module-info.java)",
    "named consumer entry point": "[main class](../../tools/compatibility/fixtures/named_module/example/Main.java)",
    "named module runtime boundary": "The named module path requires Java 9 or newer.",
    "named module artifact": "`io.github.rubixhacker:dyn4k-core-jvm:0.1.0-alpha.1`",
    "earlier provider artifact SHA": "An earlier bounded named-module consumer passed on the `578b8207ba19dcf633a56adbe293e3cd78b5e861` branch artifact",
    "combined-head source revision": "combined source tree at revision `edea0c4723e0d092fe8614860937ad9c6f4001ec`",
    "combined-head provider SHA": "SHA-256 `63cd3852e2727306ae0dc2abe5fb5a0faae49d5d7c704f8397643c3ffcad3560`",
    "combined-head qualification boundary": "does not establish candidate ledger mapping, ledger replay, or full named-module compatibility",
    "guide-base artifact SHA": "`b56d947ea183e6b8e7affddd1f24ad3ebd8e3276c6c56fa3e319e114793165f4`",
    "required expected SHA": "--expected-provider-sha256",
    "direct probe supplied hash": "The direct probe received `--expected-provider-sha256` with the separately verified publication hash above.",
    "named-module declaration ledger": "[named-module declaration ledger](https://github.com/rubixhacker/dyn4k/blob/578b8207ba19dcf633a56adbe293e3cd78b5e861/tools/compatibility/declaration-ledger.json)",
    "empty candidate mapping evidence": "`module.candidate: null` and empty module evidence",
    "pending candidate mapping and replay": "Candidate mapping and ledger replay remain unpassed.",
    "proposed mapping status": "A candidate mapping is proposed, not recorded.",
    "classpath artifact identity": "Record the resolved GAV, JAR path, and SHA-256",
    "Java 8 classpath command": "javac --release 8",
    "guide-base automatic module": "still derives automatic module `dyn4k.core.jvm`",
    "guide-base operator conflict": "fails to compile the `+=` line because both `plus` and `plusAssign` are available",
    "policy staged run status": "The staged artifact from API revision `0a141816` compiles and runs this block.",
    "default physical failure count": "penetration gate failed in 125,847 of 126,000 end states",
    "assignment evidence revision": "[IdiomaticApiTest at API revision `0a141816`](https://github.com/rubixhacker/dyn4k/blob/0a141816d77dbb4db08fbac429a1c3e5ed24a41d/dyn4k/src/commonTest/kotlin/io/github/rubixhacker/dyn4k/IdiomaticApiTest.kt)",
    "checked Kotlin example": "[check_examples.py](check_examples.py)",
    "operator example stage revision": "against a repository produced from API revision `0a141816`",
    "declared example body": "val body = Body()",
}
PROHIBITED_GUIDE_CLAIMS = (
    "`+=` mutates the shared vector",
    "The named-module name is not qualified in this preview.",
    "penetration passed at 125,847 of 126,000 samples",
)
UNSUPPORTED_CANDIDATE_MAPPING_CLAIMS = (
    "The independently recorded candidate mapping supplies",
    "The mapping binds the staged artifact identity.",
)


def assignment_example_code(guide: str) -> str | None:
    heading = re.search(r"(?m)^### Vector assignment and shared mutation\s*$", guide)
    if heading is None:
        return None
    section = guide[heading.end():]
    next_heading = re.search(r"(?m)^#{1,3} ", section)
    if next_heading is not None:
        section = section[:next_heading.start()]
    block = re.search(r"```kotlin\s*\n(.*?)\n```", section, re.DOTALL)
    return block.group(1) if block is not None else None


def check_assignment_example(guide: str) -> list[str]:
    code = assignment_example_code(guide)
    if code is None:
        return ["Kotlin assignment example is missing"]
    declaration = re.search(r"(?m)^\s*val\s+body\s*=\s*Body\(\)\s*$", code)
    use = re.search(r"\bbody\.linearVelocity\b", code)
    if use is not None and (declaration is None or declaration.start() > use.start()):
        return ["Kotlin assignment example uses `body` before it is declared"]
    return []


def check_candidate_mapping_claim(guide: str) -> list[str]:
    return [
        f"unsupported candidate mapping claim: {claim}"
        for claim in UNSUPPORTED_CANDIDATE_MAPPING_CLAIMS
        if claim in guide
    ]


def check_guide_claims(guide: str) -> list[str]:
    errors: list[str] = []
    for claim, text in REQUIRED_GUIDE_CLAIMS.items():
        if text not in guide:
            errors.append(f"missing required claim: {claim}")
    for text in PROHIBITED_GUIDE_CLAIMS:
        if text in guide:
            errors.append(f"obsolete claim: {text}")
    errors.extend(check_assignment_example(guide))
    errors.extend(check_candidate_mapping_claim(guide))
    return errors


def main() -> int:
    errors: list[str] = []
    checked = 0
    for document in FILES:
        source = document.read_text(encoding="utf-8")
        for match in LINK.finditer(source):
            target = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("//") or not parsed.path:
                continue
            checked += 1
            path = (document.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(ROOT) or not path.exists():
                line = source.count("\n", 0, match.start()) + 1
                errors.append(f"{document.relative_to(ROOT)}:{line}: missing or out-of-repository link: {target}")
    guide = (ROOT / "docs/guide/migration.md").read_text(encoding="utf-8")
    errors.extend(
        f"docs/guide/migration.md: {error}"
        for error in check_guide_claims(guide)
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"guide links checked: {checked}; claims checked: {len(REQUIRED_GUIDE_CLAIMS) + len(PROHIBITED_GUIDE_CLAIMS)}; failures: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
