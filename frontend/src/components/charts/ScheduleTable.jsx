import React from 'react';

const CAD = (n) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(n);

export default function ScheduleTable({ schedule }) {
  return (
    <div className="schedule-table-wrap">
      <h4>Year-by-Year Schedule</h4>
      <div className="table-scroll">
        <table className="schedule-table">
          <thead>
            <tr>
              <th>Year</th>
              <th>Principal</th>
              <th>Interest</th>
              <th>Balance</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((row) => (
              <tr key={row.year}>
                <td>{row.year}</td>
                <td className="green">{CAD(row.principal_paid)}</td>
                <td className="red">{CAD(row.interest_paid)}</td>
                <td>{CAD(row.remaining_balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
