import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { SHOW_TAB_EVENT, rememberedTab, showTab, stepTab, subTabKey } from '../subTabs'
import { isTyping } from '../useGridNav'

export interface SubTab<T extends string> {
  id: T
  label: ReactNode
  tip: string
  /** Small marks after the label (the Control Desk's override and route dots). */
  marks?: (active: boolean) => ReactNode
  /** A gap before this tab: it starts a group of its own (Routes after the channel subpages). */
  gap?: boolean
  mono?: boolean
}

/**
 * The tab of a page's subpage tabs, remembered per page (subTabs.ts), and the keys Q / E that step through them (not
 * while typing; they wrap around at the ends). Every change goes through showTab, so the app (the footer) and the
 * header's indicators see the same tab.
 */
export function useSubTab<T extends string>(page: string, ids: readonly T[], fallback: T): [T, (id: T) => void] {
  const [tab, setTabState] = useState<T>(() => rememberedTab(page, ids, fallback))
  const tabRef = useRef(tab)
  tabRef.current = tab
  const idsRef = useRef(ids)
  idsRef.current = ids
  const setTab = useCallback((id: T) => showTab(page, id), [page])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const dir = subTabKey(e, isTyping(e))
      if (!dir) return
      e.preventDefault()
      showTab(page, stepTab(idsRef.current, tabRef.current, dir))
    }
    const onShow = (e: Event) => {
      const { page: p, id } = (e as CustomEvent<{ page: string; id: T }>).detail
      if (p === page && idsRef.current.includes(id)) setTabState(id)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener(SHOW_TAB_EVENT, onShow)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener(SHOW_TAB_EVENT, onShow)
    }
  }, [page])
  return [tab, setTab]
}

/** The tabs in their groups: a tab with ``gap`` starts a new one. */
function groups<T extends string>(tabs: SubTab<T>[]): SubTab<T>[][] {
  const out: SubTab<T>[][] = []
  for (const t of tabs) {
    if (t.gap || !out.length) out.push([])
    out[out.length - 1].push(t)
  }
  return out
}

/**
 * The row of subpage tabs under the page row (Connections, Control Desk), starting at the page row's left edge. Q / E step
 * through them (useSubTab), shown in the footer and the Help page, not in the row. A tab with ``gap`` stands apart from
 * the ones before it (the Control Desk's Routes, item 74).
 */
export function SubTabs<T extends string>({ tabs, value, onChange }: { tabs: SubTab<T>[]; value: T; onChange: (id: T) => void }) {
  return (
    <div className="flex flex-none items-stretch" role="tablist">
      {groups(tabs).map((group, i) => (
        <div key={group[0].id} className={`flex border border-edge ${i === 0 ? '' : group[0].gap ? 'ml-10' : 'ml-1.5'}`}>
          {group.map((t) => {
            const active = t.id === value
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                onClick={() => onChange(t.id)}
                data-hint="subtab"
                data-tip={t.tip}
                className={`lbl relative flex h-8 items-center gap-1.5 border-edge px-3 text-[11px] whitespace-nowrap not-first:border-l ${t.mono ? 'font-mono' : ''} ${
                  active ? 'glow-on bg-ink text-ground' : 'text-ink hover:bg-panel-2'
                }`}
              >
                {t.label}
                {t.marks?.(active)}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
