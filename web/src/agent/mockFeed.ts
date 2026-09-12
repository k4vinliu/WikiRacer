import type { Pair } from "../lib/pairs";
import type { AgentEvent, AgentFeed } from "./types";
import type { FeedHandle } from "./sseFeed";

/** Scripted hops. These four were verified 2026-09-12 against action=parse
 *  HTML (title present as a /wiki/ article href): Cat→Ancient Egypt→Napoleon,
 *  Banana→Africa→Jazz, Bicycle→Coventry→William Shakespeare,
 *  Umbrella→Japan→Tsunami. The rest still follow §5.4 named hubs but were
 *  not fully confirmed (a later 429 stopped the sweep). */
type Hop = { to: string; anchor: string; reason: string };

const ROUTES: Record<string, Hop[]> = {
  "Cat>Napoleon": [
    { to: "Ancient Egypt", anchor: "Ancient Egypt", reason: "Cats were sacred in Egypt — a broad ancient hub." },
    { to: "Napoleon", anchor: "Napoleon", reason: "Napoleon invaded Egypt; the target is on the page." },
  ],
  "Chess>Antarctica": [
    { to: "Russia", anchor: "Russia", reason: "Chess is a national sport of Russia — a geographic hub." },
    { to: "Antarctica", anchor: "Antarctica", reason: "Russian Antarctic stations put the target on the page." },
  ],
  "Honey>Saturn": [
    { to: "Bee", anchor: "bees", reason: "Honey is made by bees; bees open biology and mythology." },
    { to: "Saturn", anchor: "Saturn", reason: "Saturn is named for a Roman god also tied to agriculture." },
  ],
  "Tea>Basketball": [
    { to: "United States", anchor: "United States", reason: "Tea culture plus a large country hub." },
    { to: "Basketball", anchor: "basketball", reason: "Basketball was invented in the United States." },
  ],
  "Banana>Jazz": [
    { to: "Africa", anchor: "Africa", reason: "Bananas originated in the tropics; Africa is the named hub." },
    { to: "Jazz", anchor: "jazz", reason: "Jazz has deep African roots." },
  ],
  "Guitar>Albert Einstein": [
    { to: "United States", anchor: "United States", reason: "The modern guitar's popular history runs through the US." },
    { to: "Albert Einstein", anchor: "Albert Einstein", reason: "Einstein emigrated to the United States." },
  ],
  "Bicycle>William Shakespeare": [
    { to: "Coventry", anchor: "Coventry", reason: "Coventry was a British bicycle-manufacturing centre." },
    { to: "William Shakespeare", anchor: "William Shakespeare", reason: "Shakespeare is a hop from English cities." },
  ],
  "Sushi>Volcano": [
    { to: "Japan", anchor: "Japan", reason: "Sushi is Japanese; Japan is a volcanic archipelago." },
    { to: "Volcano", anchor: "volcanoes", reason: "Japan sits on the Ring of Fire." },
  ],
  "Umbrella>Tsunami": [
    { to: "Japan", anchor: "Japan", reason: "The folding umbrella's modern form is tied to Japan." },
    { to: "Tsunami", anchor: "tsunami", reason: "Japan is the type-case for tsunami science." },
  ],
  "Pizza>Mars": [
    { to: "Italy", anchor: "Italy", reason: "Pizza is Neapolitan; Italy is the country hub." },
    { to: "Mars", anchor: "Mars", reason: "Roman mythology: Mars is the namesake planet." },
  ],
  "Waffle>Tornado": [
    { to: "United States", anchor: "United States", reason: "American waffle houses open a US hub." },
    { to: "Tornado", anchor: "tornado", reason: "Tornado Alley is in the United States." },
  ],
  "Violin>Glacier": [
    { to: "Italy", anchor: "Italy", reason: "The violin was born in northern Italy." },
    { to: "Alps", anchor: "Alps", reason: "Italy meets the Alps — then ice." },
    { to: "Glacier", anchor: "glacier", reason: "Alpine ice is a glacier." },
  ],
  "Coffee>Mount Everest": [
    { to: "Ethiopia", anchor: "Ethiopia", reason: "Coffee's origin story starts in Ethiopia." },
    { to: "Himalayas", anchor: "Himalayas", reason: "A mountain-range hub toward the target." },
    { to: "Mount Everest", anchor: "Mount Everest", reason: "Everest is the Himalaya's highest peak." },
  ],
  "Chocolate>Samurai": [
    { to: "Mexico", anchor: "Mexico", reason: "Cacao is Mesoamerican." },
    { to: "Japan", anchor: "Japan", reason: "A country hop toward feudal Japan." },
    { to: "Samurai", anchor: "samurai", reason: "Samurai is the Japanese warrior class." },
  ],
  "Origami>Submarine": [
    { to: "Japan", anchor: "Japan", reason: "Origami is Japanese paper folding." },
    { to: "World War II", anchor: "World War II", reason: "A 20th-century hub with naval articles." },
    { to: "Submarine", anchor: "submarine", reason: "WWII popularized the modern submarine." },
  ],
  "Pencil>Kangaroo": [
    { to: "Graphite", anchor: "graphite", reason: "Pencils write with graphite." },
    { to: "Australia", anchor: "Australia", reason: "Australia is a major graphite and wildlife hub." },
    { to: "Kangaroo", anchor: "kangaroo", reason: "Kangaroos are Australian macropods." },
  ],
  "Lighthouse>Dinosaur": [
    { to: "United Kingdom", anchor: "United Kingdom", reason: "British lighthouse boards are a country hub." },
    { to: "Fossil", anchor: "fossil", reason: "A science hop toward paleontology." },
    { to: "Dinosaur", anchor: "dinosaur", reason: "Dinosaurs are known from fossils." },
  ],
  "Soap>Jupiter": [
    { to: "Chemistry", anchor: "chemistry", reason: "Saponification is chemistry." },
    { to: "Planet", anchor: "planet", reason: "A solar-system hub." },
    { to: "Jupiter", anchor: "Jupiter", reason: "Jupiter is the largest planet." },
  ],
  "Bread>Black hole": [
    { to: "Wheat", anchor: "wheat", reason: "Bread is made from cereal grain." },
    { to: "Physics", anchor: "physics", reason: "A field hub toward astrophysics." },
    { to: "Black hole", anchor: "black hole", reason: "Black holes are a physics topic." },
  ],
  "Penguin>Sahara": [
    { to: "Antarctica", anchor: "Antarctica", reason: "Most penguins live on the Southern Ocean rim." },
    { to: "Africa", anchor: "Africa", reason: "A continental hop north." },
    { to: "Sahara", anchor: "Sahara", reason: "The Sahara is in North Africa." },
  ],
};

