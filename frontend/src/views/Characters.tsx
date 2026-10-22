import { useEffect, useState } from "react";
import { api, artifactUrl } from "../api";
import type { Character, Voice } from "../types";

export default function Characters() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setCharacters(await api.characters());
      setVoices(await api.voices());
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const createCharacter = async () => {
    if (!name.trim()) return;
    try {
      await api.createCharacter({ name: name.trim(), description, appearance: {} });
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const createVoice = async () => {
    if (!voiceName.trim()) return;
    try {
      await api.createVoice({ name: voiceName.trim(), engine: "chatterbox", language: "fr" });
      setVoiceName("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Personnages & voix</h1>
          <p className="muted">
            Une identité réutilisable = une image de référence + une voix de référence. Les deux sont conservées pour
            toutes les vidéos.
          </p>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <section className="two-col">
        <div className="card">
          <h2>Personnages</h2>
          <div className="row gap wrap">
            <input
              className="input grow"
              placeholder="Prénom ou nom du présentateur"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <button className="btn primary" onClick={createCharacter}>
              Ajouter
            </button>
          </div>
          <input
            className="input"
            placeholder="Description physique (âge, cheveux, tenue…)"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />

          <div className="grid chars">
            {characters.map((character) => (
              <div key={character.id} className="character">
                <div className="thumb">
                  {character.base_image ? (
                    <img src={artifactUrl(character.base_image)} alt={character.name} />
                  ) : (
                    <span className="muted tiny">pas d'image</span>
                  )}
                </div>
                <div>
                  <strong>{character.name}</strong>
                  <p className="muted tiny clamp">{character.description || "—"}</p>
                  <label className="btn ghost small file">
                    {character.base_image ? "Remplacer la référence" : "Image de référence"}
                    <input
                      type="file"
                      accept="image/*"
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        if (file) {
                          await api.uploadCharacterImage(character.id, file);
                          await load();
                        }
                        event.target.value = "";
                      }}
                    />
                  </label>
                </div>
              </div>
            ))}
            {characters.length === 0 && <p className="muted small">Aucun personnage.</p>}
          </div>
        </div>

        <div className="card">
          <h2>Voix</h2>
          <div className="row gap wrap">
            <input
              className="input grow"
              placeholder="Nom de la voix (ex. « Présentateur FR »)"
              value={voiceName}
              onChange={(event) => setVoiceName(event.target.value)}
            />
            <button className="btn primary" onClick={createVoice}>
              Ajouter
            </button>
          </div>
          <p className="muted tiny">
            Chatterbox Multilingual V3 (23+ langues, clonage ~5 s) par défaut. VoxCPM2 en alternative 48 kHz. Un
            échantillon de 5–15 s suffit.
          </p>
          <div className="grid chars">
            {voices.map((voice) => (
              <div key={voice.id} className="character">
                <div className="thumb small">
                  {voice.ref_audio ? <audio src={artifactUrl(voice.ref_audio)} controls /> : <span className="muted tiny">—</span>}
                </div>
                <div>
                  <strong>{voice.name}</strong>
                  <p className="muted tiny">
                    {voice.engine} · {voice.language}
                  </p>
                  <label className="btn ghost small file">
                    Échantillon de voix
                    <input
                      type="file"
                      accept="audio/*"
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        if (file) {
                          await api.uploadVoiceSample(voice.id, file);
                          await load();
                        }
                        event.target.value = "";
                      }}
                    />
                  </label>
                </div>
              </div>
            ))}
            {voices.length === 0 && <p className="muted small">Aucune voix.</p>}
          </div>
        </div>
      </section>
    </div>
  );
}
