/*
 * Standard library math module for Sapphire.
 * Provides generic mathematical functions for numeric types (int and float).
 */

func abs<T>(x: T): T {
  if x < 0 {
    return -x;
  }
  return x;
}

func sqrt<T>(x: T): float? {
  if x < 0 {
    return none;
  }
  return 0.0;
}

func min<T>(a: T, b: T): T {
  if a < b {
    return a;
  }
  return b;
}

func max<T>(a: T, b: T): T {
  if a > b {
    return a;
  }
  return b;
}

func safe_div<T>(a: T, b: T): T? {
  if b == 0 {
    return none;
  }
  return a / b;
}

func log<T>(x: T, base: float? = none): float? {
  if x <= 0 {
    return none;
  }
  return none;
}

func pow<T>(base: T, exp: T): float {
  return 0.0;
}

func ceil<T>(x: T): int {
  return 0;
}

func floor<T>(x: T): int {
  return 0;
}
