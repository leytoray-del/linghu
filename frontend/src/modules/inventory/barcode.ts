/**
 * Picking the serial number out of what a barcode contains.
 *
 * Equipment labels often follow the ANSI MH10.8.2 convention: each barcode starts with a data identifier,
 * printed in brackets next to it, for example "(S) S/N", "(1P) P/N" and "(D) MFD". The barcode for
 * "(S) S/N: HUR400A260500052" therefore contains "SHUR400A260500052". This module removes the
 * identifier from serial numbers and recognises part numbers, dates and quantities so they are skipped.
 */

export type Verdict =
  | { kind: 'serial'; serial: string }
  | { kind: 'skip'; reason: string; wrongFormat?: boolean }

/** Part number, customer part number, date and quantity identifiers: never a serial number. */
const NOT_A_SERIAL: { re: RegExp; what: string }[] = [
  { re: /^1P./, what: 'a part number' },
  { re: /^30P./, what: 'a part number' },
  { re: /^\d{0,2}D\d{4}[/.-]?\d{2}[/.-]?\d{2}$/, what: 'a date' },
  { re: /^D\d{6,8}$/, what: 'a date' },
  { re: /^Q\d{1,6}$/, what: 'a quantity' },
  { re: /^\d{4}[/.-]\d{1,2}[/.-]\d{1,2}$/, what: 'a date' },
  { re: /^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$/, what: 'a date' },
]

export function normaliseCode(raw: string): string {
  // Strip control characters some scanners add, and spaces.
  return raw.replace(/[\u0000-\u001f]/g, '').replace(/\s+/g, '').toUpperCase()
}

function matches(pattern: string, value: string): boolean {
  try {
    return new RegExp(`^(?:${pattern})$`).test(value)
  } catch {
    return true
  }
}

/** Values the code could stand for, most likely first. */
function candidates(code: string): string[] {
  const list = [code]
  if (/^1S[A-Z0-9]/.test(code)) list.unshift(code.slice(2))
  else if (/^S[A-Z0-9-]{5,}$/.test(code)) list.unshift(code.slice(1))
  return list
}

/**
 * Decide whether a scanned code is a serial number for the model.
 * With a serial number format, only a matching value is accepted. Without one, identifiers are removed
 * and part numbers, dates and quantities are skipped.
 */
export function pickSerial(raw: string, pattern: string | null | undefined, modelNo = 'this model'): Verdict {
  const code = normaliseCode(raw)
  if (!code) return { kind: 'skip', reason: 'The barcode is empty.' }
  const options = candidates(code)
  if (pattern) {
    // Try the value as read first, then without an identifier.
    const hit = [code, ...options.filter((c) => c !== code)].find((c) => matches(pattern, c))
    return hit
      ? { kind: 'serial', serial: hit }
      : { kind: 'skip', wrongFormat: true, reason: `${code} does not match the serial number format of ${modelNo}.` }
  }
  const other = NOT_A_SERIAL.find((n) => n.re.test(code))
  if (other) return { kind: 'skip', reason: `${code} looks like ${other.what}, not a serial number.` }
  return { kind: 'serial', serial: options[0]! }
}
