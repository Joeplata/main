# World
WORLD_W  = 100
WORLD_H  = 36

# Population
INITIAL_POP = 60
MAX_POP     = 600
SPAWN_THRESHOLD = 4          # reintroduce life if population drops below this

# Food
FOOD_DENSITY  = 0.10         # fraction of cells with food at start
FOOD_REGEN    = 0.0035       # probability per empty cell per tick to sprout food
FOOD_MAX      = 3.0          # max food units per cell
FOOD_TO_NRG   = 12.0         # energy gained per food unit eaten

# Energy
ENERGY_INIT      = 100.0
ENERGY_MAX       = 200.0
ENERGY_TICK      = 0.5       # base metabolism drain per tick
ENERGY_MOVE_EX   = 0.3       # extra drain for moving (on top of tick cost)
ENERGY_REPRO_MIN = 140.0     # must have this much to reproduce
ENERGY_REPRO_COST = 65.0     # energy transferred to child
REPRO_COOLDOWN    = 25       # ticks before can reproduce again

# Lifespan
MAX_AGE = 700

# Neural network
SENSOR_RANGE = 7
NN_INPUTS  = 20   # 8 food dirs + 8 org dirs + energy + age + bias + noise
NN_HIDDEN  = 24
NN_OUTPUTS = 9    # 8 movement directions + 1 reproduce signal

# Evolution
MUTATION_RATE      = 0.12
MUTATION_SCALE     = 0.65    # larger drift → faster speciation
SPECIES_THRESHOLD  = 0.80    # genome distance within which = same species

# Display
FPS = 15
HISTORY_LEN = 80

# 8-connected directions: (dy, dx)
DIRS = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]

# Species visual palette: (curses color index, bold?)
# mapped to curses COLOR_* constants in main.py
SPECIES_COLOR_IDS = [6, 1, 3, 5, 4, 2, 7, 6, 1, 3, 5, 4]
# COLOR_CYAN=6, COLOR_RED=1, COLOR_YELLOW=3, COLOR_MAGENTA=5,
# COLOR_BLUE=4, COLOR_GREEN=2, COLOR_WHITE=7
SPECIES_SYMS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
