import { configure } from '@testing-library/react'

// Panes are code-split, so the first render of one loads a chunk. A generous
// async timeout keeps the suite stable on slow or busy CI machines.
configure({ asyncUtilTimeout: 5000 })

// jsdom lacks several browser APIs that React Flow, cmdk and CodeMirror rely on.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!('ResizeObserver' in globalThis)) {
  Object.assign(globalThis, { ResizeObserver: ResizeObserverStub })
}

class DOMMatrixStub {
  m22 = 1
  constructor(_init?: unknown) {}
}
if (!('DOMMatrixReadOnly' in globalThis)) {
  Object.assign(globalThis, { DOMMatrixReadOnly: DOMMatrixStub, DOMMatrix: DOMMatrixStub })
}

Element.prototype.scrollIntoView ??= () => {}
Range.prototype.getClientRects ??= () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList
Range.prototype.getBoundingClientRect ??= () => new DOMRect(0, 0, 0, 0)

// <dialog>: older jsdom versions have no showModal/close.
HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
  this.setAttribute('open', '')
}
HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
  this.removeAttribute('open')
}

window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia
