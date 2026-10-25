export type ShotKind = "avatar" | "b_roll" | "screen_capture" | "title" | "product";

export interface Job {
  id: string;
  project_id: string | null;
  shot_id: string | null;
  type: string;
  engine: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  stage: string;
  error: string | null;
  simulated: number;
  cost_usd: number;
  gpu_seconds: number;
  provider: string;
  gpu: string;
  created_at: string;
  finished_at: string | null;
  log?: string;
  artifacts?: Artifact[];
}

export interface Artifact {
  id: string;
  kind: string;
  path: string;
  mime: string;
  bytes: number;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface VoicePerformance {
  expected_text: string;
  transcript: string | null;
  duration_s: number;
  accepted: boolean;
  human_approved: boolean;
  source_sha256: string;
}

export interface Shot {
  id: string;
  project_id: string;
  idx: number;
  kind: ShotKind;
  title: string;
  duration_s: number;
  dialogue: string;
  prompt: string;
  camera: string;
  character_id: string | null;
  voice_id: string | null;
  transition: string;
  status: string;
  selected_artifact: string | null;
  params: Record<string, unknown>;
  qc: QcResult;
  artifacts: Artifact[];
  start_s: number;
  character?: Character | null;
  voice?: Voice | null;
}

export interface QcResult {
  verdict?: "pass" | "review" | "fail";
  checks?: { id: string; status: string; detail: string }[];
  human_checks?: string[];
  simulated?: boolean;
}

export interface ExportRecord {
  id: string;
  project_id: string;
  path: string;
  duration_s: number;
  spec: Record<string, unknown>;
  qc: QcResult;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  brief: string;
  format: "9:16" | "16:9" | "1:1";
  status: string;
  concept: string;
  script: string;
  style_guide: string;
  music_path: string | null;
  created_at: string;
  updated_at: string;
  shot_count?: number;
  generated_count?: number;
  total_duration_s?: number;
  shots?: Shot[];
  exports?: ExportRecord[];
  cost?: CostSummary;
}

export interface CostSummary {
  cost_usd: number;
  gpu_seconds: number;
  jobs: number;
  jobs_succeeded: number;
  jobs_failed: number;
  attempts_per_success: number | null;
  exports: number;
  cost_per_export_usd: number | null;
}

export interface Character {
  id: string;
  name: string;
  description: string;
  appearance: Record<string, unknown>;
  base_image: string | null;
  voice_id: string | null;
  refs: string[];
  project_id: string | null;
}

export interface Voice {
  id: string;
  name: string;
  engine: string;
  language: string;
  ref_audio: string | null;
  transcript: string;
  params: Record<string, unknown>;
}

export interface EngineInfo {
  name: string;
  kind: string;
  label: string;
  capabilities: string[];
  requires_gpu: boolean;
  provider: string;
  gpu: string;
  simulated: boolean;
  verified: boolean;
  notes: string;
  available: boolean;
  unavailable_reason: string;
}

export interface SystemInfo {
  ffmpeg: string;
  data_dir: string;
  engines: EngineInfo[];
  director: { llm_configured: boolean; model: string; base_url: string; fallback: string };
  provider: string;
  rate_card: Record<string, number>;
  workers: number;
  job_stats: { jobs: number; by_status: Record<string, number>; cost_usd: number; active: number };
  blockers: string[];
}

export interface StoryboardShot {
  kind: ShotKind;
  title: string;
  duration_s: number;
  dialogue: string;
  prompt: string;
  camera: string;
  transition: string;
  engine_hint: string;
  notes: string;
}

export interface Storyboard {
  concept: string;
  script: string;
  style_guide: string;
  shots: StoryboardShot[];
}

export interface Proposal {
  source: "llm" | "heuristic";
  model: string;
  notes: string;
  storyboard: Storyboard;
}
