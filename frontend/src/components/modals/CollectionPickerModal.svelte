<script lang="ts">
  // Add to Collection modal — opened from the multi-select right-click
  // menu. Adds every selected node (stubs and crawled) to one collection,
  // chosen via the shared CollectionPicker. Spec: explore-graph.md:156,198.

  import Modal from './Modal.svelte';
  import CollectionPicker from '../CollectionPicker.svelte';
  import { addItemsToCollection } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  interface Props {
    // Just the ids: the modal only ever adds by id, so any surface holding
    // node ids (graph multi-select, a freshly-created Search stub) can open it.
    nodeIds: number[];
    onClose: () => void;
  }

  let { nodeIds, onClose }: Props = $props();

  let collectionId = $state<number | null>(null);
  let busy = $state(false);

  async function submit(): Promise<void> {
    if (busy || collectionId === null) return;
    busy = true;
    try {
      const res = await addItemsToCollection(collectionId, nodeIds);
      toastStore.show(
        res.skipped > 0
          ? `Added ${res.added} node(s) — ${res.skipped} already in collection`
          : `Added ${res.added} node(s) to collection`,
      );
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Add to collection failed: ${msg}`, 'error');
      busy = false;
    }
  }
</script>

<Modal
  title="Add to Collection"
  {onClose}
  onConfirm={() => void submit()}
  confirmLabel={`Add (${nodeIds.length})`}
  confirmDisabled={collectionId === null}
  {busy}
>
  <label class="row">
    <span>Collection</span>
    <CollectionPicker
      value={collectionId}
      onChange={(id) => (collectionId = id)}
    />
  </label>
  <p class="hint">
    <span class="count">{nodeIds.length}</span> node(s) will be added.
  </p>
</Modal>
