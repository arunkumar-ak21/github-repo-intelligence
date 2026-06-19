import importlib
import os
import unittest


os.environ.setdefault("ALLOW_UNREGISTERED_REPOS", "true")
os.environ.setdefault("DASHBOARD_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///data/test_imports.db")


MODULES = [
    "server",
    "core.cache",
    "core.config",
    "core.database",
    "core.errors",
    "core.github_client",
    "core.models",
    "modules.cicd.analyzer",
    "modules.cicd.detector",
    "modules.cicd.report_generator",
    "modules.cicd.routes",
    "modules.cicd.scanner",
    "modules.cicd.security_checker",
    "modules.deps.analysis",
    "modules.deps.detector",
    "modules.deps.package_apis",
    "modules.deps.reporter",
    "modules.deps.routes",
    "modules.deps.scorer",
    "modules.deps.parsers.base",
    "modules.deps.parsers.go_parser",
    "modules.deps.parsers.java_parser",
    "modules.deps.parsers.node_parser",
    "modules.deps.parsers.php_parser",
    "modules.deps.parsers.python_parser",
    "modules.deps.parsers.ruby_parser",
    "modules.deps.parsers.rust_parser",
    "modules.metadata.extractor",
    "modules.metadata.models",
    "modules.metadata.routes",
    "modules.auth.routes",
    "modules.auth.service",
    "modules.github_app.routes",
    "modules.github_app.service",
    "modules.provisioning.routes",
    "modules.provisioning.automation",
    "modules.provisioning.service",
    "modules.quality.local_runner",
    "modules.quality.normalizer",
    "modules.quality.report_receiver",
    "modules.quality.routes",
    "modules.quality.schemas",
    "modules.security.sanitizer",
    "modules.tenancy.api_keys",
    "modules.tenancy.service",
]


class ImportSmokeTests(unittest.TestCase):
    def test_core_and_feature_modules_import(self):
        failures = []
        for module_name in MODULES:
            try:
                importlib.import_module(module_name)
            except Exception as exc:
                failures.append(f"{module_name}: {exc!r}")

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
