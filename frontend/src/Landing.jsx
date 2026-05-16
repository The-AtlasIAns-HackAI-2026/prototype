import { Headphones, RadioTower, Search } from "lucide-react";
import { useState } from "react";
import { sendChat } from "./api.js";

export default function Landing() {
  const [message, setMessage] = useState("Ch7al taman l-maticha lyoum f Casablanca?");
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
        <p className="eyebrow">Moulcyber</p>
        <h1>معلومة f telephone — بلا internet</h1>
        <p className="lead">
          سول على الطقس، الثمن، الأخبار، ولا أي معلومة. Moulcyber كيرد عليك
          بدارجة مفهومة فالتليفون.
        </p>
        <div className="signal-row" dir="ltr">
          <span>
            <PhoneBadge /> +1 775 406 0061
          </span>
          <span>Twilio + LiveKit + Gemini Live</span>
        </div>
      </div>

      <div className="demo-panel">
        <div className="panel-title">
          <Search size={18} />
          <span>جرب الجواب</span>
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
