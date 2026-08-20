import generated from "./memory10.generated.json";
import dummy from "./memory10.dummy.json";
import type { Dataset, Series } from "./types";
import { COMPANY_COLORS } from "../theme";

/**
 * 本番データとダミーデータは別々の Composition から読む。
 * ダミーの数字が本番の書き出しに混ざらないようにするため、
 * ここ以外で切り替えないこと。
 */
export const realDataset = generated as unknown as Dataset;
export const dummyDataset = dummy as unknown as Dataset;

/** 指標ごとに 8社ぶんの系列へ組み替える */
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
      color: COMPANY_COLORS[c.id] ?? "#8B96AB",
      values: dataset.years.map((y) => byYear.get(y)?.value ?? null),
      isEstimate: dataset.years.map((y) => byYear.get(y)?.isEstimate ?? false),
    };
  });
}

/** その指標に1つでも値があるか（無ければ「データ未取得」表示に切り替える） */
export function hasAnyValue(series: Series[]): boolean {
  return series.some((s) => s.values.some((v) => v !== null));
}
