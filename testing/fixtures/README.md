# Sapphire cross-backend test fixtures

## Overview
This directory contains end-to-end integration test fixtures used to verify runtime behavior and consistency across Sapphire's target transpiler backends (**Python** and **Lua 5.1**).

## Scope & purpose
Unlike compiler and parser unit tests (located in [`src/`](../../src)), which test internal AST construction, type-checker diagnostics, and syntax-parsing rules, the test fixtures in this directory serve a specific integration purpose:

1. **Cross-backend consistency**: Ensuring that a Sapphire program (`.sp`) transpiles and executes with identical runtime behavior and return values when targeted to Python and Lua 5.1.
2. **Ground-truth verification**: Matching function outputs against ground-truth expectations defined in [`_expectations.py`](_expectations.py).
3. **Language feature coverage**: Providing concise, readable benchmark cases for every Sapphire language construct that requires backend code generation.

## Directory structure
- **`*.sp`**: Sapphire source files containing `@test` annotated functions that return comparable values (scalars, strings, structures).
- **`_expectations.py`**: Central ground-truth registry mapping `{"<fixture>.sp": {"test_func": expected_value}}`. Both Python and Lua test harnesses validate their execution against this dictionary.
- **`*_test.py`**: Transpiled Python output corresponding to each fixture file.

## Running fixture tests
Fixture tests are executed via `unittest`:
```bash
python -m unittest src/code_gen/python_transpiler_test.py
python -m unittest src/code_gen/lua_transpiler_test.py
```
Or using the Sapphire CLI:
```bash
sapphire test testing/fixtures/
```
