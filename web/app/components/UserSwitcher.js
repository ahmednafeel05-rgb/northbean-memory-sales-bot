"use client";

export default function UserSwitcher({ customers, currentId, onSwitch }) {
  return (
    <div className="user-switcher" role="group" aria-label="Switch shopper">
      {customers.map((c) => (
        <button
          key={c.id}
          aria-pressed={c.id === currentId}
          onClick={() => onSwitch(c)}
        >
          {c.display_name}
        </button>
      ))}
    </div>
  );
}
