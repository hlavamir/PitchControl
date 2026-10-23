import { ICON_MEANING, ICON_PATHS, type IconName } from '../icons'

/** One of the app's line icons (icons.ts), in the current text colour. ``label``: named for a screen reader and shown as
 * the tooltip; without it the icon is decoration next to a text that says the same. */
export function Icon({ name, label = false, className = '' }: { name: IconName; label?: boolean; className?: string }) {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1}
      strokeLinecap="square"
      className={`inline-block flex-none ${className}`}
      role={label ? 'img' : undefined}
      aria-label={label ? ICON_MEANING[name] : undefined}
      aria-hidden={label ? undefined : true}
    >
      {label && <title>{ICON_MEANING[name]}</title>}
      <path d={ICON_PATHS[name]} />
    </svg>
  )
}
