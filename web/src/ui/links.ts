/** CUReviews course page for a code like "CS 2110". Links only; we never fetch from CUReviews. */
export function cureviewsUrl(code: string): string {
  const m = code.trim().match(/^([A-Za-z&]+)\s*(\d+[A-Za-z]?)$/)
  if (!m) return 'https://www.cureviews.org/'
  return `https://www.cureviews.org/course/${encodeURIComponent(m[1].toUpperCase())}/${m[2]}`
}
