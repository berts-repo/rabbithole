// Centralized SSE manager — one EventSource per path, ref-counted across
// subscribers, with a global pause/resume hook for the Tor kill switch.
//
// Phase F1: lifecycle only. Consumers parse `event.data` themselves and
// own data shapes. Currently used by /api/crawl/events and /api/crawl/log
// once F3 wires them up; future B8 streams reuse the same manager.
//
// Scope: DATA-plane channels only. Control-plane channels (currently
// just /api/kill_switch/events) own their own EventSource so they are
// not affected by pauseAll() — otherwise a tripped kill switch would
// close the very stream that delivers its own recovery signal. See
// lib/pollers/killSwitch.svelte.ts.

export interface SseHandlers {
  /** Fires for unnamed events (the default "message" stream). */
  onMessage?: (event: MessageEvent) => void;
  /** Map of named event types → handler. Each one is attached as an
   *  addEventListener on the underlying EventSource. */
  onEvent?: Record<string, (event: MessageEvent) => void>;
  /** Fires on connection open. */
  onOpen?: (event: Event) => void;
  /** Fires on transport error. EventSource auto-reconnects unless we close
   *  it; the manager does not close on errors — that's the consumer's call
   *  if they want different behaviour. */
  onError?: (event: Event) => void;
}

interface Entry {
  source: EventSource;
  subscribers: Set<SseHandlers>;
  // Listener bookkeeping so pause() can detach and resume() can reattach
  // without losing handler identity.
  attached: { type: string; listener: EventListener }[];
}

class SseManager {
  #entries = new Map<string, Entry>();
  #paused = false;

  /**
   * Open (or share) an EventSource for `path`, attach handlers, and return
   * an `unsubscribe` callback. Last unsubscribe closes the connection.
   */
  subscribe(path: string, handlers: SseHandlers): () => void {
    let entry = this.#entries.get(path);
    if (!entry) {
      entry = {
        source: this.#open(path),
        subscribers: new Set(),
        attached: [],
      };
      this.#entries.set(path, entry);
    }

    entry.subscribers.add(handlers);
    this.#attachHandlers(entry, handlers);

    return () => this.#unsubscribe(path, handlers);
  }

  /** Close every open stream. Subscriber sets stay intact so resume() can
   *  reopen the same paths with the same handlers. */
  pauseAll(): void {
    if (this.#paused) return;
    this.#paused = true;
    for (const entry of this.#entries.values()) {
      this.#detachHandlers(entry);
      entry.source.close();
    }
  }

  /** Reopen every previously-paused stream and re-attach all handlers. */
  resumeAll(): void {
    if (!this.#paused) return;
    this.#paused = false;
    for (const [path, entry] of this.#entries) {
      entry.source = this.#open(path);
      for (const sub of entry.subscribers) {
        this.#attachHandlers(entry, sub);
      }
    }
  }

  /** Test helper. */
  get paused(): boolean {
    return this.#paused;
  }

  /** Test helper — how many paths are currently held open. */
  get openPaths(): string[] {
    return [...this.#entries.keys()];
  }

  // ---- internals ----

  #open(path: string): EventSource {
    // withCredentials so the session cookie travels on the SSE handshake.
    // The backend ApiAuthMiddleware enforces it on /api/* streams.
    return new EventSource(path, { withCredentials: true });
  }

  #attachHandlers(entry: Entry, handlers: SseHandlers): void {
    if (handlers.onOpen) {
      const l = handlers.onOpen as EventListener;
      entry.source.addEventListener('open', l);
      entry.attached.push({ type: 'open', listener: l });
    }
    if (handlers.onError) {
      const l = handlers.onError as EventListener;
      entry.source.addEventListener('error', l);
      entry.attached.push({ type: 'error', listener: l });
    }
    if (handlers.onMessage) {
      const l = handlers.onMessage as EventListener;
      entry.source.addEventListener('message', l);
      entry.attached.push({ type: 'message', listener: l });
    }
    if (handlers.onEvent) {
      for (const [type, fn] of Object.entries(handlers.onEvent)) {
        const l = fn as EventListener;
        entry.source.addEventListener(type, l);
        entry.attached.push({ type, listener: l });
      }
    }
  }

  #detachHandlers(entry: Entry): void {
    for (const { type, listener } of entry.attached) {
      entry.source.removeEventListener(type, listener);
    }
    entry.attached = [];
  }

  #unsubscribe(path: string, handlers: SseHandlers): void {
    const entry = this.#entries.get(path);
    if (!entry) return;
    entry.subscribers.delete(handlers);
    if (entry.subscribers.size === 0) {
      this.#detachHandlers(entry);
      entry.source.close();
      this.#entries.delete(path);
    }
  }
}

export const sse = new SseManager();
