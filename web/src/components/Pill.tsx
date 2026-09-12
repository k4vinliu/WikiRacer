import type { ButtonHTMLAttributes, ReactNode } from "react";

export type PillVariant = "black" | "grey" | "ghost";
export type PillSize = "sm" | "md";

type PillProps = {
  variant: PillVariant;
  size?: PillSize;
  children: ReactNode;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & {
    className?: string;
  };

const VARIANT: Record<PillVariant, string> = {
  black:
    "bg-accent-black text-text-on-dark hover:bg-accent-black/90 disabled:opacity-40 disabled:hover:bg-accent-black",
  grey: "bg-surface-grey text-text-on-light hover:bg-surface-grey-dark disabled:opacity-40",
  ghost:
    "bg-transparent text-text-on-dark ring-1 ring-inset ring-text-on-dark/25 hover:bg-card-green-soft disabled:opacity-40",
};

const SIZE: Record<PillSize, string> = {
  sm: "px-4 py-2 text-sm",
  md: "px-7 py-3.5 text-base",
};

export function Pill({
  variant,
  size = "md",
  children,
  className = "",
  type = "button",
  ...rest
}: PillProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center rounded-pill font-medium transition-colors ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
