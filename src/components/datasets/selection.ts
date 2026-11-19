/** Toggle the data-screen row selection: a complete selection clears, otherwise every listed id is selected. */
export function toggleSelectAll(checkedIds: string[], ids: string[]): string[] {
  if (!ids.length) return [];
  return ids.every(id => checkedIds.includes(id)) ? [] : [...new Set(ids)];
}
