#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$HOME/.local/bin" "$HOME/.local/lib"
touch "$HOME/.bashrc"

# Ensure ~/.bashrc runs in non-interactive shells and exports tool paths.
sed -i '/case \$- in/,/esac/d' "$HOME/.bashrc" 2>/dev/null || true

add_bashrc_line() {
  local line="$1"
  grep -qxF "$line" "$HOME/.bashrc" || echo "$line" >> "$HOME/.bashrc"
}

add_bashrc_line 'export LANG=C.UTF-8'
add_bashrc_line 'export PATH="$HOME/.local/bin:$PATH"'
add_bashrc_line 'export SAPPHIRE_BIN="$HOME/.local/bin/sapphire"'
add_bashrc_line 'export LUA_PATH="./?.lua;./?/init.lua;$HOME/.local/share/lua/5.1/?.lua;$HOME/.local/share/lua/5.1/?/init.lua;;"'
add_bashrc_line 'export LUA_CPATH="./?.so;$HOME/.local/lib/lua/5.1/?.so;;"'
add_bashrc_line 'export LUA_INIT='\''local ok, u = pcall(require, "lua-utf8"); if ok then _G.utf8 = u; package.preload["utf8"] = function() return u end end'\'''

sed -i '/^export SAPPHIRE_HOME=/d' "$HOME/.bashrc"
echo "export SAPPHIRE_HOME=\"$REPO_ROOT\"" >> "$HOME/.bashrc"

export LANG=C.UTF-8
export PATH="$HOME/.local/bin:$PATH"
export SAPPHIRE_HOME="$REPO_ROOT"
export SAPPHIRE_BIN="$HOME/.local/bin/sapphire"
export LUA_PATH="./?.lua;./?/init.lua;$HOME/.local/share/lua/5.1/?.lua;$HOME/.local/share/lua/5.1/?/init.lua;;"
export LUA_CPATH="./?.so;$HOME/.local/lib/lua/5.1/?.so;;"
export LUA_INIT='local ok, u = pcall(require, "lua-utf8"); if ok then _G.utf8 = u; package.preload["utf8"] = function() return u end end'

# 1. Python 3.14 & Pipenv via uv
if [ ! -x "$HOME/.local/bin/python3.14" ]; then
  uv python install 3.14 --default
fi
if [ ! -x "$HOME/.local/bin/pipenv" ]; then
  uv tool install pipenv
fi

# 2. ANTLR 4.13.2 CLI wrapper
ANTLR_JAR="$HOME/.local/lib/antlr-4.13.2-complete.jar"
if [ ! -f "$ANTLR_JAR" ]; then
  curl -fsSL \
    "https://www.antlr.org/download/antlr-4.13.2-complete.jar" \
    -o "$ANTLR_JAR"
fi
cat > "$HOME/.local/bin/antlr" << 'EOF'
#!/bin/sh
exec java -jar "$HOME/.local/lib/antlr-4.13.2-complete.jar" "$@"
EOF
chmod +x "$HOME/.local/bin/antlr"
ln -sfn "$HOME/.local/bin/antlr" "$HOME/.local/bin/antlr4"

# 3. LuaJIT 2.1, LuaRocks 3.13.0, and luautf8 (for Lua 5.1 target & E2E tests)
tmpdir=""
cleanup() {
  if [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then
    rm -rf "$tmpdir"
  fi
}
trap cleanup EXIT

if [ ! -x "$HOME/.local/bin/luajit" ]; then
  tmpdir="${tmpdir:-$(mktemp -d)}"
  git clone --depth 1 https://github.com/LuaJIT/LuaJIT.git "$tmpdir/LuaJIT"
  make -C "$tmpdir/LuaJIT" -j"$(nproc)" PREFIX="$HOME/.local"
  make -C "$tmpdir/LuaJIT" install PREFIX="$HOME/.local"
  luajit_bin="$(ls "$HOME/.local/bin"/luajit-2.1* | head -n 1)"
  ln -sfn "$luajit_bin" "$HOME/.local/bin/luajit"
fi
ln -sfn "$HOME/.local/bin/luajit" "$HOME/.local/bin/lua"
ln -sfn "$HOME/.local/bin/luajit" "$HOME/.local/bin/lua5.1"

if [ ! -x "$HOME/.local/bin/luarocks" ] || \
   ! "$HOME/.local/bin/luarocks" --version | head -n 1 | \
     grep -Eq '3\.(1[2-9]|[2-9][0-9])'; then
  tmpdir="${tmpdir:-$(mktemp -d)}"
  LR_URL="https://luarocks.github.io/luarocks/releases/luarocks-3.13.0.tar.gz"
  curl -fsSL "$LR_URL" -o "$tmpdir/luarocks.tar.gz"
  tar -xzf "$tmpdir/luarocks.tar.gz" -C "$tmpdir"
  (
    cd "$tmpdir/luarocks-3.13.0"
    ./configure --prefix="$HOME/.local" \
      --with-lua="$HOME/.local" \
      --lua-suffix=jit \
      --with-lua-include="$HOME/.local/include/luajit-2.1"
    make
    make install
  )
fi

if [ ! -f "$HOME/.local/lib/lua/5.1/lua-utf8.so" ]; then
  luarocks install luautf8
fi

# 4. Sapphire virtualenv & editable CLI
(
  cd "$REPO_ROOT"
  pipenv install --dev --deploy || pipenv install --dev --skip-lock
  pipenv run pip install --no-deps -e .
  ln -sfn "$(pipenv --venv)/bin/sapphire" "$HOME/.local/bin/sapphire"
)
