// Underline lanes of the spans in a chunk's text. Each span keeps one lane along its
// whole length, so its line stays at the same depth under every segment it covers.

interface LaneSpan {
  id?: string | null
  start: number
  end: number
}

/**
 * Assigns each span the first lane that is free at its start, in start order (longer
 * spans first at the same start). Returns the lane of each span id; lane 0 is nearest
 * the text.
 */
export function assignLanes (spans: LaneSpan[]): Map<string, number> {
  const ordered = spans
    .filter((s): s is LaneSpan & { id: string } => !!s.id)
    .sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start))
  const laneEnds: number[] = []
  const lanes = new Map<string, number>()
  for (const span of ordered) {
    let lane = laneEnds.findIndex((end) => end <= span.start)
    if (lane === -1) lane = laneEnds.length
    laneEnds[lane] = span.end
    lanes.set(span.id, lane)
  }
  return lanes
}
