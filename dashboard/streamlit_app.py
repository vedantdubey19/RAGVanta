import csv
import io
import json
import os
from datetime import datetime
import httpx
import streamlit as st

st.set_page_config(page_title="RAGVanta · Security Lab", page_icon="◈", layout="wide")
st.markdown('''<style>
.stApp {background:#0b1020} [data-testid="stSidebar"] {background:#11182c}
h1,h2,h3 {letter-spacing:-.035em} .stMetric {border:1px solid #26334b;border-radius:12px;padding:16px}
[data-testid="stCaptionContainer"] {color:#9eabc1}
</style>''', unsafe_allow_html=True)
API = os.environ.get("RAGVANTA_API_URL", "http://127.0.0.1:8000")
TOKEN = os.environ.get("RAGVANTA_API_TOKEN", "")


def request(method, path, **kwargs):
    try:
        response = httpx.request(method, API + path, timeout=3600,
                                 headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            st.error(f"API {exc.response.status_code}: {exc.response.text[:300]}")
        else:
            st.error("API unavailable. Start the FastAPI service on port 8000.")
        st.stop()


def show_metrics(report):
    st.caption("Measured run · " + report["provider"] + " / " + report["model"] + " · " + report["retrieval"])
    for limitation in report["limitations"]:
        st.caption(limitation)
    rows = []
    for mode, values in report["metrics"].items():
        row = {"Mode": mode}
        for key in ("retrieval_exposure", "conditional_attack_success", "end_to_end_attack_success",
                    "legitimate_answer_success", "false_block"):
            metric = values[key]
            row[key.replace("_", " ")] = (f"{metric['numerator']}/{metric['denominator']} "
                f"({metric['rate']:.1%})" if metric["rate"] is not None else "Not exercised")
        row["p95 latency (ms)"] = values["latency_p95_ms"]
        row["incomplete"] = values["incomplete"]
        rows.append(row)
    st.dataframe(rows, hide_index=True, width="stretch")
    chart = [{"mode": mode, "attack success": values["end_to_end_attack_success"]["rate"],
              "legitimate answer success": values["legitimate_answer_success"]["rate"]}
             for mode, values in report["metrics"].items()]
    st.bar_chart(chart, x="mode", y=["attack success", "legitimate answer success"])


with st.sidebar:
    st.title("◈ RAGVanta")
    st.caption("ADVERSARIAL RAG SECURITY LAB")
    page = st.radio("Workspace", ["Overview", "Documents", "RAG Playground", "Attack Lab",
                                  "Defense Comparison", "Runs & Reports"])
    st.divider()
    health = request("GET", "/health")
    st.caption(f"Local operator · {health['provider']}")
    st.caption(f"Retrieval · {health['retrieval']}")
    if health["provider"] == "extractive":
        st.info("Offline extraction mode. Security results do not measure LLM robustness.")

st.title(page)
st.caption("Test the threats. Protect the intelligence.")
collections = request("GET", "/v1/collections")


def select_collection():
    if not collections:
        st.info("Create a synthetic document collection in Documents first.")
        st.stop()
    selected = st.selectbox("Collection", collections, format_func=lambda c: c["name"])
    return selected["id"]


if page == "Overview":
    st.markdown("### Evidence for safer document AI")
    st.write("Upload a test corpus, ask grounded questions, and compare controlled attacks before and after defenses.")
    runs = request("GET", "/v1/experiments")
    scenarios = request("GET", "/v1/scenarios")
    a, b, c = st.columns(3)
    a.metric("Collections", len(collections))
    b.metric("Versioned scenarios", len(scenarios))
    c.metric("Saved experiments", len(runs))
    if runs:
        show_metrics(request("GET", f"/v1/experiments/{runs[0]['id']}"))
    else:
        st.info("No runs yet. Metrics appear after an actual experiment.")
    st.markdown("**Workflow:** Documents → RAG Playground → Attack Lab → Defense Comparison → Export")

elif page == "Documents":
    with st.expander("Create collection", expanded=not collections):
        with st.form("collection"):
            name = st.text_input("Collection name", max_chars=100)
            if st.form_submit_button("Create collection") and name.strip():
                request("POST", "/v1/collections", json={"name": name})
                st.rerun()
    cid = select_collection()
    st.caption("Synthetic test data only · PDF/TXT · 10 MB · 50 PDF pages · 100 files per collection")
    with st.form("upload"):
        file = st.file_uploader("Upload test document", type=["pdf", "txt"])
        if st.form_submit_button("Ingest document") and file:
            with st.spinner("Extracting, chunking and indexing…"):
                result = request("POST", "/v1/documents", data={"collection_id": cid},
                                 files={"file": (file.name, file.getvalue(), file.type)})
            st.success(f"Ready: {result['chunks']} chunks across {result['pages']} pages")
    docs = request("GET", "/v1/documents", params={"collection_id": cid})
    st.dataframe(docs, width="stretch", hide_index=True)
    if docs:
        doc = st.selectbox("Preview document", docs, format_func=lambda d: d["filename"])
        with st.expander("Untrusted source chunks"):
            for chunk in request("GET", f"/v1/documents/{doc['id']}/chunks"):
                st.caption(f"{chunk['id']} · page {chunk['page']} · offsets {chunk['start']}–{chunk['end']}")
                st.code(chunk["text"], language=None)

elif page == "RAG Playground":
    cid = select_collection()
    with st.form("question"):
        mode = st.radio("Pipeline", ["protected", "baseline"], horizontal=True)
        top_k = st.slider("Retrieved chunks", 1, 5, 3)
        question = st.text_area("Question", max_chars=2000, placeholder="What is the return policy?")
        submit = st.form_submit_button("Ask RAG", type="primary")
    if submit and question.strip():
        with st.spinner("Retrieving evidence and generating answer…"):
            result = request("POST", "/v1/chat", json={"question": question, "collection_id": cid,
                                                       "mode": mode, "top_k": top_k})
        if result["blocked"]:
            st.warning(result["answer"])
        else:
            st.text(result["answer"])
        st.caption(f"{result['model']} · {result['latency_ms']} ms · trace {result['trace_id']}")
        st.dataframe(result["citations"], hide_index=True)
        with st.expander("Retrieval and defense trace"):
            st.json({k: result[k] for k in ("retrieved", "included_ids", "decisions", "output_reasons")})

elif page == "Attack Lab":
    st.write("Run paired baseline/protected cases against an isolated, synthetic corpus. Your document collections stay separate.")
    scenarios = request("GET", "/v1/scenarios")
    with st.form("experiment"):
        split = st.selectbox("Dataset split", ["development", "held_out"])
        offset = st.number_input("Starting scenario offset (for additional batches)", min_value=0, max_value=59, value=0)
        limit = st.slider("Scenarios (each runs in both modes)", 1, 50, 50)
        submitted = st.form_submit_button("Run comparison", type="primary")
    if submitted:
        with st.spinner("Running bounded experiment; live providers may take several minutes…"):
            report = request("POST", "/v1/experiments", json={"split": split, "limit": limit, "offset": offset})
        st.session_state["report"] = report
    report = st.session_state.get("report")
    if report:
        st.write(f"Run {report['id']} · {report['status']}")
        show_metrics(report)
        category = st.selectbox("Filter category", ["all"] + sorted({c["category"] for c in report["cases"]}))
        st.dataframe([c for c in report["cases"] if category == "all" or c["category"] == category], hide_index=True)
    with st.expander("Scenario catalog"):
        st.dataframe(scenarios, hide_index=True)

else:
    runs = request("GET", "/v1/experiments")
    if not runs:
        st.info("No runs yet. Start a comparison in Attack Lab.")
        st.stop()
    selected = st.selectbox("Experiment", runs, format_func=lambda r:
        f"{datetime.fromtimestamp(r['created']).strftime('%Y-%m-%d %H:%M')} · {r['status']} · {r['id'][:8]}")
    report = request("GET", f"/v1/experiments/{selected['id']}")
    show_metrics(report)
    st.dataframe(report["cases"], width="stretch", hide_index=True)
    st.download_button("Download JSON report", json.dumps(report, indent=2),
                       file_name=f"ragvanta-{report['id']}.json", mime="application/json")
    output = io.StringIO()
    fields = sorted({key for case in report["cases"] for key in case})
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(report["cases"])
    st.download_button("Download CSV cases", output.getvalue(),
                       file_name=f"ragvanta-{report['id']}.csv", mime="text/csv")
    with st.expander("Reproducibility metadata"):
        st.json({k: v for k, v in report.items() if k not in ("cases", "metrics")})
