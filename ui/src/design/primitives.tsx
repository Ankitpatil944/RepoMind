import { AlertTriangle, Globe, KeyRound, Loader2, ShieldCheck } from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'

import { cx } from '../lib/cx'

const METHOD_TONE: Record<string, string> = {
  GET: 'text-teal',
  POST: 'text-sage',
  PUT: 'text-brass',
  PATCH: 'text-brass',
  DELETE: 'text-terracotta',
}

/** HTTP verb. The word itself carries the meaning; colour is secondary. */
export function MethodPill({ method, className }: { method: string; className?: string }) {
  return (
    <span
      className={cx(
        'inline-block min-w-[3.6rem] rounded-[5px] bg-raised px-1.5 py-0.5 text-center font-mono text-[11px] font-medium leading-4',
        METHOD_TONE[method] ?? 'text-text-2',
        className,
      )}
    >
      {method}
    </span>
  )
}

export type Role = 'auth' | 'protected' | 'public'

export function roleOf(e: { handles_authentication?: boolean; requires_auth?: boolean }): Role {
  if (e.handles_authentication) return 'auth'
  if (e.requires_auth) return 'protected'
  return 'public'
}

const ROLE: Record<Role, { label: string; tone: string; Icon: ComponentType<{ size?: number; 'aria-hidden'?: boolean }> }> = {
  auth: { label: 'Auth', tone: 'text-auth', Icon: KeyRound },
  protected: { label: 'Protected', tone: 'text-ok', Icon: ShieldCheck },
  public: { label: 'Public', tone: 'text-terracotta', Icon: Globe },
}

/** Auth role = icon + word + colour, never colour alone. */
export function RoleBadge({
  role,
  compact = false,
  className,
}: {
  role: Role
  compact?: boolean
  className?: string
}) {
  const { label, tone, Icon } = ROLE[role]
  return (
    <span
      className={cx('inline-flex items-center gap-1 text-[12px] font-medium', tone, className)}
      title={`${label} endpoint`}
    >
      <Icon size={13} aria-hidden />
      <span className={compact ? 'sr-only' : undefined}>{label}</span>
    </span>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded-[5px] border border-b-2 border-border-control bg-bg-1 px-1.5 py-px font-mono text-[11px] text-text-2">
      {children}
    </kbd>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-text-2">
      <Loader2 size={16} className="animate-spin" aria-hidden />
      <span>{label}…</span>
    </span>
  )
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: ReactNode
  title: string
  children?: ReactNode
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon && <div className="text-text-3">{icon}</div>}
      <h3 className="serif text-[26px] leading-tight text-cream">{title}</h3>
      {children && <div className="max-w-sm text-text-2">{children}</div>}
    </div>
  )
}

export function ErrorNote({ children, title = 'Something went wrong' }: { children: ReactNode; title?: string }) {
  return (
    <div
      role="alert"
      className="flex gap-2 rounded-[10px] border border-border-control bg-bg-2 p-3 text-[13px] text-text-1"
    >
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" aria-hidden />
      <div>
        <p className="font-medium">{title}</p>
        <div className="mt-0.5 text-text-2">{children}</div>
      </div>
    </div>
  )
}

export function IconButton({
  label,
  onClick,
  children,
  pressed,
  className,
}: {
  label: string
  onClick: () => void
  children: ReactNode
  pressed?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={cx(
        'inline-flex h-8 w-8 items-center justify-center rounded-[7px] border border-transparent text-text-2 transition-colors duration-150 hover:bg-bg-3 hover:text-text-1',
        pressed && 'border-sage-border bg-sage-bg text-sage',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onChange: (v: T) => void
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-[7px] border border-border-control">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            'h-[30px] px-3 text-[12px] font-medium transition-colors duration-150',
            o.value === value
              ? 'bg-sage-bg text-sage shadow-[inset_0_0_0_1px_var(--accent-400)]'
              : 'bg-bg-2 text-text-2 hover:bg-bg-3 hover:text-text-1',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
