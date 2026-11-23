export interface CustomerClockInput {
  country?: unknown;
  city?: unknown;
  timeZone?: unknown;
}

export interface CustomerClockConfig {
  countryCode: string;
  countryName: string;
  regionCode: string;
  label: string;
  timeZone: string;
}

export const COUNTRY_CLOCKS_BY_ISO: Record<string, Omit<CustomerClockConfig, 'label'>>;
export function countryNameFor(country: unknown): string;
export function countryCardLabel(country: unknown): string;
export function regionCodeForCountry(country: unknown): string;
export function cityNameFor(city: unknown): string;
export function resolveCustomerClock(customer: CustomerClockInput): CustomerClockConfig | null;
