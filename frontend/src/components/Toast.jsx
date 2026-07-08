export default function Toast({ msg, spinner }) {
  if (!msg) return null;
  return (
    <div className="toast open">
      <div className="toast-inner">
        {spinner && <div className="spinner" />}
        <span>{msg}</span>
      </div>
    </div>
  );
}
