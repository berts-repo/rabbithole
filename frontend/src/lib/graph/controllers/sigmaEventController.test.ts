import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createSigmaEventController } from './sigmaEventController';
import type { SigmaEventControllerDeps } from './sigmaEventController';

// Minimal Sigma event emitter mock
type EventHandler = (...args: unknown[]) => void;
function makeSigmaMock() {
  const handlers: Record<string, EventHandler[]> = {};
  const captorHandlers: Record<string, EventHandler[]> = {};

  const captor = {
    on: (event: string, handler: EventHandler) => {
      if (!captorHandlers[event]) captorHandlers[event] = [];
      captorHandlers[event].push(handler);
    },
    emit: (event: string, ...args: unknown[]) => {
      (captorHandlers[event] ?? []).forEach((h) => h(...args));
    },
  };

  return {
    on: (event: string, handler: EventHandler) => {
      if (!handlers[event]) handlers[event] = [];
      handlers[event].push(handler);
    },
    emit: (event: string, ...args: unknown[]) => {
      (handlers[event] ?? []).forEach((h) => h(...args));
    },
    getMouseCaptor: () => captor,
    getCamera: () => ({ disable: vi.fn(), enable: vi.fn() }),
    viewportToGraph: (coords: { x: number; y: number }) => coords,
  };
}

function keyHandler(addEvt: ReturnType<typeof vi.fn>): (event: KeyboardEvent) => void {
  return addEvt.mock.calls.find(([event]) => event === 'keydown')?.[1] as (event: KeyboardEvent) => void;
}

function makeDeps(overrides: Partial<SigmaEventControllerDeps> = {}): SigmaEventControllerDeps {
  return {
    setHover: vi.fn(),
    highlight: vi.fn(),
    toggleCluster: vi.fn(),
    clearSelection: vi.fn(),
    multiCount: () => 0,
    isSelected: () => false,
    onNodeClick: vi.fn(),
    onNodeMenu: vi.fn(),
    onEdgeMenu: vi.fn(),
    clearMenus: vi.fn(),
    drawEdgeActive: () => false,
    drawEdgeSource: () => null,
    onDrawEdgeOutcome: vi.fn(),
    toggleDomainExpanded: vi.fn(),
    isGroupByDomain: () => false,
    isDomainFoldCollapsed: () => false,
    expandDomainFold: vi.fn(),
    expandLabelFold: vi.fn(),
    lookupNode: (id: number) => ({ id, raw_url: `http://n${id}.onion`, label: `N${id}` } as ReturnType<SigmaEventControllerDeps['lookupNode']>),
    lookupNodeDomain: () => null,
    lookupEdgeRaw: () => undefined,
    getNodePayloadCount: () => 0,
    onEscape: vi.fn(),
    onSelectAll: vi.fn(),
    onFocusNode: vi.fn(),
    getHoveredNode: () => null,
    visibleNodeCount: () => 10,
    selectedNodeId: () => null,
    setNodePosition: vi.fn(),
    setNodeUserPositioned: vi.fn(),
    refresh: vi.fn(),
    onAfterRender: vi.fn(),
    // Use no-op event listener to avoid touching document in tests
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    ...overrides,
  };
}

