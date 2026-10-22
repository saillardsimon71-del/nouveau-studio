import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Project, SystemInfo } from "./types";
import Projects from "./views/Projects";
import Studio from "./views/Studio";
import Characters from "./views/Characters";
import System from "./views/System";

type Tab = "projects" | "characters" | "system";

// Hash routing keeps the app dependency-free and survives a hard refresh on any
// path (the backend serves index.html for unknown routes).
function parseHash(): { tab: Tab; projectId: string | null } {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [section, id] = hash.split("/");
  if (section === "project" && id) return { tab: "projects", projectId: id };
  if (section === "characters") return { tab: "characters", projectId: null };
  if (section === "system") return { tab: "system", projectId: null };
  return { tab: "projects", projectId: null };
}

export default function App() {
  const [route, setRoute] = useState(parseHash());
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (path: string) => {
    window.location.hash = path;
  };

  const refreshSystem = useCallback(async () => {
    try {
      setSystem(await api.system());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const refreshProject = useCallback(async (projectId: string) => {
    try {
      setProject(await api.project(projectId));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refreshSystem();
    const timer = window.setInterval(refreshSystem, 20000);
    return () => window.clearInterval(timer);
  }, [refreshSystem]);

  useEffect(() => {
    if (route.projectId) void refreshProject(route.projectId);
    else setProject(null);
  }, [route.projectId, refreshProject]);

  const simulatedEngine = system?.engines.some((e) => e.simulated && e.available);

  return (
    <div className="app">
      <aside className="sidebar">
        <button className="brand" onClick={() => go("projects")}>
          <span className="brand-mark" aria-hidden />
          <span>
            <strong>Premium</strong>
            <em>Video Studio</em>
          </span>
        </button>

        <nav>
          <button className={route.tab === "projects" ? "nav active" : "nav"} onClick={() => go("projects")}>
            Projets
          </button>
          <button
            className={route.tab === "characters" ? "nav active" : "nav"}
            onClick={() => go("characters")}
          >
            Personnages & voix
          </button>
          <button className={route.tab === "system" ? "nav active" : "nav"} onClick={() => go("system")}>
            Moteurs & coûts
          </button>
        </nav>

        <div className="sidebar-foot">
          {simulatedEngine && (
            <div className="pill warn" title="Les moteurs réels nécessitent un GPU distant">
              mode simulation disponible
            </div>
          )}
          <div className="muted small">
            {system?.job_stats ? `${system.job_stats.jobs} job(s) · ${system.job_stats.cost_usd.toFixed(2)} $` : "…"}
          </div>
        </div>
      </aside>

      <main>
        {error && (
          <div className="banner error" onClick={() => setError(null)}>
            {error} <span className="muted">(cliquer pour fermer)</span>
          </div>
        )}

        {route.tab === "projects" &&
          (route.projectId && project ? (
            <Studio
              project={project}
              system={system}
              reload={() => route.projectId && refreshProject(route.projectId)}
              onBack={() => go("projects")}
            />
          ) : (
            <Projects
              onOpen={(id) => go(`project/${id}`)}
              onChanged={refreshSystem}
            />
          ))}

        {route.tab === "characters" && <Characters />}
        {route.tab === "system" && <System system={system} reload={refreshSystem} />}
      </main>
    </div>
  );
}
