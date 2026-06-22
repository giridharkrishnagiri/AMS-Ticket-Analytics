const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseDate(value: string | Date | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  if (typeof value === "string") {
    const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
    if (dateOnlyMatch) {
      return new Date(
        Number(dateOnlyMatch[1]),
        Number(dateOnlyMatch[2]) - 1,
        Number(dateOnlyMatch[3])
      );
    }
  }
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

export function formatDisplayDate(value: string | Date | null | undefined): string {
  const parsed = parseDate(value);
  if (!parsed) {
    return "Not available";
  }
  return `${pad(parsed.getDate())}-${monthNames[parsed.getMonth()]}-${parsed.getFullYear()}`;
}

export function formatDisplayDateTime(value: string | Date | null | undefined): string {
  const parsed = parseDate(value);
  if (!parsed) {
    return "Not available";
  }
  return `${formatDisplayDate(parsed)} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

export function formatDisplayDateRange(
  startValue: string | Date | null | undefined,
  endValue: string | Date | null | undefined
): string {
  if (!startValue || !endValue) {
    return "Not available";
  }
  return `${formatDisplayDate(startValue)} to ${formatDisplayDate(endValue)}`;
}

export function formatDisplayMonth(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  const match = /^(\d{4})-(\d{2})$/.exec(value.trim());
  if (!match) {
    return value;
  }
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) {
    return value;
  }
  return `${monthNames[monthIndex]}-${match[1]}`;
}
