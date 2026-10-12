import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors border',
  {
    variants: {
      variant: {
        default:
          'bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] border-transparent',
        secondary:
          'bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))] border-transparent',
        outline:
          'border-[hsl(var(--border))] text-[hsl(var(--foreground))]',
        info:
          'bg-[hsl(var(--info-subtle))] text-[hsl(var(--info))] border-[hsl(var(--info)/0.2)]',
        success:
          'bg-[hsl(var(--success-subtle))] text-[hsl(var(--success))] border-[hsl(var(--success)/0.2)]',
        warning:
          'bg-[hsl(var(--warning-subtle))] text-[hsl(var(--warning))] border-[hsl(var(--warning)/0.2)]',
        destructive:
          'bg-[hsl(var(--destructive-subtle))] text-[hsl(var(--destructive))] border-[hsl(var(--destructive)/0.2)]'
      }
    },
    defaultVariants: {
      variant: 'default'
    }
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
