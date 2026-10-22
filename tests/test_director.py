from app.director import _infer_duration, propose
from app.schemas import Storyboard

MAIL_BRIEF = (
    "Crée une publicité Instagram de 35 secondes avec mon avatar. Il présente une automatisation "
    "qui trie les e-mails et prépare des réponses. Style technologique premium, en français."
)


def test_infer_duration_from_brief():
    assert _infer_duration(MAIL_BRIEF) == 35
    assert _infer_duration("une vidéo de 12 secondes") == 12
    assert _infer_duration("aucune durée indiquée") is None


def test_heuristic_storyboard_structure():
    result = propose(MAIL_BRIEF, use_llm=False)
    assert result.source == "heuristic"
    board = result.storyboard
    assert isinstance(board, Storyboard)
    assert 4 <= len(board.shots) <= 7

    total = sum(shot.duration_s for shot in board.shots)
    assert 33 <= total <= 37, total

    kinds = [shot.kind for shot in board.shots]
    assert "avatar" in kinds
    assert "screen_capture" in kinds
    assert kinds[0] == "b_roll"  # a silent hook, no talking in the first 3 s

    # the hook is silent and the demo is a real capture, never a generated UI
    assert board.shots[0].dialogue == ""
    screen = next(shot for shot in board.shots if shot.kind == "screen_capture")
    assert "screen recording" in screen.prompt.lower()

    # dialogue is French and the visual prompts are English (better adherence)
    assert any("automatiser" in shot.dialogue for shot in board.shots)
    assert "cinematic" in board.shots[1].prompt.lower()


def test_storyboard_rejects_empty_shots():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Storyboard.model_validate({"concept": "x", "shots": []})


def test_target_duration_is_respected():
    result = propose("Une pub de 20 secondes sur la productivité", use_llm=False)
    total = sum(shot.duration_s for shot in result.storyboard.shots)
    assert 19 <= total <= 21, total
