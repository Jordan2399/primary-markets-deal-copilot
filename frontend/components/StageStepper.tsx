import type { Stage } from "@/lib/types";

/**
 * The deal's journey from mandate to booking as a row of steps: finished, current, still to come.
 * The state is also written as text for screen readers, not only shown with colour.
 */
export default function StageStepper({ stages, currentPosition, complete }: { stages: Stage[]; currentPosition: number; complete: boolean }) {
  return (
    <ol className="stepper" aria-label="Deal stages">
      {stages.map((stage) => {
        // A finished deal has passed every stage, including the last one.
        const done = complete || stage.position < currentPosition;
        const current = !complete && stage.position === currentPosition;
        return (
          <li key={stage.code} className={done ? "done" : current ? "current" : ""} aria-current={current ? "step" : undefined}>
            <span className="step-dot" aria-hidden="true">{done ? "✓" : stage.position}</span>
            <span className="step-name">{stage.name}</span>
            <span className="sr-only">{done ? " (done)" : current ? " (current)" : " (to do)"}</span>
          </li>
        );
      })}
    </ol>
  );
}
