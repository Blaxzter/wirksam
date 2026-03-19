import type { BadgeVariants } from '@/components/ui/badge'

export function statusVariant(status?: string | null): NonNullable<BadgeVariants['variant']> {
  switch (status) {
    case 'published':
      return 'default'
    case 'draft':
      return 'secondary'
    case 'archived':
      return 'outline'
    default:
      return 'secondary'
  }
}