function routeKey(pair: Pair): string {
  return `${pair.start}>${pair.target}`;
}

export function hopsFor(pair: Pair): Hop[] {
  return ROUTES[routeKey(pair)] ?? [
    { to: pair.target, anchor: pair.target, reason: "No scripted route — stepping toward the target." },
  ];
}

export function mockFeed(pair: Pair, speed = 1): FeedHandle {
  let go!: () => void;
  const whenGo = new Promise<void>((resolve) => {
    go = resolve;
  });
  const timers: ReturnType<typeof setTimeout>[] = [];
  let seq = 1;

  const feed: FeedHandle = {
    async arm() {
      /* mock is ready locally; no server */
    },
    subscribe(on: (e: AgentEvent) => void) {
      let cancelled = false;
      const emit = (e: AgentEvent) => {
        if (!cancelled) on(e);
      };

      queueMicrotask(() => {
        emit({
          seq: seq++,
          t: "ready",
          at: 0,
          session_id: "mock",
          live_url: "",
        });
      });

      void whenGo.then(() => {
        if (cancelled) return;
        const hops = hopsFor(pair);
        let from = pair.start;
        let at = 0;
        hops.forEach((hop, i) => {
          const currentFrom = from;
          const thinkAt = at + 700 / speed;
          const pickAt = thinkAt + 350 / speed;
          const arriveAt = pickAt + 1400 / speed;
          timers.push(
            setTimeout(() => {
              emit({
                seq: seq++,
                t: "thinking",
                at: thinkAt,
                article: currentFrom,
                n_candidates: pair.fanout,
              });
            }, thinkAt),
          );
          timers.push(
            setTimeout(() => {
              emit({
                seq: seq++,
                t: "pick",
                at: pickAt,
                from: currentFrom,
                to: hop.to,
                anchor_text: hop.anchor,
                reason: hop.reason,
                was_fallback: false,
              });
            }, pickAt),
          );
          const landed = hop.to;
          const hopN = i + 1;
          timers.push(
            setTimeout(() => {
              emit({
                seq: seq++,
                t: "arrive",
                at: arriveAt,
                article: landed,
                hop: hopN,
              });
            }, arriveAt),
          );
          from = landed;
          at = arriveAt;
        });
        const doneAt = at + 40 / speed;
        timers.push(
          setTimeout(() => {
            emit({
              seq: seq++,
              t: "done",
              at: doneAt,
              reason: "won",
              hops: hops.length,
            });
          }, doneAt),
        );
      });

      return () => {
        cancelled = true;
        for (const t of timers) clearTimeout(t);
      };
    },
    async go() {
      go();
    },
    stop() {
      for (const t of timers) clearTimeout(t);
    },
  };

  return feed;
}

export type { AgentFeed };
