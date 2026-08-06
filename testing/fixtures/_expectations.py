"""Ground-truth expected return values for shared Sapphire fixture tests.

Each fixture file (`*_test.sp`) exposes one or more `@test` functions that
return a single comparable value. This module maps fixture filename →
`{test_function_name: expected_value}` so that both transpiler test suites
can share the same ground truth without duplicating it.

Values here are the *normalized* Python equivalents — enum member `.value`
fields, not the enum objects themselves. Both the Python and Lua test harnesses
are expected to perform that normalisation before comparing.
"""

EXPECTATIONS: dict[str, dict[str, object]] = {
    "arithmetic_test.sp": {
        "test_integer_arithmetic": 15,
        "test_integer_division": 4.25,
        "test_modulo": 2,
        "test_negative_arithmetic": -2,
    },
    "closures_test.sp": {
        "test_single_param_lambda": 10,
        "test_lambda_arithmetic": 17,
        "test_lambda_captures_call": 15,
    },
    "control_flow_test.sp": {
        "test_if_else": 1,
        "test_while_loop": 10,
        "test_for_loop": 60,
        "test_break": 5,
        "test_continue": 12,
        "test_range": 10,
    },
    "enums_test.sp": {
        "test_int_enum_value": 2,
        "test_int_enum_comparison": 1,
        "test_string_enum_value": "green",
    },
    "inheritance_test.sp": {
        "test_inherited_field": 4,
        "test_overridden_field": 6,
        "test_own_field": 1,
    },
    "maps_test.sp": {
        "test_map_lookup": 2,
        "test_map_iteration_sum": 60,
    },
    "match_expressions_test.sp": {
        "test_match_statement": 20,
        "test_match_expression": 300,
        "test_match_wildcard": 1,
        "test_match_first_arm": 111,
    },
    "optionals_test.sp": {
        "test_coalesce_none": 42,
        "test_coalesce_value": 7,
        "test_optional_unwrap_taken": 10,
        "test_optional_unwrap_missed": -1,
    },
    "strings_test.sp": {
        "test_interpolation": "Hello, World!",
        "test_size": 5,
        "test_empty_false": 0,
        "test_empty_true": 1,
        "test_contains": 1,
        "test_upper": "HELLO",
        "test_lower": "hello",
    },
    "arrays_test.sp": {
        "test_array_indexing": 20,
        "test_array_size": 5,
        "test_array_mutation": 99,
        "test_array_push": 3,
        "test_array_contains": 1,
    },
    "expressions_and_casting_test.sp": {
        "test_float_to_int_cast": 9,
        "test_enum_to_int_cast": 1,
        "test_ternary_expression": 100,
        "test_optional_chaining": 42,
        "test_optional_chaining_none": -1,
    },
    "functions_and_returns_test.sp": {
        "test_default_parameter": 20,
        "test_override_default_parameter": 30,
        "test_named_parameters": 20,
        "test_multiple_returns_destructuring": 40,
    },
    "guards_and_traits_test.sp": {
        "test_guard_taken": 80,
        "test_guard_else_branch": -1,
        "test_trait_implementation": 50,
    },
    "prototypes_test.sp": {
        "test_proto_delegation": 100,
        "test_proto_shadowing": 250,
        "test_live_proto_mutation": 30,
    },
    "structs_and_methods_test.sp": {
        "test_default_fields": 0,
        "test_method_call": 2,
        "test_static_method": 7,
    },
}
