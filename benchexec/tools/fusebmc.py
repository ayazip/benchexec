# This file is part of BenchExec, a framework for reliable benchmarking:
# https://github.com/sosy-lab/benchexec
#
# SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
#
# SPDX-License-Identifier: Apache-2.0

import os
from benchexec.tools.sv_benchmarks_util import get_data_model_from_task, ILP32, LP64
import benchexec.tools.template
import benchexec.result as result

class Tool(benchexec.tools.template.BaseTool2):
    """
    This class serves as tool adaptor for FuSeBMC (https://github.com/kaled-alshmrany/FuSeBMC)
    """

    REQUIRED_PATHS_TESTCOMP20 = ["esbmc", "esbmc-wrapper.py", "my_instrument"]
    REQUIRED_PATHS_TESTCOMP21 = [
        "esbmc",
        "fusebmc.py",
        "FuSeBMC_inustrment/FuSeBMC_inustrment",
        "fusebmc_output",
        "map2check-fuzzer",
    ]
    REQUIRED_PATHS_TESTCOMP22 = [
        "FuSeBMC_engines",
        "FuSeBMC_FuzzerLib",
        "FuSeBMC_GoalTracerLib",
        "FuSeBMC_inustrument/FuSeBMC_inustrment",
        "fusebmc_output",
        "FuSeBMC_SeedGenLib",
        "FuSeBMC_TCGen",
        "fusebmc_util",
        "fusebmc.py",
        "fusebmc_getinput_from_testcase.py",
        "fusebmc_seed_gen.py",
    ]
    def executable(self, tool_locator):
        return tool_locator.find_executable("fusebmc.py")
    
    def working_directory(self, executable):
        executableDir = os.path.dirname(executable)
        return executableDir
    
    def version(self, executable):
        return self._version_from_tool(executable, "-v")
    
    def name(self):
        return "FuSeBMC"
    
    def cmdline(self, executable, options, task, rlimits):
        data_model_param = get_data_model_from_task(task, {ILP32: "32", LP64: "64"})
        if data_model_param and "--arch" not in options:
            options += ["--arch", data_model_param]
        return (
            [executable]
            + ["-p", task.property_file]
            + options
            + [task.single_input_file]
        )
    
    def program_files(self, executable):
        """
        Determine the file paths to be adopted
        """
        if self._version == 21:
            paths = self.REQUIRED_PATHS_TESTCOMP21
        elif self._version > 21:
            paths = self.REQUIRED_PATHS_TESTCOMP22
        return self._program_files_from_executable(executable, paths)
    
    def determine_result(self, run):
        status = result.RESULT_UNKNOWN
        
        if run.output.any_line_contains("DONE"):
            status = result.RESULT_DONE
            
        if status == result.RESULT_UNKNOWN:
            if run.was_timeout:
                status = "TIMEOUT"
            elif not run.output.any_line_contains("Unknown"):
                status = "ERROR"
                
        return status
