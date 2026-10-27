"use client";

import { useState } from "react";
import { endConversation, sendChat } from "../../lib/api";

// The system prompt tells the model to reply in plain text, but free-tier models don't always
// comply -- strip stray markdown so a slip-up never reaches the chat bubble as literal asterisks.
function stripMarkdown(text) {
  return text.replace(/\*\*/g, "").replace(/^[ \t]*\*[ \t]+/gm, "- ");
}

export default function ChatWindow({ customer, consented, messages, setMessages, onReplyMessageId }) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const customerId = consented ? customer?.id : null; // I6: no consent -> no customer_id -> no memory write
      const res = await sendChat(text, customerId);
      setMessages((prev) => [...prev, { role: "assistant", content: stripMarkdown(res.reply) }]);
      if (res.message_id) onReplyMessageId(res.message_id);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, something went wrong." }]);
    } finally {
      setSending(false);
    }
  }

  async function handleNewChat() {
    setMessages([]);
    if (customer) {
      try {
        await endConversation(customer.id);
      } catch (err) {
        // best-effort; a stale conversation thread is cosmetic, never blocks chat (I3)
      }
    }
  }

  return (
    <div className="chat-column panel">
      <div className="toolbar">
        <strong>{customer ? `Chatting as ${customer.display_name}` : "Pick a shopper above"}</strong>
        <button onClick={handleNewChat} disabled={!customer}>
          New chat
        </button>
      </div>
      <div className="chat-log" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          aria-label="Message"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={customer ? "Ask about a coffee..." : "Pick a shopper first"}
          disabled={!customer || sending}
        />
        <button type="submit" disabled={!customer || sending}>
          Send
        </button>
      </form>
    </div>
  );
}
