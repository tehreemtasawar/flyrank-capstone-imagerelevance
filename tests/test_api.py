import pytest

FOX = {"title": "The Secret Life of Red Foxes", "body": "Foxes are adaptable hunters in forests."}
VULPES = {"title": "Notes on Vulpes vulpes", "body": "Range and diet of the species."}
TECH = {"title": "Best Programming Languages", "body": "Python and FastAPI for backend code."}


def post(client, payload):
    r = client.post("/posts", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def ids(client):
    return {i["filename"]: i["id"] for i in client.get("/images").json()}


def test_fox_post_ranks_fox_first_and_wolf_dog_lower(client, processed):
    p = post(client, FOX)
    body = client.get(f"/posts/{p['id']}/images").json()
    assert body["decision"] == "MATCH"
    assert body["suggestion"]["image"]["subject"] == "red fox"
    names = [c["filename"] for c in body["candidates"]]
    assert names[0].startswith("fox_") and names.index("wolf_01.jpg") > 1
    sims = {c["filename"]: c["similarity_score"] for c in body["candidates"]}
    assert sims["fox_01.jpg"] > sims["wolf_01.jpg"] + 0.1


def test_equivalent_concept_matches(client, processed):
    """'Vulpes vulpes' (no word 'fox') still surfaces a fox image — via the embedding, not keywords."""
    p = post(client, VULPES)
    body = client.get(f"/posts/{p['id']}/images").json()
    assert body["decision"] == "MATCH" and body["suggestion"]["image"]["subject"] == "red fox"


def test_forced_wolf_on_fox_post_is_rejected_with_explanation(client, processed):
    p = post(client, FOX)
    wolf = ids(client)["wolf_01.jpg"]
    r = client.get(f"/posts/{p['id']}/check/{wolf}").json()
    assert r["guard_decision"] == "REJECT"
    assert r["guard_reason"] == "Animal category mismatch: expected red fox, detected gray wolf"


def test_forced_correct_image_is_accepted(client, processed):
    p = post(client, FOX)
    r = client.get(f"/posts/{p['id']}/check/{ids(client)['fox_01.jpg']}").json()
    assert r["guard_decision"] == "ACCEPT"


def test_no_suitable_image_gives_no_confident_match_with_reason(client, processed):
    p = post(client, TECH)
    body = client.get(f"/posts/{p['id']}/images").json()
    assert body["decision"] == "NO_CONFIDENT_MATCH"
    assert body["suggestion"]["image"] is None and body["suggestion"]["image_id"] is None
    reason = body["suggestion"]["guard_reason"]
    assert "No confident match" in body["message"]
    assert "threshold" in reason and "fell below the similarity threshold" in reason
    assert any("below threshold" in c["guard_reason"] for c in body["candidates"])


def test_low_confidence_image_never_suggested(client, processed):
    p = post(client, {"title": "Dogs and puppies", "body": "A dog and a puppy at play"})
    body = client.get(f"/posts/{p['id']}/images").json()
    assert body["decision"] == "NO_CONFIDENT_MATCH"
    dog = next(c for c in body["candidates"] if c["filename"] == "dog_01.jpg")
    assert "Low classifier confidence" in dog["guard_reason"]


def test_suggestion_is_idempotent(client, processed):
    p = post(client, FOX)
    a = client.get(f"/posts/{p['id']}/images").json()["suggestion"]["id"]
    b = client.get(f"/posts/{p['id']}/images").json()["suggestion"]["id"]
    assert a == b and len(client.get("/suggestions").json()) == 1


def test_post_creation_is_idempotent_and_validated(client):
    a, b = post(client, FOX), post(client, FOX)
    assert a["id"] == b["id"]
    for bad in ({}, {"title": "", "body": "x"}, {"title": "x"}, {"title": "  ", "body": "y"}, {"title": 5, "body": "y"}):
        assert client.post("/posts", json=bad).status_code == 422


def test_review_workflow(client, processed):
    p = post(client, FOX)
    sid = client.get(f"/posts/{p['id']}/images").json()["suggestion"]["id"]
    assert client.get(f"/suggestions/{sid}").json()["review_status"] == "pending"
    assert client.post(f"/suggestions/{sid}/review", json={"action": "approve"}).json()["review_status"] == "approved"
    assert client.post(f"/suggestions/{sid}/review", json={"action": "approve"}).json()["review_status"] == "approved"  # idempotent
    assert client.post(f"/suggestions/{sid}/review", json={"action": "reject"}).json()["review_status"] == "rejected"
    assert client.get("/suggestions", params={"review_status": "rejected"}).json()[0]["id"] == sid


def test_cannot_approve_a_no_match(client, processed):
    p = post(client, TECH)
    sid = client.get(f"/posts/{p['id']}/images").json()["suggestion"]["id"]
    assert client.post(f"/suggestions/{sid}/review", json={"action": "approve"}).status_code == 409


@pytest.mark.parametrize("url,method,body,code", [
    ("/posts/999/images", "get", None, 404),
    ("/posts/999/check/1", "get", None, 404),
    ("/images/999", "get", None, 404),
    ("/suggestions/999", "get", None, 404),
    ("/suggestions/999/review", "post", {"action": "approve"}, 404),
    ("/suggestions/1/review", "post", {"action": "delete"}, 422),
    ("/suggestions/1/review", "post", {}, 422),
    ("/suggestions?review_status=bogus", "get", None, 422),
    ("/posts/abc/images", "get", None, 422),
    ("/posts/1/images?limit=0", "get", None, 422),
])
def test_bad_input_is_clean_4xx_never_500(client, url, method, body, code):
    r = getattr(client, method)(url, **({"json": body} if body is not None else {}))
    assert r.status_code == code


def test_embedding_dimension_mismatch_is_409_not_500(client, processed, db):
    from app.models import Post
    import json
    p = post(client, FOX)
    row = db.get(Post, p["id"])
    row.embedding_json = json.dumps([0.1, 0.2, 0.3])
    db.commit()
    assert client.get(f"/posts/{p['id']}/images").status_code == 409


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
