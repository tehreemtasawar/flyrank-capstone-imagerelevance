# Design

## Problem
Given an image library and a set of blog posts, tag each image with a vision model,
match images to posts by meaning, and refuse to suggest an image when no candidate
is a confident match. The key risk is a wrong match, so the system is built around a guard.

## Data model
- images: filename, subject, category, attributes, caption, confidence, flagged, embedding
- posts: title, body, embedding
- suggestions: post, image (null for no match), similarity, decision, reason, review_status
- cost_log: one row per vision or embedding call (type, model, cost)
- jobs: status and progress counters for the background batch job

## API surface
POST /images/batch-process, GET /jobs/{id}, GET /images, GET /posts/{id}/images,
GET /posts/{id}/check/{image_id}, GET /suggestions, POST /suggestions/{id}/review

## Layers
HTTP (app/routers) -> logic (guard, matching, vision, embeddings, batch job) -> data (models, Alembic migrations).

## Mismatch guard
Per candidate: metadata present, confidence at least 0.6, post does not name another
known subject more strongly, cosine similarity at least 0.75. Any failure gives a reason string.

## Non-goals
No frontend, no authentication (single-tenant demo), no model comparison.
