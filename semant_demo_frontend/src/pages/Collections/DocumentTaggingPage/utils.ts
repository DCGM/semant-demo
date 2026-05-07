export const snapToWordBoundary = (
  index: number,
  type: 'start' | 'end',
  text: string
): number => {
  // \p{L} matches ANY letter from ANY language (including ěščřžýáíé)
  // \p{N} matches ANY number
  // _ matches underscore (to keep parity with the original \w)
  // The 'u' flag enables unicode matching
  const isWordChar = (char: string) => /[\p{L}\p{N}_]/u.test(char)
  const isLineBreakChar = (char: string) => char === '\n' || char === '\r'

  const trimLineBreakBoundary = (boundaryIndex: number): number => {
    let nextIndex = boundaryIndex

    if (type === 'start') {
      while (
        nextIndex < text.length &&
        isLineBreakChar(text[nextIndex] as string)
      ) {
        nextIndex++
      }
      return nextIndex
    }

    while (nextIndex > 0 && isLineBreakChar(text[nextIndex - 1] as string)) {
      nextIndex--
    }

    return nextIndex
  }

  if (index < 0) return 0
  if (index > text.length) return text.length

  if (type === 'start') {
    // Only snap backward if the character we landed on is ACTUALLY part of a word.
    // If it's a space or a dot, we leave the index exactly where it is.
    if (index < text.length && isWordChar(text[index])) {
      let i = index
      while (i > 0 && isWordChar(text[i - 1])) {
        i--
      }
      return trimLineBreakBoundary(i)
    }
  } else if (type === 'end') {
    // For 'end', the index is positioned just *after* the selected character.
    // We only snap forward to finish the word if the selection ended IN THE MIDDLE of a word.
    // (Meaning the char just before index is a word char, AND the char at index is also a word char).
    if (
      index > 0 &&
      index < text.length &&
      isWordChar(text[index - 1]) &&
      isWordChar(text[index])
    ) {
      let i = index
      while (i < text.length && isWordChar(text[i])) {
        i++
      }
      return trimLineBreakBoundary(i)
    }
  }

  // If we selected a space or punctuation, just return the exact selected index without snapping.
  return trimLineBreakBoundary(index)
}
