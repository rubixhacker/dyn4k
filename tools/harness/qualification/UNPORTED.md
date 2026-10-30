# Not ported in `:qualification`'s collection port

`tools/qualification/collection.py` is ported to `CollectionRules` (pure contracts) and
`CollectionRuntime` (filesystem, archive, process, and HTTP work). The following reference
behaviour is deliberately absent; every consumer fails closed instead of degrading silently.

## Windows handle machinery

Reference: `_windows_handle_directory`, `_windows_open`, `_windows_close`,
`_windows_handle_identity`, `_windows_relative_open`, `_windows_names`,
`_open_windows_no_reparse`, and the `os.name == "nt"` branches of `_anchored_open`,
`_directory_names`, `_directory_child`, `_copy_regular`, `_copy_directory`.

Reason: the reference opens directories and files with `CreateFileW` (share modes, reparse-point
open) and `NtCreateFile` relative to an open parent handle, reads `FileIdInfo` identities, and
queries directory entries with `NtQueryDirectoryFile`. The JVM has no descriptor or handle that can
be passed to an open, renamed, or locked directory; a faithful port would need a JNI shim, which is
out of scope. The port therefore applies the POSIX path logic on every host, so:

* a junction or reparse point that is not also a JVM-visible symbolic link is followed;
* `CreateFileW` share modes (the reference's protection against a rename while a directory is
  anchored) have no equivalent;
* `_windows_names` bounds (duplicate member, 200 000 entries) are enforced on the JVM stream
  instead.

`test_cross_run_collection.py::test_windows_directory_backend_model_rejects_unreadable_descendant`,
`::test_windows_open_route_keeps_bound_archive_and_rejects_replacement`, and
`::test_windows_parent_handle_blocks_rename_and_junction_is_rejected` are therefore reproduced only
in their POSIX-observable half. No Windows run is claimed.

## Descriptor-relative atomicity

Reference: `_anchored_open` opens each component with `O_NOFOLLOW`/`O_DIRECTORY` relative to the
previous descriptor and compares `fstat` identities of the descriptor with `lstat` of the path.

The port instead re-checks every component with `NOFOLLOW_LINKS` and re-reads the file identity
(`fileKey`, `unix:dev`/`unix:ino`, size, mtime) before and after each read or copy. Consequences:

* a swap that changes the identity between the inventory and the read is detected;
* a swap that restores an identical identity, or that replaces a parent directory with another
  ordinary directory between two separate opens, is **not** detectable.

The anchoring cases in `CrossRunCollectionSuite` assert the detected behaviour and state the
undetected one in the test body; they do not assert a rejection the port cannot make.

## `full-ci` archive verification

`inspect_artifact`'s `full-ci` branch calls `full_ci.verify_archive`, which lives in the
`:compatibility` module; `:qualification` does not depend on it. A `full-ci` producer artifact
therefore fails closed with an explicit reason instead of being verified.

## Signed adapter

`ingest_external` runs `python3 tools/qualification/qualify.py record …` exactly as the reference
does; the adapter itself is not reimplemented here.
