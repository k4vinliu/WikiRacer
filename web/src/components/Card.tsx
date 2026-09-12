import type { ReactNode } from "react";

type CardProps = {
  tone: "green" | "light";
  radius: "hero" | "card";
  children: ReactNode;
  className?: string;
};

export function Card({ tone, radius, children, className = "" }: CardProps) {
  const toneClass =
    tone === "green"
      ? "on-dark bg-card-green text-text-on-dark shadow-hero"
      : "bg-surface-well text-text-on-light shadow-card";
  const radiusClass = radius === "hero" ? "rounded-hero" : "rounded-card";
  return (
    <section className={`${toneClass} ${radiusClass} ${className}`}>{children}</section>
  );
}
