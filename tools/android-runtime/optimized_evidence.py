import re

from evidence import parse_instrumentation, validate_lane


CASE = "io.github.rubixhacker.dyn4k.optimized.OptimizedJourneyTest#appSideWorldAndSubclassCallbacks"
REQUIRED_CLASSES = (
    "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer$CountingWorld",
    "org.dyn4j.geometry.Vector2",
    "org.dyn4j.dynamics.Body",
    "org.dyn4j.world.World",
)
PROTECTED_NAMESPACES = ("org.dyn4j", "io.github.rubixhacker.dyn4k", "kotlin")
EFFECTIVE_KEEP_DIRECTIVES = frozenset((
    "keep", "keepclassmembers", "keepclasseswithmembers", "keepnames",
    "keepclassmembernames", "keepclasseswithmembernames",
))
NON_CLASS_KEEP_DIRECTIVES = frozenset((
    "keepattributes", "keepdirectories", "keeppackagenames", "keepparameternames",
))
CLASS_KINDS = frozenset(("class", "interface", "enum", "@interface"))
KEEP_OPTIONS = frozenset((
    "allowshrinking", "allowoptimization", "allowobfuscation", "includedescriptorclasses",
    "allowaccessmodification", "allowrepackage", "allowannotationremoval",
))
CLASS_MODIFIERS = frozenset(("public", "private", "protected", "final", "abstract", "synthetic"))
MEMBER_MODIFIERS = frozenset((
    "public", "private", "protected", "static", "final", "abstract", "native", "synthetic",
    "synchronized", "transient", "volatile", "strictfp", "bridge",
))
MEMBER_KEEP_DIRECTIVES = frozenset((
    "keepclassmembers", "keepclasseswithmembers", "keepclassmembernames",
    "keepclasseswithmembernames",
))
CLASS_SELECTOR = re.compile(r"!?[\w.$*?]+\Z")
DIRECTIVE = re.compile(r"-[A-Za-z][A-Za-z0-9]*\Z")


def validate_installed_case(raw, process_exit_code, expected_case=CASE):
    result = parse_instrumentation(raw)
    validate_lane(result, set(), {expected_case}, process_exit_code)
    return result


def validate_provider(graph):
    required = ("io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
                "io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1")
    if any(coordinate not in graph for coordinate in required) or "org.dyn4j:dyn4j:" in graph:
        raise ValueError("optimized app provider graph does not contain only staged dyn4k")


def _pattern_covers_namespace(pattern):
    if pattern in ("*", "**", "***"):
        return True
    if not ("*" in pattern or "?" in pattern):
        return False
    if any(pattern.startswith(namespace + ".") for namespace in PROTECTED_NAMESPACES):
        return True
    glob = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^.]*").replace(r"\?", "[^.]")
    if any(re.fullmatch(glob, namespace + ".Probe") for namespace in PROTECTED_NAMESPACES):
        return True
    first_wildcard = min(index for index, char in enumerate(pattern) if char in "*?")
    prefix = pattern[:first_wildcard]
    return any(namespace.startswith(prefix) for namespace in PROTECTED_NAMESPACES) and (
        "**" in pattern or "." in pattern[first_wildcard + 1:])


