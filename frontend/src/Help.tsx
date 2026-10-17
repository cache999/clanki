import { SHORTCUTS } from "./keys";

const pretty = (k: string) =>
  k
    .replace(/(^|\+)([a-z])$/, (_m, p, c: string) => p + c.toUpperCase())
    .replace("ArrowDown", "↓")
    .replace("ArrowUp", "↑");

export function Help({ onClose }: { onClose(): void }) {
  const groups = [...new Set(SHORTCUTS.map((s) => s.group))];
  return (
    <div className="overlay" onClick={onClose}>
      <div className="help" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Keyboard shortcuts">
        <h2>Keyboard shortcuts</h2>
        {groups.map((g) => (
          <section key={g}>
            <h3>{g}</h3>
            <table>
              <tbody>
                {SHORTCUTS.filter((s) => s.group === g).map((s) => (
                  <tr key={s.command}>
                    <td className="keys">
                      {s.keys.map((k) => (
                        <kbd key={k}>{pretty(k)}</kbd>
                      ))}
                    </td>
                    <td>{s.help}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
        <p className="muted">Shortcuts are off while you type in a field. Esc closes this.</p>
      </div>
    </div>
  );
}