describe('sigmaEventController', () => {
  let sigma: ReturnType<typeof makeSigmaMock>;

  beforeEach(() => {
    sigma = makeSigmaMock();
  });

  it('bind registers keydown listener', () => {
    const addEvt = vi.fn();
    const deps = makeDeps({ addEventListener: addEvt });
    const ctrl = createSigmaEventController(deps);
    ctrl.bind(sigma as never);
    expect(addEvt).toHaveBeenCalledWith('keydown', expect.any(Function));
  });

  it('unbind removes keydown listener', () => {
    const removeEvt = vi.fn();
    const deps = makeDeps({ removeEventListener: removeEvt });
    const ctrl = createSigmaEventController(deps);
    ctrl.bind(sigma as never);
    ctrl.unbind();
    expect(removeEvt).toHaveBeenCalledWith('keydown', expect.any(Function));
  });

  it('Ctrl+A selects all visible nodes on normal graph targets', () => {
    const addEvt = vi.fn();
    const onSelectAll = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ addEventListener: addEvt, onSelectAll }));
    ctrl.bind(sigma as never);
    const preventDefault = vi.fn();

    keyHandler(addEvt)({
      key: 'a',
      ctrlKey: true,
      metaKey: false,
      altKey: false,
      target: { tagName: 'DIV', isContentEditable: false, closest: () => null },
      preventDefault,
    } as unknown as KeyboardEvent);

    expect(preventDefault).toHaveBeenCalled();
    expect(onSelectAll).toHaveBeenCalledWith(10);
  });

  it('does not trap Ctrl+A inside terminal surfaces', () => {
    const addEvt = vi.fn();
    const onSelectAll = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ addEventListener: addEvt, onSelectAll }));
    ctrl.bind(sigma as never);
    const preventDefault = vi.fn();

    keyHandler(addEvt)({
      key: 'a',
      ctrlKey: true,
      metaKey: false,
      altKey: false,
      target: {
        tagName: 'DIV',
        isContentEditable: false,
        closest: (selector: string) => selector.includes('[role="terminal"]') ? {} : null,
      },
      preventDefault,
    } as unknown as KeyboardEvent);

    expect(preventDefault).not.toHaveBeenCalled();
    expect(onSelectAll).not.toHaveBeenCalled();
  });

  it('enterNode calls setHover', () => {
    const setHover = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ setHover }));
    ctrl.bind(sigma as never);
    sigma.emit('enterNode', { node: '42' });
    expect(setHover).toHaveBeenCalledWith('42');
  });

  it('leaveNode calls setHover(null)', () => {
    const setHover = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ setHover }));
    ctrl.bind(sigma as never);
    sigma.emit('leaveNode', {});
    expect(setHover).toHaveBeenCalledWith(null);
  });

  it('clickNode on plain node calls highlight and onNodeClick', () => {
    const highlight = vi.fn();
    const onNodeClick = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ highlight, onNodeClick }));
    ctrl.bind(sigma as never);
    sigma.emit('clickNode', { node: '5', event: { original: null } });
    expect(highlight).toHaveBeenCalledWith(5);
    expect(onNodeClick).toHaveBeenCalledWith(5);
  });

  it('clickNode with ctrl modifier calls toggleCluster', () => {
    const toggleCluster = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ toggleCluster }));
    ctrl.bind(sigma as never);
    const mockMouseEvent = { ctrlKey: true, metaKey: false, shiftKey: false } as MouseEvent;
    sigma.emit('clickNode', { node: '5', event: { original: mockMouseEvent } });
    expect(toggleCluster).toHaveBeenCalledWith(5);
  });

  it('clickStage calls clearSelection', () => {
    const clearSelection = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ clearSelection }));
    ctrl.bind(sigma as never);
    sigma.emit('clickStage', {});
    expect(clearSelection).toHaveBeenCalled();
  });

  it('rightClickNode fires onNodeMenu with single mode', () => {
    const onNodeMenu = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ onNodeMenu }));
    ctrl.bind(sigma as never);
    sigma.emit('rightClickNode', {
      node: '7',
      event: { x: 100, y: 200, preventSigmaDefault: vi.fn(), original: { preventDefault: vi.fn() } },
    });
    expect(onNodeMenu).toHaveBeenCalledWith(expect.objectContaining({ nodeId: 7, mode: 'single' }));
  });

  it('rightClickNode fires multi mode when part of multi-selection', () => {
    const onNodeMenu = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({
      onNodeMenu,
      multiCount: () => 2,
      isSelected: (id) => id === 7,
    }));
    ctrl.bind(sigma as never);
    sigma.emit('rightClickNode', {
      node: '7',
      event: { x: 100, y: 200, preventSigmaDefault: vi.fn(), original: { preventDefault: vi.fn() } },
    });
    expect(onNodeMenu).toHaveBeenCalledWith(expect.objectContaining({ mode: 'multi' }));
  });

  it('double-clicking a label cluster un-collapses that label', () => {
    const expandLabelFold = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ expandLabelFold }));
    ctrl.bind(sigma as never);
    sigma.emit('doubleClickNode', { node: 'cluster:label:5', event: { preventSigmaDefault: vi.fn() } });
    expect(expandLabelFold).toHaveBeenCalledWith(5);
  });

  it('double-clicking a selectively-folded domain expands it persistently', () => {
    const expandDomainFold = vi.fn();
    const toggleDomainExpanded = vi.fn();
    const ctrl = createSigmaEventController(
      makeDeps({ expandDomainFold, toggleDomainExpanded, isDomainFoldCollapsed: () => true }),
    );
    ctrl.bind(sigma as never);
    sigma.emit('doubleClickNode', { node: 'cluster:x.onion', event: { preventSigmaDefault: vi.fn() } });
    expect(expandDomainFold).toHaveBeenCalledWith('x.onion');
    expect(toggleDomainExpanded).not.toHaveBeenCalled();
  });

  it('double-clicking a groupByDomain fold uses the transient exception set', () => {
    const expandDomainFold = vi.fn();
    const toggleDomainExpanded = vi.fn();
    const ctrl = createSigmaEventController(
      makeDeps({ expandDomainFold, toggleDomainExpanded, isDomainFoldCollapsed: () => false }),
    );
    ctrl.bind(sigma as never);
    sigma.emit('doubleClickNode', { node: 'cluster:x.onion', event: { preventSigmaDefault: vi.fn() } });
    expect(toggleDomainExpanded).toHaveBeenCalledWith('x.onion');
    expect(expandDomainFold).not.toHaveBeenCalled();
  });

  it('rightClickEdge with analyst edge fires onEdgeMenu', () => {
    const onEdgeMenu = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({
      onEdgeMenu,
      lookupEdgeRaw: () => ({ from: 1, to: 2, source: 'analyst', label: null }),
    }));
    ctrl.bind(sigma as never);
    sigma.emit('rightClickEdge', {
      edge: 'e1',
      event: { x: 10, y: 20, preventSigmaDefault: vi.fn(), original: { preventDefault: vi.fn() } },
    });
    expect(onEdgeMenu).toHaveBeenCalledWith({ x: 10, y: 20, edgeKey: 'e1' });
  });

  it('rightClickEdge with crawl edge does not fire onEdgeMenu', () => {
    const onEdgeMenu = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({
      onEdgeMenu,
      lookupEdgeRaw: () => ({ from: 1, to: 2, source: 'crawl', label: null }),
    }));
    ctrl.bind(sigma as never);
    sigma.emit('rightClickEdge', {
      edge: 'e1',
      event: { x: 10, y: 20, preventSigmaDefault: vi.fn(), original: { preventDefault: vi.fn() } },
    });
    expect(onEdgeMenu).not.toHaveBeenCalled();
  });

  it('afterRender calls onAfterRender', () => {
    const onAfterRender = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ onAfterRender }));
    ctrl.bind(sigma as never);
    sigma.emit('afterRender', {});
    expect(onAfterRender).toHaveBeenCalled();
  });

  it('drag: downNode + mousemovebody past threshold sets node position', () => {
    const setNodePosition = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ setNodePosition }));
    ctrl.bind(sigma as never);

    // Start drag
    sigma.emit('downNode', {
      node: '3',
      event: { x: 10, y: 10, original: { button: 0 } },
    });
    // Move past threshold (4px)
    sigma.getMouseCaptor().emit('mousemovebody', {
      x: 15,
      y: 15,
      preventSigmaDefault: vi.fn(),
      original: { preventDefault: vi.fn(), stopPropagation: vi.fn() },
    });
    expect(setNodePosition).toHaveBeenCalledWith('3', expect.any(Number), expect.any(Number));
  });

  it('drag below threshold does not set node position', () => {
    const setNodePosition = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ setNodePosition }));
    ctrl.bind(sigma as never);

    sigma.emit('downNode', {
      node: '3',
      event: { x: 10, y: 10, original: { button: 0 } },
    });
    // Move only 2px — below the 4px threshold
    sigma.getMouseCaptor().emit('mousemovebody', {
      x: 12,
      y: 10,
      preventSigmaDefault: vi.fn(),
      original: { preventDefault: vi.fn(), stopPropagation: vi.fn() },
    });
    expect(setNodePosition).not.toHaveBeenCalled();
  });

  it('mouseup after drag sets userPositioned', () => {
    const setNodeUserPositioned = vi.fn();
    const ctrl = createSigmaEventController(makeDeps({ setNodeUserPositioned }));
    ctrl.bind(sigma as never);

    sigma.emit('downNode', {
      node: '3',
      event: { x: 10, y: 10, original: { button: 0 } },
    });
    sigma.getMouseCaptor().emit('mousemovebody', {
      x: 20, y: 20,
      preventSigmaDefault: vi.fn(),
      original: { preventDefault: vi.fn(), stopPropagation: vi.fn() },
    });
    sigma.getMouseCaptor().emit('mouseup', {});
    expect(setNodeUserPositioned).toHaveBeenCalledWith('3');
  });
});
