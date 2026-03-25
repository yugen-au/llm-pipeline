const LINE_WIDTHS = [
  'w-3/4',
  'w-full',
  'w-5/6',
  'w-2/3',
  'w-full',
  'w-4/5',
  'w-1/2',
  'w-full',
  'w-3/5',
  'w-5/6',
  'w-2/3',
  'w-3/4',
] as const

export function EditorSkeleton() {
  return (
    <div className="flex h-full flex-col gap-1 rounded-md bg-muted p-4">
      {LINE_WIDTHS.map((w, i) => (
        <div
          key={i}
          className={`h-4 animate-pulse rounded bg-muted-foreground/10 ${w}`}
        />
      ))}
    </div>
  )
}
