# Independent audit preparation for 112 lanes

The audit preparer reads observations supplied by an auditor. It creates one
archive map and one canonical audit for an exact candidate commit. It does not
hold a signing key. The approved suite must contain all 112 lanes, and the
staged audit must account for both binaries on all 21 targets.

## Inputs

Run from a clean checkout of the candidate commit. Supply the candidate
manifest and staged publication audit used by the qualification harness.
The preparer rechecks the staged files with `qualify.verify_audit_against_staging`.
Its signed audit binds their semantic digests and exact input byte hashes.
The signing request repeats those hashes for the external signer to check.

Supply a JSON observation with this shape:

```json
{
  "schema": 1,
  "candidate_sha": "40 lowercase hex characters",
  "lanes": {
    "every approved lane ID": {
      "archives": {},
      "signed_fields": {}
    }
  }
}
```

`lanes` must contain all 112 approved IDs. An absent gate has no archive
entry. Its result is `NOT_RUN`. Each supplied archive path is absolute and
names a retained directory. The preparer records every file's SHA-256 and
nanosecond modification time. It also computes the gate verifier's archive
digest and runs the public gate evaluator. A malformed attempt remains
`FAILED`. A receipt that reports `PASSED` cannot fill a missing signed route
field or replace a public verifier result.
For a JVM mode publication, `prepare` copies the verified path and digest
into the signed lane fields and rejects conflicting supplied values.

`signed_fields` contains observations gathered outside the producer archive.
For a passing staged consumer, supply the fields used by its route in
[the signed route guide](full-signed-112-gate.md). The preparer checks that
the required field names are present. The public route verifier checks their
values after detached signing. Use `expected_producer_scopes` for applicable
JVM, migration, performance, numerical, or review evidence. A staged consumer
`UNAVAILABLE` receipt needs an exact `expected_unavailability` observation.
No archive entry is never treated as `UNAVAILABLE`.

The auditor must inspect the process, runtime, executable, artifact, case,
provider, and witness evidence before supplying signed fields. Copying a
producer's `PASSED` value or its own asserted toolchain into these fields is
not an independent observation. Public verification checks consistency. It
cannot establish who observed a process.

## Detached handoff

The verifier operator obtains the trusted Ed25519 public key fingerprint
outside the producer archive. The fingerprint is the SHA-256 of the public
key's DER SubjectPublicKeyInfo bytes. The operator pins it at both steps.

```sh
python3 tools/qualification/independent_audit_producer.py prepare \
  --repository "$PWD" --candidate-sha "$CANDIDATE_SHA" \
  --candidate-manifest "$CANDIDATE_MANIFEST" \
  --staged-audit "$STAGED_AUDIT" \
  --observations "$INDEPENDENT_OBSERVATIONS" \
  --trusted-key-sha256 "$TRUSTED_KEY_SHA256" \
  --output-dir "$AUDIT_HANDOFF"
```

`prepare` creates `archive-map.json`, `audit.json`, and
`signing-request.json` in a new directory. The audit is canonical UTF-8 JSON:
sorted keys, compact separators, one final newline, and no nonfinite values.
The signing request gives the exact audit byte digest. Give the external
signer the audit bytes and request. The signer should confirm the candidate,
input digests, and expected key before producing a detached Ed25519 signature.

The signing key stays with the independent signer. The preparer accepts only
the detached signature, public key, and externally pinned fingerprint. It
does not create or save a private key. To check the signed audit and run the
existing public 112-lane assembly:

```sh
python3 tools/qualification/independent_audit_producer.py finalize \
  --repository "$PWD" --candidate-sha "$CANDIDATE_SHA" \
  --prepared-dir "$AUDIT_HANDOFF" \
  --candidate-manifest "$CANDIDATE_MANIFEST" \
  --staged-audit "$STAGED_AUDIT" \
  --observations "$INDEPENDENT_OBSERVATIONS" \
  --signature "$DETACHED_SIGNATURE" \
  --trusted-public-key "$TRUSTED_PUBLIC_KEY" \
  --trusted-key-sha256 "$TRUSTED_KEY_SHA256" \
  --output "$ASSEMBLY_RESULT"
```

Finalization checks the signed exact input hashes, all archive files and times,
the signature, the pinned DER fingerprint, and the public verifier output. It
rechecks every archive after public assembly, including failed attempts. It
compares every lane's public gate result digest with the signed preflight.
The output contains the assembly `result_sha256`, the signed audit byte digest,
and the archive map byte digest.
The command exits 1 for an honest `NOT_RUN`, `FAILED`, or `UNAVAILABLE`
assembly. It exits 0 only if the existing assembler reports `PASSED`.

A task-local mode-700 directory limits accidental reads. A separate process
under the same user does not establish independent signing custody. The
operator must arrange that custody outside this tool. The test suite uses an
isolated generated key only to check the protocol. Its synthetic staged
audit does not qualify a runtime lane or the full port.
