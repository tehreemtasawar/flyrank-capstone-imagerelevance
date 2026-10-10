from app.guard import best_candidate_or_none, evaluate, evaluate_candidates

KW = dict(similarity_threshold=0.55, confidence_threshold=0.6)


def ev(post, subject, conf=0.9, sim=0.8, known=None):
    return evaluate(post, subject, "animal", conf, sim, other_known_subjects=known, **KW)


def test_accepts_clear_match():
    assert ev("The behavior of red foxes in the wild", "red fox").decision == "ACCEPT"


def test_rejects_wolf_on_fox_post_with_explanation():
    r = ev("The behavior of red foxes in the wild", "gray wolf", sim=0.7, known=["red fox", "gray wolf"])
    assert r.decision == "REJECT" and r.code == "SUBJECT_MISMATCH"
    assert r.reason == "Animal category mismatch: expected red fox, detected gray wolf"


def test_rejects_low_confidence():
    r = ev("A post about some animal", "red fox", conf=0.3, sim=0.9)
    assert r.decision == "REJECT" and r.code == "LOW_CONFIDENCE"


def test_rejects_low_similarity():
    r = ev("A post about gardening tools", "red fox", sim=0.2)
    assert r.decision == "REJECT" and r.code == "LOW_SIMILARITY"


def test_rejects_missing_metadata():
    assert evaluate("x", None, None, None, 0.9, **KW).code == "NO_METADATA"


def test_shared_generic_word_does_not_hide_mismatch():
    # "red" is shared by 'red fox' and 'red deer stag'; a red-deer post must still refuse the fox
    r = ev("Red deer in autumn", "red fox", known=["red fox", "red deer stag"])
    assert r.decision == "REJECT" and "expected red deer stag" in r.reason


def test_right_subject_passes_when_other_subject_shares_a_word():
    assert ev("Red deer in autumn", "red deer stag", known=["red fox", "red deer stag"]).decision == "ACCEPT"


def test_polar_bear_rejected_for_brown_bear_post():
    r = ev("Brown bear hibernation facts", "polar bear cub", known=["polar bear cub", "brown bear"])
    assert r.decision == "REJECT" and "expected brown bear" in r.reason


def test_polar_bear_and_cub_stopword_does_not_match_everything():
    r = ev("Training tips for a new dog and its owner", "polar bear and cub", known=["polar bear and cub", "domestic dog"])
    assert r.decision == "REJECT"


def test_plural_and_irregular_plural_matching():
    assert ev("Dogs make great pets", "domestic dog", known=["domestic dog", "red fox"]).decision == "ACCEPT"
    assert ev("Wolves live in packs", "gray wolf", known=["gray wolf", "red fox"]).decision == "ACCEPT"


def test_substring_trap_red_in_bred():
    # 'red' must not match inside 'bred'
    r = ev("Dogs have been bred alongside humans", "red fox", known=["red fox", "domestic dog"])
    assert r.decision == "REJECT"


def test_best_candidate_falls_through_ranked_list():
    cands = [
        {"image_id": 1, "subject": "gray wolf", "category": "animal", "confidence": 0.9, "similarity_score": 0.85},
        {"image_id": 2, "subject": "red fox", "category": "animal", "confidence": 0.9, "similarity_score": 0.75},
    ]
    chosen, r = best_candidate_or_none("The behavior of red foxes", cands, **KW)
    assert chosen == 2 and r.decision == "ACCEPT"


def test_none_when_all_rejected():
    cands = [{"image_id": 1, "subject": "gray wolf", "category": "animal", "confidence": 0.9, "similarity_score": 0.3}]
    chosen, r = best_candidate_or_none("The behavior of red foxes", cands, **KW)
    assert chosen is None and r.decision == "REJECT"


def test_empty_candidates():
    assert best_candidate_or_none("x", [], **KW)[0] is None


def test_every_candidate_gets_a_verdict():
    cands = [
        {"image_id": 1, "subject": "gray wolf", "category": "animal", "confidence": 0.9, "similarity_score": 0.85},
        {"image_id": 2, "subject": "red fox", "category": "animal", "confidence": 0.9, "similarity_score": 0.75},
    ]
    v = evaluate_candidates("red foxes", cands, **KW)
    assert [r.decision for _, r in v] == ["REJECT", "ACCEPT"]
