// Screenshot tray: the document's saved screenshots (dragged boxes and pasted images). Click picks one,
// Shift+click adds or removes; T reads the picked ones; a thumbnail can be dragged onto a card's field.
import type { Source } from "./api";
import { SHOT_TYPE } from "./figure";

export function ShotTray(p: {
  shots: Source[]; // newest first
  picked: string[];
  reading: Set<string>; // being transcribed
  onPick(id: string, shift: boolean): void;
  onDelete(id: string): void;
}) {
  if (!p.shots.length) return null;
  return (
    <div className="tray" aria-label="Screenshots">
      {p.shots.map((s) => (
        <div
          key={s.id}
          className={`shot${p.picked.includes(s.id) ? " picked" : ""}`}
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData(SHOT_TYPE, s.id);
            e.dataTransfer.effectAllowed = "copy";
          }}
          onClick={(e) => p.onPick(s.id, e.shiftKey)}
          title={`${s.kind === "region" ? "Figure" : "Pasted image"} on p.${s.page}${s.text ? " (read)" : ""} · click to pick, Shift+click to add · drag onto a card`}
        >
          <img src={`/api/sources/${s.id}/image`} alt="" draggable={false} />
          <span className="shot-label">
            p.{s.page} {p.reading.has(s.id) ? "…" : s.text ? "✓" : ""}
          </span>
          <button
            className="shot-delete"
            title="Remove this screenshot"
            onClick={(e) => {
              e.stopPropagation();
              p.onDelete(s.id);
            }}
          >
            ×
          </button>
        </div>
      ))}
      <span className="muted tray-hint">
        <kbd>T</kbd> read picked · <kbd>Shift+T</kbd> read again · drag onto a card
      </span>
    </div>
  );
}
