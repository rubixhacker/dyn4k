const token = new URL(self.location.href).searchParams.get('token');

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'dyn4k-control' &&
            event.data.token === token && event.ports[0]) {
        event.ports[0].postMessage({token, client_id: event.source.id});
    }
});

self.addEventListener('fetch', event => {
    const address = new URL(event.request.url);
    if (address.origin !== self.location.origin ||
            address.pathname.startsWith('/__dyn4k_')) return;
    const name = address.pathname.split('/').pop();
    const selected = /^\/(?:absolute|base)\//.test(address.pathname) &&
        (/^(?:runtime|commons|kotlin-test-karma-runner\.[0-9]+|load\.[0-9]+|dyn4k-full-staged-browser-consumer-(?:core|facade)-test\.[0-9]+)\.js$/.test(name) ||
         /^[0-9a-f]{20}\.wasm$/.test(name) ||
         /^(?:dyn4k-full-staged-browser-consumer-(?:core|facade)-test\.(?:mjs|wasm|import-object\.mjs|js-builtins\.mjs)|custom-formatters\.js)$/.test(name));
    const navigation = event.request.mode === 'navigate';
    if (!selected && !navigation) return;
    event.respondWith((async () => {
        try {
            const request_ns = Date.now() * 1000000;
            const response = await fetch(event.request);
            const response_ns = Date.now() * 1000000;
            if (response.status !== 200 || response.type !== 'basic') {
                throw new Error('Safari witness received a non-network response');
            }
            let client = event.clientId ? await self.clients.get(event.clientId) : null;
            let client_id_source = 'fetch-event';
            let eligible_count = 0;
            if (!client && navigation && !event.clientId) {
                const candidates = await self.clients.matchAll({type: 'window',
                    includeUncontrolled: false});
                const eligible = candidates.filter(candidate => {
                    const url = new URL(candidate.url);
                    return url.origin === self.location.origin &&
                        (url.pathname !== '/__dyn4k_bootstrap' ||
                         (url.searchParams.get('token') === token &&
                          url.searchParams.get('target') === event.request.url));
                });
                eligible_count = eligible.length;
                if (eligible.length === 1) {
                    client = eligible[0];
                    client_id_source = 'single-controlled-client';
                }
            }
            if (!client || !client.url) {
                throw new Error('Safari witness client is absent; eligible=' + eligible_count);
            }
            const body = selected ? await response.clone().arrayBuffer() : new ArrayBuffer(0);
            const request_id = self.crypto.randomUUID();
            const metadata = {
                token, kind: selected ? 'response' : 'navigation', request_id,
                url: event.request.url, client_id: client.id,
                fetch_client_id: event.clientId, client_id_source, eligible_count,
                client_url: client.url, resulting_client_id: event.resultingClientId || '',
                status: response.status, request_ns, response_ns,
                finished_ns: Date.now() * 1000000
            };
            const recorded = await fetch('/__dyn4k_record', {
                method: 'POST', headers: {'content-type': 'application/octet-stream',
                    'x-dyn4k-metadata': JSON.stringify(metadata)}, body
            });
            if (recorded.status !== 204) {
                throw new Error('Safari witness body recording failed');
            }
            return response;
        } catch (error) {
            try {
                await fetch('/__dyn4k_error', {method: 'POST',
                    headers: {'content-type': 'application/json'},
                    body: JSON.stringify({token, url: event.request.url,
                        client_id: event.clientId, mode: event.request.mode,
                        resulting_client_id: event.resultingClientId,
                        error: String(error)})});
            } catch (_) {}
            throw error;
        }
    })());
});
