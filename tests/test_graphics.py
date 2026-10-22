from app.graphics import Event, build_ass, subtitle_events, wrap


def test_wrap_keeps_words_whole():
    text = "L'outil lit chaque message, le classe, et prépare une réponse prête à envoyer."
    wrapped = wrap(text, 30, 3)
    for line in wrapped.split("\n"):
        assert len(line) <= 34
    assert " ".join(wrapped.split()) == text


def test_subtitle_events_stay_inside_shot_window():
    shots = [
        {"start_s": 0.0, "duration_s": 3.0, "dialogue": ""},
        {"start_s": 3.0, "duration_s": 5.0, "dialogue": "Et si tu pouvais automatiser toutes ces tâches ?"},
        {"start_s": 8.0, "duration_s": 6.0, "dialogue": "L'outil lit chaque message. Il le classe."},
    ]
    events = subtitle_events(shots)
    assert len(events) >= 2
    for event in events:
        assert 3.0 <= event.start <= 14.0
        assert event.end > event.start
        assert event.end <= 14.05
        assert len(event.text) <= 60


def test_build_ass_writes_valid_header(tmp_path):
    path = build_ass([Event(0, 2, "Bonjour")], tmp_path / "subs.ass", 1080, 1920)
    content = path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "PlayResX: 1080" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle" in content


def test_long_dialogue_is_split_not_truncated():
    shots = [{"start_s": 0.0, "duration_s": 8.0, "dialogue": "Un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze."}]
    events = subtitle_events(shots)
    assert len(events) > 1
    merged = " ".join(event.text for event in events)
    for word in ("un", "deux", "quinze"):
        assert word in merged.lower()
