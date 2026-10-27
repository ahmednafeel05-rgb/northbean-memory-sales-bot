"use client";

// Design brief §11: consent prompt on first login. No = chat still works, nothing personalised
// is stored. S5 keeps this client-side (localStorage per customer) -- withdrawing consent after
// the fact is a separate S6 feature (§13 sprint table).
export default function ConsentModal({ customerName, onDecide }) {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Personalisation consent">
      <div className="modal">
        <h2>Remember you, {customerName}?</h2>
        <p>
          Northbean can remember your taste, brew method, and budget across visits so you don't
          have to repeat yourself. You can see, correct, or delete anything it remembers, any time.
        </p>
        <div className="actions">
          <button className="secondary" onClick={() => onDecide(false)}>
            No thanks
          </button>
          <button className="primary" onClick={() => onDecide(true)}>
            Yes, remember me
          </button>
        </div>
      </div>
    </div>
  );
}
