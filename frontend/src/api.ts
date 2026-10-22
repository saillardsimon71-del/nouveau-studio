const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  system: () => request<import("./types").SystemInfo>("/api/system"),
  projects: () => request<import("./types").Project[]>("/api/projects"),
  avatarDemo: () => request<import("./types").Project>("/api/projects/avatar-demo", { method: "POST" }),
  project: (id: string) => request<import("./types").Project>(`/api/projects/${id}`),
  createProject: (body: { name: string; brief: string; format?: string }) =>
    request<import("./types").Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (id: string, body: Record<string, unknown>) =>
    request<import("./types").Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProject: (id: string) => request<{ deleted: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),

  propose: (body: Record<string, unknown>) =>
    request<import("./types").Proposal>("/api/director/propose", { method: "POST", body: JSON.stringify(body) }),
  applyStoryboard: (projectId: string, storyboard: unknown) =>
    request<import("./types").Project>(`/api/projects/${projectId}/storyboard`, {
      method: "POST",
      body: JSON.stringify(storyboard),
    }),

  patchShot: (shotId: string, body: Record<string, unknown>) =>
    request<import("./types").Shot>(`/api/shots/${shotId}`, { method: "PATCH", body: JSON.stringify(body) }),
  generateShot: (shotId: string, body: Record<string, unknown> = {}) =>
    request<import("./types").Job>(`/api/shots/${shotId}/generate`, { method: "POST", body: JSON.stringify(body) }),
  generateVoice: (shotId: string, body: Record<string, unknown> = {}) =>
    request<import("./types").Job>(`/api/shots/${shotId}/voice`, { method: "POST", body: JSON.stringify(body) }),
  retakeShot: (shotId: string, body: Record<string, unknown>) =>
    request<import("./types").Job>(`/api/shots/${shotId}/retake`, { method: "POST", body: JSON.stringify(body) }),
  selectArtifact: (shotId: string, artifactId: string) =>
    request<unknown>(`/api/shots/${shotId}/select/${artifactId}`, { method: "POST" }),
  uploadShot: async (shotId: string, file: File, kind = "video") => {
    const form = new FormData();
    form.append("file", file);
    return request<import("./types").Artifact>(`/api/shots/${shotId}/upload?kind=${kind}`, {
      method: "POST",
      body: form,
    });
  },

  jobs: (projectId?: string) =>
    request<import("./types").Job[]>(`/api/jobs${projectId ? `?project_id=${projectId}` : ""}`),
  job: (id: string) => request<import("./types").Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => request<import("./types").Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  retryJob: (id: string) => request<import("./types").Job>(`/api/jobs/${id}/retry`, { method: "POST" }),

  exportProject: (projectId: string, body: Record<string, unknown>) =>
    request<import("./types").Job>(`/api/projects/${projectId}/export`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  exports: (projectId: string) => request<import("./types").ExportRecord[]>(`/api/projects/${projectId}/exports`),

  characters: () => request<import("./types").Character[]>("/api/characters"),
  createCharacter: (body: Record<string, unknown>) =>
    request<import("./types").Character>("/api/characters", { method: "POST", body: JSON.stringify(body) }),
  uploadCharacterImage: async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<import("./types").Character>(`/api/characters/${id}/image`, { method: "POST", body: form });
  },
  voices: () => request<import("./types").Voice[]>("/api/voices"),
  createVoice: (body: Record<string, unknown>) =>
    request<import("./types").Voice>("/api/voices", { method: "POST", body: JSON.stringify(body) }),
  uploadVoiceSample: async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<import("./types").Voice>(`/api/voices/${id}/sample`, { method: "POST", body: form });
  },
};

export const artifactUrl = (id: string) => `/api/artifacts/${id}/file`;
export const exportUrl = (id: string) => `/api/exports/${id}/file`;
export const posterId = (exp: import("./types").ExportRecord): string | null =>
  (exp as unknown as { poster_artifact?: string }).poster_artifact ?? null;
