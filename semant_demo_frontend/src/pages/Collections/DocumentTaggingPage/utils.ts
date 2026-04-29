export const snapToWordBoundary = (
  index: number,
  type: 'start' | 'end',
  text: string
): number => {
  // Define what makes up a word. (\w includes letters, numbers, and underscores).
  // You can adjust the regex to include accented chars or hyphens depending on your needs.
  const isWordChar = (char: string) => /[\w]/.test(char)

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
      return i
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
      return i
    }
  }

  // If we selected a space or punctuation, just return the exact selected index without snapping.
  return index
}
