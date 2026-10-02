import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const { contains } = await import(pathToFileURL(`${process.argv[2]}/bounds.ts`));
assert.equal(contains(0, 10), true);
assert.equal(contains(-1, 10), false);
assert.equal(contains(11, 10), false);
assert.equal(contains(10, 10), true, 'REAPER_EXPECTED_BOUNDARY_FAILURE');
console.log('Trusted boundary and regression checks passed');
