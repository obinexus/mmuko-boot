# MMUKO-BOOT Design Document

**Project:** OBINexus / MMUKO OS Boot Scaffold  
**Version:** 0.1-qemu  
**Date:** 2026-05-28  
**Status:** Phase-0 Freestanding Kernel — Proof of Concept

---

## 1. Architectural Overview

MMUKO-BOOT is a **freestanding x86 kernel scaffold** that introduces a non-traditional memory model: every byte is treated as an 8-position **cubit ring** rather than a flat scalar value. The boot sequence does not merely copy data into RAM; it *resolves* each byte through a series of oriented states, local constraints, and relative reference frames until the system converges on a coherent operational basis.

This document separates the **physics-inspired metaphor** (the conceptual vocabulary) from the **computational semantics** (what the code actually does), so that reviewers can engage with the architecture on precise technical grounds rather than dismissing it as speculative prose.

### 1.1 Boot Paths

The scaffold supports two entry paths:

| Path | Loader | Mode | Files |
|------|--------|------|-------|
| Direct BIOS | `boot16.s` | 16-bit real → 32-bit protected | `boot16.s`, `kernel-entry.s`, `kernel.c` |
| GRUB Multiboot | `boot.asm` | 32-bit protected (GRUB-entered) | `boot.asm`, `kernel.c`, `linker.ld` |

Both paths converge on `kernel_main()`, which initializes VGA (`0xB8000`) and COM1 (`0x3F8`) via raw port I/O, then executes the MMUKO boot phases.

---

## 2. Metaphor-to-Code Mapping

The following table is the authoritative bridge between MMUKO's conceptual language and its C implementation. Every row is verifiable in `kernel.c`.

| Metaphor | Code Artifact | Physics Inspiration | Computational Semantics |
|----------|---------------|---------------------|------------------------|
| **Cubit Ring** | `struct Cubit cubit_ring[8]` inside `MMUKO_Byte` | Quantum spin-1/2 particles arranged on a ring; each position has an orientation | Each byte is decomposed into 8 indexed sub-states. Each sub-state carries value, direction, spin, and state fields. This allows per-bit oriented operations rather than whole-byte arithmetic. |
| **Spin** | `uint16_t spin_mrad` | Angular momentum eigenvalue in milliradians | A discrete angular tag (785, 1047, 1571, 3142, 6283 mrad) assigned by ring position. Used as an input to rotation operators (Phase 6). Not a physical angular momentum. |
| **Direction (Compass)** | `Direction` enum: `N, NE, E, SE, S, SW, W, NW` | Magnetic compass headings on a toroidal surface | An 8-valued orientation label per cubit. Phase 2 resolves any `UNDEFINED_DIR` by majority vote of neighbors. Provides a local coordinate system for each byte. |
| **State** | `State` enum: `UP, DOWN, CHARM, STRANGE, LEFT, RIGHT` | Quark flavor / spin projection states | A 6-valued classification derived deterministically from a cubit's own bit and its clockwise neighbor's bit (`resolve_state`). Used in Phase 3 to enforce local parity constraints. |
| **Entanglement** | `int entangled_pairs[] = {7,6,5,-1,-1,2,1,0}` | Quantum entanglement (non-local correlation) | **Local complementary pairing within a single byte.** Cubit *i* is paired with cubit *entangled_pairs[i]*. If both cubits share the same state after Phase 1, Phase 3 flips the partner's state. This is a deterministic parity rule, not a non-local quantum correlation. |
| **Superposition** | `primary_superposition`, `secondary_superposition` | Quantum superposition (coexistence of eigenstates) | A **resolution order** stored as two `Direction` values. The byte is not in two states simultaneously; rather, it carries an ordered pair of candidate directions that the nonlinear resolution phase (Phase 5) selects from based on `base_index`. |
| **Vacuum Medium** | `struct VacuumMedium { gravity_milli, air_milli, water_milli }` | Physical fields permeating spacetime | A struct of scaling constants. Currently only `gravity_milli = 9800` is initialized. Reserved for future environmental tuning (e.g., memory-pressure-aware scheduling constants). |
| **Frame of Reference** | `Direction frame_of_reference` | Relativity: no absolute rest frame | The system-wide direction chosen at boot (Phase 4) to serve as the "zero axis" for all subsequent byte-oriented operations. Because it is chosen dynamically from the superposition table rather than hard-coded, the OS has no compile-time polarity. |
| **Non-Polar** | Absence of a fixed `NORTH = 0` operational semantics | Magnetic monopole absence; no privileged pole | No phase assumes `N` is the universal "up." The frame of reference is resolved at runtime from the superposition table. The architecture is rotationally symmetric by design. |
| **Non-Linear Boot** | `boot_order[] = {12, 6, 8, 4, 10, 2, 1}` in Phase 5 | Nonlinear dynamical systems; strange attractors | The resolution of memory bases does not follow address order. Instead, bases are visited in a fixed permutation. This is **non-sequential resolution**, not feedback-loop nonlinearity. (See §5.1 for the feedback-loop roadmap.) |
| **Rotation Lock** | `BOOT_ROTATION_LOCK` status code | Conservation of angular momentum; rotational symmetry breaking | A boot-failure mode intended to detect whether the cubit ring forms a proper cyclic group under bit-rotation. **Current implementation is trivially true for 8-bit values** (see §4.1). |

