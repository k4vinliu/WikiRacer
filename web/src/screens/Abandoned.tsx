import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { TopNav } from "../components/TopNav";
import { dismissAbandoned } from "../state/gameStore";

export function Abandoned() {
  return (
    <div className="min-h-screen p-6 font-body">
      <TopNav />
      <div className="mt-16 flex justify-center">
        <Card tone="green" radius="hero" className="w-[min(630px,92vw)] p-10">
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight">
            race
            <br />
            abandoned
          </h1>
          <p className="mt-6 max-w-md text-lg leading-snug text-text-on-dark-muted">
            Reloading mid-race isn't supported. The agent session was asked to stop.
          </p>
          <div className="mt-10">
            <Pill variant="black" onClick={dismissAbandoned}>
              Back to setup
            </Pill>
          </div>
        </Card>
      </div>
    </div>
  );
}
