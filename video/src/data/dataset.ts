import memory10 from "./memory10.generated.json";
import memory10Dummy from "./memory10.dummy.json";
import security8 from "./security8.generated.json";
import security8Dummy from "./security8.dummy.json";
import type { Dataset, Series } from "./types";

const asDataset = (raw: unknown) => raw as unknown as Dataset;

/**
 * 本番データとダミーデータは別々の Composition から読む。
 * ダミーの数字が本番の書き出しに混ざらないようにするための分離なので、
 * 本番の Composition がダミー側を読むようにはしないこと。
 */
export const DATASETS = {
  memory10: asDataset(memory10),
  security8: asDataset(security8),
} as const;

export const DUMMY_DATASETS = {
  memory10: asDataset(memory10Dummy),
  security8: asDataset(security8Dummy),
} as const;

export type DatasetSlug = keyof typeof DATASETS;

/** 指標ごとに各社の系列へ組み替える */
export function seriesFor(dataset: Dataset, metricId: string): Series[] {
  return dataset.companies.map((c) => {
    const byYear = new Map<number, { value: number | null; isEstimate: boolean }>();
    for (const p of dataset.data) {
      if (p.company_id === c.id && p.metric_id === metricId) {
        byYear.set(p.year, { value: p.value, isEstimate: p.is_estimate });
      }
    }
    return {
      companyId: c.id,
      nameJa: c.name_ja,
      monogram: c.monogram,
      color: c.color,
      values: dataset.years.map((y) => byYear.get(y)?.value ?? null),
      isEstimate: dataset.years.map((y) => byYear.get(y)?.isEstimate ?? false),
    };
  });
}

/** その指標に1つでも値があるか（無ければ「データ未取得」表示に切り替える） */
export function hasAnyValue(series: Series[]): boolean {
  return series.some((s) => s.values.some((v) => v !== null));
}
