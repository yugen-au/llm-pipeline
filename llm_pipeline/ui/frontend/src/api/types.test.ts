import { describe, expect, it } from 'vitest'
import { toSearchParams, ApiError } from './types'

describe('toSearchParams', () => {
  it('returns empty string for empty object', () => {
    expect(toSearchParams({})).toBe('')
  })

  it('returns query string for single param', () => {
    expect(toSearchParams({ key: 'value' })).toBe('?key=value')
  })

  it('returns query string for multiple params', () => {
    const result = toSearchParams({ a: '1', b: '2' })
    expect(result).toBe('?a=1&b=2')
  })

  it('omits null values', () => {
    expect(toSearchParams({ a: '1', b: null })).toBe('?a=1')
  })

  it('omits undefined values', () => {
    expect(toSearchParams({ a: '1', b: undefined })).toBe('?a=1')
  })

  it('returns empty string when all values are null/undefined', () => {
    expect(toSearchParams({ a: null, b: undefined })).toBe('')
  })

  it('converts number values to strings', () => {
    expect(toSearchParams({ offset: 10, limit: 25 })).toBe('?offset=10&limit=25')
  })

  it('converts boolean values to strings', () => {
    expect(toSearchParams({ active: true })).toBe('?active=true')
  })

  it('encodes special characters', () => {
    const result = toSearchParams({ q: 'hello world' })
    expect(result).toBe('?q=hello+world')
  })
})

describe('ApiError', () => {
  it('sets name to ApiError', () => {
    const err = new ApiError(404, 'not found')
    expect(err.name).toBe('ApiError')
  })

  it('sets status from constructor', () => {
    const err = new ApiError(500, 'server error')
    expect(err.status).toBe(500)
  })

  it('sets detail from constructor', () => {
    const err = new ApiError(422, 'validation failed')
    expect(err.detail).toBe('validation failed')
  })

  it('uses detail as Error message', () => {
    const err = new ApiError(400, 'bad request')
    expect(err.message).toBe('bad request')
  })

  it('is instanceof Error', () => {
    const err = new ApiError(403, 'forbidden')
    expect(err).toBeInstanceOf(Error)
  })

  it('is instanceof ApiError', () => {
    const err = new ApiError(401, 'unauthorized')
    expect(err).toBeInstanceOf(ApiError)
  })
})
