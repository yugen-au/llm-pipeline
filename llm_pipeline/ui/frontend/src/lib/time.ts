const DEFAULT_LOCALE = 'en'

const rtf = new Intl.RelativeTimeFormat(DEFAULT_LOCALE, { numeric: 'auto' })
const dtf = new Intl.DateTimeFormat(DEFAULT_LOCALE, {
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

function getRtf(locale: string): Intl.RelativeTimeFormat {
  if (locale === DEFAULT_LOCALE) return rtf
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
}

function getDtf(locale: string): Intl.DateTimeFormat {
  if (locale === DEFAULT_LOCALE) return dtf
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

/**
 * Human-readable relative timestamp ("3 minutes ago", "2 hours ago").
 * Picks the largest unit where the absolute elapsed value >= 1.
 * Future dates are formatted the same way (e.g. "in 5 minutes").
 */
export function formatRelative(
  isoString: string,
  locale: string = DEFAULT_LOCALE,
): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffSeconds = Math.floor((then - now) / 1_000)

  const abs = Math.abs(diffSeconds)
  const fmt = getRtf(locale)

  for (const [threshold, unit] of THRESHOLDS) {
    if (abs >= threshold) {
      const value =
        diffSeconds >= 0
          ? Math.floor(diffSeconds / threshold)
          : -Math.floor(abs / threshold)
      return fmt.format(value, unit)
    }
  }

  // < 1 second or exactly 0
  return fmt.format(0, 'second')
}

/**
 * Locale date+time string for tooltip display.
 * e.g. "Feb 23, 2026, 10:30 AM"
 */
export function formatAbsolute(
  isoString: string,
  locale: string = DEFAULT_LOCALE,
): string {
  return getDtf(locale).format(new Date(isoString))
}

/**
 * Format millisecond duration as seconds with 1 decimal.
 * Returns em dash for null/undefined.
 */
export function formatDuration(ms: number | null): string {
  if (ms == null) return '\u2014'
  return `${(ms / 1000).toFixed(1)}s`
}
