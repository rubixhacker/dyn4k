const test = require('node:test');
const assert = require('node:assert/strict');
const {Bidi, bodyBytes} = require('./firefox_bidi_witness.js');

class FakeSocket {
    constructor() { this.sent = []; }
    open() { this.onopen(); }
    send(message) { this.sent.push(JSON.parse(message)); }
    reply(id, result) {
        this.onmessage({data: JSON.stringify({id, type: 'success', result})});
    }
    drop() { this.onclose(); }
    close() { this.drop(); }
}

test('closed BiDi connection rejects pending body query', async () => {
    const bidi = new Bidi('ws://fake', FakeSocket, 1000);
    bidi.socket.open();
    const body = bidi.send('network.getData', {request: 'one', dataType: 'response'});
    await Promise.resolve();
    assert.equal(bidi.pending.size, 1);
    bidi.socket.drop();
    await assert.rejects(body, /closed/);
    assert.equal(bidi.pending.size, 0);
    await assert.rejects(bidi.send('network.getData'), /closed/);
});

test('closed idle BiDi connection reports capture failure', async () => {
    const bidi = new Bidi('ws://fake', FakeSocket, 1000);
    bidi.socket.open();
    let observed = null;
    bidi.onFailure = error => { observed = error.message; };
    bidi.socket.drop();
    assert.match(observed, /closed/);
    assert.equal(bidi.failure.message, observed);
});

test('silent BiDi command has a bounded deadline', async () => {
    const bidi = new Bidi('ws://fake', FakeSocket, 20);
    bidi.socket.open();
    await assert.rejects(bidi.send('network.getData'), /timed out/);
    assert.equal(bidi.pending.size, 0);
    bidi.close();
});

test('BiDi response bytes decode text and binary without substitution', () => {
    assert.deepEqual(bodyBytes({type: 'string', value: 'π'}), Buffer.from('π'));
    assert.deepEqual(bodyBytes({type: 'base64', value: 'AAECAw=='}),
        Buffer.from([0, 1, 2, 3]));
    assert.throws(() => bodyBytes({type: 'unknown', value: 'x'}), /encoding/);
});
