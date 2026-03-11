import { describe, expect, it } from 'vitest'
import { validateForm } from './InputForm'

describe('validateForm', () => {
  it('returns empty object when schema is null', () => {
    expect(validateForm(null, {})).toEqual({})
  })

  it('returns empty object when schema has no required fields', () => {
    const schema = { properties: { name: { type: 'string' } } }
    expect(validateForm(schema, {})).toEqual({})
  })

  it('returns error for missing required field (undefined)', () => {
    const schema = {
      required: ['name'],
      properties: { name: { type: 'string', title: 'Name' } },
    }
    expect(validateForm(schema, {})).toEqual({ name: 'Name is required' })
  })

  it('returns error for null required field', () => {
    const schema = {
      required: ['name'],
      properties: { name: { type: 'string', title: 'Name' } },
    }
    expect(validateForm(schema, { name: null })).toEqual({ name: 'Name is required' })
  })

  it('returns error for empty string required field', () => {
    const schema = {
      required: ['name'],
      properties: { name: { type: 'string', title: 'Name' } },
    }
    expect(validateForm(schema, { name: '' })).toEqual({ name: 'Name is required' })
  })

  it('uses field key as fallback when title is missing', () => {
    const schema = {
      required: ['name'],
      properties: { name: { type: 'string' } },
    }
    expect(validateForm(schema, {})).toEqual({ name: 'name is required' })
  })

  it('returns empty object when all required fields present', () => {
    const schema = {
      required: ['name', 'age'],
      properties: {
        name: { type: 'string', title: 'Name' },
        age: { type: 'integer', title: 'Age' },
      },
    }
    expect(validateForm(schema, { name: 'Alice', age: 30 })).toEqual({})
  })

  it('returns errors for multiple missing required fields', () => {
    const schema = {
      required: ['name', 'email'],
      properties: {
        name: { type: 'string', title: 'Name' },
        email: { type: 'string', title: 'Email' },
      },
    }
    expect(validateForm(schema, {})).toEqual({
      name: 'Name is required',
      email: 'Email is required',
    })
  })

  it('treats 0 and false as present values', () => {
    const schema = {
      required: ['count', 'active'],
      properties: {
        count: { type: 'integer', title: 'Count' },
        active: { type: 'boolean', title: 'Active' },
      },
    }
    expect(validateForm(schema, { count: 0, active: false })).toEqual({})
  })

  it('handles schema with no properties gracefully', () => {
    const schema = { required: ['name'] }
    expect(validateForm(schema, {})).toEqual({ name: 'name is required' })
  })
})
