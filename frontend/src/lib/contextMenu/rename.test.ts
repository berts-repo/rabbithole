import { describe, it, expect } from 'vitest';
import {
  renameModal,
  renameTargetIdentity,
  type RenameTarget,
} from './rename';

describe('renameTargetIdentity', () => {
  it('labels a domain target with its host', () => {
    const target: RenameTarget = { kind: 'domain', host: 'abc.onion' };
    expect(renameTargetIdentity(target)).toEqual({
      label: 'Domain',
      value: 'abc.onion',
    });
  });

  it('labels a page target with its id', () => {
    const target: RenameTarget = { kind: 'page', pageId: 42 };
    expect(renameTargetIdentity(target)).toEqual({
      label: 'Page',
      value: '#42',
    });
  });
});

describe('renameModal', () => {
  it('builds a rename modal carrying the target, anchor, and current name', () => {
    const target: RenameTarget = { kind: 'domain', host: 'abc.onion' };
    const modal = renameModal(target, { x: 10, y: 20 }, 'My alias');
    expect(modal).toEqual({
      kind: 'rename',
      x: 10,
      y: 20,
      target,
      currentName: 'My alias',
    });
  });

  it('carries a null current name through unchanged (unset alias)', () => {
    const modal = renameModal({ kind: 'page', pageId: 7 }, { x: 0, y: 0 }, null);
    expect(modal.currentName).toBeNull();
    expect(modal.target).toEqual({ kind: 'page', pageId: 7 });
  });
});
