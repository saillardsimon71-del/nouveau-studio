import { useEffect, useState } from "react";
import { api } from "../api";
import type { Project, Proposal } from "../types";

const EXAMPLE =
  "Crée une publicité Instagram de 35 secondes avec mon avatar. Il présente une automatisation qui trie les e-mails " +
  "et prépare des réponses. Style technologique premium, en français.";

export default function Projects({
  onOpen,
  onChanged,
}: {
  onOpen: (id: string) => void;
  onChanged: () => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [brief, setBrief] = useState(EXAMPLE);
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setProjects(await api.projects());
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const draft = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!name.trim()) throw new Error("Donner un nom au projet");
      const project = await api.createProject({ name: name.trim(), brief, format: "9:16" });
      const proposal = await api.propose({ brief, target_duration_s: 35 });
      await api.applyStoryboard(project.id, proposal.storyboard);
      setProposal(null);
      setName("");
      await load();
      onChanged();
      onOpen(project.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const preview = async () => {
    setBusy(true);
    setError(null);
    try {
      setProposal(await api.propose({ brief, target_duration_s: 35 }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const avatarDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      const project = await api.avatarDemo();
      onChanged();
      onOpen(project.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Studio</h1>
          <p className="muted">Décrire la vidéo, obtenir un storyboard, générer plan par plan.</p>
        </div>
      </header>

      <section className="card">
        <div className="row between gap">
          <div>
            <strong>Avatar français</strong>
            <p className="muted small">Portrait synthétique, voix Henri et synchronisation labiale. Plan vertical de 3,72 s maximum.</p>
          </div>
          <button className="btn primary" onClick={avatarDemo} disabled={busy}>Préparer un avatar français</button>
        </div>
        <p className="muted small">La préparation ne lance aucun rendu. Le bouton Générer du plan utilise les crédits Modal.</p>
      </section>

      <section className="card composer">
        <div className="row gap">
          <input
            className="input grow"
            placeholder="Nom du projet"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button className="btn ghost" onClick={preview} disabled={busy || !brief.trim()}>
            Proposer un storyboard
          </button>
          <button className="btn primary" onClick={draft} disabled={busy || !brief.trim()}>
            {busy ? "…" : "Créer le projet"}
          </button>
        </div>
        <textarea
          className="input area"
          rows={4}
          value={brief}
          onChange={(event) => setBrief(event.target.value)}
          placeholder="Décris la vidéo comme tu l'expliquerais à un réalisateur…"
        />
        {error && <div className="banner error">{error}</div>}

        {proposal && (
          <div className="proposal">
            <div className="row between">
              <strong>Proposition</strong>
              <span className={`pill ${proposal.source === "llm" ? "ok" : ""}`}>
                {proposal.source === "llm" ? `directeur IA · ${proposal.model}` : "directeur local"}
              </span>
            </div>
            <p className="muted small">{proposal.notes || proposal.storyboard.concept}</p>
            <ol className="proposal-shots">
              {proposal.storyboard.shots.map((shot, index) => (
                <li key={index}>
                  <span className={`kind k-${shot.kind}`}>{shot.kind}</span>
                  <strong>{shot.title}</strong>
                  <span className="muted">{shot.duration_s}s</span>
                  {shot.dialogue && <p className="dialogue">« {shot.dialogue} »</p>}
                </li>
              ))}
            </ol>
            <p className="muted small">
              Durée totale {proposal.storyboard.shots.reduce((sum, s) => sum + s.duration_s, 0).toFixed(1)}s ·
              style : {proposal.storyboard.style_guide}
            </p>
          </div>
        )}
      </section>

      <section className="grid projects">
        {projects.map((project) => (
          <button key={project.id} className="card project" onClick={() => onOpen(project.id)}>
            <div className="row between">
              <strong>{project.name}</strong>
              <span className="pill">{project.format}</span>
            </div>
            <p className="muted small clamp">{project.concept || project.brief}</p>
            <div className="row between small muted">
              <span>
                {project.generated_count ?? 0}/{project.shot_count ?? 0} plans générés
              </span>
              <span>{(project.total_duration_s ?? 0).toFixed(0)}s</span>
            </div>
            <div className="progress">
              <div
                style={{
                  width: `${((project.generated_count ?? 0) / Math.max(1, project.shot_count ?? 1)) * 100}%`,
                }}
              />
            </div>
          </button>
        ))}
        {projects.length === 0 && <div className="muted">Aucun projet. Décris une vidéo ci-dessus.</div>}
      </section>
    </div>
  );
}
