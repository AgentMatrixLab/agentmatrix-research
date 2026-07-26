from __future__ import annotations

import py_compile
import unittest
from pathlib import Path


class QlibRuntimeCompileTest(unittest.TestCase):
    def test_runtime_module_compiles(self) -> None:
        runtime_file = Path(__file__).with_name("runtime.py")
        compiled = True
        try:
            py_compile.compile(str(runtime_file), doraise=True)
        except py_compile.PyCompileError:
            compiled = False
        self.assertTrue(compiled, "research_core.qlib_lab.runtime should compile cleanly")


if __name__ == "__main__":
    unittest.main()
