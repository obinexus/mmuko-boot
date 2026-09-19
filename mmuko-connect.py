"""
MMUKO Calibration Sequence
OBINexus / NSIGII Constitutional Computing Framework
Calibration tuple: C = (NOISE, NONOISE, SIGNAL, NOSIGNAL)
Tripartite stream: S = (TRANSMITTER, RECEIVER, VERIFIER)
A signal is a byte stream with intentional structure that survives
planar elimination — the reduction of 2D (noise × signal) ambiguity
into a 1D resolved classification vector.
"""

from __future__ import annotations
import os
import time
import hashlib
import enum
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Core: Byte State Classification
# ---------------------------------------------------------------------------

class ByteState(enum.IntEnum):
    """
    The four calibration states.
    Every byte in a stream is classified into exactly one of these.
    """
    NOISE    = 0  # Real-world entropy — cannot be structured
    NONOISE  = 1  # Entropy excluded — channel is clean but silent
    SIGNAL   = 2  # Intentional pattern — distinguishable structure
    NOSIGNAL = 3  # Null / silence — no transmission event


# ---------------------------------------------------------------------------
# Calibration Tuple  C = (NOISE, NONOISE, SIGNAL, NOSIGNAL)
# ---------------------------------------------------------------------------

@dataclass
class CalibrationTuple:
    """
    C = (NOISE, NONOISE, SIGNAL, NOSIGNAL)
    The calibrator for a tripartite NSIGII stream.
    Classifies a raw byte stream by projecting it through
    planar elimination: collapsing the 2D (noise × signal)
    plane into a resolved 1D classification vector.
    Planar elimination:
        Any byte b exists simultaneously on two axes:
            axis_noise  : P(b is entropy)
            axis_signal : P(b is intentional)
        Calibration resolves the 2D ambiguity by applying
        threshold cuts — one per axis — to eliminate the plane
        and leave a discrete classification.
    """
    noise_threshold:     float = 0.7   # P(entropy) above this → NOISE
    signal_threshold:    float = 0.6   # P(intentional) above this → SIGNAL
    silence_window:      int   = 8     # consecutive null bytes → NOSIGNAL

    def _entropy_score(self, window: bytes) -> float:
        """
        Shannon-style entropy score [0.0, 1.0].
        High entropy → likely NOISE.
        Low entropy  → likely structured (SIGNAL or NONOISE).
        """
        if not window:
            return 0.0
        counts = [0] * 256
        for b in window:
            counts[b] += 1
        n = len(window)
        score = 0.0
        import math
        for c in counts:
            if c > 0:
                p = c / n
                score -= p * math.log2(p)
        return score / 8.0  # normalise to [0, 1]  (max = log2(256) = 8)

    def _structure_score(self, window: bytes) -> float:
        """
        Structure score [0.0, 1.0].
        Measures repetition, framing bytes, or known preamble patterns.
        High score → likely SIGNAL.
        """
        if not window:
            return 0.0
        unique = len(set(window))
        # More unique bytes in a small window → less structured
        structure = 1.0 - (unique / max(len(window), 1))
        # Boost score if window starts with a known preamble (0xAA 0x55)
        if len(window) >= 2 and window[0] == 0xAA and window[1] == 0x55:
            structure = min(1.0, structure + 0.3)
        return structure

    def classify(self, window: bytes) -> ByteState:
        """
        Planar elimination: classify a byte window.
        Step 1 — Check for silence (all null bytes)
        Step 2 — Compute noise and structure scores
        Step 3 — Resolve 2D (entropy × structure) plane into 1D state
        """
        if not window:
            return ByteState.NOSIGNAL

        # Silence check
        if all(b == 0x00 for b in window):
            return ByteState.NOSIGNAL

        e_score = self._entropy_score(window)
        s_score = self._structure_score(window)

        # Planar elimination matrix
        #   High entropy, low structure  → NOISE
        #   Low entropy,  high structure → SIGNAL
        #   Low entropy,  low structure  → NONOISE
        #   High entropy, high structure → NOISE (entropy dominates)

        if e_score >= self.noise_threshold:
            return ByteState.NOISE
        if s_score >= self.signal_threshold:
            return ByteState.SIGNAL
        return ByteState.NONOISE

    def classify_stream(self, stream: bytes, window_size: int = 16) -> list[ByteState]:
        """
        Classify an entire byte stream in fixed-size windows.
        Returns a list of ByteState — one per window.
        This is the calibration vector (1D projection of the stream).
        """
        states = []
        for i in range(0, len(stream), window_size):
            window = stream[i:i + window_size]
            states.append(self.classify(window))
        return states


# ---------------------------------------------------------------------------
# Tripartite Stream  S = (TRANSMITTER, RECEIVER, VERIFIER)
# ---------------------------------------------------------------------------

@dataclass
class CalibrationEvent:
    """A single event in the event-agnostic calibration sequence."""
    kind:       str         # 'connect' | 'disconnect' | 'data' | 'recalibrate'
    payload:    bytes = b""
    timestamp:  float = field(default_factory=time.time)
    node_id:    str   = ""


