import { useCallback, useEffect, useRef, useState } from "react";
import { api, artifactUrl, exportUrl } from "../api";
import type { Job, Project, Shot, SystemInfo } from "../types";

const ACTIVE = new Set(["queued", "running"]);

export default function Studio({
  project,
  system,
  reload,
  onBack,
}: {
  project: Project;
  system: SystemInfo | null;
  reload: () => void;
  onBack: () => void;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busyShot, setBusyShot] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [musicGain, setMusicGain] = useState(-20);
  const [subtitles, setSubtitles] = useState(true);
  const [transitionsOn, setTransitionsOn] = useState(true);
  const [retake, setRetake] = useState<{ shotId: string; start: number; end: number } | null>(null);
  const galleryRef = useRef<HTMLDivElement | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await api.jobs(project.id));
    } catch {
      /* transient */
    }
  }, [project.id]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const hasActive = jobs.some((job) => ACTIVE.has(job.status));

  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(async () => {
      await loadJobs();
      reload();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [hasActive, loadJobs, reload]);

  const jobForShot = (shotId: string) => jobs.find((job) => job.shot_id === shotId);
  const assemblyJob = jobs.find((job) => job.type === "assembly");

  const act = async (shot: Shot, kind: "video" | "voice" | "upload") => {
    setBusyShot(shot.id);
    setError(null);
    try {
      if (kind === "video") await api.generateShot(shot.id);
      if (kind === "voice") await api.generateVoice(shot.id);
      await loadJobs();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyShot(null);
    }
  };

  const upload = async (shot: Shot, file: File) => {
    setError(null);
    try {
      await api.uploadShot(shot.id, file, "video");
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const runRetake = async (shot: Shot) => {
    if (!shot.selected_artifact || !retake) return;
    setError(null);
    setBusyShot(shot.id);
    try {
      await api.retakeShot(shot.id, {
        artifact_id: shot.selected_artifact,
        start_s: retake.start,
        end_s: retake.end,
        prompt: shot.prompt,
      });
      setRetake(null);
      await loadJobs();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyShot(null);
    }
  };

  const saveDialogue = async (shot: Shot, dialogue: string) => {
    if (dialogue === shot.dialogue) return;
    await api.patchShot(shot.id, { dialogue });
    reload();
  };

  const doExport = async () => {
    setExporting(true);
    setError(null);
    try {
      await api.exportProject(project.id, {
        subtitles,
        transitions: transitionsOn,
        music_gain_db: musicGain,
        format: project.format,
        fps: 30,
      });
      await loadJobs();
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setExporting(false);
    }
  };

  const missing = (project.shots ?? []).filter((shot) => !shot.selected_artifact).length;
  const latestExport = project.exports?.[0];

  return (
    <div className="page studio">
      <header className="page-head">
        <div className="row gap center">
          <button className="btn ghost small" onClick={onBack}>
            ← Projets
          </button>
          <h1>{project.name}</h1>
          <span className="pill">{project.format}</span>
          <span className="pill">{project.total_duration_s?.toFixed(0)}s</span>
        </div>
        <div className="row gap">
          <span className="pill">{(project.cost?.cost_usd ?? 0).toFixed(2)} $ dépensés</span>
          <button className="btn primary" onClick={doExport} disabled={exporting || missing > 0}>
            {exporting ? "…" : missing > 0 ? `Exporter (${missing} plan(s) manquant(s))` : "Exporter la vidéo"}
          </button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}
      {!system?.director.llm_configured && (
        <div className="banner info small">
          Aucune clé LLM configurée : le directeur utilise son modèle de storyboard local. Renseigner
          <code> PVS_LLM_API_KEY</code> active DeepSeek.
        </div>
      )}

      <div className="studio-body">
        <div className="shots" ref={galleryRef}>
          {(project.shots ?? []).map((shot) => {
            const job = jobForShot(shot.id);
            const running = job ? ACTIVE.has(job.status) : false;
            const selected = shot.artifacts?.find((artifact) => artifact.id === shot.selected_artifact);
            const latestVideo = shot.artifacts?.find((artifact) => artifact.kind === "video");
            const media = selected ?? latestVideo;
            return (
              <article key={shot.id} className="card shot">
                <div className="row between">
                  <span className="shot-index">PLAN {String(shot.idx + 1).padStart(2, "0")}</span>
                  <span className={`kind k-${shot.kind}`}>{shot.kind}</span>
                </div>

                <h3>{shot.title || "Sans titre"}</h3>

                <div className="row gap small muted">
                  <span>{shot.duration_s.toFixed(1)}s</span>
                  <span>·</span>
                  <span>{shot.transition}</span>
                  {shot.qc?.verdict && (
                    <span className={`pill qc-${shot.qc.verdict}`}>QC {shot.qc.verdict}</span>
                  )}
                  {job?.simulated === 1 && <span className="pill warn">simulation</span>}
                </div>

                <div className="preview">
                  {media ? (
                    <video src={artifactUrl(media.id)} controls playsInline preload="metadata" />
                  ) : (
                    <div className="placeholder">Pas encore de clip</div>
                  )}
                </div>

                <label className="field">
                  <span className="muted small">Dialogue (français)</span>
                  <textarea
                    className="input"
                    rows={2}
                    defaultValue={shot.dialogue}
                    onBlur={(event) => void saveDialogue(shot, event.target.value)}
                  />
                </label>

                <details>
                  <summary className="muted small">Prompt & caméra</summary>
                  <pre className="prompt">{shot.prompt}</pre>
                  <p className="muted small">{shot.camera}</p>
                </details>

                {job && (
                  <div className="jobline small">
                    <span className={`dot ${job.status}`} />
                    {job.status} · {job.stage || job.type} · {Math.round(job.progress * 100)}%
                    {job.error && <div className="muted tiny">{job.error.slice(0, 220)}</div>}
                  </div>
                )}

                <div className="row gap wrap">
                  <button
                    className="btn primary small"
                    onClick={() => void act(shot, "video")}
                    disabled={busyShot === shot.id || running}
                  >
                    {running ? "En cours" : shot.selected_artifact ? "Régénérer" : "Générer"}
                  </button>
                  {shot.kind === "avatar" && (
                    <button className="btn ghost small" onClick={() => void act(shot, "voice")} disabled={running}>
                      Voix
                    </button>
                  )}
                  <label className="btn ghost small file">
                    Importer
                    <input
                      type="file"
                      accept="video/*"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void upload(shot, file);
                        event.target.value = "";
                      }}
                    />
                  </label>
                  {shot.selected_artifact && (
                    <button
                      className="btn ghost small"
                      onClick={() =>
                        setRetake(
                          retake?.shotId === shot.id
                            ? null
                            : { shotId: shot.id, start: 0, end: Math.min(2, shot.duration_s) },
                        )
                      }
                    >
                      Régénérer une zone
                    </button>
                  )}
                  {shot.artifacts && shot.artifacts.filter((a) => a.kind === "video").length > 1 && (
                    <select
                      className="input small-select"
                      value={shot.selected_artifact ?? ""}
                      onChange={async (event) => {
                        await api.selectArtifact(shot.id, event.target.value);
                        reload();
                      }}
                    >
                      {shot.artifacts
                        .filter((artifact) => artifact.kind === "video")
                        .map((artifact) => (
                          <option key={artifact.id} value={artifact.id}>
                            {new Date(artifact.created_at).toLocaleTimeString()} · {artifact.id.slice(-4)}
                          </option>
                        ))}
                    </select>
                  )}
                </div>

                {retake?.shotId === shot.id && (
                  <div className="retake">
                    <p className="muted tiny">
                      Seule la zone choisie est régénérée puis réinsérée dans le clip. Le clip d'origine reste intact
                      comme prise de référence.
                    </p>
                    <div className="row gap small">
                      <label className="field grow">
                        <span className="muted tiny">début (s)</span>
                        <input
                          className="input"
                          type="number"
                          min={0}
                          max={Math.max(0, shot.duration_s - 0.2)}
                          step={0.1}
                          value={retake.start}
                          onChange={(event) => setRetake({ ...retake, start: Number(event.target.value) })}
                        />
                      </label>
                      <label className="field grow">
                        <span className="muted tiny">fin (s)</span>
                        <input
                          className="input"
                          type="number"
                          min={0.2}
                          max={shot.duration_s}
                          step={0.1}
                          value={retake.end}
                          onChange={(event) => setRetake({ ...retake, end: Number(event.target.value) })}
                        />
                      </label>
                    </div>
                    <button
                      className="btn primary small"
                      disabled={busyShot === shot.id || retake.end <= retake.start}
                      onClick={() => void runRetake(shot)}
                    >
                      {busyShot === shot.id ? "…" : `Régénérer ${(retake.end - retake.start).toFixed(1)}s`}
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </div>

        <aside className="panel">
          <h2>Sortie</h2>
          <label className="field">
            <span className="muted small">Musique (volume {musicGain} dB)</span>
            <input
              type="range"
              min={-40}
              max={-6}
              step={1}
              value={musicGain}
              onChange={(event) => setMusicGain(Number(event.target.value))}
            />
          </label>
          <label className="check">
            <input type="checkbox" checked={subtitles} onChange={(event) => setSubtitles(event.target.checked)} />
            Sous-titres incrustés + fichier SRT
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={transitionsOn}
              onChange={(event) => setTransitionsOn(event.target.checked)}
            />
            Transitions enchaînées
          </label>

          <button className="btn primary full" onClick={doExport} disabled={exporting || missing > 0}>
            {exporting ? "…" : "Assembler l'export"}
          </button>

          {assemblyJob && ACTIVE.has(assemblyJob.status) && (
            <div className="jobline small">
              <span className={`dot ${assemblyJob.status}`} />
              {assemblyJob.stage} · {Math.round(assemblyJob.progress * 100)}%
            </div>
          )}

          {latestExport && (
            <div className="export-card">
              <video src={exportUrl(latestExport.id)} controls playsInline />
              <div className="row between small">
                <span>{latestExport.duration_s.toFixed(1)}s</span>
                <span className={`pill qc-${latestExport.qc.verdict}`}>QC {latestExport.qc.verdict}</span>
              </div>
              <a className="btn ghost small full" href={exportUrl(latestExport.id)} download>
                Télécharger le MP4
              </a>
              {typeof latestExport.spec.srt_artifact === "string" && (
                <a className="btn ghost small full" href={artifactUrl(latestExport.spec.srt_artifact as string)}>
                  Sous-titres .srt
                </a>
              )}
            </div>
          )}

          <h3>Contrôle qualité</h3>
          <p className="muted tiny">
            Les vérifications automatiques portent sur le conteneur, la durée, le format, l'audio, les noirs et les
            images figées. L'identité, la synchronisation labiale et le jeu restent des vérifications humaines :
          </p>
          <ul className="tiny muted">
            {(latestExport?.qc.human_checks ?? [
              "identité du visage",
              "synchronisation labiale",
              "expressions et mouvements",
              "respect du prompt",
            ]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <h3>Coût</h3>
          <div className="cost">
            <div className="row between">
              <span className="muted small">Total</span>
              <strong>{(project.cost?.cost_usd ?? 0).toFixed(2)} $</strong>
            </div>
            <div className="row between">
              <span className="muted small">Jobs</span>
              <span>{project.cost?.jobs ?? 0}</span>
            </div>
            <div className="row between">
              <span className="muted small">Tentatives / succès</span>
              <span>{project.cost?.attempts_per_success ?? "—"}</span>
            </div>
            <div className="row between">
              <span className="muted small">Coût par export</span>
              <span>{project.cost?.cost_per_export_usd ?? "—"}</span>
            </div>
          </div>

          <h3>Brief initial</h3>
          <p className="muted tiny">{project.brief}</p>
        </aside>
      </div>
    </div>
  );
}
