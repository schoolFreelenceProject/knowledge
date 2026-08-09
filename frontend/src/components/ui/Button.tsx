import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "../../utils/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  isLoading?: boolean;
  icon?: ReactNode;
};

const variants: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-blue-700 focus-visible:ring-blue-500",
  secondary:
    "border border-border bg-white text-ink hover:bg-slate-50 focus-visible:ring-blue-500",
  ghost: "text-muted hover:bg-slate-100 hover:text-ink focus-visible:ring-blue-500",
  danger: "bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500",
};

export function Button({
  className,
  variant = "primary",
  isLoading = false,
  icon,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium",
        "transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-60",
        variants[variant],
        className,
      )}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}
