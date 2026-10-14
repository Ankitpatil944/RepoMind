import {
  ArrowRight,
  Boxes,
  Braces,
  FileCode2,
  Flame,
  GitFork,
  KeyRound,
  Layers,
  Package,
  PhoneCall,
  Route,
  ShieldCheck,
} from 'lucide-react'
import { useMemo, type ReactNode } from 'react'

import { useFiles, useOverview } from '../../api/hooks'
import type { Endpoint, HotFunction, Overview as OverviewData, Repo } from '../../api/types'
import { ErrorNote } from '../../design/primitives'
import { cx } from '../../lib/cx'
import { useCountUp } from '../../lib/useCountUp'
import { langColor } from './colors'
import { Treemap } from './Treemap'

interface Props {
  repo: Repo
  endpoints: Endpoint[]
  onOpenChunk: (h: HotFunction) => void
  onOpenFile: (path: string) => void
  onOpenEndpoint: (e: Endpoint) => void
  onOpenArchitecture: () => void
  onShowEndpoints: () => void
}

const fmt = (n: number) => n.toLocaleString('en-US')

export function Overview({
  repo,
  endpoints,
  onOpenChunk,
  onOpenFile,
  onOpenEndpoint,
  onOpenArchitecture,
  onShowEndpoints,
}: Props) {
  const overview = useOverview(repo.id)
  const files = useFiles(repo.id)

  if (overview.isLoading || files.isLoading) return <OverviewSkeleton />
  if (overview.error || !overview.data) {
    return (
      <div className="p-6">
        <ErrorNote title="Could not summarise this repository">
          {overview.error?.message ?? 'Unknown error'}. Try re-indexing the project.
        </ErrorNote>
      </div>
    )
  }
  const o = overview.data

  return (
    <div className="view-enter h-full overflow-auto">
      <div className="mx-auto max-w-[1180px] space-y-6 p-5 pb-10">
        <Hero repo={repo} o={o} />
        <StatRow o={o} />
        <StartHere
          endpoints={endpoints}
          o={o}
          onOpenEndpoint={onOpenEndpoint}
          onOpenChunk={onOpenChunk}
          onOpenArchitecture={onOpenArchitecture}
        />

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Languages" icon={<Braces size={15} aria-hidden />} delay={0}>
            <LanguageBar o={o} />
          </Card>
          <Card
            title="Auth surface"
            icon={<ShieldCheck size={15} aria-hidden />}
            delay={60}
            action={
              <button type="button" onClick={onShowEndpoints} className="link-btn">
                View endpoints <ArrowRight size={12} aria-hidden />
              </button>
            }
          >
            <AuthSurface o={o} />
          </Card>
        </div>

        <Card
          title="Structure"
          icon={<Layers size={15} aria-hidden />}
          delay={100}
          action={
            <button type="button" onClick={onOpenArchitecture} className="link-btn">
              Dependency map <ArrowRight size={12} aria-hidden />
            </button>
          }
          hint="Every file, sized by lines of code. Click one to open it."
        >
          <Treemap files={files.data ?? []} onOpen={onOpenFile} />
        </Card>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Most called" icon={<PhoneCall size={15} aria-hidden />} delay={140}
            hint="Functions many others depend on: change with care.">
            <HotList
              items={o.hotspots.most_called}
              value={(h) => h.fan_in ?? 0}
              unit={(v) => `${v} caller${v === 1 ? '' : 's'}`}
              onOpen={onOpenChunk}
              empty="No resolved calls between functions yet."
            />
          </Card>
          <Card title="Most complex" icon={<Flame size={15} aria-hidden />} delay={180}
            hint="Branch-heavy functions: likely hardest to test.">
            <HotList
              items={o.hotspots.most_complex}
              value={(h) => h.complexity}
              unit={(v) => `cx ${v}`}
              badge={(h) => h.label}
              onOpen={onOpenChunk}
              empty="Everything is straightforward."
            />
          </Card>
          <Card title="Largest files" icon={<FileCode2 size={15} aria-hidden />} delay={220}
            hint="Where most of the code lives.">
            <FileList items={o.hotspots.largest_files} onOpen={onOpenFile} />
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Auth guards" icon={<KeyRound size={15} aria-hidden />} delay={260}
            hint="Functions that check identity or permissions, and how widely they are used.">
            <HotList
              items={o.guards}
              value={(h) => h.fan_in ?? 0}
              unit={(v) => `${v} use${v === 1 ? '' : 's'}`}
              onOpen={onOpenChunk}
              empty="No functions named like auth checks were found."
            />
          </Card>
          <Card title="Dependencies" icon={<Package size={15} aria-hidden />} delay={300}
            hint="Libraries imported by this project (file counts).">
            <Dependencies o={o} />
          </Card>
        </div>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------- pieces */

function Card({
  title,
  icon,
  children,
  action,
  hint,
  delay = 0,
}: {
  title: string
  icon: ReactNode
  children: ReactNode
  action?: ReactNode
  hint?: string
  delay?: number
}) {
  return (
    <section
      aria-label={title}
      className="rise-in rounded-xl border border-border-subtle bg-bg-1 p-4"
      style={{ animationDelay: `${delay}ms` }}
    >
      <header className="mb-3 flex items-center gap-2">
        <span className="text-text-2">{icon}</span>
        <h2 className="text-[13.5px] font-semibold">{title}</h2>
        <span className="ml-auto">{action}</span>
      </header>
      {hint && <p className="-mt-1 mb-3 text-[12.5px] text-text-2">{hint}</p>}
      {children}
    </section>
  )
}

function Hero({ repo, o }: { repo: Repo; o: OverviewData }) {
  const stack = [...o.frameworks.map((f) => (f === 'fastapi' ? 'FastAPI' : f[0].toUpperCase() + f.slice(1))),
    ...o.languages.map((l) => l.language[0].toUpperCase() + l.language.slice(1))]
  return (
    <header className="rise-in">
      <p className="text-[12px] font-medium uppercase tracking-wide text-text-3">Repository overview</p>
      <h1 className="mt-1 text-[26px] font-semibold tracking-tight">{repo.name}</h1>
      <p className="mt-1 font-mono text-[12.5px] text-text-2">{repo.path}</p>
      {stack.length > 0 && (
        <ul aria-label="Detected stack" className="mt-3 flex flex-wrap gap-1.5">
          {[...new Set(stack)].map((s) => (
            <li key={s} className="rounded-full border border-border-control px-2.5 py-0.5 text-[12px] text-text-1">
              {s}
            </li>
          ))}
        </ul>
      )}
    </header>
  )
}

function Stat({ label, value, icon, delay }: { label: string; value: number; icon: ReactNode; delay: number }) {
  const shown = useCountUp(value)
  return (
    <div
      className="rise-in rounded-xl border border-border-subtle bg-bg-1 p-3.5"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center gap-1.5 text-[12px] text-text-2">
        <span aria-hidden>{icon}</span>
        {label}
      </div>
      <div className="mt-1 font-mono text-[26px] font-medium leading-none tabular-nums" aria-label={`${fmt(value)} ${label}`}>
        {fmt(shown)}
      </div>
    </div>
  )
}

function StatRow({ o }: { o: OverviewData }) {
  const t = o.totals
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Stat label="Files" value={t.files} icon={<FileCode2 size={13} />} delay={0} />
      <Stat label="Lines of code" value={t.loc} icon={<Braces size={13} />} delay={40} />
      <Stat label="Functions" value={t.functions} icon={<Route size={13} />} delay={80} />
      <Stat label="Classes" value={t.classes} icon={<Boxes size={13} />} delay={120} />
      <Stat label="Endpoints" value={t.endpoints} icon={<GitFork size={13} />} delay={160} />
      <Stat label="Module links" value={t.internal_links} icon={<Layers size={13} />} delay={200} />
    </div>
  )
}

function StartHere({
  endpoints,
  o,
  onOpenEndpoint,
  onOpenChunk,
  onOpenArchitecture,
}: {
  endpoints: Endpoint[]
  o: OverviewData
  onOpenEndpoint: (e: Endpoint) => void
  onOpenChunk: (h: HotFunction) => void
  onOpenArchitecture: () => void
}) {
  const login = endpoints.find((e) => e.handles_authentication)
  const guarded = endpoints.find((e) => e.requires_auth && !e.handles_authentication)
  const hub = o.hotspots.most_called[0]
  const steps: Array<{ title: string; body: string; run: () => void; show: boolean }> = [
    {
      title: login ? `Trace ${login.method} ${login.path}` : 'Trace an endpoint',
      body: 'Follow a request from the route through handlers to the database and libraries.',
      run: () => login && onOpenEndpoint(login),
      show: !!login,
    },
    {
      title: guarded ? `See how ${guarded.path} is protected` : 'See a protected route',
      body: 'Find the guard function behind an authenticated endpoint.',
      run: () => guarded && onOpenEndpoint(guarded),
      show: !!guarded,
    },
    {
      title: hub ? `Inspect the hub: ${hub.name}` : 'Inspect the busiest function',
      body: hub ? `Called from ${hub.fan_in} places. See who depends on it.` : 'See who depends on it.',
      run: () => hub && onOpenChunk(hub),
      show: !!hub,
    },
    {
      title: 'Map the architecture',
      body: 'Which folders depend on which, and where the heavy modules are.',
      run: onOpenArchitecture,
      show: true,
    },
  ]
  return (
    <section aria-label="Start here" className="rise-in" style={{ animationDelay: '60ms' }}>
      <h2 className="mb-2 text-[13.5px] font-semibold">Start here</h2>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {steps
          .filter((s) => s.show)
          .map((s, i) => (
            <li key={s.title}>
              <button
                type="button"
                onClick={s.run}
                className="group h-full w-full rounded-xl border border-border-control bg-bg-2 p-3.5 text-left transition-[transform,border-color,background-color] duration-150 hover:-translate-y-0.5 hover:border-accent-500 hover:bg-bg-3"
              >
                <span className="font-mono text-[11px] text-text-3">0{i + 1}</span>
                <span className="mt-1 flex items-start gap-1 text-[13.5px] font-medium">
                  <span className="min-w-0 flex-1">{s.title}</span>
                  <ArrowRight
                    size={14}
                    className="mt-0.5 shrink-0 text-text-2 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent-400"
                    aria-hidden
                  />
                </span>
                <span className="mt-1 block text-[12.5px] text-text-2">{s.body}</span>
              </button>
            </li>
          ))}
      </ul>
    </section>
  )
}

function LanguageBar({ o }: { o: OverviewData }) {
  const total = o.languages.reduce((a, l) => a + l.loc, 0) || 1
  return (
    <div>
      <div
        role="img"
        aria-label={o.languages
          .map((l) => `${l.language} ${Math.round((l.loc / total) * 100)} percent`)
          .join(', ')}
        className="flex h-3 overflow-hidden rounded-full bg-bg-3"
      >
        {o.languages.map((l) => (
          <div
            key={l.language}
            className="bar-grow h-full"
            style={{ width: `${(l.loc / total) * 100}%`, background: langColor(l.language) }}
          />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5">
        {o.languages.map((l) => (
          <li key={l.language} className="flex items-center gap-2 text-[13px]">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: langColor(l.language) }} aria-hidden />
            <span className="capitalize">{l.language}</span>
            <span className="ml-auto font-mono text-[12px] text-text-2">
              {l.files} files · {fmt(l.loc)} lines · {Math.round((l.loc / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function AuthSurface({ o }: { o: OverviewData }) {
  const { authentication, protected: prot, public: pub } = o.auth
  const total = authentication + prot + pub
  if (!total) return <p className="text-text-2">No HTTP endpoints were detected in this project.</p>
  const seg = [
    { key: 'authentication', n: authentication, color: 'var(--auth)', label: 'Perform authentication', Icon: KeyRound },
    { key: 'protected', n: prot, color: 'var(--ok)', label: 'Require authentication', Icon: ShieldCheck },
    { key: 'public', n: pub, color: 'var(--text-3)', label: 'No auth signal detected', Icon: Route },
  ]
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-bg-3" role="img"
        aria-label={`${authentication} authentication, ${prot} protected, ${pub} with no auth signal`}>
        {seg.map((s) => (
          <div key={s.key} className="bar-grow h-full" style={{ width: `${(s.n / total) * 100}%`, background: s.color }} />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5">
        {seg.map((s) => (
          <li key={s.key} className="flex items-center gap-2 text-[13px]">
            <s.Icon size={14} style={{ color: s.color }} aria-hidden />
            <span>{s.label}</span>
            <span className="ml-auto font-mono text-[12px] text-text-2">
              {s.n} · {Math.round((s.n / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[12.5px] text-text-2">
        “No auth signal” means none was found by static analysis: not proof an endpoint is public.
      </p>
    </div>
  )
}

function HotList({
  items,
  value,
  unit,
  badge,
  onOpen,
  empty,
}: {
  items: HotFunction[]
  value: (h: HotFunction) => number
  unit: (v: number) => string
  badge?: (h: HotFunction) => string | undefined
  onOpen: (h: HotFunction) => void
  empty: string
}) {
  const max = Math.max(1, ...items.map(value))
  if (!items.length) return <p className="text-text-2">{empty}</p>
  return (
    <ol className="space-y-1">
      {items.map((h, i) => {
        const v = value(h)
        return (
          <li key={h.chunk_id}>
            <button
              type="button"
              onClick={() => onOpen(h)}
              className="group relative w-full overflow-hidden rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3"
              title={h.doc || undefined}
            >
              <span
                className="bar-grow absolute inset-y-0 left-0 rounded-md bg-bg-3 group-hover:bg-bg-2"
                style={{ width: `${(v / max) * 100}%`, animationDelay: `${i * 50}ms` }}
                aria-hidden
              />
              <span className="relative flex items-center gap-2">
                <span className="w-4 shrink-0 font-mono text-[11px] text-text-3">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-mono text-[12.5px]">{h.name}</span>
                  <span className="block truncate font-mono text-[11px] text-text-2">
                    {h.file}:{h.line}
                  </span>
                </span>
                {badge?.(h) && (
                  <span className={cx('metric-chip', badge(h) === 'high' && 'text-warn')}>{badge(h)}</span>
                )}
                <span className="shrink-0 font-mono text-[11.5px] text-text-2">{unit(v)}</span>
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function FileList({
  items,
  onOpen,
}: {
  items: Array<{ path: string; loc: number; language: string }>
  onOpen: (path: string) => void
}) {
  const max = Math.max(1, ...items.map((f) => f.loc))
  return (
    <ol className="space-y-1">
      {items.map((f, i) => (
        <li key={f.path}>
          <button
            type="button"
            onClick={() => onOpen(f.path)}
            className="group relative w-full overflow-hidden rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-bg-3"
          >
            <span
              className="bar-grow absolute inset-y-0 left-0 rounded-md bg-bg-3 group-hover:bg-bg-2"
              style={{ width: `${(f.loc / max) * 100}%`, animationDelay: `${i * 50}ms` }}
              aria-hidden
            />
            <span className="relative flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: langColor(f.language) }} aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={f.path}>
                {f.path}
              </span>
              <span className="shrink-0 font-mono text-[11.5px] text-text-2">{fmt(f.loc)} loc</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  )
}

function Dependencies({ o }: { o: OverviewData }) {
  const third = o.dependencies.third_party
  const std = o.dependencies.stdlib
  const maxFiles = useMemo(() => Math.max(1, ...third.map((d) => d.files)), [third])
  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-1.5 text-[11.5px] font-medium uppercase tracking-wide text-text-3">Third-party</h3>
        {third.length === 0 ? (
          <p className="text-text-2">None detected.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {third.map((d, i) => (
              <li
                key={d.name}
                className="cell-in rounded-md border border-border-control bg-bg-2 px-2 py-1 font-mono text-[12px]"
                style={{
                  animationDelay: `${i * 35}ms`,
                  boxShadow: `inset 0 -2px 0 color-mix(in srgb, var(--accent-500) ${Math.round((d.files / maxFiles) * 100)}%, transparent)`,
                }}
                title={`${d.name}: imported in ${d.files} file${d.files === 1 ? '' : 's'}`}
              >
                {d.name} <span className="text-text-2">{d.files}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {std.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-[11.5px] font-medium uppercase tracking-wide text-text-3">Standard library</h3>
          <ul className="flex flex-wrap gap-1.5">
            {std.map((d) => (
              <li key={d.name} className="rounded-md bg-bg-2 px-2 py-1 font-mono text-[12px] text-text-2">
                {d.name} {d.files}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function OverviewSkeleton() {
  return (
    <div className="mx-auto max-w-[1180px] space-y-6 p-5" aria-busy="true" aria-label="Loading overview">
      <div className="skeleton h-20 w-2/3" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="skeleton h-20" />
        ))}
      </div>
      <div className="skeleton h-72" />
      <div className="grid gap-6 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="skeleton h-56" />
        ))}
      </div>
    </div>
  )
}
