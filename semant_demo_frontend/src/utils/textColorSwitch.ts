export function textColorSwitcher (color: string): string {
  try {
    // validate hex color must be #RRGGBB
    if (!/^#[0-9A-Fa-f]{6}$/.test(color)) {
      console.warn('Invalid color format, using default white text:', color)
      return '#FFFFFF'
    }

    const r = parseInt(color.substring(1, 3), 16)
    const g = parseInt(color.substring(3, 5), 16)
    const b = parseInt(color.substring(5, 7), 16)

    // calculate relative luminance
    const luminance = 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255)
    console.log('Luminance:', luminance, 'Returning:', luminance > 0.5 ? '#000000' : '#FFFFFF')
    return luminance > 0.5 ? 'black' : 'white'
  } catch (error) {
    console.error('Error in textColorSwitcher:', error)
    return 'white' // fallback to white text
  }
}
