"""Three headline candidates + blind reviewer (Dirección 13-nov-2026)."""
import random
from types import SimpleNamespace

from src.radar_salud import weekly_headline as wh

W = {"headline": "Draft", "dek": "Draft dek", "body": "texto"}
CANDS = {"A": {"headline": "Fondo con meta de UF 1,5 millones apuesta por residencias", "dek": "Parte con 250 habitaciones."},
         "B": {"headline": "Las residencias entran al radar de los fondos", "dek": "Un fondo apunta a UF 1,5 millones."},
         "C": {"headline": "250 camas para un país que envejece", "dek": "Un fondo de UF 1,5 millones."}}


def _run(scores, verdicts=None, draft=CANDS):
    verdicts = verdicts or {}
    w = dict(W)
    seen = {}
    def review(prompt, feat):
        seen["prompt"] = prompt
        return SimpleNamespace(output={"scores": scores(prompt)})
    audit = wh.choose(w, {"numbers": []}, lambda t: {"verdict": verdicts.get(t["headline"], "PASS"), "errors": []},
                      lambda pr, f: SimpleNamespace(output=draft), review, rng=random.Random(1))
    return w, audit, seen


def _by_title(prompt, table):
    out = []
    for i, line in enumerate([l for l in prompt.splitlines() if l[:2].rstrip(".").isdigit()]):
        title = line.split("Título: ", 1)[1]
        style = next(k for k, c in CANDS.items() if c["headline"] == title)
        out.append({"option": i + 1, **dict(zip(wh.CRITERIA, table[style]))})
    return out


def test_highest_total_wins_and_reviewer_is_blind():
    w, audit, seen = _run(lambda p: _by_title(p, {"A": (4, 4, 3, 4), "B": (5, 5, 4, 4), "C": (3, 4, 4, 5)}))
    assert audit["status"] == "chosen" and audit["winner"] == "B" and w["headline"] == CANDS["B"]["headline"]
    assert "hecho + tensión" not in seen["prompt"] and "A:" not in seen["prompt"]  # styles are hidden


def test_tie_goes_to_a():
    _, audit, _ = _run(lambda p: _by_title(p, {"A": (4, 4, 4, 4), "B": (4, 4, 4, 4), "C": (4, 4, 4, 4)}))
    assert audit["winner"] == "A"


def test_candidate_failing_verification_is_never_chosen_and_failures_keep_the_draft():
    bad = {CANDS["B"]["headline"]: "FAIL"}
    w, audit, _ = _run(lambda p: _by_title(p, {"A": (2, 2, 2, 2), "C": (3, 3, 3, 3)}), verdicts=bad)
    assert audit["winner"] == "C" and audit["candidates"]["B"]["verdict"] == "FAIL"
    w, audit, _ = _run(lambda p: [], draft="not json")
    assert audit["status"] == "kept_draft" and w["headline"] == "Draft"
