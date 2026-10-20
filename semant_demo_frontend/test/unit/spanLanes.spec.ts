import { describe, expect, it } from 'vitest'
import { assignLanes } from 'src/features/annotations/spanLanes'

const span = (id: string, start: number, end: number) => ({ id, start, end })

describe('assignLanes', () => {
  it('gives overlapping spans separate lanes, the longer one first at the same start', () => {
    const lanes = assignLanes([span('word', 0, 5), span('phrase', 0, 20), span('inner', 8, 12)])
    expect(lanes.get('phrase')).toBe(0)
    expect(lanes.get('word')).toBe(1)
    expect(lanes.get('inner')).toBe(1)
  })

  it('reuses a lane once its span has ended', () => {
    const lanes = assignLanes([span('a', 0, 5), span('b', 3, 9), span('c', 5, 7), span('d', 9, 12)])
    expect([lanes.get('a'), lanes.get('b'), lanes.get('c'), lanes.get('d')]).toEqual([0, 1, 0, 0])
  })

  it('keeps one lane per span however many overlap', () => {
    const lanes = assignLanes([0, 1, 2, 3, 4].map((i) => span(`s${i}`, i, 30)))
    expect([...lanes.values()]).toEqual([0, 1, 2, 3, 4])
  })

  it('skips spans without an id', () => {
    expect(assignLanes([{ id: null, start: 0, end: 4 }, span('a', 0, 2)])).toEqual(new Map([['a', 0]]))
  })
})
