import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["PVS_MODAL_ENABLED"] = "1"
os.environ["PVS_ALLOW_MOCK"] = "0"
os.environ["PVS_PROVIDER"] = "modal"
os.environ["PVS_REQUEUE_ON_BOOT"] = "0"
os.environ.setdefault("PVS_HOST", "127.0.0.1")
os.environ.setdefault("PVS_PORT", "8787")

if __name__ == "__main__":
    import modal
    import uvicorn

    if modal.Workspace.from_context().hydrate().name != "kulejean567":
        raise SystemExit("Activer le profil Modal kulejean567 avant de lancer le studio.")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("Compiler l'interface : cd frontend puis npm ci et npm run build.")
    uvicorn.run("app.main:app", host=os.environ["PVS_HOST"], port=int(os.environ["PVS_PORT"]), workers=1)
