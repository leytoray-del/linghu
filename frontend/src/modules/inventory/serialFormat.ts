/**
 * Serial number formats in plain words.
 *
 * Models can carry a serial number format so that, on a label with several barcodes, only the serial
 * number is accepted. People should never have to write one: they scan or type one real serial number,
 * choose one of the suggestions below, and see the format described in words.
 */

export interface FormatOption {
  pattern: string | null
  description: string
  /** Explains when to choose this option. */
  hint: string
}

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

function runs(value: string): { kind: 'digit' | 'letter' | 'other'; text: string }[] {
  const out: { kind: 'digit' | 'letter' | 'other'; text: string }[] = []
  for (const ch of value) {
    const kind = /[0-9]/.test(ch) ? 'digit' : /[A-Z]/.test(ch) ? 'letter' : 'other'
    const last = out[out.length - 1]
    if (last && last.kind === kind && kind !== 'other') last.text += ch
    else out.push({ kind, text: ch })
  }
  return out
}

function classOf(kind: 'digit' | 'letter' | 'other', text: string): string {
  if (kind === 'digit') return `[0-9]{${text.length}}`
  if (kind === 'letter') return `[A-Z]{${text.length}}`
  return esc(text)
}

/** Format suggestions for one example serial number, most specific first. */
export function suggestFormats(sample: string): FormatOption[] {
  const s = sample.replace(/\s+/g, '').toUpperCase()
  const options: FormatOption[] = []
  if (!s) return [{ pattern: null, description: 'Accept any code', hint: 'No check. Every barcode on the label is accepted, so choose the right one with care.' }]

  // 1. Everything up to the last letter is fixed; a run of digits follows (the most common layout).
  const tail = /^(.*[^0-9])([0-9]{3,})$/.exec(s)
  if (tail) {
    options.push({
      pattern: `${esc(tail[1]!)}[0-9]{${tail[2]!.length}}`,
      description: describeFormat(`${esc(tail[1]!)}[0-9]{${tail[2]!.length}}`),
      hint: 'Best when every unit of this model starts the same way. Safest choice.',
    })
  }
  // 2. Only the leading letters are fixed; the rest keeps its shape of digits and letters.
  const parts = runs(s)
  if (parts[0]?.kind === 'letter' && parts.length > 1) {
    const pattern = esc(parts[0].text) + parts.slice(1).map((p) => classOf(p.kind, p.text)).join('')
    if (!options.some((o) => o.pattern === pattern)) {
      options.push({ pattern, description: describeFormat(pattern), hint: 'Use when the characters after the first letters change between units.' })
    }
  }
  // 3. Same length, any letters and digits.
  if (/^[A-Z0-9]+$/.test(s)) {
    options.push({
      pattern: `[A-Z0-9]{${s.length}}`,
      description: describeFormat(`[A-Z0-9]{${s.length}}`),
      hint: 'Loose: other barcodes of the same length would also be accepted.',
    })
  }
  options.push({ pattern: null, description: 'Accept any code', hint: 'No check. Part numbers and dates are still skipped automatically.' })
  return options
}

/** Describe a format in words. Formats made by suggestFormats are always described; others are shown as written. */
export function describeFormat(pattern: string | null | undefined): string {
  if (!pattern) return 'Any code (no check)'
  const token = /\[(?:A-Z0-9|0-9A-Z)\](?:\{(\d+)\})?|\[0-9\](?:\{(\d+)\})?|\[A-Z\](?:\{(\d+)\})?|\\(.)|([A-Z0-9-])/gy
  let prefix = ''
  const rest: string[] = []
  let m: RegExpExecArray | null
  let pos = 0
  while ((m = token.exec(pattern))) {
    pos = token.lastIndex
    const literal = m[4] ?? m[5]
    if (literal !== undefined) {
      if (rest.length) rest.push(`"${literal}"`)
      else prefix += literal
    } else if (m[0].startsWith('[A-Z0-9]') || m[0].startsWith('[0-9A-Z]')) rest.push(plural(Number(m[1] ?? 1), 'letter or digit', 'letters or digits'))
    else if (m[0].startsWith('[0-9]')) rest.push(plural(Number(m[2] ?? 1), 'digit', 'digits'))
    else rest.push(plural(Number(m[3] ?? 1), 'letter', 'letters'))
  }
  if (pos !== pattern.length) return `Custom format: ${pattern}`
  const list = rest.length > 1 ? `${rest.slice(0, -1).join(', ')} and ${rest[rest.length - 1]}` : (rest[0] ?? '')
  if (prefix && list) return `Starts with ${prefix}, followed by ${list}`
  if (prefix) return `Exactly ${prefix}`
  return list ? `Any ${list}`.replace('Any 1 ', 'One ') : 'Any code (no check)'
}

export function formatMatches(pattern: string | null | undefined, value: string): boolean {
  if (!pattern) return true
  try {
    return new RegExp(`^(?:${pattern})$`).test(value.replace(/\s+/g, '').toUpperCase())
  } catch {
    return false
  }
}
