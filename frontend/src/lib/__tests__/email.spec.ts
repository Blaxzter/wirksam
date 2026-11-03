import { describe, expect, it } from 'vitest'

import { addressNameParts, looksLikeEmail } from '@/lib/email'

describe('looksLikeEmail', () => {
  it.each([
    'jonas.weber@example.org',
    'a@b.co',
    '  anna@example.com  ',
    'first+tag@sub.example.co.uk',
    'ANNA@EXAMPLE.COM',
  ])('accepts %s', (text) => {
    expect(looksLikeEmail(text)).toBe(true)
  })

  it.each([
    ['empty', ''],
    ['only spaces', '   '],
    ['a name', 'Jonas Weber'],
    ['no @', 'jonas.example.org'],
    ['nothing before the @', '@example.org'],
    ['two @', 'jonas@weber@example.org'],
    ['no domain', 'jonas@'],
    ['no dot in the domain', 'jonas@localhost'],
    ['a dot at the end', 'jonas@example.'],
    ['a dot at the start of the domain', 'jonas@.org'],
    ['a space inside', 'jonas weber@example.org'],
    ['two dots in a row in the domain', 'anna@b..de'],
    ['two dots in a row before the @', 'anna..maria@example.org'],
  ])('rejects %s', (_label, text) => {
    expect(looksLikeEmail(text)).toBe(false)
  })
})

describe('addressNameParts', () => {
  it('splits the local part into the words worth matching', () => {
    expect(addressNameParts('Jonas.Weber@example.org')).toEqual(['jonas', 'weber'])
    expect(addressNameParts('anna_maria-schmidt+events@example.org')).toEqual([
      'anna',
      'maria',
      'schmidt',
      'events',
    ])
  })

  it('leaves out parts too short to tell people apart', () => {
    expect(addressNameParts('j.w@example.org')).toEqual([])
    expect(addressNameParts('jo.weber@example.org')).toEqual(['weber'])
  })

  it('keeps letters beyond ASCII and works without an @', () => {
    expect(addressNameParts('jürgen.öz@example.org')).toEqual(['jürgen'])
    expect(addressNameParts('mira.lindqvist')).toEqual(['mira', 'lindqvist'])
  })
})
