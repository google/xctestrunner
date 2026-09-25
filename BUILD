load("@rules_python//python:defs.bzl", "py_binary", "py_library", "py_test")

package(default_visibility = ["//visibility:public"])

py_library(
    name = "shared",
    srcs = glob(
        ["xctestrunner/shared/*.py"],
        exclude = ["xctestrunner/shared/*_test.py"],
    ),
)

py_test(
    name = "bundle_util_test",
    srcs = ["xctestrunner/shared/bundle_util_test.py"],
    main = "xctestrunner/shared/bundle_util_test.py",
    deps = [":shared"],
)

py_library(
    name = "simulator",
    srcs = glob(["xctestrunner/simulator_control/*.py"]),
    deps = [
        ":shared",
    ],
)

py_binary(
    name = "ios_test_runner",
    srcs = [
        "__init__.py",
        "xctestrunner/__init__.py",
    ] + glob(
        ["xctestrunner/test_runner/*.py"],
    ),
    main = "xctestrunner/test_runner/ios_test_runner.py",
    python_version = "PY3",
    deps = [
        ":shared",
        ":simulator",
    ],
)

# Consumed by bazel tests.
filegroup(
    name = "for_bazel_tests",
    testonly = 1,
    srcs = glob(["**/*"]),
    # Exposed publicly just so other rules can use this if they set up
    # integration tests that need to copy all the support files into
    # a temporary workspace for the tests.
    visibility = ["//visibility:public"],
)
