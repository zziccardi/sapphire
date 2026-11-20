import { describe, expect, it } from 'vitest';
import { stripBase, withBase } from './url';

describe('url helpers', () => {
  it('prepends non-root base paths cleanly', () => {
    expect(withBase('/docs', '/sapphire/')).toBe('/sapphire/docs');
    expect(withBase('playground', '/sapphire')).toBe('/sapphire/playground');
    expect(withBase('/', '/sapphire/')).toBe('/sapphire/');
  });

  it('handles root base paths without double slashes', () => {
    expect(withBase('/docs', '/')).toBe('/docs');
    expect(withBase('examples', '')).toBe('/examples');
  });

  it('strips base path from pathname for active nav matching', () => {
    expect(stripBase('/sapphire/docs/spec', '/sapphire/')).toBe('/docs/spec');
    expect(stripBase('/sapphire/', '/sapphire/')).toBe('/');
    expect(stripBase('/docs', '/')).toBe('/docs');
  });
});
