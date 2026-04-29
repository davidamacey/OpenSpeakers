import axiosInstance from '$lib/axios';

export type ReferenceTextStatus = 'pending' | 'ready' | 'failed' | 'manual';

export interface VoiceProfile {
  id: string;
  name: string;
  model_id: string;
  reference_audio_path: string;
  embedding_path: string | null;
  metadata?: Record<string, unknown> | null;
  extra_info?: Record<string, unknown> | null;
  description?: string | null;
  tags?: string[];
  reference_text: string | null;
  reference_text_status: ReferenceTextStatus;
  reference_language: string | null;
  created_at: string;
  /** Mean speaker_similarity across completed jobs that used this profile.
   *  ``null`` when no scored jobs exist yet. */
  avg_similarity: number | null;
  /** Number of scored completed jobs contributing to ``avg_similarity``. */
  similarity_count: number;
  /** Optional duration of the reference audio in seconds. Backend may omit. */
  reference_duration_seconds?: number | null;
}

export interface VoiceProfileUpdate {
  name?: string;
  description?: string;
  tags?: string[];
  reference_text?: string | null;
  reference_language?: string | null;
}

export interface VoiceListResponse {
  voices: VoiceProfile[];
  total: number;
}

export interface BuiltinVoice {
  id: string;
  name: string;
  language: string;
  gender: string | null;
  model_id: string;
}

export async function listVoices(modelId?: string): Promise<VoiceListResponse> {
  const res = await axiosInstance.get<VoiceListResponse>('/voices', {
    params: modelId ? { model_id: modelId } : undefined,
  });
  return res.data;
}

export async function getVoice(voiceId: string): Promise<VoiceProfile> {
  const { data } = await axiosInstance.get<VoiceProfile>(`/voices/${voiceId}`);
  return data;
}

export async function createVoiceProfile(
  name: string,
  modelId: string,
  referenceAudio: File,
  referenceText?: string
): Promise<VoiceProfile> {
  const form = new FormData();
  form.append('name', name);
  form.append('model_id', modelId);
  form.append('reference_audio', referenceAudio);
  if (referenceText !== undefined && referenceText !== null && referenceText !== '') {
    form.append('reference_text', referenceText);
  }
  const res = await axiosInstance.post<VoiceProfile>('/voices', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function updateVoice(
  voiceId: string,
  update: VoiceProfileUpdate
): Promise<VoiceProfile> {
  const { data } = await axiosInstance.patch<VoiceProfile>(`/voices/${voiceId}`, update);
  return data;
}

/** Convenience wrapper: PATCH the transcript only. Empty string clears it
 *  (server resets status to "pending" and re-runs ASR). */
export async function updateVoiceTranscript(
  voiceId: string,
  text: string
): Promise<VoiceProfile> {
  return updateVoice(voiceId, { reference_text: text });
}

/** Trigger a fresh ASR run for the profile. Server resets status to "pending". */
export async function transcribeVoice(voiceId: string): Promise<VoiceProfile> {
  const { data } = await axiosInstance.post<VoiceProfile>(`/voices/${voiceId}/transcribe`);
  return data;
}

export async function deleteVoiceProfile(voiceId: string): Promise<void> {
  await axiosInstance.delete(`/voices/${voiceId}`);
}

export async function listBuiltinVoices(modelId: string): Promise<BuiltinVoice[]> {
  const res = await axiosInstance.get<BuiltinVoice[]>(`/voices/builtin/${modelId}`);
  return res.data;
}

export function getVoiceAudioUrl(voiceId: string): string {
  return `/api/voices/${voiceId}/audio`;
}
