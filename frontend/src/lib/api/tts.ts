import axiosInstance from '$lib/axios';

export type JobStatus = 'pending' | 'running' | 'complete' | 'failed' | 'cancelled';

export interface GenerateRequest {
  model_id: string;
  text: string;
  voice_id?: string | null;
  speed?: number;
  pitch?: number;
  language?: string;
  output_format?: 'wav' | 'mp3' | 'ogg';
  extra?: Record<string, unknown>;
}

export interface GenerateResponse {
  job_id: string;
  status: JobStatus;
  message: string;
}

export interface TTSJob {
  id: string;
  model_id: string;
  text: string;
  voice_id: string | null;
  voice_profile_id: string | null;
  parameters: Record<string, unknown> | null;
  status: JobStatus;
  error_message: string | null;
  output_path: string | null;
  duration_seconds: number | null;
  processing_time_ms: number | null;
  created_at: string;
  completed_at: string | null;
  batch_id?: string;
  celery_task_id?: string;
  speaker_similarity?: number | null;
}

export interface JobListResponse {
  jobs: TTSJob[];
  total: number;
  page: number;
  page_size: number;
}

export interface BatchGenerateRequest {
  lines: string[];
  model_id: string;
  voice_id?: string;
  language?: string;
  speed?: number;
  output_format?: 'wav' | 'mp3' | 'ogg';
  extra?: Record<string, unknown>;
}

export interface BatchGenerateResponse {
  batch_id: string;
  job_ids: string[];
  total: number;
}

export interface BatchStatusResponse {
  batch_id: string;
  total: number;
  status_counts: Record<string, number>;
  jobs: TTSJob[];
}

export async function generateTTS(request: GenerateRequest): Promise<GenerateResponse> {
  const res = await axiosInstance.post<GenerateResponse>('/tts/generate', request);
  return res.data;
}

export async function getJob(jobId: string): Promise<TTSJob> {
  const res = await axiosInstance.get<TTSJob>(`/tts/jobs/${jobId}`);
  return res.data;
}

export function getAudioUrl(jobId: string): string {
  return `/api/tts/jobs/${jobId}/audio`;
}

export async function cancelJob(jobId: string): Promise<void> {
  await axiosInstance.delete(`/tts/jobs/${jobId}`);
}

export async function listJobs(params?: {
  page?: number;
  page_size?: number;
  model_id?: string;
  status?: JobStatus;
  search?: string;
}): Promise<JobListResponse> {
  const res = await axiosInstance.get<JobListResponse>('/tts/jobs', { params });
  return res.data;
}

export async function batchGenerate(req: BatchGenerateRequest): Promise<BatchGenerateResponse> {
  const { data } = await axiosInstance.post<BatchGenerateResponse>('/tts/batch', req);
  return data;
}

export async function getBatchStatus(batchId: string): Promise<BatchStatusResponse> {
  const { data } = await axiosInstance.get<BatchStatusResponse>(`/tts/batches/${batchId}`);
  return data;
}

export function getBatchZipUrl(batchId: string): string {
  return `/api/tts/batches/${batchId}/zip`;
}

/** Poll a job until it reaches a terminal state (complete or failed). */
export async function pollJob(
  jobId: string,
  onUpdate: (job: TTSJob) => void,
  intervalMs = 1000,
  timeoutMs = 1_800_000  // 30 min — Fish Speech can take 8+ min for long text
): Promise<TTSJob> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await getJob(jobId);
    onUpdate(job);
    if (job.status === 'complete' || job.status === 'failed' || job.status === 'cancelled') {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`Job ${jobId} timed out after ${timeoutMs}ms`);
}
