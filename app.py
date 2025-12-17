import os
import re
import textwrap
from dataclasses import dataclass
from typing import List, Tuple

import streamlit as st
from openai import OpenAI


# ----------------------------
# Prompt templates
# ----------------------------

DEFAULT_PROMPT_TEMPLATE = """\
You are a senior software engineer and incident analyst with strong expertise in
telecom systems, VoIP, FreeSWITCH, SIP signaling, and distributed service orchestration.

I will provide you with runtime traces and logs.

Your task is to analyze the traces **only with respect to the following target services**:

TARGET_SERVICES = {target_services}

For each service listed in TARGET_SERVICES, perform the following steps:

1. **Extract Relevant Events**
   - Identify all log entries, warnings, errors, and state transitions that are
     directly or indirectly related to the service.
   - Ignore unrelated services unless they directly affect one of the target services.

2. **Reconstruct the Event Timeline**
   - Rebuild a chronological sequence of events for each service.
   - Clearly indicate:
     - Triggering events
     - Requests, responses, retries, rescans, or restarts
     - Configuration reloads or network-related changes

3. **Analyze Service Interactions**
   - Describe how the target services interact with each other and with external
     components (e.g. SIP gateways, network interfaces, DHCP, edge devices).
   - Highlight any dependency failures or race conditions.

4. **Identify Anomalies and Failure Signals**
   - Point out symptoms such as:
     - “Invalid Gateway”
     - Registration failures
     - Timeouts or stale configuration
   - Explain why these symptoms appear based on the trace evidence.

5. **Root Cause Hypothesis**
   - Provide one or more plausible root causes, clearly labeled as hypotheses.
   - Base your reasoning strictly on observable trace data.

6. **Recovery and Mitigation Evidence**
   - Identify any recovery actions present in the traces
     (e.g. profile rescan, configuration reload, retry loops).
   - Assess whether they are sufficient or incomplete.

7. **Final Summary (Jira-Ready)**
   - Produce a concise technical summary suitable for a Jira ticket, including:
     - Impacted services
     - What happened
     - Why it happened
     - What worked
     - What did not work

Formatting requirements:
- Use clear section headers.
- Be precise and technical.
- Do not speculate beyond trace evidence.
- Prefer deterministic language over generic explanations.

LOG CHUNK:
```text
{log_text}
```\
"""

SYNTHESIS_PROMPT = """\
You are consolidating multiple chunk-level analyses of the same incident.
Combine them into ONE coherent incident report.

Requirements:
- Merge duplicated information.
- Resolve ordering into a single timeline per service when possible.
- Keep evidence-based statements.
- Clearly label hypotheses.
- Produce a Jira-ready final summary.

TARGET_SERVICES = {target_services}

CHUNK ANALYSES:
{chunk_analyses}
"""


# ----------------------------
# Utilities
# ----------------------------

def parse_target_services(raw: str) -> List[str]:
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def filter_lines_with_context(
    lines: List[str],
    target_services: List[str],
    context: int,
    max_lines: int,
) -> Tuple[List[str], int]:
    """
    Returns filtered lines plus the number of 'hits' (lines that matched directly).
    Strategy: keep any line matching any target service token (case-insensitive),
    plus +/- context lines around each hit. Deduplicate via index set.
    """
    if not target_services:
        return [], 0

    patterns = [re.compile(re.escape(svc), re.IGNORECASE) for svc in target_services]

    hit_idxs = []
    for i, line in enumerate(lines):
        if any(p.search(line) for p in patterns):
            hit_idxs.append(i)

    keep = set()
    for i in hit_idxs:
        start = max(0, i - context)
        end = min(len(lines) - 1, i + context)
        for j in range(start, end + 1):
            keep.add(j)

    kept_sorted = sorted(keep)
    filtered = [lines[i].rstrip("\n") for i in kept_sorted]

    # Safety cap (prevents enormous prompt payloads if tokens match too broadly)
    if max_lines and len(filtered) > max_lines:
        filtered = filtered[:max_lines]

    return filtered, len(hit_idxs)


def chunk_text_by_chars(text: str, chunk_size: int) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if chunk_size <= 0:
        return [text]
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


@dataclass
class OpenAIConfig:
    api_key: str
    model: str
    temperature: float


def call_openai_responses(client: OpenAI, model: str, temperature: float, prompt: str) -> str:
    """
    Uses the Responses API. The SDK supports constructing the client with env var
    or explicit api_key; we use an explicit key here (already resolved).
    """
    resp = client.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
    )
    return resp.output_text or ""


# ----------------------------
# Streamlit app
# ----------------------------

st.set_page_config(page_title="Journalctl Trace Analyzer (No-RAG)", layout="wide")
st.title("Journalctl Trace Analyzer (Service-Focused)")

