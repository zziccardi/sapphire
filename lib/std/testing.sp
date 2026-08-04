/*
 * Standard library testing module for Sapphire.
 * Provides the TestCase trait, assertion functions, and test runner primitives.
 */

trait TestCase {
  func set_up();
  func tear_down();
}
