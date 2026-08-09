export function compactParams<T extends Record<string, unknown>>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => {
      if (value === undefined || value === null) {
        return false;
      }

      if (typeof value === "string" && value.trim() === "") {
        return false;
      }

      return true;
    }),
  ) as Partial<T>;
}
