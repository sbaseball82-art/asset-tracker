export interface Company {
  id: string;
  name_ja: string;
  name_en: string;
  monogram: string;
  country: string;
  currency: string;
  fiscal_year_end: string;
  fiscal_year_end_month: number;
  scope: string;
  scope_note: string;
}

export interface Metric {
  id: string;
  label_ja: string;
  unit_ja: string;
  theme: "navy" | "green" | "rust";
  derived: boolean;
  formula?: string;
}

export interface DataPoint {
  company_id: string;
  metric_id: string;
  year: number;
  value: number | null;
  value_local: number | null;
  currency: string | null;
  fx_rate: number | null;
  is_estimate: boolean;
  source: string | null;
}

export interface Dataset {
  schema_version: number;
  is_dummy: boolean;
  year_mapping_rule: string;
  years: number[];
  companies: Company[];
  metrics: Metric[];
  fx_rates: { currency: string; year: number; rate_per_usd: number }[];
  coverage: { total_cells: number; filled_cells: number; filled_ratio: number };
  data: DataPoint[];
}

/** 1社ぶんの系列。values は years と同じ長さで、欠損は null。 */
export interface Series {
  companyId: string;
  nameJa: string;
  monogram: string;
  color: string;
  values: (number | null)[];
  isEstimate: boolean[];
}
