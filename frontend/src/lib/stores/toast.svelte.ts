// Single-slot toast — last message wins, auto-dismisses after `ttlMs`.
// `pointer-events: none` is set in Toast.svelte; this store just owns
// the message + kind + a tick counter so the component can re-trigger
// its fade-in animation when the same message fires twice in a row.

export type ToastKind = 'info' | 'warn' | 'error';

interface ToastState {
  message: string | null;
  kind: ToastKind;
  tick: number;
}

const state = $state<ToastState>({
  message: null,
  kind: 'info',
  tick: 0,
});

let timer: ReturnType<typeof setTimeout> | null = null;

function clearTimer() {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}

export const toastStore = {
  get message() {
    return state.message;
  },
  get kind() {
    return state.kind;
  },
  get tick() {
    return state.tick;
  },

  show(message: string, kind: ToastKind = 'info', ttlMs = 4000) {
    clearTimer();
    state.message = message;
    state.kind = kind;
    state.tick += 1;
    timer = setTimeout(() => {
      state.message = null;
      timer = null;
    }, ttlMs);
  },

  dismiss() {
    clearTimer();
    state.message = null;
  },
};
