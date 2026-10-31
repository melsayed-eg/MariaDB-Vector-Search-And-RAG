# Ingestion: Wikipedia acquisition and chunking

## Seed titles

`data/seed_titles.csv` defines which Wikipedia articles make up the corpus. It is a UTF-8
CSV file with the header `topic,title`:

- `topic` is a Computer Science subtopic label such as `databases` or `algorithms`. It later
  becomes the `topic` of the article in the database and can be used to filter searches.
- `title` is the English Wikipedia article title. A title that contains a comma must be
  written in quotes.

`load_seed_titles` in `src/wikirag/ingestion/wikipedia.py` reads and checks the file. It
returns `(topic, title)` pairs in file order. While reading, it:

- removes extra spaces and turns underscores into spaces (`Relational_database` becomes `Relational database`),
- skips blank lines,
- stops with a `ValidationError` that names the line number when a row is incomplete, when
  the topic or title is empty, or when the same article appears twice (an article can have
  only one topic),
- stops with a `ValidationError` when the file is missing, has the wrong header or has no rows.

### Corpus Specification & Justification

The corpus targets **Computer Science** due to its conceptual depth, rigorous taxonomic structure,
and applicability to vector retrieval benchmarking. It comprises exactly **200 validated, unique articles**
distributed across seven balanced subtopics:

- `algorithms`: 35 articles
- `systems_networks`: 35 articles
- `ai_ml`: 30 articles
- `languages_se`: 30 articles
- `databases`: 25 articles
- `theory_security`: 25 articles
- `history_people`: 20 articles


## Wikipedia source, licensing & attribution

Articles are retrieved from the public MediaWiki Action API of English Wikipedia
(`https://en.wikipedia.org/w/api.php`). `fetch_article` in
`src/wikirag/ingestion/wikipedia.py` requests one article at a time:

- the plain text of the article (stripped of raw wikitext markup),
- the latest revision id and its UTC timestamp,
- the visible categories (hidden maintenance categories are omitted),
- the titles of the linked articles from the main namespace.

Redirects are followed automatically. Wikipedia paginates long category and link lists, so
the client continues requesting continuation tokens until complete, capped at a safety limit of 20
requests per article. Every request carries a descriptive `User-Agent` and a 30-second timeout,
and `build_snapshot` pauses between articles to respect Wikipedia API etiquette. Network and server
failures raise `WikiRagError`; missing or malformed articles raise `ValidationError`.

### Attribution & License
Wikipedia text content is authored by Wikipedia contributors and licensed under the
**Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0)** and GNU Free
Documentation License (GFDL). In compliance with CC BY-SA 4.0, each article record retains its canonical
Wikipedia source `url`, `revision_id`, and title attribution.


## Snapshot atomicity and format

Wikipedia articles evolve over time, so the corpus is captured and shared as an immutable snapshot:
`data/snapshot/wikipedia_snapshot.jsonl`.

The file contains one JSON object per line with sorted keys and UTF-8 encoding:
`article_id`, `title`, `url`, `revision_id`, `revised_at`, `fetched_at`, `topic`,
`categories`, `linked_titles`, and `text`. All timestamps are UTC formatted with a trailing `Z`.

### Atomic Snapshot Guarantees
- `build_snapshot(seed_path, out_path, delay_s=0.2)` validates all inputs strictly. `delay_s` must
  be a finite, non-negative numeric value (non-numeric types like boolean or non-finite floats raise
  `ValidationError`).
- Snapshot creation is strictly atomic and all-or-nothing: articles are written to a temporary file
  (`.tmp`). If any download fails or two seeds resolve to the duplicate Wikipedia page ID, the entire
  build aborts with `WikiRagError`, the temporary file is unlinked, and any preexisting snapshot file is
  preserved intact.
- `load_snapshot(path)` reads the snapshot line by line as an iterator. Corrupted or invalid JSON lines
  raise `ValidationError` identifying the offending line number.


## Cleaning

`clean_text` in `src/wikirag/ingestion/cleaning.py` prepares the extracted plain text. The cleaning
pipeline is deterministic; any change in cleaning rules alters the SHA-256 fingerprint, triggering
idempotent re-embedding during ingestion.

Rules are applied in this strict sequence:

1. Normalize line endings (`\r\n` and `\r` become `\n`).
2. Strip HTML tags (preserving mathematical comparison operators such as `<` and `>`) and reference markers (e.g., `[edit]`, `[1]`, `[citation needed]`).
3. Remove non-functional invisible characters (zero-width spaces, soft hyphens, byte-order marks; zero-width non-joiner `\u200c` is preserved).
4. Unicode NFC normalization (performed after removing invisible characters so decomposed sequences compose correctly).
5. Collapse consecutive horizontal whitespace runs (spaces, tabs, non-breaking spaces) to a single space.
6. Strip leading and trailing whitespace from each line.
7. Collapse runs of three or more newlines into exactly two newlines (preserving single blank line paragraph boundaries).
8. Strip all leading and trailing whitespace from the full text block.

Non-string inputs immediately raise `ValidationError`.


## Chunking

`split_into_chunks` in `src/wikirag/ingestion/chunking.py` segments cleaned text into bounded windows
suitable for embedding models. Default parameters specify a maximum of 1000 characters per chunk and
an overlap of 150 characters.

Segmentation mechanics:

- If text exceeds `max_chars`, boundary breaks prioritize natural semantic breakpoints located in the
  second half of the window: paragraph boundaries (`\n\n`), line breaks (`\n`), sentence ends (`. `),
  and word spaces (` `), falling back to a hard cut at `max_chars` if no separator exists.
- Consecutive chunks advance with an overlap window of `overlap_chars`, realigned forward to the start
  of the nearest word to prevent fragmenting vocabulary across chunk boundaries.
- Continuous text without whitespace is partitioned without overlap.
- Resulting chunks feature zero leading/trailing whitespace, and indices start strictly at 0 without gaps.
- Returns a sequence of `ChunkDraft` objects containing `chunk_index`, `text`, and `section_title`.


## Validating the Snapshot (Offline & Non-Destructive)

To verify that the committed 200-article snapshot contains all required fields, valid metadata,
unique page IDs, and matches the seed list topic assignments exactly:

```bash
uv run python scripts/validate_snapshot.py