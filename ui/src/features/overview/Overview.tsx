import { ArrowRight, KeyRound, Route, ShieldCheck } from 'lucide-react'
import { Fragment, useMemo, type MouseEvent, type ReactNode } from 'react'

import { useFiles, useOverview } from '../../api/hooks'
import type { Endpoint, HotFunction, Overview as OverviewData, Repo } from '../../api/types'
import { ErrorNote } from '../../design/primitives'
import { cx } from '../../lib/cx'
import { useCountUp } from '../../lib/useCountUp'
import { cxColor, langColor, langName } from './colors'
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
      <div className="mx-auto max-w-[1180px] space-y-12 px-5 pb-16 pt-8">
        <Section n="01" title="Begin here">
          <Hero
            repo={repo}
            o={o}
            endpoints={endpoints}
            onOpenEndpoint={onOpenEndpoint}
            onOpenChunk={onOpenChunk}
          />
          <StartHere
            endpoints={endpoints}
            o={o}
            onOpenEndpoint={onOpenEndpoint}
            onOpenChunk={onOpenChunk}
            onOpenArchitecture={onOpenArchitecture}
          />
        </Section>

        <Section n="02" title="The shape of it">
          <StatRow o={o} />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card title="Languages" delay={0}>
              <LanguageBar o={o} />
            </Card>
            <Card
              title="Auth surface"
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
        </Section>

        <Section n="03" title="Where the risk lives">
          <Card
            title="Structure"
            delay={100}
            action={
              <button type="button" onClick={onOpenArchitecture} className="link-btn">
                Dependency map <ArrowRight size={12} aria-hidden />
              </button>
            }
            hint="Every file, sized by lines of code and heated by complexity. Click one to open it."
          >
            <Treemap files={files.data ?? []} onOpen={onOpenFile} />
          </Card>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <Card title="Most called" delay={140} hint="Functions many others depend on: change with care.">
              <HotList
                items={o.hotspots.most_called}
                value={(h) => h.fan_in ?? 0}
                unit={(v) => `${v} caller${v === 1 ? '' : 's'}`}
                onOpen={onOpenChunk}
                empty="No resolved calls between functions yet."
              />
            </Card>
            <Card title="Most complex" delay={180} hint="Branch-heavy functions: likely hardest to test.">
              <HotList
                items={o.hotspots.most_complex}
                value={(h) => h.complexity}
                unit={(v) => `cx ${v}`}
                tone={(h) => cxColor(h.complexity)}
                badge={(h) => h.label}
                onOpen={onOpenChunk}
                empty="Everything is straightforward."
              />
            </Card>
            <Card title="Largest files" delay={220} hint="Where most of the code lives.">
              <FileList items={o.hotspots.largest_files} onOpen={onOpenFile} />
            </Card>
          </div>
        </Section>

        <Section n="04" title="Guards and dependencies">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card
              title="Auth guards"
              delay={260}
              hint="Functions that check identity or permissions, and how widely they are used."
            >
              <HotList
                items={o.guards}
                value={(h) => h.fan_in ?? 0}
                unit={(v) => `${v} use${v === 1 ? '' : 's'}`}
                tone={() => 'var(--lavender)'}
                onOpen={onOpenChunk}
                empty="No functions named like auth checks were found."
              />
            </Card>
            <Card title="Dependencies" delay={300} hint="Libraries imported by this project (file counts).">
              <Dependencies o={o} />
            </Card>
          </div>
        </Section>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------- pieces */

/** Numbered serif section label: `01  Begin here`. */
function Section({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-4">
      <h2 className="rise flex items-baseline gap-3 border-b border-border-subtle pb-2">
        <span className="font-mono text-[11px] text-sage" aria-hidden>
          {n}
        </span>
        <span className="serif text-[28px] leading-none text-cream">{title}</span>
      </h2>
      {children}
    </section>
  )
}

function Card({
  title,
  children,
  action,
  hint,
  delay = 0,
}: {
  title: string
  children: ReactNode
  action?: ReactNode
  hint?: string
  delay?: number
}) {
  return (
    <section
      aria-label={title}
      className="rise relative rounded-[10px] border border-border-subtle bg-bg-2 p-4"
      style={{ animationDelay: `${delay}ms` }}
    >
      <header className="mb-3 flex items-center gap-2">
        <h3 className="label">{title}</h3>
        <span className="ml-auto">{action}</span>
      </header>
      {hint && <p className="-mt-1 mb-3 text-[12.5px] text-text-2">{hint}</p>}
      {children}
    </section>
  )
}

