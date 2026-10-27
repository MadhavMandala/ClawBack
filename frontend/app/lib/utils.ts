import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Join class names; a caller's Tailwind classes override the defaults (shadcn's helper).
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
