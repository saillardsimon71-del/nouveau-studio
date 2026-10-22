import { useEffect, useState } from "react";
import { api } from "../api";
import type { Job, SystemInfo } from "../types";

export default function System({ system, reload }: { system: SystemInfo | null; reload: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    void api.jobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  if (!system) return <div className="page muted">Chargement…</div>;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Moteurs & coûts</h1>
          <p className="muted">
            Ce que l'environnement sait réellement faire. Un moteur « disponible » a ses fichiers et ses poids ; un
            moteur « non vérifié » n'a pas encore produit de vidéo.
          </p>
        </div>
        <button className="btn ghost" onClick={reload}>
          Rafraîchir
        </button>
      </header>

      {system.blockers.length > 0 && (
        <section className="card">
          <h2>Blocages actuels</h2>
          <ul className="tiny">
            {system.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
          <p className="muted tiny">
            Les scripts <code>scripts/gpu/</code> installent LTX-2.5, LongCat-Video-Avatar et Chatterbox sur une
            machine GPU, puis <code>PVS_LTX_REPO</code>, <code>PVS_LTX_MODELS</code>, <code>PVS_AVATAR_REPO</code> et{" "}
            <code>PVS_AVATAR_WEIGHTS</code> pointent vers les bons chemins.
          </p>
        </section>
      )}

      <section className="card">
        <h2>Moteurs</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Type</th>
              <th>État</th>
              <th>GPU</th>
              <th>Vérifié</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {system.engines.map((engine) => (
              <tr key={engine.name}>
                <td>
                  <strong>{engine.label}</strong>
                  <div className="muted tiny">{engine.name}</div>
                </td>
                <td>{engine.kind}</td>
                <td>
                  {engine.available ? (
                    <span className="pill ok">disponible</span>
                  ) : (
                    <span className="pill">indisponible</span>
                  )}
                  {engine.simulated && <span className="pill warn">simulation</span>}
                  {!engine.available && <div className="muted tiny">{engine.unavailable_reason}</div>}
                </td>
                <td className="tiny">{engine.requires_gpu ? engine.gpu : "CPU"}</td>
                <td className="tiny">{engine.verified ? "oui" : "non"}</td>
                <td className="muted tiny">{engine.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Tarifs utilisés pour le calcul de coût</h2>
        <p className="muted tiny">
          Les tarifs sont des prix publics indicatifs (octobre 2026). Ils se surchargent par{" "}
          <code>PVS_RATE_&lt;PROVIDER&gt;_&lt;GPU&gt;</code>.
        </p>
        <div className="row gap wrap">
          {Object.entries(system.rate_card).map(([key, rate]) => (
            <span key={key} className="pill">
              {key} · {rate.toFixed(2)} $/h
            </span>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Derniers jobs</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Moteur</th>
              <th>Statut</th>
              <th>GPU s</th>
              <th>Coût</th>
              <th>Erreur</th>
            </tr>
          </thead>
          <tbody>
            {jobs.slice(0, 12).map((job) => (
              <tr key={job.id}>
                <td>{job.type}</td>
                <td className="tiny">{job.engine}</td>
                <td>
                  <span className={`dot ${job.status}`} /> {job.status}
                </td>
                <td>{(job.gpu_seconds ?? 0).toFixed(1)}</td>
                <td>{(job.cost_usd ?? 0).toFixed(3)} $</td>
                <td className="muted tiny">{(job.error ?? "").slice(0, 90)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
