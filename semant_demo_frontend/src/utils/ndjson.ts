/**
 * Read an NDJSON (one JSON value per line) response body, calling `onValue` for each
 * line as it arrives. Lines may be split across network chunks, also inside a multi-byte
 * UTF-8 character. Blank lines are skipped; a line that is not JSON is reported to
 * `onInvalid` and skipped. Resolves when the stream ends; rejects when reading fails
 * (e.g. `AbortError` after the request was aborted).
 */
export async function readNdjson (
  body: ReadableStream<Uint8Array>,
  onValue: (value: unknown) => void,
  onInvalid: (line: string, error: unknown) => void = () => undefined
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const handleLine = (line: string) => {
    const trimmed = line.trim()
    if (!trimmed) return
    let value: unknown
    try {
      value = JSON.parse(trimmed)
    } catch (e) {
      onInvalid(trimmed, e)
      return
    }
    onValue(value)
  }

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let newlineIdx = buffer.indexOf('\n')
    while (newlineIdx !== -1) {
      handleLine(buffer.slice(0, newlineIdx))
      buffer = buffer.slice(newlineIdx + 1)
      newlineIdx = buffer.indexOf('\n')
    }
  }
  buffer += decoder.decode()
  handleLine(buffer)
}
