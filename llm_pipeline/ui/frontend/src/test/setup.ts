import '@testing-library/jest-dom/vitest'

// Polyfill pointer capture APIs missing in jsdom (required by Radix UI)
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}

// Polyfill scrollIntoView (used by Radix for select items)
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
