export function PublicLinks() {
  return (
    <nav aria-label="About Graider" className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
      <a href="/about/" className="underline underline-offset-4 hover:text-fuchsia-200">
        About Graider
      </a>
      <a href="/privacy/" className="underline underline-offset-4 hover:text-fuchsia-200">
        Privacy policy
      </a>
    </nav>
  )
}
