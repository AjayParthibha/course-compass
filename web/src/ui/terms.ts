export function termLabel(term: string, long = false) {
  const season = term.startsWith('FA') ? 'Fall' : term.startsWith('SP') ? 'Spring' : term.slice(0, 2)
  return long ? `${season} 20${term.slice(2)}` : `${season} ’${term.slice(2)}`
}

export function initials(code: string) {
  return code.replace(/[^A-Z0-9]/gi, '').slice(0, 2).toUpperCase()
}
