// Service-level pill state: LLM worker, Tor reachability, kill switch,
// embed service. Pollers themselves land with F2 (header pills) — this
// store just owns the slots and wires the kill-switch effect to the SSE
// manager so a Tor outage doesn't leave streams hammering a dead proxy.
//
// Kill switch FSM (frontend-owned):
//   armed         → normal, network activity allowed
//   tripped       → safety on, all SSE streams paused, pollers skip
//   cleared_idle  → safety cleared (Tor recovered) but no auto-resume;
//                   the analyst must explicitly re-arm before traffic
//                   restarts. This is the difference between a safety
//                   device and a pause button.
//
// Backend events drive transitions:
//   kill_switch.engaged → armed/cleared_idle → tripped (reason=tor_lost)
//   kill_switch.clear   → tripped → cleared_idle
// User action drives armed re-entry from cleared_idle.

import { sse } from '$lib/sse.svelte';

interface LlmState {
  running: boolean;
  queueDepth: number;
  lastPoll: number | null;
}

interface TorState {
  reachable: boolean;
  lastPoll: number | null;
  /** Latches `true` the first time a probe reports Tor reachable in this
   *  session. Distinguishes a fresh-load "never connected" state from a
   *  mid-session drop so the kill-switch modal can pick the right copy. */
  everReachable: boolean;
}

export type KillSwitchPhase = 'armed' | 'tripped' | 'cleared_idle';
export type KillSwitchReason = 'tor_lost' | null;

interface KillSwitchState {
  /** Enforcement setting — when false, a Tor drop only warns, doesn't
   *  cancel tasks. Persisted server-side as `tor.kill_switch`. */
  enabled: boolean;
  /** Current FSM phase. */
  phase: KillSwitchPhase;
  /** Reason for the most recent trip. Cleared on re-arm. */
  reason: KillSwitchReason;
}

interface EmbedState {
  running: boolean;
  paused: boolean;
}

interface ServicesState {
  llm: LlmState;
  tor: TorState;
  killSwitch: KillSwitchState;
  embed: EmbedState;
}

const state = $state<ServicesState>({
  llm: { running: false, queueDepth: 0, lastPoll: null },
  tor: { reachable: false, lastPoll: null, everReachable: false },
  killSwitch: { enabled: true, phase: 'armed', reason: null },
  embed: { running: false, paused: false },
});

function applyKillSwitchSse(): void {
  // Tripped AND cleared_idle keep streams paused. Only an explicit
  // re-arm (user action) reopens them. This mirrors backend behaviour
  // — the backend cancelled in-flight tasks on trip; we don't keep
  // listening to closed streams, and we don't auto-resume on recovery
  // because that defeats the point of a safety device.
  if (state.killSwitch.phase === 'armed') {
    sse.resumeAll();
  } else {
    sse.pauseAll();
  }
}

export const servicesStore = {
  get llm() {
    return state.llm;
  },
  get tor() {
    return state.tor;
  },
  get killSwitch() {
    return state.killSwitch;
  },
  get embed() {
    return state.embed;
  },

  setLlm(patch: Partial<LlmState>) {
    state.llm = { ...state.llm, ...patch };
  },
  setTor(patch: Partial<TorState>) {
    const everReachable = state.tor.everReachable || patch.reachable === true;
    state.tor = { ...state.tor, ...patch, everReachable };
  },
  /** Update the enforcement setting only. Phase is driven by SSE/user
   *  actions, never by this setter. */
  setKillSwitchEnabled(enabled: boolean): void {
    state.killSwitch = { ...state.killSwitch, enabled };
  },
  /** Trip the FSM. Idempotent — re-trip with a new reason updates the
   *  reason but does not re-fire the pause side effect. */
  tripKillSwitch(reason: KillSwitchReason): void {
    if (state.killSwitch.phase === 'tripped') {
      state.killSwitch = { ...state.killSwitch, reason };
      return;
    }
    state.killSwitch = { ...state.killSwitch, phase: 'tripped', reason };
    applyKillSwitchSse();
  },
  /** Backend reports the trip condition cleared (Tor recovered). Move to
   *  cleared_idle so the analyst must re-arm explicitly. No-op when
   *  already armed (initial state). */
  clearKillSwitch(): void {
    if (state.killSwitch.phase !== 'tripped') return;
    state.killSwitch = { ...state.killSwitch, phase: 'cleared_idle' };
    // Stay paused — applyKillSwitchSse leaves streams closed.
  },
  /** Re-arm. Called from the modal's Acknowledge → Resume flow or from
   *  the toolbar inline Resume button. Resumes SSE streams. */
  armKillSwitch(): void {
    if (state.killSwitch.phase === 'armed') return;
    state.killSwitch = { ...state.killSwitch, phase: 'armed', reason: null };
    applyKillSwitchSse();
  },
  setEmbed(patch: Partial<EmbedState>) {
    state.embed = { ...state.embed, ...patch };
  },
};
