const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const dtf = new Intl.DateTimeFormat('en', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

type TimeUnit = 'second' | 'minute' | 'hour' | 'day'

const THRESHOLDS: [number, TimeUnit][] = [
  [86_400, 'day'],
  [3_600, 'hour'],
  [60, 'minute'],
  [1, 'second'],
]

/**
 * Human-readable relative timestamp ("3 minutes ago", "2 hours ago").
 * Picks the largest unit where the absolute elapsed value >= 1.
 * Future dates are formatted the same way (e.g. "in 5 minutes").
 */
export function formatRelative(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffSeconds = Math.round((then - now) / 1_000)

  const abs = Math.abs(diffSeconds)

  for (const [threshold, unit] of THRESHOLDS) {
    if (abs >= threshold) {
      const value = Math.round(diffSeconds / threshold)
      return rtf.format(value, unit)
    }
  }

  // < 1 second or exactly 0
  return rtf.format(0, 'second')
}

/**
 * Locale date+time string for tooltip display.
 * e.g. "Feb 23, 2026, 10:30 AM"
 */
export function formatAbsolute(isoString: string): string {
  return dtf.format(new Date(isoString))
}
