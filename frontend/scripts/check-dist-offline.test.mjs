import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { findExternalReferences } from './check-dist-offline.mjs'

describe('check-dist-offline', () => {
  it('the source index.html loads nothing from another origin', () => {
    // Το vitest τρέχει με root το frontend/ (jsdom: το import.meta.url δεν είναι file:).
    const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')
    expect(findExternalReferences(html)).toEqual([])
  })

  it('flags Google Fonts links', () => {
    const html =
      '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />' +
      '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk" rel="stylesheet" />'
    const findings = findExternalReferences(html)
    expect(findings).toContain('https://fonts.gstatic.com')
    expect(findings).toContain('https://fonts.googleapis.com/css2?family=Space+Grotesk')
  })

  it('allows only the exact XML namespaces and the react.dev/errors/ prefix', () => {
    const js =
      'createElementNS("http://www.w3.org/2000/svg",t);n="http://www.w3.org/1999/xlink";' +
      'm="http://www.w3.org/1998/Math/MathML";x="http://www.w3.org/XML/1998/namespace";' +
      'throw Error(`https://react.dev/errors/`+e)'
    expect(findExternalReferences(js)).toEqual([])

    expect(findExternalReferences('"http://www.w3.org/2000/svg-evil"')).toEqual(['http://www.w3.org/2000/svg-evil'])
    expect(findExternalReferences('"http://www.w3.org/"')).toEqual(['http://www.w3.org/'])
    expect(findExternalReferences('"https://react.dev/learn"')).toEqual(['https://react.dev/learn'])
    expect(findExternalReferences('src="//cdn.example.com/x.js"')).toEqual(['//cdn.example.com/x.js'])
  })

  it('ignores URLs inside license comments only', () => {
    expect(findExternalReferences('/*! lib | MIT | https://example.com/license */a=1')).toEqual([])
    expect(findExternalReferences('/** @license MIT https://example.com */a=1')).toEqual([])
    expect(findExternalReferences('/* https://example.com */a=1')).toEqual(['https://example.com'])
  })
})