def _has_broad_member_selector(body, class_kind, generated_enum_rule):
    statements = [statement.strip() for statement in body.split(";") if statement.strip()]
    if not body.rstrip().endswith(";") or not statements:
        raise ValueError("unsupported optimized R8 keep member selector")
    for statement in statements:
        head, has_args, args = statement.partition("(")
        if has_args and (not args.endswith(")") or "(" in args):
            raise ValueError("unsupported optimized R8 keep member selector")
        arguments = args[:-1].strip() if has_args else None
        if arguments and any(not re.fullmatch(r"[\w.$*?%\[\]<>]+|\.\.\.", part.strip())
                             for part in arguments.split(",")):
            raise ValueError("unsupported optimized R8 keep member selector")
        tokens = head.split()
        if not tokens:
            raise ValueError("unsupported optimized R8 keep member selector")
        member_name = tokens[-1]
        if member_name in ("<methods>", "<fields>"):
            _validate_member_modifiers(tokens[:-1])
            if has_args:
                raise ValueError("unsupported optimized R8 keep member selector")
            annotations = [token for token in tokens if token.startswith("@")]
            if annotations and not all(token.startswith(("@android.", "@androidx."))
                                       for token in annotations):
                return True
            if "native" not in tokens and not annotations:
                return True
            continue
        if member_name == "<init>":
            _validate_member_modifiers(tokens[:-1])
            if not has_args:
                raise ValueError("unsupported optimized R8 keep member selector")
            if arguments and not any(token.startswith(("@android.", "@androidx."))
                                     for token in tokens):
                return True
            continue
        if not re.fullmatch(r"[\w$*?<>]+", member_name):
            raise ValueError("unsupported optimized R8 keep member selector")
        if len(tokens) >= 2:
            _validate_member_modifiers(tokens[:-2])
        generated_signature = generated_enum_rule and class_kind == "enum" and has_args and (
            (tokens == ["public", "static", "**[]", "values"] and arguments == "") or
            (tokens == ["public", "static", "**", "valueOf"] and arguments == "java.lang.String")
        )
        if generated_signature:
            continue
        if class_kind == "enum" and member_name in ("values", "valueOf"):
            return True
        if "*" in member_name or "?" in member_name:
            return True
        if len(tokens) < 2:
            raise ValueError("unsupported optimized R8 keep member selector")
        member_type = tokens[-2]
        if not re.fullmatch(r"[\w.$*?%\[\]<>]+", member_type):
            raise ValueError("unsupported optimized R8 keep member selector")
        if any(char in member_type for char in "*?%") or \
                (arguments and any(char in arguments for char in "*?%")) or \
                (arguments and "..." in arguments):
            return True
    return False


def _validate_member_modifiers(tokens):
    for token in tokens:
        if token.startswith("@") and CLASS_SELECTOR.fullmatch(token[1:]):
            continue
        if not re.fullmatch(r"!?[A-Za-z]+", token) or token.removeprefix("!") not in MEMBER_MODIFIERS:
            raise ValueError("unsupported optimized R8 keep member modifier")


def _configuration_tokens(configuration):
    tokens = []
    index = 0
    while index < len(configuration):
        char = configuration[index]
        if char == "#":
            end = configuration.find("\n", index)
            index = len(configuration) if end < 0 else end + 1
        elif char.isspace():
            index += 1
        elif char in "{}();,":
            tokens.append(char)
            index += 1
        else:
            end = index
            while end < len(configuration) and not configuration[end].isspace() and \
                    configuration[end] not in "#{}();,":
                end += 1
            tokens.append(configuration[index:end])
            index = end
    return tokens


def _directives(configuration):
    tokens = _configuration_tokens(configuration)
    index = 0
    while index < len(tokens):
        if not DIRECTIVE.fullmatch(tokens[index]):
            raise ValueError("unsupported optimized R8 configuration token")
        name = tokens[index][1:]
        start = index + 1
        index = start
        depth = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth < 0:
                    raise ValueError("unsupported optimized R8 keep block")
            elif depth == 0 and DIRECTIVE.fullmatch(token):
                break
            index += 1
        if depth:
            raise ValueError("unsupported optimized R8 keep block")
        yield name, tokens[start:index]


def _parse_class_spec(name, tokens):
    if "{" in tokens:
        opening = tokens.index("{")
        if tokens.count("{") != 1 or tokens.count("}") != 1 or tokens[-1] != "}":
            raise ValueError("unsupported optimized R8 keep block")
        header = tokens[:opening]
        members = tokens[opening + 1:-1]
        if not members or members[-1] != ";":
            raise ValueError("unsupported optimized R8 keep member selector")
    else:
        if "}" in tokens or name in MEMBER_KEEP_DIRECTIVES:
            raise ValueError("unsupported optimized R8 keep block")
        header = tokens
        members = None
    index = 0
    while index < len(header) and header[index] == ",":
        if index + 1 >= len(header) or header[index + 1] not in KEEP_OPTIONS or name == "if":
            raise ValueError("unsupported optimized R8 keep option")
        index += 2
    kinds = [position for position, token in enumerate(header) if token in CLASS_KINDS]
    if len(kinds) != 1 or kinds[0] < index:
        raise ValueError("unsupported optimized R8 keep class selector")
    kind_index = kinds[0]
    prefix = header[index:kind_index]
    for token in prefix:
        if token.startswith("@") and CLASS_SELECTOR.fullmatch(token[1:]):
            continue
        if not re.fullmatch(r"!?[A-Za-z]+", token) or token.removeprefix("!") not in CLASS_MODIFIERS:
            raise ValueError("unsupported optimized R8 keep class modifier")
    remainder = header[kind_index + 1:]
    inheritance = [position for position, token in enumerate(remainder)
                   if token in ("extends", "implements")]
    if len(inheritance) > 1:
        raise ValueError("unsupported optimized R8 keep class selector")
    selector_tokens = remainder[:inheritance[0]] if inheritance else remainder
    if not selector_tokens or len(selector_tokens) % 2 == 0 or \
            any((position % 2 == 1) != (token == ",") for position, token in enumerate(selector_tokens)):
        raise ValueError("unsupported optimized R8 keep class selector")
    selectors = selector_tokens[::2]
    if any(not CLASS_SELECTOR.fullmatch(selector) for selector in selectors):
        raise ValueError("unsupported optimized R8 keep class selector")
    ancestry = remainder[inheritance[0] + 1:] if inheritance else []
    if inheritance and (len(ancestry) != 1 or not CLASS_SELECTOR.fullmatch(ancestry[0])):
        raise ValueError("unsupported optimized R8 keep ancestry")
    kind = header[kind_index]
    member_broad = False
    if members is not None:
        member_broad = _has_broad_member_selector(
            " ".join(members), kind,
            name == "keepclassmembers" and kind == "enum" and selectors == ["*"] and
            not prefix and not ancestry,
        )
    return selectors, [token for token in prefix if token.startswith("@")], ancestry, member_broad


