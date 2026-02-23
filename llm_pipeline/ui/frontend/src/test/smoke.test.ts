// Smoke test: verifies vitest + jsdom + jest-dom matchers work
describe('vitest infrastructure', () => {
  it('has jsdom environment', () => {
    expect(document).toBeDefined()
    expect(window).toBeDefined()
  })

  it('has jest-dom matchers', () => {
    const el = document.createElement('div')
    el.textContent = 'hello'
    document.body.appendChild(el)
    expect(el).toBeInTheDocument()
    document.body.removeChild(el)
  })
})
