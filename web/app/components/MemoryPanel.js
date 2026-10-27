"use client";

import { useEffect, useState } from "react";
import {
  correctMemory,
  downloadDataUrl,
  forgetEverything,
  forgetMemory,
  getMemories,
  getRetrieval,
  withdrawConsent,
} from "../../lib/api";

// FR-6/FR-7 (design brief §3.2, §11): what's remembered and why, plus the governance actions.
export default function MemoryPanel({ customer, lastMessageId }) {
  const [memories, setMemories] = useState([]);
  const [used, setUsed] = useState([]);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    if (!customer) return;
    setLoading(true);
    try {
      const res = await getMemories(customer.id);
      setMemories(res.memories);
    } catch (err) {
      setNote("Could not load memories right now.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    setUsed([]);
  }, [customer]);

  useEffect(() => {
    if (!customer || !lastMessageId) return;
    getRetrieval(lastMessageId, customer.id)
      .then((res) => setUsed(res.memories))
      .catch(() => setUsed([]));
  }, [lastMessageId, customer]);

  async function runAction(fn, label) {
    try {
      await fn();
      setNote(`${label}: done.`);
      refresh();
    } catch (err) {
      setNote(`${label}: failed.`);
    }
  }

  async function handleWithdrawConsent() {
    try {
      await withdrawConsent(customer.id);
      // No future chat turn will write a memory from here on (I6, enforced server-side in
      // write_path.has_consent()) -- existing memories are untouched, so this panel stays as-is.
      setNote("Consent withdrawn. Nothing new will be remembered from here on.");
    } catch (err) {
      setNote("Withdraw consent: failed.");
    }
  }

  if (!customer) return null;

  return (
    <aside className="memory-drawer panel" aria-label="What I remember about you">
      <h2>What I remember about you</h2>
      {note && <p className="inline-note">{note}</p>}
      <div className="toolbar">
        <button onClick={() => runAction(() => forgetEverything(customer.id), "Forget everything")}>
          Forget everything
        </button>
        <a href={downloadDataUrl(customer.id)} target="_blank" rel="noreferrer">
          Download my data
        </a>
        <button onClick={handleWithdrawConsent}>Withdraw consent</button>
      </div>

      {loading && <p>Loading…</p>}
      {!loading && memories.length === 0 && <p>Nothing remembered yet.</p>}
      {memories.map((m) => (
        <div className="memory-card" key={m.id}>
          <div className="meta">
            {m.type} · {m.category} · importance {m.importance} · confidence {m.confidence}
          </div>
          <div>{m.content}</div>
          {m.source_quote && (
            <div className="source">
              from your message on {m.source_date?.slice(0, 10)}: "{m.source_quote}"
            </div>
          )}
          <div className="actions">
            <button onClick={() => runAction(() => correctMemory(m.id, customer.id), "That's wrong")}>
              That's wrong
            </button>
            <button onClick={() => runAction(() => forgetMemory(m.id, customer.id), "Forget this")}>
              Forget this
            </button>
          </div>
        </div>
      ))}

      <h3>Memories used for this answer</h3>
      {used.length === 0 && <p>None yet — send a message first.</p>}
      {used.map((m) => (
        <div className="memory-card" key={m.id}>
          <div className="meta">{m.category} · score {Number(m.score).toFixed(2)}</div>
          <div>{m.content}</div>
        </div>
      ))}
    </aside>
  );
}