def _has_broad_namespace_keep(configuration):
    pending_condition = False
    for name, tokens in _directives(configuration):
        if name == "if":
            if pending_condition:
                raise ValueError("unsupported optimized R8 conditional keep")
            _parse_class_spec(name, tokens)
            pending_condition = True
            continue
        if pending_condition and name not in EFFECTIVE_KEEP_DIRECTIVES:
            raise ValueError("unsupported optimized R8 conditional keep")
        if name in NON_CLASS_KEEP_DIRECTIVES:
            if "{" in tokens or "}" in tokens:
                raise ValueError("unsupported optimized R8 metadata option")
            if name == "keepparameternames" and tokens:
                raise ValueError("unsupported optimized R8 metadata option")
            continue
        if not name.startswith("keep"):
            continue
        if name not in EFFECTIVE_KEEP_DIRECTIVES:
            raise ValueError(f"unsupported optimized R8 keep directive: -{name}")
        pending_condition = False
        selectors, annotations, ancestry, member_broad = _parse_class_spec(name, tokens)
        if any(selector.startswith("!") for selector in selectors):
            return True
        for selector in selectors:
            if not _pattern_covers_namespace(selector):
                continue
            if selector not in ("*", "**", "***"):
                return True
            if annotations and not all(annotation.startswith(("@android.", "@androidx."))
                                       for annotation in annotations):
                return True
            if ancestry and not all(pattern.startswith(("android.", "androidx."))
                                    for pattern in ancestry):
                return True
            if annotations or ancestry:
                continue
            if name in ("keep", "keepnames") or member_broad:
                return True
    if pending_condition:
        raise ValueError("unsupported optimized R8 conditional keep")
    return False


def validate_r8(configuration, mapping, usage, dex_descriptors):
    if _has_broad_namespace_keep(configuration):
        raise ValueError("optimized route has a broad keep rule")
    if not mapping.strip() or not usage.strip() or "org.dyn4j." not in usage:
        raise ValueError("optimized R8 mapping or usage evidence missing")
    if "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer.run()" not in mapping or \
            "io.github.rubixhacker.dyn4k.optimized.OptimizedConsumer" not in usage:
        raise ValueError("optimized consumer run was not transformed and trimmed")
    mapped = {}
    for original in REQUIRED_CLASSES:
        match = re.search(rf"(?m)^{re.escape(original)} -> ([^:\s]+):$", mapping)
        if not match:
            raise ValueError(f"optimized R8 mapping missing: {original}")
        target = match.group(1)
        removed = target.startswith("R8$$REMOVED$$CLASS$$")
        descriptor = None if removed else "L" + target.replace(".", "/") + ";"
        if not removed and descriptor not in dex_descriptors:
            raise ValueError(f"optimized DEX class missing: {original} -> {descriptor}")
        mapped[original] = {"name": target, "descriptor": descriptor}
    if not mapped["org.dyn4j.world.World"]["name"].startswith("R8$$REMOVED$$CLASS$$"):
        raise ValueError("optimized world class was not R8 merged")
    if not any(mapped[name]["name"] != name for name in REQUIRED_CLASSES[1:]):
        raise ValueError("optimized engine path has no R8 rename evidence")
    return mapped
