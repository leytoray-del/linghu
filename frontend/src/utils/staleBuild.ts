/**
 * After a new release, a tab opened earlier still runs the old app and asks for page files that no
 * longer exist. Reload once to get the current version. A short guard prevents a reload loop if the
 * failure has another cause (for example, the server is unreachable).
 */
const KEY = 'erf-stale-reload-at'
const GUARD_MS = 30_000

export function isStaleBuildError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS|MIME type/i.test(
    message,
  )
}

export function reloadForNewVersion(target?: string): boolean {
  let last = 0
  try {
    last = Number(sessionStorage.getItem(KEY) ?? 0)
    sessionStorage.setItem(KEY, String(Date.now()))
  } catch {
    // Storage can be unavailable (private mode); reload anyway.
  }
  if (Date.now() - last < GUARD_MS) return false
  if (target) window.location.assign(target)
  else window.location.reload()
  return true
}
