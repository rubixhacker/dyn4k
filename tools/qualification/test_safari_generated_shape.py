import json
import tempfile
import unittest
from pathlib import Path

import safari_reporter


class SafariGeneratedShapeTests(unittest.TestCase):
    def test_generated_fragment_header_binds_source_and_consumer(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary).resolve()
            fragment = (Path(__file__).parent / safari_reporter.SOURCE.name).read_bytes()
            for project in (Path("dyn4k-core"), Path("dyn4k"),
                            Path("consumers/qualification/portable")):
                for mode in ("development", "production"):
                    with self.subTest(project=str(project), mode=mode):
                        package = safari_reporter.PACKAGES[project]
                        build_root = (repository / project if project ==
                                      Path("consumers/qualification/portable") else repository)
                        package_root = build_root / "build/js/packages" / package
                        runner = str(build_root / "build/js/node_modules/kotlin-web-helpers/dist"
                                     / "kotlin-test-karma-runner.js")
                        selected = str((package_root / "kotlin" / f"{package}.js") if
                                       mode == "development" else
                                       (repository / project / "build/compileSync/js/test"
                                        / "testProductionExecutable/kotlin" / f"{package}.js"))
                        settings = {
                            "singleRun": True, "autoWatch": False,
                            "basePath": str(package_root), "files": [runner, selected],
                            "frameworks": ["webpack-output", "mocha", "webpack"],
                            "client": {"args": []}, "browsers": ["Safari"],
                            "customLaunchers": {}, "failOnFailingTestSuite": False,
                            "failOnEmptyTestSuite": False,
                            "reporters": ["karma-kotlin-reporter"],
                            "preprocessors": {runner: ["webpack", "sourcemap"],
                                              selected: ["webpack", "sourcemap"]},
                            "proxies": {}, "webpackCopy": [],
                        }
                        generated = ("\nmodule.exports = function(config) {\n\nconfig.set("
                                     + json.dumps(settings) + ");"
                                     + safari_reporter.APPROVED_GENERATOR_TAIL
                                     + fragment.decode() + "\n}\n").encode()
                        self.assertEqual(mode, safari_reporter.validate_config(
                            generated, fragment, repository, project, mode))
                        for changed in (
                            generated.replace(b"// qualification-safari-reporter.js\n",
                                              b"// other-reporter.js\n"),
                            generated.replace(b"// qualification-safari-reporter.js\n",
                                              b"config.plugins = [];\n"),
                        ):
                            with self.assertRaises(safari_reporter.ConfigBindingError):
                                safari_reporter.validate_config(
                                    changed, fragment, repository, project, mode)


if __name__ == "__main__":
    unittest.main()
