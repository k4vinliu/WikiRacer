import type { Difficulty, Pair } from "../agent/types";

export type { Pair };

export const PAIRS: Record<Difficulty, Pair[]> = {
  easy: [
    { start: "Cat", target: "Napoleon", hops: 2, fanout: 472 },
    { start: "Chess", target: "Antarctica", hops: 2, fanout: 537 },
    { start: "Honey", target: "Saturn", hops: 2, fanout: 419 },
    { start: "Tea", target: "Basketball", hops: 2, fanout: 415 },
    { start: "Banana", target: "Jazz", hops: 2, fanout: 414 },
    { start: "Guitar", target: "Albert Einstein", hops: 2, fanout: 349 },
    { start: "Bicycle", target: "William Shakespeare", hops: 2, fanout: 322 },
  ],
  medium: [
    { start: "Sushi", target: "Volcano", hops: 2, fanout: 299 },
    { start: "Umbrella", target: "Tsunami", hops: 2, fanout: 289 },
    { start: "Pizza", target: "Mars", hops: 2, fanout: 204 },
    { start: "Waffle", target: "Tornado", hops: 2, fanout: 125 },
    { start: "Violin", target: "Glacier", hops: 3, atLeast: true, fanout: 350 },
    { start: "Coffee", target: "Mount Everest", hops: 3, atLeast: true, fanout: 312 },
    { start: "Chocolate", target: "Samurai", hops: 3, atLeast: true, fanout: 312 },
  ],
  hard: [
    { start: "Origami", target: "Submarine", hops: 3, atLeast: true, fanout: 144 },
    { start: "Pencil", target: "Kangaroo", hops: 3, atLeast: true, fanout: 185 },
    { start: "Lighthouse", target: "Dinosaur", hops: 3, atLeast: true, fanout: 215 },
    { start: "Soap", target: "Jupiter", hops: 3, atLeast: true, fanout: 224 },
    { start: "Bread", target: "Black hole", hops: 3, atLeast: true, fanout: 240 },
    { start: "Penguin", target: "Sahara", hops: 3, atLeast: true, fanout: 256 },
  ],
};

export const REDIRECT_FIXTURES = [
  { typed: "Snakes", canonical: "Snake" },
  { typed: "WWII", canonical: "World War II" },
  { typed: "Obama", canonical: "Barack Obama" },
];

export function randomPair(tier: Difficulty, avoid?: Pair): Pair {
  const pool = PAIRS[tier];
  if (pool.length === 1) return pool[0];
  let pick = pool[Math.floor(Math.random() * pool.length)];
  if (avoid && pool.length > 1) {
    let guard = 0;
    while (pick.start === avoid.start && pick.target === avoid.target && guard < 8) {
      pick = pool[Math.floor(Math.random() * pool.length)];
      guard += 1;
    }
  }
  return pick;
}

export function findPair(start: string, target: string, tier: Difficulty): Pair | null {
  const key = (s: string) => s.replace(/_/g, " ").trim().toLowerCase();
  return (
    PAIRS[tier].find(
      (p) => key(p.start) === key(start) && key(p.target) === key(target),
    ) ?? null
  );
}
