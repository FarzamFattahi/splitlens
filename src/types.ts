export type Split = 'train' | 'validation' | 'test' | 'unassigned';
export type IssueKind =
  'leakage' | 'duplicate' | 'similar' | 'blur' | 'dark' | 'bright' | 'small' | 'broken';
export interface InputImage {
  id: string;
  path: string;
  file: File;
  split?: Split;
}
export interface ImageRecord {
  id: string;
  path: string;
  split: Split;
  label: string;
  width: number;
  height: number;
  bytes: number;
  sha256: string;
  dhash: string;
  brightness: number;
  sharpness: number;
  meanRgb?: [number, number, number];
  thumbnail: string;
  error?: string;
}
export interface Finding {
  id: string;
  kind: IssueKind;
  imageIds: string[];
  title: string;
  detail: string;
  distance?: number;
}
export interface AuditSettings {
  similarity: number;
  blur: number;
  dark: number;
  bright: number;
  minSize: number;
}
export const DEFAULT_SETTINGS: AuditSettings = {
  similarity: 4,
  blur: 60,
  dark: 35,
  bright: 225,
  minSize: 256,
};
export interface AuditResult {
  images: ImageRecord[];
  findings: Finding[];
  settings: AuditSettings;
  elapsed: number;
}
export type Decision = 'keep' | 'exclude';
