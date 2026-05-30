import numpy as np
from config import (
    NN_INPUTS, NN_HIDDEN, NN_OUTPUTS, MUTATION_RATE, MUTATION_SCALE,
    SENSOR_RANGE, WORLD_W, WORLD_H, FOOD_MAX, ENERGY_MAX, MAX_AGE, DIRS,
    ENERGY_INIT, REPRO_COOLDOWN,
)


class Brain:
    """
    Two-layer feedforward neural network.
    Weights are the genome — evolution acts directly on them.
    """
    __slots__ = ("w1", "w2")

    def __init__(self, w1=None, w2=None):
        if w1 is None:
            # Xavier-ish init: keeps activations from saturating at start
            scale1 = np.sqrt(2.0 / NN_INPUTS)
            scale2 = np.sqrt(2.0 / NN_HIDDEN)
            self.w1 = np.random.randn(NN_INPUTS, NN_HIDDEN) * scale1
            self.w2 = np.random.randn(NN_HIDDEN, NN_OUTPUTS) * scale2
        else:
            self.w1, self.w2 = w1, w2

    def forward(self, x: np.ndarray) -> np.ndarray:
        h = np.tanh(x @ self.w1)
        return np.tanh(h @ self.w2)

    def genome_distance(self, other: "Brain") -> float:
        """Mean squared weight difference — used for species classification."""
        d1 = np.mean((self.w1 - other.w1) ** 2)
        d2 = np.mean((self.w2 - other.w2) ** 2)
        return float(np.sqrt(d1 + d2))

    def mutate(self) -> "Brain":
        w1, w2 = self.w1.copy(), self.w2.copy()
        m1 = np.random.random(w1.shape) < MUTATION_RATE
        m2 = np.random.random(w2.shape) < MUTATION_RATE
        if m1.any():
            w1[m1] += np.random.randn(int(m1.sum())) * MUTATION_SCALE
        if m2.any():
            w2[m2] += np.random.randn(int(m2.sum())) * MUTATION_SCALE
        return Brain(w1, w2)

    def crossover(self, other: "Brain") -> "Brain":
        """Uniform crossover: each weight taken from either parent."""
        mask1 = np.random.random(self.w1.shape) < 0.5
        mask2 = np.random.random(self.w2.shape) < 0.5
        w1 = np.where(mask1, self.w1, other.w1)
        w2 = np.where(mask2, self.w2, other.w2)
        return Brain(w1, w2)


class Organism:
    """
    A neural-brained agent living in the world.
    State: position, energy, age, brain weights, species tag.
    """
    _uid = 0
    __slots__ = (
        "id", "x", "y", "brain", "energy", "age", "generation",
        "species", "alive", "children", "repro_cooldown", "last_dir",
    )

    def __init__(self, x: int, y: int, brain: Brain = None,
                 energy: float = ENERGY_INIT, generation: int = 0):
        Organism._uid += 1
        self.id         = Organism._uid
        self.x          = x
        self.y          = y
        self.brain      = brain or Brain()
        self.energy     = energy
        self.age        = 0
        self.generation = generation
        self.species    = 0
        self.alive      = True
        self.children   = 0
        self.repro_cooldown = 0
        self.last_dir   = 0

    def build_inputs(self, food_grid: np.ndarray, density_grid: np.ndarray) -> np.ndarray:
        """
        Construct the 20-dimensional input vector:
          [0-7]  : food gradient in 8 directions (normalized)
          [8-15] : organism density in 8 directions (normalized)
          [16]   : own energy (normalized)
          [17]   : own age (normalized)
          [18]   : bias = 1.0
          [19]   : small noise (breaks symmetry)
        """
        food_s = np.zeros(8)
        org_s  = np.zeros(8)

        for i, (dy, dx) in enumerate(DIRS):
            f_acc = 0.0
            o_acc = 0.0
            for r in range(1, SENSOR_RANGE + 1):
                ny = (self.y + dy * r) % WORLD_H
                nx = (self.x + dx * r) % WORLD_W
                f_acc += food_grid[ny, nx]
                o_acc += density_grid[ny, nx]
            food_s[i] = f_acc / (SENSOR_RANGE * FOOD_MAX)
            org_s[i]  = min(o_acc / SENSOR_RANGE, 1.0)

        return np.array([
            *food_s,
            *org_s,
            self.energy / ENERGY_MAX,
            self.age / MAX_AGE,
            1.0,
            np.random.random() * 0.05,
        ], dtype=np.float32)

    def decide(self, inputs: np.ndarray):
        """
        Returns (dir_idx: int 0-7, should_reproduce: bool).
        Movement direction is the argmax of the first 8 outputs.
        """
        out = self.brain.forward(inputs)
        dir_idx    = int(np.argmax(out[:8]))
        do_repro   = bool(out[8] > 0.2)
        return dir_idx, do_repro
