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
            <tr key={m.config_id}>
              <td>{m.config_id}</td>
              <td>{m.model}</td>
              <td>{m.temperature}</td>
              <td>{m.fix_applied ? "yes" : "no"}</td>
              <td className={m.success ? "pass" : "fail"}>
                {m.success ? "PASS" : "FAIL"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
