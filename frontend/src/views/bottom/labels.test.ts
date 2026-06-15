import { describe, it, expect } from 'vitest';
import type { LabelDomainMember, LabelResourceMember } from '$lib/api';
import { domainDisplayName, labelTabLabel, memberDisplayName } from './labels';

const resource = (over: Partial<LabelResourceMember>): LabelResourceMember => ({
  id: 1,
  url: 'http://abc.onion/p',
  host: 'abc.onion',
  alias: null,
  title: null,
  ...over,
});

describe('memberDisplayName', () => {
  it('prefers the alias, then title, then url', () => {
    expect(memberDisplayName(resource({ alias: 'Vendor X', title: 'T' }))).toBe(
      'Vendor X',
    );
    expect(memberDisplayName(resource({ title: 'Front page' }))).toBe('Front page');
    expect(memberDisplayName(resource({}))).toBe('http://abc.onion/p');
  });

  it('ignores whitespace-only alias/title', () => {
    expect(memberDisplayName(resource({ alias: '   ', title: 'T' }))).toBe('T');
  });
});

describe('domainDisplayName', () => {
  it('prefers the alias, else the host', () => {
    const d = (over: Partial<LabelDomainMember>): LabelDomainMember => ({
      host: 'abc.onion',
      alias: null,
      ...over,
    });
    expect(domainDisplayName(d({ alias: 'NightMarket' }))).toBe('NightMarket');
    expect(domainDisplayName(d({}))).toBe('abc.onion');
  });
});

describe('labelTabLabel', () => {
  it('prefixes the label name', () => {
    expect(labelTabLabel('Market')).toBe('Label: Market');
  });
});
