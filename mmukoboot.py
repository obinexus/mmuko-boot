# /mmuko/mmuko_boot_sim.py
"""
MMUKO-OS Boot Sequence Simulator (from MMUKO-BOOT.PSC)
This implements the provided pseudocode as a deterministic simulator:
- Byte -> 8-cubit compass ring
- Weak-map superposition lookup
- Phase pipeline (alignment, entanglement resolution, diamond traversal, rotation check)
Run:
  python mmuko_boot_sim.py --bytes 00 ff 2a --bases 12 6 8
Or (bases auto default to 6):
  python mmuko_boot_sim.py --bytes 01 02 03
Notes:
- This is a simulator of *semantics*, not a real bootloader.
- It is designed to be a reference implementation for porting to C/C++/ASM.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

PI = 3.14159265358979
G_VACUUM = 9.8
G_LEPTON = G_VACUUM / 10.0
G_MUON = G_LEPTON / 10.0
G_DEEP = G_MUON / 10.0

class Direction(str, Enum):
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"
    UNDEFINED = "UNDEFINED"

class State(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    CHARM = "CHARM"
    STRANGE = "STRANGE"
    LEFT = "LEFT"
    RIGHT = "RIGHT"

SPINS: List[float] = [
    PI / 4,   # N
    PI / 3,   # NE
    PI / 2,   # E
    PI,       # SE (as given in PSC constants)
    PI * 2,   # S
    PI / 2,   # SW (dual with E)
    PI / 3,   # W  (dual with NE)
    PI / 4,   # NW (dual with N)
]

DIRECTIONS: List[Direction] = [
    Direction.N,
    Direction.NE,
    Direction.E,
    Direction.SE,
    Direction.S,
    Direction.SW,
    Direction.W,
    Direction.NW,
]

ENTANGLED_WITH: List[int] = [
    7,  # N <-> NW
    6,  # NE <-> W
    5,  # E <-> SW
    -1, # SE
    -1, # S
    2,  # SW <-> E
    1,  # W <-> NE
    0,  # NW <-> N
]

@dataclass(frozen=True)
class SuperpositionPair:
    primary: Direction
    secondary: Direction

SUPERPOSITION_TABLE: Dict[int, SuperpositionPair] = {
    12: SuperpositionPair(primary=Direction.S, secondary=Direction.N),
    10: SuperpositionPair(primary=Direction.SE, secondary=Direction.N),
    8:  SuperpositionPair(primary=Direction.E, secondary=Direction.W),
    6:  SuperpositionPair(primary=Direction.SW, secondary=Direction.E),
    4:  SuperpositionPair(primary=Direction.W, secondary=Direction.E),
    2:  SuperpositionPair(primary=Direction.NE, secondary=Direction.W),
    1:  SuperpositionPair(primary=Direction.N, secondary=Direction.S),
}

@dataclass
class Cubit:
    index: int
    value: int
    spin: float
    direction: Direction
    state: State
    superposed: bool
    entangled_with: int

@dataclass
class ByteNode:
    raw_value: int
    base_index: int
    cubit_ring: List[Cubit]
    superposition_state: SuperpositionPair

@dataclass
class BootStatus:
    ok: bool
    reason: str = ""

def resolve_state(index: int, byte_val: int) -> State:
    bit = (byte_val >> index) & 1
    neighbor = (byte_val >> ((index + 1) % 8)) & 1
    if bit == 1 and neighbor == 1:
        return State.UP
    if bit == 1 and neighbor == 0:
        return State.CHARM
    if bit == 0 and neighbor == 1:
        return State.STRANGE
    return State.DOWN

def init_cubit_ring(byte_value: int) -> List[Cubit]:
    ring: List[Cubit] = []
    for i in range(8):
        value = (byte_value >> i) & 1
        ent = ENTANGLED_WITH[i]
        ring.append(
            Cubit(
                index=i,
                value=value,
                spin=SPINS[i],
                direction=DIRECTIONS[i],
                state=resolve_state(i, byte_value),
                superposed=(ent != -1),
                entangled_with=ent,
            )
        )
    return ring

def round_to_even_base(base: int) -> int:
    if base <= 1:
        return 1
    if base in SUPERPOSITION_TABLE:
        return base
    keys = sorted(SUPERPOSITION_TABLE.keys())
    best = keys[0]
    best_dist = abs(base - best)
    for k in keys[1:]:
        dist = abs(base - k)
        if dist < best_dist or (dist == best_dist and k < best):
            best, best_dist = k, dist
    return best

def lookup_superposition(base: int) -> SuperpositionPair:
    if base in SUPERPOSITION_TABLE:
        return SUPERPOSITION_TABLE[base]
    nearest = round_to_even_base(base)
    return SUPERPOSITION_TABLE[nearest]

def rotate_bits(value: int, n: int) -> int:
    n %= 8
    return ((value >> n) | (value << (8 - n))) & 0xFF

def flip_state(s: State) -> State:
    mapping = {
        State.UP: State.DOWN,
        State.DOWN: State.UP,
        State.CHARM: State.STRANGE,
        State.STRANGE: State.CHARM,
        State.LEFT: State.RIGHT,
        State.RIGHT: State.LEFT,
    }
    return mapping[s]

def get_middle_base() -> int:
    return 12 // 2

def mode(items: List[Direction]) -> Direction:
    counts: Dict[Direction, int] = {}
    for it in items:
        counts[it] = counts.get(it, 0) + 1
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].value))[0][0]
    return best

def resolve_direction_from_neighbors(ring: List[Cubit], idx: int) -> Direction:
    n1 = ring[(idx - 1) % 8].direction
    n2 = ring[(idx + 1) % 8].direction
    neighbor_dirs = [d for d in (n1, n2) if d != Direction.UNDEFINED]
    if not neighbor_dirs:
        return Direction.N
    return mode(neighbor_dirs)

def resolve_base_state(base: int, logs: List[str]) -> None:
    pair = lookup_superposition(base)
    logs.append(f"[resolve_base_state] base={base} -> primary={pair.primary.value}, secondary={pair.secondary.value}")

def set_frame_of_reference(center_direction: Direction, logs: List[str]) -> None:
    logs.append(f"[set_frame_of_reference] center_direction={center_direction.value}")

def mmuko_boot(memory_bytes: List[int], base_indices: Optional[List[int]] = None) -> Tuple[BootStatus, List[str], List[ByteNode]]:
    logs: List[str] = []
    nodes: List[ByteNode] = []

    logs.append("MMUKO PHASE 0: Initializing vacuum medium...")
    medium = {"gravity": G_VACUUM, "air": 0, "water": 0}
    logs.append(f"[medium] {medium}")

    logs.append("MMUKO PHASE 1: Initializing cubit rings...")
    if base_indices is None:
        base_indices = [6 for _ in memory_bytes]
    if len(base_indices) != len(memory_bytes):
        return BootStatus(False, "base_indices length must match bytes length"), logs, nodes

    for b, base in zip(memory_bytes, base_indices):
        ring = init_cubit_ring(b)
        sp = lookup_superposition(base)
        nodes.append(ByteNode(raw_value=b, base_index=base, cubit_ring=ring, superposition_state=sp))
        logs.append(f"[byte] raw=0x{b:02X} base={base} superposition=({sp.primary.value},{sp.secondary.value})")

    all_cubits: List[Tuple[int, Cubit]] = []
    for bi, node in enumerate(nodes):
        for c in node.cubit_ring:
            all_cubits.append((bi, c))

    logs.append("MMUKO PHASE 2: Compass alignment...")
    for bi, node in enumerate(nodes):
        ring = node.cubit_ring
        for i, c in enumerate(ring):
            if c.direction == Direction.UNDEFINED:
                new_dir = resolve_direction_from_neighbors(ring, i)
                ring[i] = Cubit(**{**c.__dict__, "direction": new_dir})
            if ring[i].direction == Direction.UNDEFINED:
                return BootStatus(False, f"Boot lock detected at byte={bi} cubit={i}"), logs, nodes

    logs.append("MMUKO PHASE 3: Entangling superposition pairs...")
    for bi, node in enumerate(nodes):
        ring = node.cubit_ring
        for i, c in enumerate(ring):
            if not c.superposed or c.entangled_with == -1:
                continue
            partner_idx = c.entangled_with
            partner = ring[partner_idx]
            if c.state == partner.state:
                flipped = flip_state(partner.state)
                ring[partner_idx] = Cubit(**{**partner.__dict__, "state": flipped})
                logs.append(f"[interference] byte={bi} pair=({i},{partner_idx}) state={partner.state.value}->{flipped.value}")

    logs.append("MMUKO PHASE 4: Frame of reference centering...")
    center_base = get_middle_base()
    center_dir = lookup_superposition(center_base).primary
    set_frame_of_reference(center_dir, logs)

    logs.append("MMUKO PHASE 5: Nonlinear index resolution (diamond table)...")
    boot_order = [12, 6, 8, 4, 10, 2, 1]
    for base in boot_order:
        resolve_base_state(base, logs)

    logs.append("MMUKO PHASE 6: Rotation freedom check...")
    for bi, node in enumerate(nodes):
        for c in node.cubit_ring:
            test_val = rotate_bits(c.value, 4)
            test_val = rotate_bits(test_val, 4)
            if test_val != c.value:
                return BootStatus(False, f"Rotation lock at byte={bi} cubit={c.index}"), logs, nodes

    logs.append("MMUKO BOOT COMPLETE — All cubits aligned, no lock detected.")
    return BootStatus(True, "BOOT_OK"), logs, nodes

def parse_hex_byte(s: str) -> int:
    s = s.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    v = int(s, 16)
    if not (0 <= v <= 0xFF):
        raise ValueError(f"byte out of range: {s}")
    return v

def main() -> None:
    ap = argparse.ArgumentParser(description="MMUKO-BOOT.PSC semantics simulator")
    ap.add_argument("--bytes", nargs="+", required=True, help="Bytes in hex (e.g., 00 ff 2a or 0x2a)")
    ap.add_argument("--bases", nargs="*", type=int, help="Optional base indices per byte (same count as --bytes)")
    ap.add_argument("--quiet", action="store_true", help="Only print final status")
    args = ap.parse_args()
    memory = [parse_hex_byte(x) for x in args.bytes]
    bases = args.bases if args.bases else None
    status, logs, nodes = mmuko_boot(memory, bases)
    if not args.quiet:
        for line in logs:
            print(line)
        print()
        for i, node in enumerate(nodes):
            print(f"[ring byte {i}] raw=0x{node.raw_value:02X} base={node.base_index} sp=({node.superposition_state.primary.value},{node.superposition_state.secondary.value})")
            for c in node.cubit_ring:
                ent = f" ent={c.entangled_with}" if c.entangled_with != -1 else ""
                print(f"  - cubit {c.index}: v={c.value} dir={c.direction.value} spin={c.spin:.4f} state={c.state.value} superposed={c.superposed}{ent}")
            print()
    if status.ok:
        print("STATUS: BOOT_OK")
    else:
        print(f"STATUS: BOOT_FAILED: {status.reason}")

if __name__ == "__main__":
    main()