const FRAMEWORK: Record<string, string> = {
  fastapi: 'FastAPI',
  flask: 'Flask',
  express: 'Express',
  starlette: 'Starlette',
  django: 'Django',
  nestjs: 'NestJS',
  fastify: 'Fastify',
}

/** The one-sentence briefing: how exposed is this API, and what guards it? */
const HOUSEKEEPING_PATH =
  /^\/?$|(^|\/)(healthz?|ready|readiness|live|liveness|ping|metrics|docs|redoc|openapi(\.json)?|swagger|version|favicon\.ico|robots\.txt)(\/|$)/i
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/** The unguarded endpoint most worth a second look: a write before a read, and never a
 *  health check or docs route (those are meant to be open). */
export function mostTellingOpenEndpoint(endpoints: Endpoint[]): Endpoint | undefined {
  const open = endpoints.filter((e) => !e.requires_auth && !e.handles_authentication)
  const real = open.filter((e) => !HOUSEKEEPING_PATH.test(e.path))
  return real.find((e) => WRITE_METHODS.has(e.method.toUpperCase())) ?? real[0] ?? open[0]
}

function headline(o: OverviewData): ReactNode[] {
  const eps = o.totals.endpoints
  const pub = o.auth.public
  const guard = o.guards[0]?.name
  if (eps === 0) {
    return [`${fmt(o.totals.files)} files, `, <em key="e">no</em>, ' HTTP endpoints. ', `${fmt(o.totals.functions)} functions to read.`]
  }
  const parts: ReactNode[] = [`${fmt(eps)} endpoint${eps === 1 ? '' : 's'}, `]
  parts.push(pub === 0 ? <em key="p">none wide open.</em> : <em key="p">{`${pub} wide open.`}</em>)
  if (guard) parts.push(` ${guard} holds the rest.`)
  return parts
}

function Hero({
  repo,
  o,
  endpoints,
  onOpenEndpoint,
  onOpenChunk,
}: {
  repo: Repo
  o: OverviewData
  endpoints: Endpoint[]
  onOpenEndpoint: (e: Endpoint) => void
  onOpenChunk: (h: HotFunction) => void
}) {
  const stack = [
    ...o.frameworks.map((f) => FRAMEWORK[f] ?? f[0].toUpperCase() + f.slice(1)),
    ...o.languages.map((l) => langName(l.language)),
  ]
  // Word-by-word rise: split the plain text but keep <em> emphasis intact.
  const words: Array<{ text: string; em: boolean }> = []
  for (const part of headline(o)) {
    if (typeof part === 'string') {
      for (const w of part.split(/\s+/).filter(Boolean)) words.push({ text: w, em: false })
    } else {
      const child = (part as { props: { children: string } }).props.children
      for (const w of String(child).split(/\s+/).filter(Boolean)) words.push({ text: w, em: true })
    }
  }

  const open = mostTellingOpenEndpoint(endpoints)
  const hub = o.hotspots.most_called[0]
  const hard = o.hotspots.most_complex[0]
  const findings: Array<{ tag: string; tone: string; text: string; run: () => void }> = []
  if (open) {
    findings.push({
      tag: 'Exposure',
      tone: 'var(--terracotta)',
      text: `${open.method} ${open.path} has no auth signal. Is that intended?`,
      run: () => onOpenEndpoint(open),
    })
  }
  if (hub) {
    findings.push({
      tag: 'Hub',
      tone: 'var(--teal)',
      text: `${hub.name} is called from ${hub.fan_in ?? 0} place${hub.fan_in === 1 ? '' : 's'}. Change it with care.`,
      run: () => onOpenChunk(hub),
    })
  }
  if (hard) {
    findings.push({
      tag: 'Complexity',
      tone: cxColor(hard.complexity),
      text: `${hard.name} has complexity ${hard.complexity}: the hardest function to test.`,
      run: () => onOpenChunk(hard),
    })
  }

  return (
    <header className="space-y-5">
      <div className="rise">
        <p className="font-mono text-[12px] text-sage">~/ briefing</p>
        <h1 className="mt-1 font-mono text-[13px] font-medium text-text-1">{repo.name}</h1>
        <p className="font-mono text-[11.5px] text-text-3">{repo.path}</p>
      </div>
      <p
        className="serif max-w-[32ch] text-[clamp(38px,5.2vw,68px)] leading-[1.04] tracking-[-0.01em] text-cream"
        role="heading"
        aria-level={2}
        aria-label={words.map((w) => w.text).join(' ')}
      >
        {words.map((w, i) => (
          <Fragment key={i}>
            <span
              className={cx('wordrise', w.em && 'italic text-sage')}
              style={{ animationDelay: `${120 + i * 70}ms` }}
            >
              {w.text}
            </span>{' '}
          </Fragment>
        ))}
      </p>
      {stack.length > 0 && (
        <ul aria-label="Detected stack" className="rise flex flex-wrap gap-1.5" style={{ animationDelay: '300ms' }}>
          {[...new Set(stack)].map((s) => (
            <li
              key={s}
              className="rounded-full border border-border-control bg-bg-2 px-2.5 py-0.5 text-[12px] text-text-1"
            >
              {s}
            </li>
          ))}
        </ul>
      )}
      {findings.length > 0 && (
        <ul aria-label="Findings" className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {findings.map((f, i) => (
            <li key={f.tag} className="rise" style={{ animationDelay: `${400 + i * 90}ms` }}>
              <button
                type="button"
                onClick={f.run}
                className="group flex h-full w-full flex-col items-start gap-2 rounded-xl border border-border-subtle bg-bg-1 p-4 text-left transition-[border-color,transform,background-color] duration-200 hover:-translate-y-[3px] hover:border-sage hover:bg-[#12171c]"
              >
                <span className="label inline-flex items-center gap-2" style={{ color: f.tone }}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: f.tone }} aria-hidden />
                  {f.tag}
                </span>
                <span className="text-[14px] leading-snug text-text-1">{f.text}</span>
                <ArrowRight
                  size={14}
                  className="mt-auto text-text-2 transition-colors group-hover:text-sage"
                  aria-hidden
                />
              </button>
            </li>
          ))}
        </ul>
      )}
    </header>
  )
}

