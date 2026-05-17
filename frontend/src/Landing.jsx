import { Headphones, RadioTower, Search } from "lucide-react";
import { useState } from "react";
import { sendChat } from "./api.js";

export default function Landing() {
  const [message, setMessage] = useState("Chno kaygol qanoun lmaghribi 3la l7adana ba3d talaq?");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submitDemo(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await sendChat(message, "darija");
      setAnswer(data.response);
    } catch {
      setError("API ma jawbatch daba.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="landing" dir="rtl">
      <div className="hero-copy">
        <p className="eyebrow">Moulcyber Legal Hotline</p>
        <h1>قانون مغربي f telephone</h1>
        <p className="lead">
          سول على الأسرة، الجنائي، المسطرة المدنية، الدستور، الضرائب، ولا شكاية.
          Moulcyber كيرجع للوثائق وكيجاوبك بمصادر مختصرة.
        </p>
        <div className="signal-row" dir="ltr">
          <span>
            <PhoneBadge /> +1 775 406 0061
          </span>
          <span>Legal RAG + LiveKit + MCP</span>
        </div>
      </div>

      <div className="demo-panel">
        <div className="panel-title">
          <Search size={18} />
          <span>جرب triage</span>
        </div>
        <form onSubmit={submitDemo}>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            rows={4}
            aria-label="Demo question"
          />
          <button type="submit" disabled={loading}>
            {loading ? "Kay9elleb..." : "Sift"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        {answer && <p className="answer">{answer}</p>}
        <div className="feature-grid">
          <span>
            <Headphones size={16} /> Voice
          </span>
          <span>
            <RadioTower size={16} /> 2G
          </span>
        </div>
      </div>
    </section>
  );
}

function PhoneBadge() {
  return <span className="phone-dot" aria-hidden="true" />;
}
