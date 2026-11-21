import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseAICommand } from '../src/services/searchCommands.ts'

test('recognizes /AI: queries case-insensitively and trims the question', () => {
  assert.equal(parseAICommand(' /AI:  Ông A được bổ nhiệm năm nào? '), 'Ông A được bổ nhiệm năm nào?')
  assert.equal(parseAICommand('/ai : tìm công văn'), 'tìm công văn')
})

test('does not route ordinary text or an empty /AI: command to global AI search', () => {
  assert.equal(parseAICommand('tìm công văn bổ nhiệm'), null)
  assert.equal(parseAICommand('/AI:'), null)
  assert.equal(parseAICommand('/AI:   '), null)
})
