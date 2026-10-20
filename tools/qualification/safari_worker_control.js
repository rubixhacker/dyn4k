const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const vm = require('node:vm');

const [root, archive, portFile] = process.argv.slice(2);
const token = 'e'.repeat(64);
const folder = path.join(root, 'consumers/qualification/portable/full-browser');
const observer = path.join(folder, 'safari_karma_observer.js');
const environment = {
    DYN4K_BROWSER_KARMA_PORT: '0',
    DYN4K_BROWSER_TOKEN: token,
    DYN4K_SAFARI_OBSERVER_ARCHIVE: archive,
    DYN4K_SAFARI_OBSERVER_SOURCE: observer,
    DYN4K_SAFARI_WORKER_SOURCE: path.join(folder, 'safari_response_worker.js'),
    DYN4K_SAFARI_BOOTSTRAP_SOURCE: path.join(folder, 'safari_response_bootstrap.js')
};
const config = {
    plugins: [], beforeMiddleware: ['qualification-response'],
    set(values) { Object.assign(this, values); }
};
const javascript = Buffer.from('window.dyn4kExecuted = true;');
const wasm = Buffer.from([0, 97, 115, 109, 1, 0, 0, 0]);
const selected = new Map([
    ['/absolute/build/runtime.js', javascript],
    ['/absolute/build/aaaaaaaaaaaaaaaaaaaa.wasm', wasm]
]);
const ipv4 = http.createServer();
const ipv6 = http.createServer();
function start(port) {
    environment.DYN4K_BROWSER_KARMA_PORT = String(port);
    vm.runInNewContext(fs.readFileSync(observer, 'utf8'), {
        config, process: {env: environment, pid: process.pid}, require, Buffer, URL
    });
    const middleware = config.plugins[0]['middleware:qualification-safari-observer'][1]();
    const handle = (request, response) => middleware(request, response, () => {
        const pathname = new URL(request.url, 'http://localhost:' + port).pathname;
        if (pathname === '/control-done' && request.method === 'POST') {
            const chunks = [];
            request.on('data', chunk => chunks.push(chunk));
            request.on('end', () => {
                fs.writeFileSync(path.join(archive, 'browser-result.txt'),
                    Buffer.concat(chunks), {flag: 'wx'});
                response.writeHead(204);
                response.end();
            });
            return;
        }
        if (pathname === '/test.html') {
            response.writeHead(200, {'Content-Type': 'text/html'});
            response.end('<script src="/absolute/build/runtime.js"></script><script>' +
                'fetch("/absolute/build/aaaaaaaaaaaaaaaaaaaa.wasm")' +
                '.then(response => WebAssembly.compileStreaming(response))' +
                '.then(() => { document.body.textContent = "PASS:" + window.dyn4kExecuted;' +
                'return fetch("/control-done", {method:"POST",body:document.body.textContent}); })' +
                '.catch(error => document.body.textContent = "FAIL:" + error)' +
                '</script>');
            return;
        }
        const bytes = selected.get(pathname);
        if (!bytes) {
            response.writeHead(404);
            response.end('missing');
            return;
        }
        response.writeHead(200, {'Content-Type': pathname.endsWith('.wasm')
            ? 'application/wasm' : 'text/javascript'});
        response.end(bytes);
    });
    ipv4.on('request', handle);
    ipv6.on('request', handle);
    fs.writeFileSync(portFile, String(port), {flag: 'wx'});
}
ipv4.listen(0, '127.0.0.1', () => {
    const port = ipv4.address().port;
    ipv6.listen(port, '::1', () => start(port));
});
process.on('SIGTERM', () => {
    for (const server of [ipv4, ipv6]) {
        if (server.listening) server.close();
    }
});
