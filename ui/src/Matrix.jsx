import React from "react";

export default function Matrix({ matrix }) {
  return (
    <div className="panel matrix">
      <h2>Counterfactual success matrix</h2>
      <table>
        <thead>
          <tr>
            <th>config</th>
            <th>model</th>
            <th>temp</th>
            <th>fix</th>
            <th>result</th>
          </tr>
        </thead>
        <tbody>
          {matrix.map((m) => (
            <React.Fragment key={m.config_id}>
              <tr className={m.reason ? "no-border" : ""}>
                <td>{m.config_id}</td>
                <td>{m.model}</td>
                <td>{Number(m.temperature).toFixed(1)}</td>
                <td>{m.fix_applied ? <span className="badge badge-fix">FIX</span> : "—"}</td>
                <td>
                  <span className={`badge ${m.success ? "badge-pass" : "badge-fail"}`}>
                    {m.success ? "PASS" : "FAIL"}
                  </span>
                </td>
              </tr>
              {m.reason && (
                <tr className="reason-row">
                  <td colSpan={5}>
                    <span className="reason-label">Reason:</span> {m.reason}
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
