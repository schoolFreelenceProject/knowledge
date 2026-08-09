export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "0";
  }

  return new Intl.NumberFormat().format(value);
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "0 ms";
  }

  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`;
  }

  return `${value.toFixed(0)} ms`;
}

export function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "0%";
  }

  return `${(value * 100).toFixed(1)}%`;
}

export function formatRating(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "No rating";
  }

  return value.toFixed(2);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }

  return value.toFixed(4);
}

export function titleCase(value: string): string {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function compactHash(value: string, chars = 8): string {
  return value.length <= chars ? value : value.slice(0, chars);
}