with st.sidebar:
    st.header("Configuration")

    env_key = os.getenv("OPENAI_API_KEY", "")
    ui_key = st.text_input("OpenAI API Key (optional override)", type="password", value="")
    api_key = (ui_key.strip() or env_key.strip())

    model = st.text_input("Model", value="gpt-5.2")
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.3, step=0.05)

    st.divider()

    raw_services = st.text_input("TARGET_SERVICES (comma-separated)", value="freeswitch,tai6-manager")
    target_services = parse_target_services(raw_services)

    context = st.slider("Context lines (+/- around each match)", 0, 200, 40, 10)
    max_filtered_lines = st.number_input("Max filtered lines safeguard", min_value=100, max_value=200000, value=20000, step=1000)
    chunk_size = st.number_input("Chunk size (characters)", min_value=2000, max_value=100000, value=20000, step=1000)

    st.divider()

    with st.expander("Advanced: prompt template (Pass 1)", expanded=False):
        prompt_template = st.text_area("Prompt template", value=DEFAULT_PROMPT_TEMPLATE, height=380)

uploaded = st.file_uploader("Upload a journalctl export file (text)", type=["log", "txt", "out", "journal"])
if not uploaded:
    st.info("Upload a journalctl file to begin.")
    st.stop()

raw_bytes = uploaded.read()
try:
    text = raw_bytes.decode("utf-8", errors="replace")
except Exception:
    text = raw_bytes.decode(errors="replace")

lines = text.splitlines()

col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("Input stats")
    st.write(f"- Total lines: **{len(lines):,}**")
    st.write(f"- TARGET_SERVICES: **{', '.join(target_services) if target_services else '(none)'}**")

filtered_lines, hits = filter_lines_with_context(
    lines=lines,
    target_services=target_services,
    context=context,
    max_lines=int(max_filtered_lines),
)

with col2:
    st.subheader("Filtered stats")
    st.write(f"- Direct matches (hits): **{hits:,}**")
    st.write(f"- Filtered lines (with context): **{len(filtered_lines):,}**")

st.subheader("Filtered preview")
preview = "\n".join(filtered_lines[:200])
st.code(preview if preview else "(no matching lines found)", language="text")

if not api_key:
    st.error("No OpenAI API key found. Set OPENAI_API_KEY in the environment or provide an override key in the sidebar.")
    st.stop()

if not target_services:
    st.error("Please provide at least one target service (comma-separated).")
    st.stop()

analyze = st.button("Analyze", type="primary")
if not analyze:
    st.stop()

# Build filtered text for analysis
filtered_text = "\n".join(filtered_lines).strip()
if not filtered_text:
    st.warning("No relevant lines were found for the selected TARGET_SERVICES.")
    st.stop()

cfg = OpenAIConfig(api_key=api_key, model=model.strip(), temperature=float(temperature))
client = OpenAI(api_key=cfg.api_key)

chunks = chunk_text_by_chars(filtered_text, int(chunk_size))

st.subheader("Analysis progress")
progress = st.progress(0)
status = st.empty()

chunk_outputs = []
total_steps = len(chunks) + 1  # +1 for synthesis

# Pass 1: chunk analyses
for idx, chunk in enumerate(chunks, start=1):
    status.write(f"Pass 1/2 — analyzing chunk {idx}/{len(chunks)} ...")
    prompt = prompt_template.format(
        target_services=target_services,
        log_text=chunk,
    )
    out = call_openai_responses(client, cfg.model, cfg.temperature, prompt)
    chunk_outputs.append(out.strip())
    progress.progress(min(0.99, idx / total_steps))

# Pass 2: synthesis
status.write("Pass 2/2 — synthesizing final report ...")
joined = "\n\n---\n\n".join(
    f"Chunk {i+1} analysis:\n{chunk_outputs[i]}" for i in range(len(chunk_outputs))
)

synth_prompt = SYNTHESIS_PROMPT.format(
    target_services=target_services,
    chunk_analyses=joined,
)
final_report = call_openai_responses(client, cfg.model, cfg.temperature, synth_prompt).strip()
progress.progress(1.0)
status.write("Done ✅")

st.divider()

tabs = st.tabs(["Final report", "Chunk analyses", "Download"])

with tabs[0]:
    st.subheader("Final report")
    st.markdown(final_report if final_report else "(empty)")

with tabs[1]:
    st.subheader("Chunk analyses")
    for i, out in enumerate(chunk_outputs, start=1):
        with st.expander(f"Chunk {i}"):
            st.markdown(out if out else "(empty)")

with tabs[2]:
    st.subheader("Download")
    md = f"# Journalctl Trace Analysis\n\n## Target services\n- " + "\n- ".join(target_services) + "\n\n---\n\n" + final_report
    st.download_button(
        label="Download report as Markdown",
        data=md.encode("utf-8"),
        file_name="journalctl_trace_report.md",
        mime="text/markdown",
    )
