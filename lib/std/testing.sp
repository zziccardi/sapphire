/*
 * Standard library testing module for Sapphire.
 * Provides the TestCase trait, assertion functions, and test runner primitives.
 */

trait TestCase {
  var func set_up();
  var func tear_down();
}
