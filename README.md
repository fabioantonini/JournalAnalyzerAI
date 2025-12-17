# Journalctl Trace Analyzer (Service-Focused)

Streamlit-based incident analysis tool for **journalctl** logs.  
The application uploads a systemd journal export, filters events by **target services**
(e.g. `freeswitch`, `avahi-daemon`), and uses an OpenAI-powered **two-pass analysis**
to reconstruct timelines, detect anomalies, formulate root-cause hypotheses, and
produce a **Jira-ready technical summary**.

The application supports `OPENAI_API_KEY` from the environment, with an optional
override directly from the UI.

---

## Features

- Upload and parse `journalctl` log files (text exports)
- Service-scoped analysis via `TARGET_SERVICES`
- Context-aware log filtering (±N lines)
- Two-pass LLM analysis:
  - Pass 1: chunk-level analysis
  - Pass 2: global synthesis
- Deterministic, evidence-based incident reports
- Jira-ready final summary
- Markdown export of the final report
- No RAG / vector database required (optimized for files < 10MB)

---

## Architecture Overview

1. **Log ingestion**
   - Reads a `journalctl` export file as plain text
2. **Deterministic filtering**
   - Keeps only lines related to selected services
   - Adds contextual lines to preserve causality
3. **Chunking**
   - Splits filtered logs into manageable chunks
4. **LLM Analysis**
   - Pass 1: analyze each chunk independently
   - Pass 2: synthesize a single coherent incident report
5. **Output**
   - Human-readable technical report
   - Jira-ready summary
   - Downloadable Markdown file

---

## Requirements

- Python **3.9+**
- An OpenAI API key

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-org>/journalctl-trace-analyzer.git
cd journalctl-trace-analyzer
````

### 2. Create and activate a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Configuration

### OpenAI API Key

The application looks for the API key in the environment:

```bash
export OPENAI_API_KEY="your_openai_api_key"
```

Alternatively, you can **override the key from the UI** using the password field in
the Streamlit sidebar.
If both are present, the UI key takes precedence.

---

## Running the Application

```bash
streamlit run app.py
```

Once started, open the browser at:

```
http://localhost:8501
```

---

## Usage

1. Upload a `journalctl` export file
   Example:

   ```bash
   journalctl --no-pager > system.log
   ```

2. Specify `TARGET_SERVICES` (comma-separated), for example:

   ```
   freeswitch,tai6-manager
   ```

3. Adjust optional parameters:

   * Context lines
   * Chunk size
   * Model and temperature

4. Click **Analyze**

5. Review:

   * Final incident report
   * Chunk-level analyses
   * Jira-ready summary

6. Download the report as Markdown if needed

---

## Typical Use Cases

* SIP / VoIP incident analysis
* FreeSWITCH gateway or registration failures
* Post-mortem analysis after network or edge-device replacement
* Support ticket documentation (Jira, ServiceNow, etc.)

---

## Limitations

* Designed for **single-run analysis**, not interactive Q&A
* Optimized for log files up to ~10MB
* Assumes journalctl logs are exported as plain text

---

## License

MIT License (or your preferred license)

---

## Disclaimer

This tool assists with log analysis but does **not replace human judgment**.
Root-cause hypotheses are generated strictly from observed log evidence and should
be validated by an engineer before operational decisions are taken.

