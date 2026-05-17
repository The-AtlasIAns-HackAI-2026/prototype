import {
  BookOpenText,
  ClipboardCheck,
  Gavel,
  Network,
  Route,
  ShieldAlert,
  Workflow,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  buildCasePacket,
  confirmOralApproval,
  fetchMockChikayaSubmissions,
  queryLegalRag,
  startOralApproval,
  submitMockChikaya,
  triageHotline,
} from "./api.js";

const initialComplaint = {
  first_name: "Yassine",
  last_name: "El Amrani",
  caller_phone: "+212600000000",
  topic:
    "I asked a public office for an administrative certificate three weeks ago and still have no clear written answer.",
  city: "Casablanca",
  category: "Administrative delay",
  desired_resolution: "I want the office to review my file and give me a written answer.",
  evidence: ["Appointment SMS", "Document receipt"],
  consent: false,
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
  const [casePacket, setCasePacket] = useState(null);
  const [approval, setApproval] = useState(null);
  const [spokenApproval, setSpokenApproval] = useState("mwafeq");
  const [recent, setRecent] = useState([]);
  const [workflow, setWorkflow] = useState([]);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [traceId] = useState(() => `web-hotline-${Date.now()}`);

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
      addWorkflow("MCP tool", "hotline_route_issue", "running");
      const data = await triageHotline(issue, "darija", { traceId });
      setTriage(data);
      addWorkflow(
        "A2A route",
        data.selected_expert?.id || "selected expert",
        "ok",
        `confidence ${Math.round((data.confidence || 0) * 100)}%`
      );
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
      addWorkflow("A2A master", "khadamati_legal_master", "running", "routing legal sector");
      addWorkflow("MCP tool", "legal_rag_retrieve", "running");
      const data = await queryLegalRag(legalQuestion, {
        language: "darija",
        topK: 4,
        useLlm: false,
        mergeRelatedSectors: true,
        traceId,
      });
      setRag(data);
      const first = data.results?.[0];
      addWorkflow(
        "Mini-agent",
        data.route?.agent_id || data.route?.sector,
        "ok",
        `${data.latency_ms} ms`
      );
      if (first?.primary_article) {
        addWorkflow("Article", first.primary_article, "ok", first.article_notice || "nearest");
      }
      if ((data.intervening_agents || []).length > 1) {
        addWorkflow("Merged agents", data.merge_strategy, "ok", `${data.intervening_agents.length} agents`);
      }
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
      addWorkflow("MCP tool", "mock_chikaya_submit", "running", "after oral approval");
      const data = await submitMockChikaya(complaint);
      setSubmission(data);
      addWorkflow("Execution", data.receipt_id || "blocked", data.submitted ? "ok" : "blocked");
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
        `${complaint.first_name} ${complaint.last_name}: ${complaint.topic}`
      );
      setApproval(data);
      addWorkflow("MCP tool", "approval_flow_start", "ok", data.approval_id);
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
      addWorkflow("MCP tool", "approval_flow_confirm", data.approved ? "ok" : "blocked", data.status);
      if (data.approved) {
        setComplaint((current) => ({ ...current, consent: true }));
      }
    } catch {
      setError("Approval confirmation ma kmlatch.");
    } finally {
      setLoading("");
    }
  }

  async function runCasePacket() {
    setLoading("case-packet");
    setError("");
    try {
      addWorkflow("MCP tool", "case_packet_build", "running", "handoff packet");
      const data = await buildCasePacket({
        topic: complaint.topic || legalQuestion || issue,
        first_name: complaint.first_name,
        last_name: complaint.last_name,
        callerPhone: complaint.caller_phone,
        caller_phone: complaint.caller_phone,
        city: complaint.city,
        traceId,
      });
      setCasePacket(data);
      addWorkflow("Case packet", data.packet_id, "ok", data.legal_anchor?.primary_article || "no article");
    } catch {
      setError("Case packet ma tbuildach daba.");
      addWorkflow("Case packet", "failed", "blocked");
    } finally {
      setLoading("");
    }
  }

  function updateComplaint(field, value) {
    setComplaint((current) => ({ ...current, [field]: value }));
  }

  function addWorkflow(stage, detail, status = "ok", meta = "") {
    setWorkflow((current) =>
      [
        {
          id: `${Date.now()}-${Math.random()}`,
          stage,
          detail,
          status,
          meta,
          at: new Date().toLocaleTimeString(),
        },
        ...current,
      ].slice(0, 10)
    );
  }

  return (
    <section className="hotline-lab">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Khadamati workflow lab</p>
          <h1>Legal and bureaucracy hotline</h1>
        </div>
        <Gavel size={24} />
      </div>

      <WorkflowPanel workflow={workflow} rag={rag} loading={loading} />

      <div className="lab-grid">
        <div className="demo-panel primary-panel">
          <div className="panel-title">
            <span>Article-first legal RAG</span>
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
              <button
                type="button"
                onClick={() =>
                  setLegalQuestion("Ila kayn 3onf bin zwj w talaq, wach lmawdo3 family law ola criminal law?")
                }
              >
                Family + criminal
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
              {rag.results?.[0]?.primary_article && (
                <div className="article-banner">
                  <strong>{rag.results[0].primary_article}</strong>
                  <span>
                    {rag.results[0].article_count > 1
                      ? `${rag.results[0].article_count} articles/fosoul detected; showing nearest first`
                      : "nearest detected article"}
                  </span>
                </div>
              )}
              {rag.answer && <p className="answer">{rag.answer}</p>}
              <ResultList
                title="Expert agents"
                items={(rag.intervening_agents || []).map(
                  (agent) => `${agent.display} · ${agent.agent_id}`
                )}
              />
              <ResultList
                title="Knowledge graph paths"
                items={(rag.knowledge_graph?.paths || []).map(
                  (path) => `${path.agent} → ${path.article || "article pending"} → ${path.chunk_id}`
                )}
              />
              <ResultList
                title="A2A trace"
                items={(rag.a2a_trace || []).map((step) => `${step.agent} → ${step.target} · ${step.action}`)}
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
            <span>Caller-phone execution</span>
            <ClipboardCheck size={18} />
          </div>
          <form onSubmit={runMockSubmit}>
            <div className="field-grid">
              <input
                value={complaint.first_name}
                onChange={(event) => updateComplaint("first_name", event.target.value)}
                aria-label="First name"
                placeholder="First name"
              />
              <input
                value={complaint.last_name}
                onChange={(event) => updateComplaint("last_name", event.target.value)}
                aria-label="Last name"
                placeholder="Last name"
              />
              <input
                value={complaint.caller_phone}
                onChange={(event) => updateComplaint("caller_phone", event.target.value)}
                aria-label="Caller phone"
                placeholder="Caller phone from call"
              />
              <input
                value={complaint.city}
                onChange={(event) => updateComplaint("city", event.target.value)}
                aria-label="City"
                placeholder="City if known"
              />
            </div>
            <textarea
              value={complaint.topic}
              onChange={(event) => updateComplaint("topic", event.target.value)}
              aria-label="Complaint topic"
              placeholder="Topic/problem"
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
            <button type="button" onClick={runCasePacket} disabled={loading === "case-packet"}>
              {loading === "case-packet" ? "Building packet..." : "Build case packet"}
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
          {casePacket && (
            <div className="result-stack">
              <div className="result-card strong">
                <span>{casePacket.packet_id}</span>
                <small>{casePacket.latency_ms} ms</small>
              </div>
              <ResultList
                title="Human handoff"
                items={[
                  `Expert: ${casePacket.workflow?.selected_expert?.label || "not routed"}`,
                  `Article: ${casePacket.legal_anchor?.primary_article || "not detected"}`,
                  `Action: ${casePacket.intake?.recommended_action || "review"}`,
                ]}
              />
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
            <span>{item.primary_article || item.chunk_id}</span>
            <small>
              {item.agent_label || item.sector} · {item.source_title} · pages {item.page_start}-{item.page_end} · {item.chunk_id}
            </small>
            {item.article_count > 1 && (
              <small>{item.article_count} detected articles, nearest shown first</small>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkflowPanel({ workflow, rag, loading }) {
  const active = Boolean(loading);
  return (
    <div className="workflow-panel">
      <div className="workflow-head">
        <span>
          <Workflow size={16} /> MCP + A2A workflow
        </span>
        <small>{active ? "Phone calls play hold music while tools run" : "Ready"}</small>
      </div>
      <div className="workflow-chips">
        <span className="chip on">channel:web demo</span>
        <span className="chip on">master:khadamati_legal_master</span>
        <span className={rag?.intervening_agents?.length ? "chip on" : "chip"}>
          {rag?.intervening_agents?.length
            ? `${rag.intervening_agents.length} expert agent${rag.intervening_agents.length > 1 ? "s" : ""}`
            : "mini-agent pending"}
        </span>
        <span className={rag?.results?.[0]?.primary_article ? "chip on" : "chip"}>
          {rag?.results?.[0]?.primary_article || "article pending"}
        </span>
        <span className={rag?.knowledge_graph?.paths?.length ? "chip on" : "chip"}>
          {rag?.knowledge_graph?.paths?.length ? "knowledge graph linked" : "graph pending"}
        </span>
      </div>
      {workflow.length ? (
        <div className="workflow-list">
          {workflow.map((event) => (
            <div className={`workflow-item ${event.status}`} key={event.id}>
              <strong>{event.stage}</strong>
              <span>{event.detail}</span>
              <small>{event.meta || event.at}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Run Legal RAG or oral approval to see the exact MCP/A2A path.</p>
      )}
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
