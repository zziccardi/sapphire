import { describe, expect, it } from 'vitest';
import { highlightCode } from './highlight';

describe('Sapphire Shiki highlighter', () => {
  it('highlights Sapphire keywords, types, and strings', async () => {
    const html = await highlightCode(
      'struct Player { let name: String; }\nfunc main() { print(f"Hi"); }',
      'sapphire',
    );
    expect(html).toContain('class="shiki');
    expect(html).toContain('struct');
    expect(html).toContain('Player');
    expect(html).toContain('--shiki-dark');
  });

  it('highlights Python and Lua targets', async () => {
    const py = await highlightCode('def main():\n    print("ok")', 'python');
    const lua = await highlightCode('local function main() print("ok") end', 'lua');
    expect(py).toContain('def');
    expect(lua).toContain('local');
  });

  it('highlights json, c, txt, and Sapphire f-strings with nested quotes', async () => {
    const jsonHtml = await highlightCode('{"a": 1}', 'json');
    const cHtml = await highlightCode('int x = 0;', 'c');
    const txtHtml = await highlightCode('plain', 'txt');
    const fstrHtml = await highlightCode('let s = f"val={m["k"]}";', 'sapphire');
    expect(jsonHtml).toContain('class="shiki');
    expect(cHtml).toContain('class="shiki');
    expect(txtHtml).toContain('plain');
    expect(fstrHtml).toContain('class="shiki');
  });
});
