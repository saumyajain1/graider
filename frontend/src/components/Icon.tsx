import type { SVGProps } from 'react'

export function Icon({
  name,
  className = 'h-4 w-4 shrink-0',
  ...props
}: SVGProps<SVGSVGElement> & {
  name: 'back' | 'forward' | 'sparkles' | 'account' | 'logout' | 'spinner'
}) {
  const paths = {
    back: 'M19 12H5m7-7-7 7 7 7',
    forward: 'M5 12h14m-7-7 7 7-7 7',
    sparkles: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Zm7 0v4m-2-2h4',
    account: 'M20 21v-2a7 7 0 0 0-14 0v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
    logout: 'M9 3H4v18h5m7-15 6 6-6 6M9 12h13',
    spinner: 'M21 12a9 9 0 1 1-9-9',
  }
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`${className} ${name === 'spinner' ? 'animate-spin motion-reduce:animate-none' : ''}`}
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  )
}