---

## 3. Data Structures

### 3.1 Cubit

```c
typedef struct {
    int index;              // 0–7: position in ring
    uint8_t value;          // 0 or 1: the actual bit
    uint16_t spin_mrad;     // Angular tag (see table above)
    Direction direction;      // Compass heading
    State state;            // Derived from neighbor parity
    bool superposed;        // true if entangled_with != -1
    int entangled_with;     // Partner index, or -1
} Cubit;
```

**Computational semantics:** A `Cubit` is a decorated bit. It does not store quantum probability amplitudes. The `superposed` flag is a boolean indicating membership in a local pair, not a complex coefficient.

### 3.2 MMUKO_Byte

```c
typedef struct {
    uint8_t raw_value;                  // Original byte value
    Cubit cubit_ring[8];                // Decomposed sub-states
    int base_index;                     // (raw_value % 12) + 1
    Direction primary_superposition;    // Candidate direction A
    Direction secondary_superposition;  // Candidate direction B
} MMUKO_Byte;
```

**Computational semantics:** `base_index` is a deterministic hash of the byte value used to index into the superposition table. The two candidate directions provide an ordered ambiguity that Phase 5 resolves.

### 3.3 MMUKO_System

```c
typedef struct {
    MMUKO_Byte *memory_map;      // Array of MMUKO_Byte
    size_t memory_size;          // Currently 16 (demo size)
    VacuumMedium medium;         // Environmental constants
    Direction frame_of_reference;// Runtime-chosen zero axis
    bool boot_complete;          // Convergence flag
} MMUKO_System;
```

---

## 4. Boot Phase Semantics

### Phase 0 — Vacuum Medium Initialization
- **Code:** `init_vacuum_medium()`
- **Does:** Sets `gravity_milli = 9800`, `air_milli = 0`, `water_milli = 0`.
- **Physics inspiration:** Establishing the background field in which computation occurs.
- **Computational semantics:** Initializes a constant struct. Future phases may read `medium.gravity_milli` to scale timeouts or memory-pressure thresholds.

### Phase 1 — Cubit Ring Initialization
- **Code:** `phase1_cubit_init()`
- **Does:** For each byte, computes `base_index = (raw_value % 12) + 1`, then populates all 8 cubits via `init_cubit_ring()` and `lookup_superposition()`.
- **Physics inspiration:** Preparing the quantum register; assigning spin states.
- **Computational semantics:** O(n) decomposition of memory into decorated bits. The `% 12` bounds `base_index` to `[1, 12]`, which matches the superposition table's domain.

### Phase 2 — Compass Alignment
- **Code:** `phase2_compass_alignment()`
- **Does:** For any cubit with `UNDEFINED_DIR`, resolves it by majority vote of its two immediate neighbors in the ring. If no majority exists, returns `BOOT_LOCK_DETECTED`.
- **Physics inspiration:** Magnetic domain alignment; spontaneous symmetry breaking into a coherent direction.
- **Computational semantics:** A local consensus algorithm on an 8-node cyclic graph. This is a **cellular automaton** rule, not a quantum field effect.

### Phase 3 — Superposition Entanglement
- **Code:** `phase3_superposition_entanglement()`
- **Does:** For every entangled pair within each byte, if both cubits share the same `state`, flip the partner's state via `flip_state()`.
- **Physics inspiration:** Measurement-induced collapse breaking entanglement symmetry.
- **Computational semantics:** A deterministic parity enforcement pass. Ensures no paired cubits remain in identical states after initialization. This is a **constraint satisfaction** step.

### Phase 4 — Frame of Reference Centering
- **Code:** `phase4_frame_centering()`
- **Does:** Looks up base `6` in the superposition table (yields `SW`/`E`), assigns `SW` as the system-wide `frame_of_reference`, and propagates the pair to all bytes.
- **Physics inspiration:** Choosing a rest frame in relativity.
- **Computational semantics:** Hard-codes base `6` as the anchor. This is the **polarity selection** step; it breaks the rotational symmetry deliberately so that later operations have a common axis.

