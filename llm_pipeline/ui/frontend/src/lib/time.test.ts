import { formatRelative, formatAbsolute } from './time'

const NOW = '2026-02-23T12:00:00.000Z'

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(NOW))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('formatRelative', () => {
  it('returns "now" for 0 seconds difference', () => {
    expect(formatRelative(NOW)).toBe('now')
  })

  it('formats seconds ago', () => {
    const thirtySecondsAgo = '2026-02-23T11:59:30.000Z'
    expect(formatRelative(thirtySecondsAgo)).toBe('30 seconds ago')
  })

  it('formats 1 minute ago at 60s boundary', () => {
    const oneMinuteAgo = '2026-02-23T11:59:00.000Z'
    expect(formatRelative(oneMinuteAgo)).toBe('1 minute ago')
  })

  it('formats minutes ago', () => {
    const fiveMinutesAgo = '2026-02-23T11:55:00.000Z'
    expect(formatRelative(fiveMinutesAgo)).toBe('5 minutes ago')
  })

  it('formats 1 hour ago at 3600s boundary', () => {
    const oneHourAgo = '2026-02-23T11:00:00.000Z'
    expect(formatRelative(oneHourAgo)).toBe('1 hour ago')
  })

  it('formats hours ago', () => {
    const threeHoursAgo = '2026-02-23T09:00:00.000Z'
    expect(formatRelative(threeHoursAgo)).toBe('3 hours ago')
  })

  it('formats 1 day ago at 86400s boundary', () => {
    const oneDayAgo = '2026-02-22T12:00:00.000Z'
    expect(formatRelative(oneDayAgo)).toBe('yesterday')
  })

  it('formats days ago', () => {
    const fiveDaysAgo = '2026-02-18T12:00:00.000Z'
    expect(formatRelative(fiveDaysAgo)).toBe('5 days ago')
  })

  it('handles future dates gracefully', () => {
    const fiveMinutesFromNow = '2026-02-23T12:05:00.000Z'
    expect(formatRelative(fiveMinutesFromNow)).toBe('in 5 minutes')
  })

  it('handles future date in hours', () => {
    const twoHoursFromNow = '2026-02-23T14:00:00.000Z'
    expect(formatRelative(twoHoursFromNow)).toBe('in 2 hours')
  })

  it('formats 59 seconds as seconds (below minute threshold)', () => {
    const fiftyNineSecondsAgo = '2026-02-23T11:59:01.000Z'
    expect(formatRelative(fiftyNineSecondsAgo)).toBe('59 seconds ago')
  })

  it('formats 23 hours as hours (below day threshold)', () => {
    const twentyThreeHoursAgo = '2026-02-22T13:00:00.000Z'
    expect(formatRelative(twentyThreeHoursAgo)).toBe('23 hours ago')
  })

  it('truncates rather than rounds at unit boundaries (90s -> 1 minute ago)', () => {
    // 90 seconds = 1.5 minutes; Math.floor ensures "1 minute ago" not "2 minutes ago"
    const ninetySecondsAgo = '2026-02-23T11:58:30.000Z'
    expect(formatRelative(ninetySecondsAgo)).toBe('1 minute ago')
  })

  it('truncates future dates at unit boundaries (90s -> in 1 minute)', () => {
    const ninetySecondsFromNow = '2026-02-23T12:01:30.000Z'
    expect(formatRelative(ninetySecondsFromNow)).toBe('in 1 minute')
  })

  it('uses default en locale when none specified', () => {
    const fiveMinutesAgo = '2026-02-23T11:55:00.000Z'
    expect(formatRelative(fiveMinutesAgo)).toBe('5 minutes ago')
    expect(formatRelative(fiveMinutesAgo, 'en')).toBe('5 minutes ago')
  })

  it('accepts a different locale', () => {
    const fiveMinutesAgo = '2026-02-23T11:55:00.000Z'
    const result = formatRelative(fiveMinutesAgo, 'de')
    // German: "vor 5 Minuten"
    expect(result).toContain('5')
    expect(result).not.toBe('5 minutes ago')
  })
})

describe('formatAbsolute', () => {
  it('returns a formatted date+time string', () => {
    const result = formatAbsolute('2026-02-23T14:30:00.000Z')
    // Output varies by timezone; check structure not exact day
    expect(result).toContain('2026')
    // Should match medium date style: "Mon DD, YYYY" or nearby day
    expect(result).toMatch(/Feb \d{1,2}, 2026/)
    // Should contain time portion
    expect(result).toMatch(/\d{1,2}:\d{2}\s[AP]M/)
  })

  it('formats a different date correctly', () => {
    const result = formatAbsolute('2025-12-25T12:00:00.000Z')
    expect(result).toContain('2025')
    expect(result).toMatch(/Dec \d{1,2}, 2025/)
  })

  it('uses default en locale when none specified', () => {
    const result = formatAbsolute('2026-02-23T14:30:00.000Z')
    const resultExplicit = formatAbsolute('2026-02-23T14:30:00.000Z', 'en')
    expect(result).toBe(resultExplicit)
  })

  it('accepts a different locale', () => {
    const result = formatAbsolute('2026-02-23T14:30:00.000Z', 'de')
    // German uses "Feb" or "Feb." for medium date style
    expect(result).toContain('2026')
    // Should not match English AM/PM pattern
    expect(result).not.toMatch(/[AP]M/)
  })
})
