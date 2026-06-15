import { describe, it, expect } from 'vitest';
import {
  labelCreateName,
  labelPickerModal,
  labelTargetIdentity,
  type LabelTarget,
} from './labels';

describe('labelTargetIdentity', () => {
  it('labels a domain target with its host', () => {
    const target: LabelTarget = { kind: 'domain', host: 'abc.onion' };
    expect(labelTargetIdentity(target)).toEqual({
      label: 'Domain',
      value: 'abc.onion',
    });
  });

  it('labels a resource target with its name', () => {
    const target: LabelTarget = { kind: 'resource', resourceId: 7, name: 'Vendor X' };
    expect(labelTargetIdentity(target)).toEqual({ label: 'Page', value: 'Vendor X' });
  });
});

describe('labelPickerModal', () => {
  it('carries the target, anchor, and current ids', () => {
    const target: LabelTarget = { kind: 'resource', resourceId: 3, name: 'P' };
    const modal = labelPickerModal(target, { x: 10, y: 20 }, [1, 2]);
    expect(modal).toEqual({
      kind: 'labelPicker',
      x: 10,
      y: 20,
      target,
      currentIds: [1, 2],
    });
  });
});

describe('labelCreateName', () => {
  it('offers the trimmed name when no existing label matches', () => {
    expect(labelCreateName('  Leak site ', ['Market', 'Forum'])).toBe('Leak site');
  });

  it('returns null for an empty / whitespace-only query', () => {
    expect(labelCreateName('', ['Market'])).toBeNull();
    expect(labelCreateName('   ', ['Market'])).toBeNull();
  });

  it('returns null when the name already exists (case-insensitive)', () => {
    expect(labelCreateName('market', ['Market', 'Forum'])).toBeNull();
    expect(labelCreateName('FORUM', ['Market', 'Forum'])).toBeNull();
  });
});
