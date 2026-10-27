"use client";

import { useEffect, useState } from "react";
import { listCustomers } from "../lib/api";
import UserSwitcher from "./components/UserSwitcher";
import ConsentModal from "./components/ConsentModal";
import ChatWindow from "./components/ChatWindow";
import MemoryPanel from "./components/MemoryPanel";

function consentKey(customerId) {
  return `northbean:consent:${customerId}`;
}

export default function Home() {
  const [customers, setCustomers] = useState([]);
  const [customer, setCustomer] = useState(null);
  const [consented, setConsented] = useState(false);
  const [pendingConsent, setPendingConsent] = useState(null); // customer awaiting a Yes/No
  const [messages, setMessages] = useState([]);
  const [lastMessageId, setLastMessageId] = useState(null);

  useEffect(() => {
    listCustomers()
      .then((res) => setCustomers(res.customers))
      .catch(() => setCustomers([]));
  }, []);

  function handleSwitch(nextCustomer) {
    setCustomer(nextCustomer);
    setMessages([]);
    setLastMessageId(null);

    const stored = typeof window !== "undefined" ? window.localStorage.getItem(consentKey(nextCustomer.id)) : null;
    if (stored === "granted") {
      setConsented(true);
    } else if (stored === "declined") {
      setConsented(false);
    } else {
      setPendingConsent(nextCustomer);
    }
  }

  function handleConsentDecision(granted) {
    const target = pendingConsent;
    setPendingConsent(null);
    setConsented(granted);
    if (target && typeof window !== "undefined") {
      window.localStorage.setItem(consentKey(target.id), granted ? "granted" : "declined");
    }
  }

  return (
    <>
      <header className="topbar">
        <h1>Northbean Coffee</h1>
        <nav>
          <a href="/ops">Ops dashboard</a>
        </nav>
      </header>
      <main className="layout">
        <div className="chat-column">
          <UserSwitcher customers={customers} currentId={customer?.id} onSwitch={handleSwitch} />
          <ChatWindow
            customer={customer}
            consented={consented}
            messages={messages}
            setMessages={setMessages}
            onReplyMessageId={setLastMessageId}
          />
        </div>
        <MemoryPanel customer={consented ? customer : null} lastMessageId={lastMessageId} />
      </main>
      {pendingConsent && (
        <ConsentModal customerName={pendingConsent.display_name} onDecide={handleConsentDecision} />
      )}
    </>
  );
}
