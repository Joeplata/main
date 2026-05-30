import numpy as np
from collections import defaultdict

from organism import Organism, Brain
from config import (
    WORLD_W, WORLD_H, INITIAL_POP, MAX_POP, FOOD_DENSITY, FOOD_REGEN,
    FOOD_MAX, FOOD_TO_NRG, ENERGY_TICK, ENERGY_MOVE_EX, ENERGY_REPRO_MIN,
    ENERGY_REPRO_COST, REPRO_COOLDOWN, MAX_AGE, DIRS, SPECIES_THRESHOLD,
    SPAWN_THRESHOLD, HISTORY_LEN, ENERGY_INIT,
)


class World:
    def __init__(self):
        self.tick        = 0
        self.total_born  = 0
        self.total_died  = 0
        self.extinctions = 0

        # Grids
        self.food    = np.zeros((WORLD_H, WORLD_W), dtype=np.float32)
        self.density = np.zeros((WORLD_H, WORLD_W), dtype=np.int32)

        # Organisms
        self.organisms: list[Organism] = []

        # Species registry: species_id -> Brain representative
        self.species_rep: dict[int, Brain] = {}
        self._next_sp = 0

        # Event tracking (for display)
        self.events: list[str] = []      # recent events (birth/death/speciation)

        # History for sparklines
        self.pop_history: list[int]   = []
        self.food_history: list[float] = []
        self.div_history: list[int]   = []    # species count history

        self._seed_world()

    # ------------------------------------------------------------------ #
    #  Initialization
    # ------------------------------------------------------------------ #

    def _seed_world(self):
        self._create_landscape()
        # Seed with 6 distinct founding genomes so we have immediate species diversity
        N_FOUNDERS = 6
        founders = []
        for _ in range(N_FOUNDERS):
            b = Brain()
            b.w1 *= 2.8   # large scale ensures inter-founder genome distance >> threshold
            b.w2 *= 2.8
            founders.append(b)
            self._new_species(b)  # pre-register each founder as its own species

        for i in range(INITIAL_POP):
            x = np.random.randint(0, WORLD_W)
            y = np.random.randint(0, WORLD_H)
            child_brain = founders[i % N_FOUNDERS].mutate()
            org = Organism(x, y, child_brain)
            org.species = i % N_FOUNDERS  # inherit founder's species
            self.organisms.append(org)
            self.density[y, x] += 1
        self.total_born = INITIAL_POP

    def _create_landscape(self):
        """
        Create an interesting food distribution:
        - Base sparse random food
        - Several rich oasis patches
        - A few food-free desert zones
        """
        rng = np.random.random((WORLD_H, WORLD_W))
        self.food = np.where(rng < FOOD_DENSITY, rng * FOOD_MAX, 0.0).astype(np.float32)

        # Rich oasis patches
        n_oases = 6
        for _ in range(n_oases):
            cy = np.random.randint(5, WORLD_H - 5)
            cx = np.random.randint(5, WORLD_W - 5)
            r  = np.random.randint(4, 8)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if dy*dy + dx*dx <= r*r:
                        ny = (cy + dy) % WORLD_H
                        nx = (cx + dx) % WORLD_W
                        self.food[ny, nx] = FOOD_MAX

        # Desert patches
        n_deserts = 4
        for _ in range(n_deserts):
            cy = np.random.randint(3, WORLD_H - 3)
            cx = np.random.randint(3, WORLD_W - 3)
            r  = np.random.randint(3, 6)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if dy*dy + dx*dx <= r*r:
                        ny = (cy + dy) % WORLD_H
                        nx = (cx + dx) % WORLD_W
                        self.food[ny, nx] = 0.0

    # ------------------------------------------------------------------ #
    #  Species management
    # ------------------------------------------------------------------ #

    def _assign_species(self, org: Organism):
        if not self.species_rep:
            org.species = self._new_species(org.brain)
            return

        min_dist = float("inf")
        closest  = 0
        for sp_id, rep in self.species_rep.items():
            d = org.brain.genome_distance(rep)
            if d < min_dist:
                min_dist, closest = d, sp_id

        if min_dist < SPECIES_THRESHOLD:
            org.species = closest
        else:
            org.species = self._new_species(org.brain)
            self.events.append(f"t{self.tick}: new species {chr(65 + org.species % 26)}")

    def _new_species(self, brain: Brain) -> int:
        sp_id = self._next_sp
        self.species_rep[sp_id] = brain
        self._next_sp += 1
        return sp_id

    def _prune_extinct_species(self):
        alive_species = {o.species for o in self.organisms}
        extinct = [sp for sp in list(self.species_rep) if sp not in alive_species]
        for sp in extinct:
            del self.species_rep[sp]
        if extinct:
            self.extinctions += len(extinct)

    def _refresh_species_reps(self):
        """
        Update each species representative to a random current member.
        Without this, reps become stale as the population evolves away from
        the original founder, causing all living organisms to look like new species.
        """
        sp_members: dict[int, list[Organism]] = defaultdict(list)
        for o in self.organisms:
            sp_members[o.species].append(o)
        for sp_id, members in sp_members.items():
            rep = members[np.random.randint(len(members))]
            self.species_rep[sp_id] = rep.brain

    # ------------------------------------------------------------------ #
    #  Main simulation step
    # ------------------------------------------------------------------ #

    def step(self):
        self.tick += 1
        new_orgs: list[Organism] = []
        died = 0

        # Shuffle to prevent systematic positional bias
        np.random.shuffle(self.organisms)  # type: ignore[arg-type]

        for org in self.organisms:
            if not org.alive:
                continue

            # --- Sense & Decide ---
            inputs   = org.build_inputs(self.food, self.density)
            dir_idx, do_repro = org.decide(inputs)

            # --- Move ---
            self.density[org.y, org.x] -= 1
            dy, dx = DIRS[dir_idx]
            org.x = (org.x + dx) % WORLD_W
            org.y = (org.y + dy) % WORLD_H
            self.density[org.y, org.x] += 1
            org.last_dir = dir_idx

            # --- Metabolism ---
            org.energy -= ENERGY_TICK + ENERGY_MOVE_EX

            # --- Eat ---
            if self.food[org.y, org.x] > 0:
                bite = min(self.food[org.y, org.x], FOOD_MAX / 2)
                self.food[org.y, org.x] -= bite
                org.energy = min(org.energy + bite * FOOD_TO_NRG, 200.0)

            # --- Reproduce ---
            if (do_repro
                    and org.repro_cooldown == 0
                    and org.energy >= ENERGY_REPRO_MIN
                    and len(self.organisms) + len(new_orgs) < MAX_POP):
                # Look for a nearby mate of same species (sexual reproduction)
                mate = self._find_mate(org)
                if mate is not None:
                    child_brain = org.brain.crossover(mate.brain).mutate()
                else:
                    child_brain = org.brain.mutate()

                child_energy = ENERGY_REPRO_COST
                org.energy  -= ENERGY_REPRO_COST
                org.repro_cooldown = REPRO_COOLDOWN
                org.children += 1

                cx = (org.x + np.random.randint(-2, 3)) % WORLD_W
                cy = (org.y + np.random.randint(-2, 3)) % WORLD_H
                child = Organism(cx, cy, child_brain, child_energy, org.generation + 1)
                self._assign_species(child)
                self.density[cy, cx] += 1
                new_orgs.append(child)
                self.total_born += 1

            org.repro_cooldown = max(0, org.repro_cooldown - 1)
            org.age += 1

            # --- Death ---
            if org.energy <= 0 or org.age >= MAX_AGE:
                org.alive = False
                self.density[org.y, org.x] -= 1
                died += 1

        self.total_died += died
        self.organisms = [o for o in self.organisms if o.alive] + new_orgs

        # Extinction recovery: inject fresh life so the sim doesn't go dead
        if len(self.organisms) < SPAWN_THRESHOLD:
            self._emergency_spawn()

        # --- Food regeneration ---
        regen_mask = (self.food < FOOD_MAX) & (
            np.random.random((WORLD_H, WORLD_W)).astype(np.float32) < FOOD_REGEN
        )
        self.food = np.clip(self.food + regen_mask.astype(np.float32) * 0.8, 0, FOOD_MAX)

        # --- History ---
        self.pop_history.append(len(self.organisms))
        self.food_history.append(float(self.food.sum()))
        n_sp = len(self.count_species())
        self.div_history.append(n_sp)
        if len(self.pop_history) > HISTORY_LEN:
            self.pop_history.pop(0)
            self.food_history.pop(0)
            self.div_history.pop(0)

        # Prune extinct species & refresh reps every 100 ticks
        if self.tick % 100 == 0:
            self._prune_extinct_species()
            self._refresh_species_reps()

        # Keep event log bounded
        if len(self.events) > 20:
            self.events = self.events[-20:]

    def _find_mate(self, org: Organism):
        """Find a nearby same-species organism, or None."""
        candidates = [
            o for o in self.organisms
            if o is not org and o.alive and o.species == org.species
            and abs(o.x - org.x) <= 3 and abs(o.y - org.y) <= 3
        ]
        return np.random.choice(candidates) if candidates else None  # type: ignore[return-value]

    def _emergency_spawn(self):
        """Add fresh random organisms when population collapses."""
        n = 15
        for _ in range(n):
            x = np.random.randint(0, WORLD_W)
            y = np.random.randint(0, WORLD_H)
            org = Organism(x, y)
            self._assign_species(org)
            self.organisms.append(org)
            self.density[y, x] += 1
        self.total_born += n
        self.events.append(f"t{self.tick}: extinction recovery (+{n})")

    # ------------------------------------------------------------------ #
    #  Queries
    # ------------------------------------------------------------------ #

    def count_species(self) -> dict[int, int]:
        counts: dict[int, int] = defaultdict(int)
        for o in self.organisms:
            counts[o.species] += 1
        return dict(counts)

    def add_food_burst(self):
        """Player-triggered food surge."""
        burst = np.random.random((WORLD_H, WORLD_W)).astype(np.float32) * FOOD_MAX * 0.4
        self.food = np.clip(self.food + burst, 0, FOOD_MAX)

    def inject_organisms(self, n: int = 10):
        """Player-triggered organism injection."""
        for _ in range(n):
            x = np.random.randint(0, WORLD_W)
            y = np.random.randint(0, WORLD_H)
            org = Organism(x, y)
            self._assign_species(org)
            self.organisms.append(org)
            self.density[y, x] += 1
        self.total_born += n

    def stats_snapshot(self) -> dict:
        orgs = self.organisms
        if not orgs:
            return {}
        return {
            "pop":      len(orgs),
            "max_gen":  max(o.generation for o in orgs),
            "avg_age":  sum(o.age for o in orgs) / len(orgs),
            "max_age":  max(o.age for o in orgs),
            "max_kids": max(o.children for o in orgs),
            "avg_energy": sum(o.energy for o in orgs) / len(orgs),
            "n_species": len(self.count_species()),
        }
