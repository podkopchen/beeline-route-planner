import { BeelineLogo } from "./BeelineLogo";

export function BeeLogo({ size = 44, animated = false, className = "" }: { size?: number; animated?: boolean; className?: string }) {
  return <BeelineLogo
    size={size}
    className={`bee-logo ${animated ? "is-animated" : ""} ${className}`}
  />;
}
