# Edge Cases & Corner Scenarios: SecondSelf AI Second Brain

This document analyzes the critical edge cases, failure modes, and corner scenarios for the **SecondSelf** personal AI second brain system, along with targeted mitigations for each.

---

## 1. Ingestion Engine (`capture.py`)

### 1.1. Empty or Whitespace Ingestion
- **Scenario**: A user triggers the capture script with empty text input or only spaces/tabs.
- **Risk**: Creates empty raw metadata files, leading to API failures during classification.
- **Mitigation**: Validate input strings post-trimming. Reject captures where content length is zero or consists only of whitespace.

### 1.2. Scraped Webpages with JS Requirements (SPAs)
- **Scenario**: Scraped URLs point to Single Page Applications (e.g., React/Vue sites) where content is client-side rendered, or pages requiring authentication (paywalls, login).
- **Risk**: Scraping returns empty HTML body blocks or login redirects.
- **Mitigation**: Detect empty or generic content results (e.g. "Please log in"). fallback to saving the raw URL and title, and configure the classification prompt to tag the note as a bookmark to process manually or fetch using headless tools if available.

### 1.3. Scanned PDFs (Images without OCR text)
- **Scenario**: Ingesting a PDF file containing images of scanned text rather than selectable fonts.
- **Risk**: `pypdf` extracts an empty string, yielding zero context.
- **Mitigation**: Detect zero-length text output from PDF parser. Log a warning message informing the user that text extraction failed (suggesting OCR processing) and save the original file reference.

### 1.4. Non-UTF-8 Encoding & Special Characters
- **Scenario**: Ingested files or URLs use legacy encodings (e.g. ISO-8859-1, Windows-1252) or contain complex mathematical notation, emoji arrays, or foreign characters.
- **Risk**: File read/write operations crash with `UnicodeDecodeError`.
- **Mitigation**: Always read and write files using explicit UTF-8 encoding (`open(..., encoding='utf-8')`). Use decoding fallbacks like `chardet` or `errors='ignore'` / `errors='replace'` to prevent processing crashes.

---

## 2. Classification Engine (`classify.py`)

### 2.1. LLM Rate Limits or API Downtime
- **Scenario**: API rate limits are hit during classification, or the Groq/Gemini API is down.
- **Risk**: Pipeline halts midway, leaving files in a semi-processed state.
- **Mitigation**: Implement exponential backoff retry logic for LLM API calls. Ensure raw captures remain marked as `"processed": false` in the raw folder so they can be re-processed when connection resumes.

### 2.2. Non-JSON or Corrupted JSON Output from LLM
- **Scenario**: The LLM outputs markdown formatting wrapping JSON codeblocks, or fails to output valid JSON keys (category, tags, summary, title).
- **Risk**: Python's `json.loads` fails, causing script crashes.
- **Mitigation**: 
  - Use structured generation features (e.g., JSON mode or structured outputs) if supported.
  - Implement regex extractors to capture JSON arrays between ` ```json ` and ` ``` ` blocks.
  - Set fallback default values if individual keys are missing.

### 2.3. Title Collisions in wiki/
- **Scenario**: Two separate notes classify to the same title (e.g., "Weekly Planning" captured in separate weeks), resolving to the same slug filename.
- **Risk**: The newer capture overwrites the older note, causing data loss.
- **Mitigation**: Check if `wiki/{category}/{title_slug}.md` already exists. If it does, append the date or a short unique hash prefix to the filename (e.g., `weekly-planning-20260721.md`).

---

## 3. Similarity & Association Engine (`link.py`)

### 3.1. Changing the Embeddings Model
- **Scenario**: The embeddings model is upgraded from `all-MiniLM-L6-v2` (384 dimensions) to a higher-dimensional model like `bge-large-en-v1.5` (1024 dimensions).
- **Risk**: Embedding vector calculations crash when comparing legacy cached vectors against new vectors.
- **Mitigation**: Save the model name string inside the metadata of `embeddings.json`. If the model name changes, invalidate the cache and re-compute embeddings for all notes.

### 3.2. Identical or Duplicate Notes
- **Scenario**: The user captures the exact same article or text snippet twice.
- **Risk**: Notes achieve a cosine similarity of $1.0$, creating self-linking patterns and cluttering the graph with redundant edges.
- **Mitigation**: Reject creating links between notes with similarity $> 0.98$ (deeming them duplicates). Provide an option to merge or ignore duplicates.

### 3.3. Infinite Linking Loops
- **Scenario**: Appending related links to Markdown files alters their text content.
- **Risk**: Modifying the file content changes its embedding, triggering a loop of re-indexing and link addition.
- **Mitigation**: Compute the embedding vector *only* on the core content of the note (excluding the `### Related Notes` section at the footer).

---

## 4. Graph Model Generator (`build_graph.py`)

### 4.1. Broken Links (Dangling Edges)
- **Scenario**: A user manually deletes a file in `wiki/Projects/` that was linked by other notes.
- **Risk**: The graph references a target ID that no longer exists, causing the frontend visualizer to crash.
- **Mitigation**: Validate all targets. When constructing edges, confirm that both `from` and `to` nodes exist in the nodes database. Discard any edge pointing to a missing node.

### 4.2. Scale Bottlenecks (Large Knowledge Bases)
- **Scenario**: The wiki grows to 1000+ notes.
- **Risk**: Rerendering a large force-directed network diagram blocks the browser's thread, causing lag.
- **Mitigation**: 
  - Set a minimum similarity threshold for edge creation.
  - Implement a configuration toggle in the Streamlit UI to filter/limit the number of nodes visible (e.g., "Show top 50 nodes" or "Filter by Category").

---

## 5. Q&A Engine (`ask.py`)

### 5.1. Context Window Exhaustion
- **Scenario**: The top $K$ retrieved context notes are very long, exceeding the LLM context token limit.
- **Risk**: LLM API calls fail with context length errors.
- **Mitigation**: Truncate note contents to a maximum token length or dynamically adjust $K$ (e.g., reduce $K$ if total context size exceeds a safe threshold of 6000 tokens).

### 5.2. Hallucinations on Irrelevant Queries
- **Scenario**: User asks a question completely unrelated to the personal knowledge base (e.g. "What is the capital of France?").
- **Risk**: System synthesizes answers based on general LLM knowledge or hallucinates associations with unrelated notes.
- **Mitigation**: Instruct the LLM in the system prompt: *"Answer the question using ONLY the provided notes. If the notes do not contain the answer, say 'I cannot find the answer in your knowledge base.'"*

---

## 6. Streamlit User Interface (`app.py`)

### 6.1. Streamlit Multi-User Session Bleed
- **Scenario**: Multiple users access the deployed Streamlit app at the public URL.
- **Risk**: Graph configurations, active filters, or query results bleed across user sessions.
- **Mitigation**: Strictly use Streamlit's `st.session_state` scope to store user-specific search queries and selection targets. Avoid writing session data to global variables.

### 6.2. UI Freeze During Model Loading
- **Scenario**: The app starts up and has to download the sentence-transformer weights (approx. 90MB).
- **Risk**: Streamlit times out or shows a blank screen to the user.
- **Mitigation**: Wrap model loading in Streamlit's `@st.cache_resource` decorator so the weights are downloaded/cached in memory once on server initialization.