@dataclass
class Transmitter:
    """
    Emits byte streams tagged with calibration preamble.
    Preamble: 0xAA 0x55 → signals the start of intentional transmission.
    """
    node_id: str = "TX-001"

    PREAMBLE = bytes([0xAA, 0x55])

    def emit(self, payload: bytes) -> CalibrationEvent:
        framed = self.PREAMBLE + payload
        return CalibrationEvent(
            kind="data",
            payload=framed,
            node_id=self.node_id
        )

    def connect(self) -> CalibrationEvent:
        return CalibrationEvent(kind="connect", node_id=self.node_id)

    def disconnect(self) -> CalibrationEvent:
        return CalibrationEvent(kind="disconnect", node_id=self.node_id)


@dataclass
class Receiver:
    """
    Receives events and classifies each payload via the CalibrationTuple.
    Maintains a rolling calibration vector — the resolved stream state.
    """
    calibrator:  CalibrationTuple = field(default_factory=CalibrationTuple)
    node_id:     str = "RX-001"
    _vector:     list[ByteState] = field(default_factory=list, init=False)
    _connected:  bool = field(default=False, init=False)

    def receive(self, event: CalibrationEvent) -> list[ByteState]:
        if event.kind == "connect":
            self._connected = True
            print(f"[{self.node_id}] Connected ← {event.node_id}")
            return []
        if event.kind == "disconnect":
            self._connected = False
            print(f"[{self.node_id}] Disconnected ← {event.node_id}")
            return []
        if not self._connected:
            print(f"[{self.node_id}] Not connected — dropping event")
            return []

        new_states = self.calibrator.classify_stream(event.payload)
        self._vector.extend(new_states)
        return new_states

    @property
    def calibration_vector(self) -> list[ByteState]:
        return list(self._vector)

    def dominant_state(self) -> Optional[ByteState]:
        if not self._vector:
            return None
        return max(set(self._vector), key=self._vector.count)


@dataclass
class Verifier:
    """
    Validates the calibration vector produced by the Receiver.
    A calibration is valid when SIGNAL is the dominant state
    (meaning the connection has negotiated a shared understanding
    of what counts as intentional data).
    Verification hash: SHA-256 of the serialised vector — used as
    the shared calibration fingerprint between two nodes.
    """
    node_id: str = "VRF-001"

    def verify(self, receiver: Receiver) -> tuple[bool, str]:
        vector = receiver.calibration_vector
        if not vector:
            return False, "empty-vector"

        dominant = receiver.dominant_state()
        is_valid = dominant == ByteState.SIGNAL

        # Calibration fingerprint — both nodes must agree on this hash
        raw = bytes([int(s) for s in vector])
        fingerprint = hashlib.sha256(raw).hexdigest()[:16]

        status = "VALID" if is_valid else "INVALID"
        print(f"[{self.node_id}] Calibration {status} — dominant={dominant.name} fingerprint={fingerprint}")
        return is_valid, fingerprint


# ---------------------------------------------------------------------------
# High-level: Calibration Session
# ---------------------------------------------------------------------------

class CalibrationSession:
    """
    Runs a full MMUKO Calibration Sequence.
    The session is event-agnostic — it handles connect, data, and
    disconnect events in any order, re-calibrating automatically.
    This matches the SEQUENCE = NOISE, NONOISE, NOSIGNAL validation
    matrix: each event is checked against the calibration tuple and
    the connection state is derived from the resolved vector.
    """

    def __init__(
        self,
        transmitter: Optional[Transmitter] = None,
        receiver:    Optional[Receiver]    = None,
        verifier:    Optional[Verifier]    = None,
    ):
        self.tx  = transmitter or Transmitter()
        self.rx  = receiver    or Receiver()
        self.vrf = verifier    or Verifier()

    def run(self, payloads: list[bytes]) -> dict:
        print("\n--- MMUKO Calibration Sequence START ---")

        # 1. Connect
        event = self.tx.connect()
        self.rx.receive(event)

        # 2. Transmit and classify each payload
        all_states: list[list[ByteState]] = []
        for payload in payloads:
            event = self.tx.emit(payload)
            states = self.rx.receive(event)
            all_states.append(states)
            labels = [s.name for s in states]
            print(f"  payload={payload.hex()[:24]}... → {labels}")

        # 3. Verify
        valid, fingerprint = self.vrf.verify(self.rx)

        # 4. Disconnect
        event = self.tx.disconnect()
        self.rx.receive(event)

        print("--- MMUKO Calibration Sequence END ---\n")
        return {
            "connected":   valid,
            "fingerprint": fingerprint,
            "dominant":    self.rx.dominant_state(),
            "vector_len":  len(self.rx.calibration_vector),
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Intentional signal: preamble + structured payload
    signal_payload = bytes([0xAA, 0x55]) + b"OBINexus::NSIGII::CONNECT"

    # Real-world noise: os.urandom produces high-entropy bytes
    noise_payload = os.urandom(32)

    # Silence: null bytes
    silence_payload = bytes(16)

    session = CalibrationSession()
    result = session.run([signal_payload, noise_payload, silence_payload])

    print("Result:")
    for k, v in result.items():
        val = v.name if isinstance(v, ByteState) else v
        print(f"  {k}: {val}")
