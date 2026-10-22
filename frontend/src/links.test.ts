import { describe, expect, it } from 'vitest'
import { linkGroups } from './links'

describe('the links of an imported type', () => {
  it('manual, product page, video, in OFL’s order, web addresses only', () => {
    expect(
      linkGroups({ links: { manual: ['https://a.example/m.pdf', 'javascript:alert(1)'], productPage: ['http://b.example/p'], video: [], other: ['https://c.example'], custom: ['https://d.example'] } }),
    ).toEqual([
      { label: 'Manual', urls: ['https://a.example/m.pdf'] },
      { label: 'Product page', urls: ['http://b.example/p'] },
      { label: 'More', urls: ['https://c.example'] },
      { label: 'custom', urls: ['https://d.example'] },
    ])
  })
  it('a type without links (or with odd ones) has none', () => {
    expect(linkGroups({})).toEqual([])
    expect(linkGroups({ links: 'x' as never })).toEqual([])
    expect(linkGroups({ links: { manual: 'https://a.example' as never } })).toEqual([])
  })
})
