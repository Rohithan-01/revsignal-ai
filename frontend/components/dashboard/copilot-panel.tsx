"use client";

import { useState, type FormEvent } from "react";
import { ArrowUp, Bot, Sparkles } from "lucide-react";
import { useRevenueData } from "@/components/data-provider";
import { formatCompactCurrency, isOpenStatus } from "@/lib/formatters";

const prompts = [
  "Which deals need attention today?",
  "Why is my pipeline at risk?",
  "Which deals have the highest value at risk?",
  "What actions should my team prioritize?",
];

export function CopilotPanel() {
  const { deals, metrics, source } = useRevenueData();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (source !== "demo" || !question.trim()) return;
    const openDeals = deals.filter((deal) => isOpenStatus(deal.status));
    const highRisk = openDeals.filter((deal) => deal.risk_level === "HIGH");
    const topDeal = [...openDeals].sort((a, b) => b.risk_score - a.risk_score)[0];
    const text = question.toLowerCase();
    if (text.includes("highest value") || text.includes("value at risk")) {
      setAnswer(`In this sample dataset, ${formatCompactCurrency(metrics.revenue_high_risk)} is associated with ${highRisk.length} high-risk open deals.`);
    } else if (text.includes("why") || text.includes("pipeline")) {
      setAnswer(`The sample pipeline has ${metrics.deals_needing_attention} open deals with medium or high rule-based risk. ${topDeal ? `${topDeal.account_name} has the highest current sample score (${topDeal.risk_score}/100).` : ""}`);
    } else if (text.includes("action") || text.includes("prioritize")) {
      setAnswer(topDeal ? `Sample next step for ${topDeal.account_name}: ${topDeal.recommended_action}` : "Import deals to see suggested next steps.");
    } else {
      setAnswer(topDeal ? `${topDeal.account_name} is the highest-risk open sample deal at ${topDeal.risk_score}/100. ${topDeal.risk_reasons[0] || ""}` : "Import deals to explore sample risk signals.");
    }
  }

  return (
    <section className="panel copilot-panel">
      <div className="copilot-header">
        <div className="copilot-orb"><span /><Bot size={17} /></div>
        <div><span className="copilot-eyebrow">REVSIGNAL COPILOT</span><h2>Understand your pipeline.</h2></div>
      </div>
      {source === "demo" ? (
        <>
          <p className="copilot-description">Explore illustrative insights from the sample deals.</p>
          {answer && <div className="copilot-answer" role="status"><span>Sample demo insight · not AI-generated</span><p>{answer}</p></div>}
          <div className="copilot-prompts">{prompts.map((prompt) => <button key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div>
          <form className="copilot-input" onSubmit={submitQuestion}>
            <input aria-label="Ask about sample deals" placeholder="Ask about your risky deals…" value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button aria-label="Get sample insight" disabled={!question.trim()}><ArrowUp size={15} /></button>
          </form>
          <div className="copilot-mode-note"><Sparkles size={12} /> Demo responses are illustrative and rule-based.</div>
        </>
      ) : (
        <>
          <p className="copilot-description">Ask about your pipeline and risk signals.</p>
          <div className="copilot-offline"><Bot size={15} /><span>Conversational AI is not connected. Review deal evidence and recommendations for live, data-backed insights.</span></div>
          <div className="copilot-prompts copilot-prompts-disabled">{prompts.map((prompt) => <button key={prompt} disabled title="A conversational AI endpoint is not implemented">{prompt}</button>)}</div>
          <form className="copilot-input">
            <input aria-label="Ask about your deals" placeholder="Chat is not connected" disabled />
            <button aria-label="Chat is not connected" disabled><ArrowUp size={15} /></button>
          </form>
          <div className="copilot-mode-note"><Sparkles size={12} /> No generated answers are shown for live data.</div>
        </>
      )}
    </section>
  );
}