function Stat({ label, short, value, delay }: { label: string; short?: string; value: number; delay: number }) {
  const shown = useCountUp(value, 1500)
  return (
    <div
      className="rise shimmer rounded-[10px] border border-border-subtle bg-bg-2 p-4"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="label whitespace-nowrap" title={label}>
        {short ?? label}
      </div>
      <div
        className="serif mt-1 text-[44px] leading-none tabular-nums text-cream"
        aria-label={`${fmt(value)} ${label}`}
      >
        {fmt(shown)}
      </div>
    </div>
  )
}

function StatRow({ o }: { o: OverviewData }) {
  const t = o.totals
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <Stat label="Files" value={t.files} delay={0} />
      <Stat label="Lines of code" short="Lines" value={t.loc} delay={50} />
      <Stat label="Functions" value={t.functions} delay={100} />
      <Stat label="Classes" value={t.classes} delay={150} />
      <Stat label="Endpoints" value={t.endpoints} delay={200} />
    </div>
  )
}

/** A card that leans toward the pointer (±9 degrees). Disabled for reduced motion via CSS. */
function tilt(e: MouseEvent<HTMLElement>) {
  const el = e.currentTarget
  const r = el.getBoundingClientRect()
  const px = (e.clientX - r.left) / r.width - 0.5
  const py = (e.clientY - r.top) / r.height - 0.5
  el.style.transform = `perspective(700px) rotateX(${(-py * 18).toFixed(1)}deg) rotateY(${(px * 18).toFixed(1)}deg) translateY(-2px)`
}
function untilt(e: MouseEvent<HTMLElement>) {
  e.currentTarget.style.transform = ''
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
    <section aria-label="Start here" className="rise" style={{ animationDelay: '700ms' }}>
      <h3 className="label mb-2">Start here</h3>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {steps
          .filter((s) => s.show)
          .map((s, i) => (
            <li key={s.title}>
              <button
                type="button"
                onClick={s.run}
                onMouseMove={tilt}
                onMouseLeave={untilt}
                className="tiltcard group flex h-full w-full flex-col items-start gap-1.5 rounded-[10px] border border-border-subtle bg-bg-2 p-4 text-left hover:border-sage hover:bg-[#151b21]"
              >
                <span className="font-mono text-[11px] text-sage">0{i + 1}</span>
                <span className="flex items-start gap-1 text-[14px] font-medium text-cream">
                  <span className="min-w-0 flex-1">{s.title}</span>
                  <ArrowRight
                    size={14}
                    className="mt-0.5 shrink-0 text-text-2 transition-colors group-hover:text-sage"
                    aria-hidden
                  />
                </span>
                <span className="block text-[12.5px] text-text-2">{s.body}</span>
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
        className="shimmer flex h-3 overflow-hidden rounded-full bg-bg-3"
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
            <span>{langName(l.language)}</span>
            <span className="ml-auto font-mono text-[12px] text-text-2">
              {l.files} file{l.files === 1 ? '' : 's'} · {fmt(l.loc)} line{l.loc === 1 ? '' : 's'} ·{' '}
              {Math.round((l.loc / total) * 100)}%
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
    { key: 'authentication', n: authentication, color: 'var(--lavender)', label: 'Perform authentication', Icon: KeyRound },
    { key: 'protected', n: prot, color: 'var(--moss)', label: 'Require authentication', Icon: ShieldCheck },
    { key: 'public', n: pub, color: 'var(--terracotta)', label: 'No auth signal detected', Icon: Route },
  ]
  return (
    <div>
      <div
        className="shimmer flex h-3 overflow-hidden rounded-full bg-bg-3"
        role="img"
        aria-label={`${authentication} authentication, ${prot} protected, ${pub} with no auth signal`}
      >
        {seg.map((s) => (
          <div
            key={s.key}
            className={cx('bar-grow h-full', s.key === 'public' && 'breathe')}
            style={{ width: `${(s.n / total) * 100}%`, background: s.color }}
          />
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
  tone,
  onOpen,
  empty,
}: {
  items: HotFunction[]
  value: (h: HotFunction) => number
  unit: (v: number) => string
  badge?: (h: HotFunction) => string | undefined
  tone?: (h: HotFunction) => string
  onOpen: (h: HotFunction) => void
  empty: string
}) {
  const max = Math.max(1, ...items.map(value))
  if (!items.length) return <p className="text-text-2">{empty}</p>
  return (
    <ol className="space-y-1">
      {items.map((h, i) => {
        const v = value(h)
        const color = tone?.(h) ?? 'var(--teal)'
        return (
          <li key={h.chunk_id}>
            <button
              type="button"
              onClick={() => onOpen(h)}
              className="group relative w-full overflow-hidden rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-[#1c232b]"
              title={h.doc || undefined}
            >
              <span
                className="bar-grow absolute inset-y-0 left-0 rounded-md opacity-[0.16]"
                style={{ width: `${(v / max) * 100}%`, animationDelay: `${i * 50}ms`, background: color }}
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
                  <span className="metric-chip" style={{ color }}>
                    {badge(h)}
                  </span>
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
            className="group relative w-full overflow-hidden rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-[#1c232b]"
          >
            <span
              className="bar-grow absolute inset-y-0 left-0 rounded-md opacity-[0.16]"
              style={{ width: `${(f.loc / max) * 100}%`, animationDelay: `${i * 50}ms`, background: langColor(f.language) }}
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
        <h4 className="label mb-1.5">Third-party</h4>
        {third.length === 0 ? (
          <p className="text-text-2">None detected.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {third.map((d, i) => (
              <li
                key={d.name}
                className="pop rounded-[6px] border border-border-control bg-bg-1 px-2 py-1 font-mono text-[12px]"
                style={{
                  animationDelay: `${i * 35}ms`,
                  boxShadow: `inset 0 -2px 0 color-mix(in srgb, var(--teal) ${Math.round((d.files / maxFiles) * 100)}%, transparent)`,
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
          <h4 className="label mb-1.5">Standard library</h4>
          <ul className="flex flex-wrap gap-1.5">
            {std.map((d) => (
              <li key={d.name} className="rounded-[6px] bg-bg-1 px-2 py-1 font-mono text-[12px] text-text-2">
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
      <div className="skeleton h-40 w-2/3" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="skeleton h-24" />
        ))}
      </div>
      <div className="skeleton h-72" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="skeleton h-56" />
        ))}
      </div>
    </div>
  )
}
