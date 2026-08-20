/** 億ドル表示。桁が大きいほど小数を落として読みやすさを優先する。 */
export function formatOku(v: number): string {
  const a = Math.abs(v);
  const digits = a >= 100 ? 0 : 1;
  return v.toLocaleString("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** 営業利益率。マイナスも符号付きで出す。 */
export function formatPercent(v: number): string {
  return `${v.toLocaleString("ja-JP", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
}

export function formatValue(v: number, metricId: string): string {
  return metricId === "operating_margin" ? formatPercent(v) : formatOku(v);
}

/** 目盛りラベル。0は「0」とだけ書く。 */
export function formatTick(v: number, metricId: string): string {
  if (Math.abs(v) < 1e-9) return "0";
  if (metricId === "operating_margin") return `${Math.round(v)}%`;
  const a = Math.abs(v);
  const digits = a >= 10 ? 0 : 1;
  return v.toLocaleString("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
