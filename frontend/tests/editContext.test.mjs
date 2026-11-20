import assert from 'node:assert/strict'
import { wordChange } from '../src/services/editContext.ts'

assert.deepEqual(wordChange('tự', 'tư', 1, 2, 1, 2), {
  start: 0, end: 2, afterStart: 0, afterEnd: 2, before: 'tự', after: 'tư',
})
assert.equal(wordChange('Tôi tự học.', 'Tôi tư học.', 5, 6, 5, 6).before, 'tự')
assert.equal(wordChange('Tôi tự học.', 'Tôi tư học.', 5, 6, 5, 6).after, 'tư')
assert.equal(wordChange('abc', 'abcd', 3, 3, 3, 4).before, 'abc')
console.log('Word-level edit context: PASS')
