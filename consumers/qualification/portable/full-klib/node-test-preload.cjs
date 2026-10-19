const { describe, it } = require('node:test');

globalThis.describe = describe;
globalThis.it = it;
globalThis.xdescribe = describe.skip;
globalThis.xit = it.skip;
