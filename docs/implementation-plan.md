# Implementation Plan: SecondSelf AI Second Brain

This document defines the step-by-step implementation plan for building **SecondSelf**. It maps out the development tasks across ten distinct phases (Phase 0 to Phase 9) spanning the 4-week milestones: Ingestion, Organization, Mapping, and RAG Q&A.

---

## Phase 0: Project Setup & Environment Configurations
- **Objective**: Establish the workspace structure, setup virtual environment, and configure third-party APIs.
- **Tasks**:
  1. Scaffold directories: `raw/`, `wiki/` (with PARA directories: `Projects/`, `Areas/`, `Resources/`, `Archives/`), `docs/`, and `templates/`.
  2. Create [requirements.txt](file:///d:/AI%20PROJECTS/Masai/masai-live/Week%201%20-%20Projects/requirements.txt) with core libraries:
     ```text
     streamlit==1.32.0
     sentence-transformers==2.5.1
     scikit-learn==1.4.1
     requests==2.31.0
     beautifulsoup4==4.12.3
     pypdf==4.1.0
     python-dotenv==1.0.1
     groq==0.5.0
     google-genai==0.1.1
     pyyaml==6.0.1
     ```
  3. Create `.env` configuration file for API credentials (`GROQ_API_KEY`, `GEMINI_API_KEY`).
  4. Create a `.gitignore` to prevent committing `.env`, `__pycache__`, raw cache files, and node caches.

---

## Phase 1: Ingestion Engine (`capture.py`)
- **Objective**: Build a single command capture pipeline that saves any note, link, or file to `raw/`.
- **Tasks**:
  1. Setup argparse interface accepting `--note` (text string), `--link` (URL string), and `--file` (path to a local file).
  2. Implement text note processing: saves content to a `.txt` raw file.
  3. Implement URL scraper: fetches web pages, extracts text via `BeautifulSoup`, and strips script/style elements.
  4. Implement file ingestion: copies documents to the `raw/` directory, extracting raw text from `.txt`, `.md`, or `.pdf` (using `pypdf`).
  5. Generate UUIDs and timestamps for each capture, producing a `{uuid}.json` metadata record alongside the raw text/file.

---

## Phase 2: Classification Engine (`classify.py`)
- **Objective**: Use LLM intelligence to structure and file raw captures using the PARA framework.
- **Tasks**:
  1. Build a helper wrapper for LLM requests (supporting Groq Llama 3 or Gemini API endpoints).
  2. Write LLM prompts that ask for structured JSON output including PARA Category, tags list, short summary, and sanitized title.
  3. Parse raw captures from `raw/`, send them to the LLM, and parse responses.
  4. Create note generation logic: saves classified captures as Markdown files at `wiki/{category}/{title_slug}.md` containing frontmatter header blocks with metadata.
  5. Mark the raw capture metadata files as processed (`"processed": true`).

---

## Phase 3: Association & Embeddings Engine (`link.py`)
- **Objective**: Use dense vectors to calculate similarity between notes and automatically insert backlinks.
- **Tasks**:
  1. Setup embedding manager loading the local `all-MiniLM-L6-v2` transformer model (cached for reuse).
  2. Generate embeddings for note contents when they are added or modified.
  3. Create vector store caching mechanism (`embeddings.json`) tracking note IDs and vectors.
  4. Implement cosine similarity threshold comparison (e.g., threshold $0.45$).
  5. Write linking logic: if two notes exceed the threshold, append reciprocal links (Wikilink format: `[[Target Note Title]]` or relative Markdown format) in a `### Related Notes` section at the footer of each file.

---

## Phase 4: Graph Model Generator (`build_graph.py`)
- **Objective**: Scan notes and relationships to construct the network structure.
- **Tasks**:
  1. Walk through the `wiki/` directory recursively.
  2. Parse frontmatter YAML configurations for all Markdown files to extract metadata (ID, Category, Title, Summary).
  3. Parse body blocks looking for link markdown patterns to identify relationships/edges.
  4. Compute node sizing weight properties based on the node's degree centrality (number of connected edges).
  5. Dump the compiled nodes and edges arrays into a single root [graph.json](file:///d:/AI%20PROJECTS/Masai/masai-live/Week%201%20-%20Projects/graph.json) file.

---

## Phase 5: Retrieval-Augmented Generation Engine (`ask.py`)
- **Objective**: Implement context retrieval and synthesization for natural-language Q&A.
- **Tasks**:
  1. Vectorize input query strings using the sentence-transformer.
  2. Query `embeddings.json` cache, sorting available notes by cosine similarity.
  3. Retrieve top $K$ (e.g., 3 to 5) context notes above the similarity threshold.
  4. Assemble a context block combining the content of retrieved files.
  5. Draft an instructions prompt to guide the LLM to synthesize answers strictly based on context notes, citing titles as references.

---

## Phase 6: UI & Dashboard Assembly (Local `app.py`)
- **Objective**: Build the Streamlit application structure integrating graph visuals and Q&A.
- **Tasks**:
  1. Create the base Streamlit layout (Title header, sidebar configuration, main body partition).
  2. Embed the network visualization using `streamlit.components.v1.html` rendering a vis.js force-directed canvas.
  3. Write standard JavaScript functions inside the template to handle zooming, panning, node tooltips, and click selection events.
  4. Add the RAG search bar input field in the Streamlit UI, triggering `ask.py` and outputting rich answers.

---

## Phase 7: Local Integration Testing
- **Objective**: Run complete system validation tests locally with real information.
- **Tasks**:
  1. Capture 15+ real-world notes, bookmarks, and files using `capture.py`.
  2. Run the organization scripts (`classify.py` and `link.py`) to process raw captures into the `wiki/` folder.
  3. Verify that the files are placed correctly in PARA folders and that relevant files are correctly linked.
  4. Execute `build_graph.py` and verify `graph.json` contains proper structure.
  5. Launch Streamlit locally (`streamlit run app.py`) to test hovers, graph rendering, and search response quality.

---

## Phase 8: Production Deployment Preparation
- **Objective**: Set up code configurations for public distribution.
- **Tasks**:
  1. Clean codebase and ensure robust error exception handling (e.g., handling missing API keys, empty raw folders).
  2. Configure dependency freeze files, ensuring explicit module versions are locked.
  3. Push clean repository folders to GitHub (ensuring `.gitignore` prevents secret key leaks).

---

## Phase 9: Live QA & Verification
- **Objective**: Deploy application and run final public validation tests.
- **Tasks**:
  1. Deploy secondself repository on Streamlit Cloud.
  2. Set secret environment variables (`GROQ_API_KEY` / `GEMINI_API_KEY`) in the deployment dashboard.
  3. Open the public URL, verify graph loads correctly, and run retrieval search tests to verify end-to-end operation.
