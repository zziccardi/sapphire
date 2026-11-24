"""Build customization for excluding unit tests from built wheels."""

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPyExcludingTests(build_py):
    """Exclude *_test.py modules from packaged wheel artifacts."""

    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [
            (pkg, mod, path)
            for pkg, mod, path in modules
            if not mod.endswith("_test")
        ]


setup(cmdclass={"build_py": BuildPyExcludingTests})
