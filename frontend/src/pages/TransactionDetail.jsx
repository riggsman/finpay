import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { transactionsApi } from "../api/transactions";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function TransactionDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [txn, setTxn] = useState(null);
  const [events, setEvents] = useState([]);
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    transactionsApi.get(id).then(setTxn).catch((e) => setError(e.message));
    transactionsApi.events(id).then(setEvents).catch(() => {});
    transactionsApi.receipt(id).then(setReceipt).catch(() => setReceipt(null));
  }, [id]);

  if (error) {
    return (
      <div className="container">
        <div className="card mt"><div className="alert alert-error">{error}</div></div>
      </div>
    );
  }
  if (!txn) return <div className="container"><p className="muted mt">Loading…</p></div>;

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay</div>
        <button className="btn-ghost" onClick={() => navigate(-1)}>← Back</button>
      </div>

      <h1>{txn.type.replaceAll("_", " ")}</h1>
      <span className={`badge ${txn.status}`}>{txn.status}</span>

      <div className="grid mt">
        <div className="card">
          <h2>Details</h2>
          <div className="review-row"><span className="muted">Reference</span><span>{txn.reference}</span></div>
          <div className="review-row"><span className="muted">Amount</span><span>{money(txn.amount)} {txn.currency}</span></div>
          <div className="review-row"><span className="muted">Fee</span><span>{money(txn.fee)} {txn.currency}</span></div>
          <div className="review-row"><span className="muted">Total</span><span>{money(txn.amount + txn.fee)} {txn.currency}</span></div>
          {txn.description && <div className="review-row"><span className="muted">Description</span><span>{txn.description}</span></div>}
          {txn.provider_reference && <div className="review-row"><span className="muted">Provider ref</span><span>{txn.provider_reference}</span></div>}
          {txn.failure_reason && <div className="review-row"><span className="muted">Failure</span><span>{txn.failure_reason}</span></div>}
          <div className="review-row"><span className="muted">Created</span><span>{new Date(txn.created_at).toLocaleString()}</span></div>
          {txn.completed_at && <div className="review-row"><span className="muted">Completed</span><span>{new Date(txn.completed_at).toLocaleString()}</span></div>}
        </div>

        <div className="card">
          <h2>Timeline</h2>
          <div className="timeline">
            {events.map((e) => (
              <div className="timeline-item" key={e.id}>
                <span className="dotmark" />
                <div>
                  <div>{e.event_type.replaceAll("_", " ")}</div>
                  <div className="muted small">{new Date(e.created_at).toLocaleString()}</div>
                </div>
              </div>
            ))}
          </div>

          {receipt && (
            <>
              <h2 className="mt-lg">Receipt</h2>
              <div className="receipt">
                <div className="review-row"><span className="muted">Receipt</span><span>{receipt.receipt_number}</span></div>
                {receipt.customer && <div className="review-row"><span className="muted">Customer</span><span>{receipt.customer}</span></div>}
                {receipt.meter_number && <div className="review-row"><span className="muted">Meter</span><span>{receipt.meter_number}</span></div>}
                <div className="review-row total"><span>Total paid</span><span>{money(receipt.total)} {receipt.currency}</span></div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
