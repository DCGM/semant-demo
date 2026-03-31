export const snapToWordBoundary = (
  index: number,
  type: 'start' | 'end',
  text: string
) => {
  if (!text || index < 0 || index > text.length) return index

  // Matches any Unicode letter or number (supports accents, e.g., á, č, ř)
  const isWordChar = (char: string) => /[\p{L}\p{N}]/u.test(char)

  let i = index
  if (type === 'start') {
    // When evaluating the start, look at the character just BEFORE the cursor
    // and push the index left until we hit a space or punctuation.
    while (i > 0 && isWordChar(text[i - 1])) {
      i--
    }
  } else {
    // When evaluating the end, look at the character AT the cursor
    // and push the index right until we hit a space or punctuation.
    while (i < text.length && isWordChar(text[i])) {
      i++
    }
  }
  return i
}
