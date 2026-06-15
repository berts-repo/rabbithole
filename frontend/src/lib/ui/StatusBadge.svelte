<script lang="ts">
  // Shared status badge pill.
  //
  // Variants map to the analysis + crawl-queue status vocabulary.
  // The `running` variant adds a pulsing dot (same animation used
  // previously in AnalysisTab.svelte and the bottom-pane Activity tab).
  //
  // Usage:
  //   <StatusBadge status="running" />
  //   <StatusBadge status="done" label="complete" />

  type Variant =
    | 'pending'
    | 'running'
    | 'done'
    | 'failed'
    | 'cancelled'
    | 'paused'
    | 'warning'
    | 'skipped'
    | 'queued';

  interface Props {
    status: Variant;
    /** Override display label. Defaults to the status string. */
    label?: string;
    /** Optional tooltip text. */
    tooltip?: string;
  }

  const { status, label, tooltip }: Props = $props();

  const displayLabel = $derived(label ?? status);

  // Map variant → tone class
  type Tone = 'good' | 'warn' | 'live' | 'wait' | 'bad' | 'neutral';

  function tone(s: Variant): Tone {
    switch (s) {
      case 'done':
        return 'good';
      case 'running':
        return 'live';
      case 'failed':
        return 'bad';
      case 'warning':
        return 'warn';
      case 'pending':
      case 'paused':
        return 'wait';
      case 'cancelled':
      case 'skipped':
      case 'queued':
        return 'neutral';
    }
  }

  const t = $derived(tone(status));
  const pulsing = $derived(status === 'running');
</script>

<span class="badge tone-{t}" title={tooltip ?? displayLabel}>
  {#if pulsing}
    <span class="dot" aria-hidden="true"></span>
  {/if}
  {displayLabel}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 6px;
    border-radius: 8px;
    border: 1px solid;
    font-size: 10px;
    text-transform: lowercase;
    white-space: nowrap;
    user-select: none;
  }

  /* Tones */
  .tone-good {
    color: var(--accent);
    border-color: var(--accent);
    background: rgba(0, 212, 170, 0.1);
  }
  .tone-live {
    color: var(--accent);
    border-color: var(--accent);
    background: rgba(0, 212, 170, 0.18);
  }
  .tone-wait {
    color: #b08a3a;
    border-color: #6e562a;
    background: transparent;
    opacity: 0.85;
  }
  .tone-warn {
    color: #e0b860;
    border-color: #b08a3a;
    background: rgba(176, 138, 58, 0.1);
  }
  .tone-bad {
    color: #ff6b6b;
    border-color: #a83232;
    background: rgba(168, 50, 50, 0.12);
  }
  .tone-neutral {
    color: var(--muted);
    border-color: var(--border);
    background: transparent;
  }

  /* Pulsing dot for running state */
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse 1.2s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
</style>
