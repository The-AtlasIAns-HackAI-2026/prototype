import "@elevenlabs/convai-widget-embed";
import { Headphones, PhoneCall, RadioTower } from "lucide-react";

export default function Demo() {
  const agentId = import.meta.env.VITE_ELEVENLABS_AGENT_ID || "";
  const showElevenLabsFallback =
    import.meta.env.VITE_SHOW_ELEVENLABS_WIDGET === "true" && agentId;

  return (
    <section className="demo" dir="ltr">
      <div className="section-heading">
        <div>
          <p className="eyebrow">LiveKit</p>
          <h1>Voice Demo</h1>
        </div>
        <PhoneCall size={24} />
      </div>

      <div className="callout">
        <strong>Phone number</strong>
        <span>+1 775 406 0061</span>
      </div>

      <div className="feature-grid">
        <span>
          <Headphones size={16} /> Gemini Live
        </span>
        <span>
          <RadioTower size={16} /> Twilio SIP
        </span>
      </div>

      <div className="widget-zone">
        {showElevenLabsFallback ? (
          <elevenlabs-convai
            agent-id={agentId}
            action-text="Talk to Khadamati"
            avatar-orb-color-1="#C1272D"
            avatar-orb-color-2="#1f8a70"
          />
        ) : (
          <p className="muted">Call the phone number to test the Khadamati LiveKit voice path.</p>
        )}
      </div>
    </section>
  );
}
