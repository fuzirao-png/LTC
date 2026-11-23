import { countryNameFor, regionCodeForCountry } from './customerClock';

/** Centralized label maps for all backend enum codes.
 *
 * Every component that displays a code to the user should import from here
 * instead of maintaining local maps. Add new mappings as domain models grow.
 */

// ---- Industry codes ----

export const INDUSTRY_LABELS: Record<string, string> = {
  TMC: '差旅平台',
  TRAVEL_OTA: '商旅OTA',
  FINTECH: '金融科技',
  OTHER: '其他',
};

export function industryLabel(code: string | null | undefined): string {
  const value = String(code || '').trim();
  return INDUSTRY_LABELS[value.toUpperCase()] || value || '其他';
}

// ---- Region codes ----

export const REGION_LABELS: Record<string, string> = {
  NA: '北美',
  EA: '东亚',
  SEA: '东南亚',
  EU: '欧洲',
  ME: '中东',
  OTHER: '其他',
};

export function regionLabel(code: string | null | undefined): string {
  return REGION_LABELS[String(code || '')] || code || '未知';
}

export function regionCodeForCountryLabel(country: string | null | undefined): string {
  return regionCodeForCountry(country);
}

// ---- Country codes ----

export const COUNTRY_LABELS: Record<string, string> = {
  JP: '日本',
  KR: '韩国',
  CN: '中国',
  US: '美国',
  CA: '加拿大',
  MY: '马来西亚',
  SG: '新加坡',
  TH: '泰国',
  GB: '英国',
  UK: '英国',
  DE: '德国',
  ES: '西班牙',
  FR: '法国',
  NL: '荷兰',
  AE: '阿联酋',
  SA: '沙特',
};

export function countryLabel(code: string | null | undefined): string {
  const value = String(code || '').trim();
  return countryNameFor(value) || COUNTRY_LABELS[value.toUpperCase()] || value;
}

// ---- City names ----

export const CITY_LABELS: Record<string, string> = {
  TOKYO: '东京', OSAKA: '大阪', KYOTO: '京都', FUKUOKA: '福冈', SAPPORO: '札幌',
  NAGOYA: '名古屋', SENDAI: '仙台', SEOUL: '首尔', BEIJING: '北京', SHANGHAI: '上海',
  SINGAPORE: '新加坡', BANGKOK: '曼谷', LONDON: '伦敦', BERLIN: '柏林', PARIS: '巴黎',
  NEW_YORK: '纽约', 'NEW YORK': '纽约', SAN_FRANCISCO: '旧金山', 'SAN FRANCISCO': '旧金山',
  DUBAI: '迪拜', RIYADH: '利雅得', TORONTO: '多伦多', VANCOUVER: '温哥华',
};

export function cityLabel(value: string | null | undefined): string {
  const city = String(value || '').trim();
  return CITY_LABELS[city.toUpperCase()] || city;
}

export function regionCountryLabel(
  regionCode: string | null | undefined,
  countryCode: string | null | undefined,
): string {
  const region = regionLabel(regionCode);
  const country = countryLabel(countryCode);
  return country ? `${region}-${country}` : region;
}

// ---- Sales tier ----

export const SALES_TIER_LABELS: Record<string, string> = {
  MA: 'MA · 关键客户',
  SA: 'SA · 战略客户',
  A: 'A · 标准客户',
};

export function salesTierLabel(code: string | null | undefined): string {
  return SALES_TIER_LABELS[String(code || '')] || code || '未知';
}

// ---- Account type ----

export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  strategic: '战略运营',
  sales: '销售',
};

export function accountTypeLabel(code: string | null | undefined): string {
  return ACCOUNT_TYPE_LABELS[String(code || '')] || code || '未知';
}

// ---- Pipeline stage ----

export const PIPELINE_STAGE_LABELS: Record<string, string> = {
  new: '新线索',
  contacted: '已触达',
  engaged: '已互动',
  meeting: '已约见',
  proposal: '提案中',
  won: '已成交',
  lost: '已流失',
  dormant: '沉眠',
};

export function pipelineStageLabel(code: string | null | undefined): string {
  return PIPELINE_STAGE_LABELS[String(code || '')] || code || '未知';
}

// ---- Allocation / pool status ----

export const POOL_STATUS_LABELS: Record<string, string> = {
  claimable: '可认领',
  claimed: '已认领',
  released: '已释放',
  selected: '已选择',
};

export function poolStatusLabel(code: string | null | undefined): string {
  return POOL_STATUS_LABELS[String(code || '')] || code || '未知';
}

// ---- Candidate processing status ----

export const PROCESSING_STATUS_LABELS: Record<string, string> = {
  collected: '已收集',
  enriching: '充实中',
  enriched: '已充实',
  scored: '已评分',
  eligible: '可入库',
  promoted: '已加入总线索库',
  rejected: '已拒绝',
  merged: '已合并',
  archived: '已归档',
};

export function processingStatusLabel(code: string | null | undefined): string {
  return PROCESSING_STATUS_LABELS[String(code || '')] || code || '未知';
}

// ---- Validation status ----

export const VALIDATION_STATUS_LABELS: Record<string, string> = {
  valid: '有效',
  incomplete: '待补全',
  review_required: '需复审',
  rejected: '无效',
};

export function validationStatusLabel(code: string | null | undefined): string {
  return VALIDATION_STATUS_LABELS[String(code || '')] || code || '未知';
}

// ---- Job status ----

export const JOB_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  retry_wait: '等待重试',
  succeeded: '已完成',
  failed_final: '失败',
  cancelled: '已取消',
  reconcile_required: '需对账',
  dead: '已终止',
};

export function jobStatusLabel(code: string | null | undefined): string {
  return JOB_STATUS_LABELS[String(code || '')] || code || '未知';
}

// ---- Scene code ----

export const SCENE_LABELS: Record<string, string> = {
  S1: '标准发现',
  S2: '商旅优先',
  S3: '定制检索',
};

export function sceneLabel(code: string | null | undefined): string {
  return SCENE_LABELS[String(code || '')] || code || '未知';
}