### Phase 5 — Nonlinear Index Resolution
- **Code:** `phase5_nonlinear_resolution()`
- **Does:** Visits bases in the order `{12, 6, 8, 4, 10, 2, 1}`, calling `resolve_base_state()` for each.
- **Physics inspiration:** Nonlinear dynamical systems where variables do not evolve in index order.
- **Computational semantics:** A permutation scan. Each base's superposition pair is written to all bytes matching that base. This is **non-sequential** because it does not walk `memory_map[0]`, `memory_map[1]`, etc., in address order. It is not yet *adaptive* or *iterative*.

### Phase 6 — Rotation Freedom Check
- **Code:** `phase6_rotation_verification()`
- **Does:** Rotates each cubit's value by 4 bits, then by 4 bits again, and asserts equality with the original.
- **Physics inspiration:** Rotational symmetry conservation; detecting angular momentum lock.
- **Computational semantics:** **Currently trivial.** For 8-bit values, `rot(rot(x, 4), 4) == x` is an identity. This phase therefore never fails. It should be replaced with a genuine group-theoretic check (see §5.1).

### Phase 7 — Boot Complete
- **Code:** Sets `boot_complete = true`.
- **Does:** Transfers control to `mmuko_program_main()`.

---

## 5. Known Limitations & Roadmap

### 5.1 Current Limitations (Phase 0)

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Memory size fixed at 16 bytes | Demo only; no real RAM map | Implement INT 15h E820 detection and scale `MMUKO_Byte` array to physical memory size |
| Phase 6 rotation check is trivial | `BOOT_ROTATION_LOCK` is dead code | Replace with cyclic-group validation: verify that `rot(x, n)` for `n = 0..7` produces 8 distinct values unless `x` is 0x00 or 0xFF |
| No feedback loops between phases | "Non-linear" claim is weak | Add re-entry: if Phase 3 flips a state, re-run Phase 2 on affected bytes until quiescence or iteration bound |
| No interrupt handling | Cannot demonstrate "inemptive" scheduling | Add IDT, PIT timer, and a task switcher that uses cubit direction as a priority vector |
| Spin duplicates unexplained | N == NW, NE == W, E == SW | Document as intentional duals (antipodes) or assign unique angles |
| "Entanglement" is local only | Invites dismissal from physicists | Rename to **complementary binding** or implement pseudo-random collapse via `rdtsc` |

### 5.2 Phase 1 Roadmap

1. **Feedback-loop boot:** Allow phases 2–3 to iterate with a convergence counter. This makes the boot genuinely nonlinear (dynamical system style).
2. **Physical memory map:** Detect RAM via BIOS E820, allocate a real `MMUKO_Byte` array, and run the phases on the machine's actual memory topology.
3. **Inemptive scheduler:** Use the PIT to trigger context switches. A task's priority is derived from its current cubit ring's directional vector relative to the global frame.
4. **Ring I/O:** Extend the cubit model to disk blocks and network frames, treating each sector as a large cubit ring with inter-sector entanglement (checksum / parity pairs).

---

## 6. Glossary of Terms

| Term | Physics Meaning | MMUKO Computational Meaning |
|------|-----------------|---------------------------|
| Cubit | Portmanteau of "cube" and "qubit" | A decorated bit with direction, spin, and state metadata |
| Superposition | Coexistence of quantum eigenstates | Ordered pair of candidate directions; resolved by base index |
| Entanglement | Non-local quantum correlation | Local complementary pairing with deterministic parity flip |
| Vacuum medium | Background quantum field | Constant struct for environmental scaling factors |
| Non-polar | No magnetic monopole; no preferred pole | No compile-time directional bias; frame chosen at runtime |
| Non-linear | Dynamical system with feedback | Non-sequential base resolution; future: iterative convergence |
| Rotation lock | Angular momentum frozen | Dead code path; intended to detect broken cyclic symmetry |

---

## 7. How to Verify This Document

Every claim above can be checked against the source:

1. Open `kernel.c` from `github.com/obinexus/mmuko-boot`.
2. Search for each function name in the Phase descriptions.
3. Compare the `spin_mrad_values[]`, `entangled_pairs[]`, `superposition_table[]`, and `boot_order[]` arrays to the tables in §2.
4. Compile and run under QEMU:
   ```bash
   make
   make run        # GRUB path
   # or
   ./build-direct.ps1   # Windows BIOS path
   qemu-system-i386 -drive format=raw,file=build/mmuko-direct.img,if=ide,index=0 -display none -serial stdio -no-reboot
   ```

---

*Document generated for code review. The physics vocabulary is intentional and metaphorical; the C implementation is literal and deterministic.*
