// Collection routes — list/create were the F3 minimum; F7 (Collection
// sub-tab) adds get-with-items, patch, delete, and the export-URL
// builder used by the download dropdown.

import { apiFetch, BASE, qs } from './core';
import type {
  AddItemsResult,
  Collection,
  CollectionDetail,
  CollectionExportFormat,
  CollectionListRow,
  CreateCollectionBody,
  NodeCollection,
  UpdateCollectionBody,
} from './types';

// The list route returns each row joined with its membership count.
export const listCollections = () =>
  apiFetch<{ collections: CollectionListRow[] }>('/collections');

// Membership lookup for the right panel Page tab's collections section.
export const listNodeCollections = (nodeId: number) =>
  apiFetch<{ collections: NodeCollection[] }>(`/nodes/${nodeId}/collections`);

export const createCollection = (body: CreateCollectionBody) =>
  apiFetch<{ id: number; name: string }>('/collections', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const getCollection = (cid: number) =>
  apiFetch<CollectionDetail>(`/collections/${cid}`);

export const patchCollection = (cid: number, body: UpdateCollectionBody) =>
  apiFetch<Collection>(`/collections/${cid}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });

export const deleteCollection = (cid: number) =>
  apiFetch<{ ok: true }>(`/collections/${cid}`, { method: 'DELETE' });

// Batch membership add — accepts one or many node ids.
export const addItemsToCollection = (cid: number, node_ids: number[]) =>
  apiFetch<AddItemsResult>(`/collections/${cid}/items`, {
    method: 'POST',
    body: JSON.stringify({ node_ids }),
  });

export const removeItemFromCollection = (cid: number, nodeId: number) =>
  apiFetch<{ ok: true }>(`/collections/${cid}/items/${nodeId}`, {
    method: 'DELETE',
  });

// Backend serves the file with the right Content-Disposition; we just
// need a same-origin URL the browser can hit. Returns the absolute /api
// path so an <a download> works from any view.
export function collectionExportUrl(
  cid: number,
  format: CollectionExportFormat,
): string {
  return `${BASE}/collections/${cid}/export${qs({ format })}`;
}
