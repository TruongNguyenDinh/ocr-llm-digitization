const word = /[\p{L}\p{M}\p{N}_]/u

export function wordChange(before: string, after: string, start: number, end: number, afterStart: number, afterEnd: number) {
  let left = start, right = end, nextLeft = afterStart, nextRight = afterEnd
  while (left > 0 && nextLeft > 0 && word.test(before[left - 1]) && word.test(after[nextLeft - 1])) { left--; nextLeft-- }
  while (right < before.length && nextRight < after.length && word.test(before[right]) && word.test(after[nextRight])) { right++; nextRight++ }
  return { start: left, end: right, afterStart: nextLeft, afterEnd: nextRight,
    before: before.slice(left, right), after: after.slice(nextLeft, nextRight) }
}
