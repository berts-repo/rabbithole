import { describe, it, expect, vi } from 'vitest';
import { createContextMenuAdapter } from './contextMenuAdapter';
import type { ContextMenuAdapterDeps, NodeMenuState, EdgeMenuState } from './contextMenuAdapter';
import type { GraphNode } from '$lib/api';

function makeNode(overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id: 1,
    label: 'Node 1',
    alias: null,
    title_text: 'Node 1 Title',
    raw_url: 'http://test.onion/page',
    color: '#2eb89a',
    domain: 'test.onion',
    network: 'tor',
    depth: 1,
    flag_status: null,
    is_bridge: false,
    betweenness: 0,
    pagerank: 0,
    cluster_id: null,
    infra_cluster_id: null,
    first_seen: null,
    is_cluster: false,
    state: 'crawled',
    analysis_excluded: false,
    reviewed: false,
    category: null,
    in_degree_count: 0,
    out_degree_count: 0,
    label_ids: [],
    domain_label_ids: [],
    ...overrides,
  };
}

function makeDeps(overrides: Partial<ContextMenuAdapterDeps> = {}): ContextMenuAdapterDeps {
  const node1 = makeNode();
  const node2 = makeNode({ id: 2, label: 'Node 2' });
  return {
    isTorArmed: () => false,
    lookupNode: (id) => (id === 1 ? node1 : id === 2 ? node2 : undefined),
    selectedGraphNodes: () => [node1, node2],
    actCopyUrl: vi.fn(),
    actOpenInTor: vi.fn(),
    actQueueCrawl: vi.fn(),
    actSaveSeedBookmark: vi.fn(),
    actFlag: vi.fn(),
    actRemoveFlag: vi.fn(),
    actToggleReviewed: vi.fn(),
    actFocus: vi.fn(),
    actHideFromGraph: vi.fn(),
    isDomainCollapsed: () => false,
    toggleCollapseDomain: vi.fn(),
    isPinned: () => false,
    actTogglePin: vi.fn(),
    openMonitorModal: vi.fn(),
    openRenamePopover: vi.fn(),
    openLabelPicker: vi.fn(),
    queueAnalysisForNodes: vi.fn(),
    openCollectionModal: vi.fn(),
    openEdgeModal: vi.fn(),
    openSelectionAsTab: vi.fn(),
    actCrawlSelected: vi.fn(),
    actFlagAll: vi.fn(),
    actMarkReviewedAll: vi.fn(),
    actHideAll: vi.fn(),
    actDeleteAnalystEdge: vi.fn().mockResolvedValue(undefined),
    lookupEdgeRaw: (key) =>
      key === 'analyst-edge'
        ? { from: 1, to: 2, source: 'analyst', label: null }
        : key === 'crawl-edge'
          ? { from: 1, to: 2, source: 'crawl', label: null }
          : undefined,
    ...overrides,
  };
}

const singleMenu: NodeMenuState = { x: 100, y: 200, nodeId: 1, mode: 'single' };
const multiMenu: NodeMenuState = { x: 100, y: 200, nodeId: 1, mode: 'multi' };
const analystEdge: EdgeMenuState = { x: 50, y: 60, edgeKey: 'analyst-edge' };
const crawlEdge: EdgeMenuState = { x: 50, y: 60, edgeKey: 'crawl-edge' };
const missingEdge: EdgeMenuState = { x: 50, y: 60, edgeKey: 'no-edge' };

describe('contextMenuAdapter', () => {
  it('buildNodeMenuSections returns null for missing node', () => {
    const adapter = createContextMenuAdapter(makeDeps({ lookupNode: () => undefined }));
    expect(adapter.buildNodeMenuSections(singleMenu, new Set())).toBeNull();
  });

  it('buildNodeMenuSections single mode returns sections', () => {
    const adapter = createContextMenuAdapter(makeDeps());
    const sections = adapter.buildNodeMenuSections(singleMenu, new Set([1]));
    expect(sections).not.toBeNull();
    expect(Array.isArray(sections)).toBe(true);
    expect(sections!.length).toBeGreaterThan(0);
  });

  it('buildNodeMenuSections multi mode returns sections', () => {
    const adapter = createContextMenuAdapter(makeDeps());
    const sections = adapter.buildNodeMenuSections(multiMenu, new Set([1, 2]));
    expect(sections).not.toBeNull();
    expect(Array.isArray(sections)).toBe(true);
    expect(sections!.length).toBeGreaterThan(0);
  });

  it('buildEdgeMenuSections returns null for crawl edge', () => {
    const adapter = createContextMenuAdapter(makeDeps());
    expect(adapter.buildEdgeMenuSections(crawlEdge)).toBeNull();
  });

  it('buildEdgeMenuSections returns null for missing edge', () => {
    const adapter = createContextMenuAdapter(makeDeps());
    expect(adapter.buildEdgeMenuSections(missingEdge)).toBeNull();
  });

  it('buildEdgeMenuSections returns delete item for analyst edge', () => {
    const adapter = createContextMenuAdapter(makeDeps());
    const sections = adapter.buildEdgeMenuSections(analystEdge);
    expect(sections).not.toBeNull();
    expect(sections!.length).toBe(1);
    expect(sections![0].items[0].label).toBe('Delete analyst edge');
  });

  it('delete analyst edge action calls actDeleteAnalystEdge', async () => {
    const actDeleteAnalystEdge = vi.fn().mockResolvedValue(undefined);
    const adapter = createContextMenuAdapter(makeDeps({ actDeleteAnalystEdge }));
    const sections = adapter.buildEdgeMenuSections(analystEdge)!;
    await sections[0].items[0].onSelect();
    expect(actDeleteAnalystEdge).toHaveBeenCalledWith(
      expect.objectContaining({ source: 'analyst' }),
    );
  });

  it('single menu copyUrl handler calls actCopyUrl', () => {
    const actCopyUrl = vi.fn();
    const adapter = createContextMenuAdapter(makeDeps({ actCopyUrl }));
    const sections = adapter.buildNodeMenuSections(singleMenu, new Set([1]))!;
    // Find the copy URL item across all sections
    const allItems = sections.flatMap((s) => s.items);
    const copyItem = allItems.find((item) => item.label.toLowerCase().includes('copy'));
    expect(copyItem).toBeDefined();
    copyItem!.onSelect();
    expect(actCopyUrl).toHaveBeenCalledWith('http://test.onion/page');
  });

  it('multi menu openCollectionModal is wired', () => {
    const openCollectionModal = vi.fn();
    const adapter = createContextMenuAdapter(makeDeps({ openCollectionModal }));
    const sections = adapter.buildNodeMenuSections(multiMenu, new Set([1, 2]))!;
    const allItems = sections.flatMap((s) => s.items);
    const collItem = allItems.find((item) => item.label.toLowerCase().includes('collection'));
    expect(collItem).toBeDefined();
    collItem!.onSelect();
    expect(openCollectionModal).toHaveBeenCalled();
  });
});
