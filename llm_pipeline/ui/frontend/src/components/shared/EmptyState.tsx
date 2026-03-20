interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return <p className="text-sm text-muted-foreground">{message}</p>
}
