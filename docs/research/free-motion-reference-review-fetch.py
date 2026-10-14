# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python3 free-motion-reference-review-fetch.py NEW_OUTPUT_DIRECTORY [KNOWN_HEADER_OFFSET]
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

if len(sys.argv) not in {2, 3} or not __debug__:
    raise SystemExit('Usage (without -O): python3 free-motion-reference-review-fetch.py NEW_OUTPUT_DIRECTORY [KNOWN_HEADER_OFFSET]')
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
target = 'package/canonical/L-free-s1.0-o0.0_0.0-hz60-0.jsonl.gz'
expected_hash = '4981795bffcd2a0262040acb53c60b20607fea14a2a0c7d79e858ba68e7f2743'
assets = json.loads(subprocess.check_output(['gh', 'release', 'view', 'calibration-raw-20260914', '--repo', 'rubixhacker/dyn4k', '--json', 'assets']))['assets']
parts = sorted((a for a in assets if a['name'].startswith('dyn4j-baseline-raw.tar.part-')), key=lambda a: a['name'])
assert len(parts) == 14 and sum(a['size'] for a in parts) == 19968512000
(out / 'assets.json').write_text(json.dumps(parts, indent=2) + '\n')
requests = []
headers = []
downloaded = 0

def fetch(offset: int, length: int) -> bytes:
    global downloaded
    assert 0 < length <= 4 * 1024 * 1024
    result = bytearray()
    while length:
        base = 0
        for part in parts:
            if offset < base + part['size']:
                break
            base += part['size']
        else:
            raise ValueError(offset)
        start = offset - base
        take = min(length, part['size'] - start)
        assert downloaded + take <= 8 * 1024 * 1024
        response = out / 'current-response.txt'
        payload = out / 'current-payload.bin'
        subprocess.run(['curl', '--location', '--silent', '--show-error', '--fail', '--range', f'{start}-{start + take - 1}', '--max-filesize', str(take), '--max-time', '20', '--dump-header', str(response), '--output', str(payload), part['url']], check=True, timeout=25)
        raw_headers = response.read_text()
        statuses = re.findall(r'^HTTP/\S+ (\d+)', raw_headers, re.M)
        ranges = re.findall(r'^content-range:\s*bytes (\d+)-(\d+)/(\d+)', raw_headers, re.I | re.M)
        assert statuses[-1] == '206' and tuple(map(int, ranges[-1])) == (start, start + take - 1, part['size'])
        data = payload.read_bytes()
        assert len(data) == take
        requests.append({'asset': part['name'], 'logical_offset': offset, 'range_start': start, 'range_end': start + take - 1, 'status': 206, 'bytes': take, 'sha256': hashlib.sha256(data).hexdigest()})
        (out / 'ranges.json').write_text(json.dumps(requests, indent=2) + '\n')
        response.unlink()
        payload.unlink()
        downloaded += take
        result.extend(data)
        length -= take
        offset += take
    return bytes(result)

offset = int(sys.argv[2]) if len(sys.argv) == 3 else 0
assert offset >= 0 and offset % 512 == 0
long_name = None
for visit in range(1200):
    block = fetch(offset, 512)
    assert block != bytes(512), 'Reached archive end without target'
    checksum = int(block[148:156].strip(b'\x00 '), 8)
    assert checksum == sum(block[:148]) + 8 * 32 + sum(block[156:])
    assert block[257:262] == b'ustar'
    name = block[:100].split(b'\0')[0].decode()
    if block[257:263] == b'ustar\0':
        prefix = block[345:500].split(b'\0')[0].decode()
        name = f'{prefix}/{name}' if prefix else name
    size = int(block[124:136].strip(b'\x00 ') or b'0', 8)
    kind = block[156:157].decode()
    if long_name is not None:
        name, long_name = long_name, None
    headers.append({'header_offset': offset, 'data_offset': offset + 512, 'member': name, 'size': size, 'type': kind, 'stored_checksum': checksum, 'checksum_validated': True, 'header_sha256': hashlib.sha256(block).hexdigest()})
    (out / 'visited-headers.json').write_text(json.dumps(headers, indent=2) + '\n')
    if kind == 'L':
        assert size <= 4096
        long_name = fetch(offset + 512, size).rstrip(b'\0').decode()
    elif kind in {'x', 'g', 'K'}:
        raise ValueError(f'Unsupported extended header at {offset}: {kind}')
    elif name == target:
        assert kind in {'0', '\0'} and size == 3945330
        data = fetch(offset + 512, size)
        assert hashlib.sha256(data).hexdigest() == expected_hash
        (out / Path(target).name).write_bytes(data)
        receipt = {'target': headers[-1], 'gzip_sha256': expected_hash, 'downloaded_bytes': downloaded, 'requests': len(requests), 'headers_visited': len(headers), 'complete_archive_hash_verified': False}
        (out / 'retrieval.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2), flush=True)
        break
    offset += 512 + ((size + 511) // 512) * 512
    if visit % 50 == 0:
        print(f'headers={visit + 1} logical_offset={offset} bytes_received={downloaded} last={name}', flush=True)
else:
    raise SystemExit('Bounded header count exhausted; retain visited-headers.json')
