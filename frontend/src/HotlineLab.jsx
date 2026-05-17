import { BookOpenText, ClipboardCheck, Gavel, Network, Route, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import {
  confirmOralApproval,
  fetchMockChikayaSubmissions,
  queryLegalRag,
  startOralApproval,
  submitMockChikaya,
  triageHotline,
} from "./api.js";

const initialComplaint = {
  citizen_name: "Yassine El Amrani",
  phone: "+212600000000",
  city: "Casablanca",
  category: "Administrative delay",
  subject: "Delay in administrative certificate",
  description:
    "I submitted all required documents to a public office three weeks ago and did not receive any clear answer or receipt update.",
  desired_resolution: "I want the office to review my file and give me a written answer.",
  evidence: ["Appointment SMS", "Document receipt"],
  consent: true,
};

export default function HotlineLab() {
  const [issue, setIssue] = useState(
    "Jani istid3a mn lmahkama w bghit n3ref wach kayn deadline dyal الاستئناف."
  );
  const [legalQuestion, setLegalQuestion] = useState(
    "Chno kaygol qanoun lmaghribi 3la l7adana ba3d talaq?"
  );
  const [rag, setRag] = useState(null);
  const [triage, setTriage] = useState(null);
  const [complaint, setComplaint] = useState(initialComplaint);
  const [submission, setSubmission] = useState(null);
  const [approval, setApproval] = useState(null);
  const [spokenApproval, setSpokenApproval] = useState("mwafeq");
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    refreshSubmissions();
  }, []);

  async function refreshSubmissions() {
    try {
      const data = await fetchMockChikayaSubmissions();
      setRecent(data.submissions || []);
    } catch {
      setRecent([]);
    }
  }

  async function runTriage(event) {
    event.preventDefault();
    setLoading("triage");
    setError("");
    try {
      const data = await triageHotline(issue, "darija");
      setTriage(data);
    } catch {
      setError("Hotline engine ma jawbatch daba.");
    } finally {
      setLoading("");
    }
  }

  async function runLegalRag(event) {
    event.preventDefault();
    setLoading("rag");
    setError("");
    try {
      const data = await queryLegalRag(legalQuestion, { language: "darija", topK: 4, useLlm: false });
      setRag(data);
    } catch {
      setError("Legal RAG ma jawbch daba.");
    } finally {
      setLoading("");
    }
  }

  async function runMockSubmit(event) {
    event.preventDefault();
    setLoading("submit");
    setError("");
    try {
      const data = await submitMockChikaya(complaint);
      setSubmission(data);
      await refreshSubmissions();
    } catch {
      setError("Mock Chikaya submit ma kmlch.");
    } finally {
      setLoading("");
    }
  }

  async function runApprovalStart() {
    setLoading("approval-start");
    setError("");
    try {
      const data = await startOralApproval(
        "mock_chikaya_submit",
        `${complaint.subject} in ${complaint.city}: ${complaint.desired_resolution}`
      );
      setApproval(data);
    } catch {
      setError("Approval flow ma bdaach.");
    } finally {
      setLoading("");
    }
  }

  async function runApprovalConfirm() {
    if (!approval?.approval_id) {
      return;
    }
    setLoading("approval-confirm");
    setError("");
    try {
      const data = await confirmOralApproval(approval.approval_id, spokenApproval);
      setApproval((current) => ({ ...current, ...data }));
      if (data.approved) {
        setComplaint((current) => ({ ...current, consent: true }));
      }
    } catch {
      setError("Approval confirmation ma kmlatch.");
    } finally {
      setLoading("");
    }
  }

  function updateComplaint(field, value) {
    setComplaint((current) => ({ ...current, [field]: value }));
  }

  return (
    <section className="hotline-lab">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Legal AI Hotline</p>
          <h1>Moroccan Legal Hotline</h1>
        </div>
        <Gavel size={24} />
      </div>

      <div className="lab-grid">
        <div className="demo-panel primary-panel">
          <div className="panel-title">
            <span>Legal RAG answer</span>
            <BookOpenText size={18} />
          </div>
          <form onSubmit={runLegalRag}>
            <textarea
              value={legalQuestion}
              onChange={(event) => setLegalQuestion(event.target.value)}
              aria-label="Legal RAG question"
            />
            <div className="quick-row">
              <button
                type="button"
                onClick={() => setLegalQuestion("Chno kaygol qanoun lmaghribi 3la l7adana ba3d talaq?")}
              >
                Family law
              </button>
              <button
                type="button"
                onClick={() => setLegalQuestion("Chno l3o9oba dyal sari9a f lqanoun jinai?")}
              >
                Criminal law
              </button>
            </div>
            <button type="submit" disabled={loading === "rag"}>
              {loading === "rag" ? "Retrieving..." : "Ask legal RAG"}
            </button>
          </form>

          {rag && (
            <div className="result-stack">
              <div className="result-card strong">
                <span>{rag.route.legal_sector}</span>
                <small>{rag.latency_ms} ms · {rag.answer_model}</small>
              </div>
              {rag.answer && <p className="answer">{rag.answer}</p>}
              <ResultList
                title="A2A trace"
                items={(rag.a2a_trace || []).map((step) => `${step.agent} → ${step.target}`)}
              />
              <SourceList items={rag.results || []} />
            </div>
          )}
        </div>

        <div className="demo-panel">
          <div className="panel-title">
            <span>Master routing</span>
            <Route size={18} />
          </div>
          <form onSubmit={runTriage}>
            <textarea
              value={issue}
              onChange={(event) => setIssue(event.target.value)}
              aria-label="Citizen issue"
            />
            <button type="submit" disabled={loading === "triage"}>
              {loading === "triage" ? "Routing..." : "Route issue"}
            </button>
          </form>

          {triage && (
            <div className="result-stack">
              <div className="result-card strong">
                <span>{triage.selected_expert.label}</span>
                <small>Confidence {Math.round((triage.confidence || 0) * 100)}%</small>
              </div>
              <ResultList title="Next questions" items={triage.next_questions} />
              <ResultList title="Evidence checklist" items={triage.evidence_checklist} />
              <ResultList title="Missing fields" items={triage.missing_fields} />
              {triage.safety_notice && (
                <p className="notice">
                  <ShieldAlert size={16} /> {triage.safety_notice}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="demo-panel mock-site">
          <div className="panel-title">
            <span>Oral approval execution</span>
            <ClipboardCheck size={18} />
          </div>
          <form onSubmit={runMockSubmit}>
            <div className="field-grid">
              <input
                value={complaint.citizen_name}
                onChange={(event) => updateComplaint("citizen_name", event.target.value)}
                aria-label="Citizen name"
                placeholder="Citizen name"
              />
              <input
                value={complaint.phone}
                onChange={(event) => updateComplaint("phone", event.target.value)}
                aria-label="Phone"
                placeholder="Phone"
              />
              <input
                value={complaint.city}
                onChange={(event) => updateComplaint("city", event.target.value)}
                aria-label="City"
                placeholder="City"
              />
              <input
                value={complaint.category}
                onChange={(event) => updateComplaint("category", event.target.value)}
                aria-label="Category"
                placeholder="Category"
              />
            </div>
            <input
              value={complaint.subject}
              onChange={(event) => updateComplaint("subject", event.target.value)}
              aria-label="Subject"
              placeholder="Subject"
            />
            <textarea
              value={complaint.description}
              onChange={(event) => updateComplaint("description", event.target.value)}
              aria-label="Complaint description"
            />
            <textarea
              value={complaint.desired_resolution}
              onChange={(event) => updateComplaint("desired_resolution", event.target.value)}
              aria-label="Desired resolution"
            />
            <label className="consent-row">
              <input
                type="checkbox"
                checked={complaint.consent}
                onChange={(event) => updateComplaint("consent", event.target.checked)}
              />
              <span>Explicit mock submission consent</span>
            </label>
            <div className="approval-box">
              <button type="button" onClick={runApprovalStart} disabled={loading === "approval-start"}>
                {loading === "approval-start" ? "Preparing..." : "Start oral approval"}
              </button>
              {approval && (
                <>
                  <p className="muted">{approval.oral_prompt || approval.message}</p>
                  <input
                    value={spokenApproval}
                    onChange={(event) => setSpokenApproval(event.target.value)}
                    aria-label="Spoken approval"
                    placeholder="mwafeq"
                  />
                  <button
                    type="button"
                    onClick={runApprovalConfirm}
                    disabled={loading === "approval-confirm"}
                  >
                    {loading === "approval-confirm" ? "Confirming..." : "Confirm oral approval"}
                  </button>
                </>
              )}
            </div>
            <button type="submit" disabled={loading === "submit"}>
              {loading === "submit" ? "Submitting..." : "Submit mock complaint"}
            </button>
          </form>

          {submission && (
            <div className="result-stack">
              <div className="result-card strong">
                <span>{submission.submitted ? "Submitted" : "Blocked"}</span>
                <small>{submission.receipt_id || "Missing data"}</small>
              </div>
              <ResultList title="Execution steps" items={submission.steps} />
            </div>
          )}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="demo-panel recent-panel">
        <div className="panel-title">
          <span>MCP and execution audit</span>
          <Network size={18} />
        </div>
        {recent.length ? (
          <div className="audit-list">
            {recent.slice(0, 5).map((item) => (
              <div className="audit-item" key={item.receipt_id}>
                <strong>{item.receipt_id}</strong>
                <span>{item.subject}</span>
                <small>{item.city} · {item.category}</small>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No mock submissions yet.</p>
        )}
      </div>
    </section>
  );
}

function SourceList({ items = [] }) {
  if (!items.length) {
    return null;
  }

  return (
    <div className="result-card">
      <strong>Retrieved sources</strong>
      <div className="source-list">
        {items.map((item) => (
          <div className="source-item" key={item.chunk_id}>
            <span>{item.chunk_id}</span>
            <small>
              {item.source_title} · pages {item.page_start}-{item.page_end}
            </small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ResultList({ title, items = [] }) {
  if (!items.length) {
    return null;
  }

  return (
    <div className="result-card">
      <strong>{title}</strong>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
