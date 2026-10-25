import { describe, expect, it } from 'vitest'

import type { Endpoint, FileEntry } from '../../api/types'
import { mostTellingOpenEndpoint } from './Overview'
import { groupByFolder } from './Treemap'

const file = (path: string, loc = 100) => ({ path, loc, language: 'python', symbols: 1, endpoints: 0, complexity: 1 }) as FileEntry
const ep = (method: string, path: string, guarded = false) =>
  ({ method, path, requires_auth: guarded, handles_authentication: false }) as Endpoint

describe('groupByFolder', () => {
  it('groups by top-level folder when that already splits the repo', () => {
    const groups = groupByFolder([file('api/a.py'), file('web/b.py'), file('lib/c.py')])
    expect([...groups.keys()].sort()).toEqual(['api', 'lib', 'web'])
  })

  it('descends into a folder that holds most of the code (monorepos)', () => {
    const groups = groupByFolder([
      file('services/auth/a.py', 500),
      file('services/billing/b.py', 400),
      file('services/jobs/c.py', 300),
      file('libs/x.py', 50),
    ])
    expect([...groups.keys()].sort()).toEqual(['libs', 'services/auth', 'services/billing', 'services/jobs'])
  })

  it('keeps root files together', () => {
    expect([...groupByFolder([file('main.py'), file('app/x.py')]).keys()].sort()).toEqual(['(root)', 'app'])
  })
})

describe('mostTellingOpenEndpoint', () => {
  it('skips health and docs routes and prefers an unguarded write', () => {
    const found = mostTellingOpenEndpoint([
      ep('GET', '/'),
      ep('GET', '/auth-service/health'),
      ep('GET', '/jobs'),
      ep('POST', '/admin/users', true),
      ep('DELETE', '/jobs/{id}'),
    ])
    expect(found?.path).toBe('/jobs/{id}')
  })

  it('does not treat words that merely contain "live" or "version" as housekeeping', () => {
    expect(mostTellingOpenEndpoint([ep('GET', '/delivery'), ep('GET', '/health')])?.path).toBe('/delivery')
    expect(mostTellingOpenEndpoint([ep('GET', '/conversion')])?.path).toBe('/conversion')
  })

  it('falls back to a housekeeping route when that is all there is', () => {
    expect(mostTellingOpenEndpoint([ep('GET', '/health')])?.path).toBe('/health')
    expect(mostTellingOpenEndpoint([ep('GET', '/x', true)])).toBeUndefined()
  })
})
