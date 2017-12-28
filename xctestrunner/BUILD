package(default_visibility = ["//visibility:public"])

load("@subpar//:subpar.bzl", "par_binary")

py_library(
    name = 'shared',
    srcs = glob(['shared/**']),
)

py_library(
    name = 'simulator',
    srcs = glob(['simulator_control/**']),
    deps = [
        ':shared',
    ],
)

par_binary(
    name = 'ios_test_runner',
    srcs = glob(
        ['test_runner/**'],
        exclude = ['test_runner/TestProject/**']
    ),
    main = 'test_runner/ios_test_runner.py',
    deps = [
        ':shared',
        ':simulator',
    ],
    data = glob(['test_runner/TestProject/**']),
)
