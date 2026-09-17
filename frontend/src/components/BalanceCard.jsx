export default function BalanceCard({
  label = "Available balance",
  amount,
  currency = "XAF",
  hidden = false,
  onToggleHide,
  chip,
  meta,
  onAdd,
  onSend,
  addLabel = "+ Add money",
  sendLabel = "Send",
}) {
  return (
    <div className="balance-card">
      <div className="balance-label">{label}</div>
      <div className="balance-row">
        <div className="balance-amount">
          {hidden ? "••••••" : amount}
          {!hidden && <span className="balance-cur">{currency}</span>}
        </div>
        {onToggleHide && (
          <button type="button" className="balance-eye" aria-label={hidden ? "Show balance" : "Hide balance"} onClick={onToggleHide}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {hidden ? (
                <>
                  <path d="M3 3l18 18" />
                  <path d="M10.6 10.6a2 2 0 002.8 2.8" />
                  <path d="M9.9 5.1A10.4 10.4 0 0112 5c6.5 0 10 7 10 7a17.4 17.4 0 01-3.2 4.1" />
                  <path d="M6.1 6.1A17.5 17.5 0 002 12s3.5 7 10 7c1.4 0 2.7-.3 3.9-.7" />
                </>
              ) : (
                <>
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
                  <circle cx="12" cy="12" r="3" />
                </>
              )}
            </svg>
          </button>
        )}
      </div>
      {(chip || meta) && (
        <div className="balance-meta">
          {chip && <span className="account-chip">{chip}</span>}
          {meta && <span>{meta}</span>}
        </div>
      )}
      {(onAdd || onSend) && (
        <div className="balance-actions">
          {onAdd && (
            <button type="button" className="add" onClick={onAdd}>
              {addLabel}
            </button>
          )}
          {onSend && (
            <button type="button" className="send" onClick={onSend}>
              {sendLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
