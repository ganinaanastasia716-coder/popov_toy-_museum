Popov Toy Museum — CLIP integration

Files:
- app.py: updated Flask app with CLIP visual search, cached image embeddings in SQLite, and duplicate checks during admin uploads.
- requirements.txt: required Python dependencies.
- render.yaml: Render build command installs CPU-only PyTorch before the rest of the requirements.

Install steps:
1. Replace the repository app.py with this app.py.
2. Replace requirements.txt with this requirements.txt.
3. Update render.yaml with this render.yaml, or at minimum use its buildCommand and CLIP environment variables in the existing Render service.
4. Commit changes and wait for Render deployment to finish.
5. First photo search/upload may be slow: the CLIP model must download from Hugging Face the first time.
6. Confirm the service has enough RAM/disk for PyTorch and the CLIP model. If Render build or runtime fails for memory/disk reasons, use a paid instance or a smaller external inference service.

Important limitations:
- CLIP compares visual similarity, not unique object identity. It can miss the same figure photographed from a very different angle, and may flag visually similar variants. The duplicate threshold is configurable using CLIP_DUPLICATE_THRESHOLD.
- When CLIP cannot run during admin upload, the app refuses to create the new card rather than silently risk adding a duplicate.
- Existing catalog embeddings are computed and cached as photos are searched or checked. The first search across a large catalog can be slow.
- Keep existing database and photo storage intact; do not delete museum.db or photos/ when deploying.
