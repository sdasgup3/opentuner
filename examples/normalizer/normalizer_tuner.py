#!/usr/bin/env python
#
# Optimize blocksize of apps/mmm_block.cpp
#
# This is an extremely simplified version meant only for tutorials
#
from __future__ import print_function
import adddeps  # fix sys.path

import opentuner
from opentuner import ConfigurationManipulator
from opentuner import EnumParameter
from opentuner import IntegerParameter
from opentuner import MeasurementInterface
from opentuner import Result

import math
import argparse
import ast
import collections
import json
import logging
import opentuner
import os
import random
import re
import shutil
import subprocess
import sys
from os.path import expanduser

log = logging.getLogger('tuneNormalizer')
#log.setLevel(os.environ.get("LOGLEVEL", "DEBUG"))
home = expanduser("~")

argparser = argparse.ArgumentParser(parents=opentuner.argparsers())
argparser.add_argument('--func', default='', help='Function name')
argparser.add_argument(
    '--outdir',
    default='mcsema',
    help='Output dir to dump the optimal pass sequence')
argparser.add_argument('--matcher', default='', help='Matcher tool path')

#OPT_SEQ_FILE = home + \
#    '/Github//validating-binary-decompilation/tests/scripts/opt_candidates.txt'
#OPT_FLAGS = open(OPT_SEQ_FILE).read().splitlines()

OPT_FLAGS = [
    '-mem2reg', '-licm', '-gvn', '-early-cse', '-globalopt', '-simplifycfg', '-basicaa' ,
    '-aa', '-memdep', '-dse', '-deadargelim', '-libcalls-shrinkwrap', '-tailcallelim',
    '-instcombine', '-memcpyopt',
    '-mem2reg', '-licm', '-gvn', '-early-cse', '-globalopt', '-simplifycfg', '-basicaa' ,
    '-aa', '-memdep', '-dse', '-deadargelim', '-libcalls-shrinkwrap', '-tailcallelim',
    '-instcombine', '-memcpyopt',
    '-mem2reg', '-licm', '-gvn', '-early-cse', '-globalopt', '-simplifycfg', '-basicaa' ,
    '-aa', '-memdep', '-dse', '-deadargelim', '-libcalls-shrinkwrap', '-tailcallelim',
    '-instcombine', '-memcpyopt',
]

## All O3 passes (DO NOT sort as it will destroy the interleaving)
#OPT_SEQ_FILE = home + \
#    '/Github//validating-binary-decompilation/tests/scripts/O3_flags.txt'
#OPT_FLAGS = open(OPT_SEQ_FILE).read().splitlines()

## Selected O3 passes (DO NOT sort as it will destroy the interleaving)
#OPT_SEQ_FILE = home + \
#    '/Github//validating-binary-decompilation/tests/scripts/selected_O3_flags.txt'
#OPT_FLAGS = open(OPT_SEQ_FILE).read().splitlines()


class NormalizerTuner(MeasurementInterface):

    def __init__(self, *pargs, **kwargs):
        super(NormalizerTuner, self).__init__(program_name=args.func, *pargs,
                                              **kwargs)
        self.parallel_compile = True
        try:
            os.stat('./tmp')
        except OSError:
            os.mkdir('./tmp')

    def manipulator(self):
        """
        Define the search space by creating a
        ConfigurationManipulator
        """
        manipulator = ConfigurationManipulator()
        for flag in OPT_FLAGS:
            manipulator.add_parameter(
                EnumParameter(flag,
                              ['on', 'off', 'default']))
        return manipulator

    def get_tmpdir(self, result_id):
        return './tmp/%d' % result_id

    def cleanup(self, result_id):
        tmp_dir = self.get_tmpdir(result_id)
        shutil.rmtree(tmp_dir)

    def compile_and_run(self, desired_result, input, limit):
        """
        Compile and run the given desired_result on input and produce a
        Result(), abort early if limit (in seconds) is reached This function
        is only used for sequential execution flow
        """
        cfg = desired_result.configuration.data
        compile_result = self.compile(cfg, 0)
        return self.run_precompiled(
            desired_result, input, limit, compile_result, 0)

    def compile(self, config_data, result_id):
        """
        Compile in PARALLEL according to the configuration in config_data
        (obtained from desired_result.configuration) Should use id parameter
        to determine output location of executable Return value will be passed
        to run_precompiled as compile_result, useful for storing error/timeout
        information
        """
        opt_seq = ''

        cfg = config_data
        for flag in OPT_FLAGS:
            if cfg[flag] == 'on':
                opt_seq += ' {0}'.format(flag)

        tmp_dir = self.get_tmpdir(result_id)
        try:
            os.stat(tmp_dir)
        except OSError:
            os.mkdir(tmp_dir)

        compd_opt_cmd = 'opt -S {0} mcsema/test.proposed.inline.ll -o {1}/test.proposed.opt.ll'.format(
            opt_seq, tmp_dir)
        compd_opt_result = self.call_program(compd_opt_cmd)
        assert compd_opt_result['returncode'] == 0

        mcsema_opt_cmd = 'opt -S {0} ../binary/test.mcsema.inline.ll -o {1}/test.mcsema.opt.ll'.format(
            opt_seq, tmp_dir)
        mcsema_opt_result = self.call_program(mcsema_opt_cmd)
        assert mcsema_opt_result['returncode'] == 0

        return mcsema_opt_result

    def run_precompiled(self, desired_result, input, limit, compile_result,
                        result_id):
        """
        Run the given desired_result SEQUENTIALLY on input and produce a Result()
        Abort early if limit (in seconds) is reached Assume that the executable
        to be measured has already been compiled to an executable corresponding to
        identifier id by compile() The compile_result is the return result of compile(),
        and it will be None if compile() was not called
        """
        opt_seq = ''

        cfg = desired_result.configuration.data
        for flag in OPT_FLAGS:
            if cfg[flag] == 'on':
                opt_seq += ' {0}'.format(flag)

        tmp_dir = self.get_tmpdir(result_id)

        matcher = args.matcher
        if(matcher == ''):
            matcher = home + '/Github//validating-binary-decompilation/source/build/bin//matcher'

        matcher_run_cmd = '{0} --file1 {1}/test.mcsema.opt.ll:{2} --file2 {1}/test.proposed.opt.ll:{2} --potential-match-accuracy'.format(
            matcher, tmp_dir, args.func)

        matcher_run_result = self.call_program(matcher_run_cmd)
        if matcher_run_result['returncode'] != 0:
            print(matcher_run_result['stderr'])
            assert 0

        matcher_stderr = matcher_run_result['stderr']
        z = re.findall(
            r"^Accuracy:(\d+\.[\deE+-]+)",
            matcher_stderr,
            re.MULTILINE)
        cost = 1 - float(z[0])

        log.debug('[RunPreC] Cost:{0} [{1}]'.format(cost, opt_seq))

        # Early exit
        outfile = args.outdir + '/' + 'normalizer_final_config.json'
        if cost == 0:
            log.info(
                "run_precompiled: Early Exit: Optimal pass sequence written to {0}: [{1}]".format(
                    outfile, opt_seq))

#shutil.rmtree("./tmp")
#            os.remove("opentuner.log")
#
            with open(outfile, 'a') as fd:
                fd.write('{0}\n'.format(opt_seq))

        return Result(time=cost)

    def run(self, desired_result, input, limit):
        """
        Compile and run a given configuration then
        return performance
        """
        cfg = desired_result.configuration.data

        opt_seq = ''

        for flag in OPT_FLAGS:
            if cfg[flag] == 'on':
                opt_seq += ' {0}'.format(flag)

        tmp_dir = "./tmp"    
        compd_opt_cmd = 'opt -S {0} mcsema/test.proposed.inline.ll -o {1}/test.proposed.opt.ll'.format(
            opt_seq, tmp_dir)
        compd_opt_result = self.call_program(compd_opt_cmd)
        if compd_opt_result['returncode'] != 0:
          print(compd_opt_result)
          assert 0

        mcsema_opt_cmd = 'opt -S {0} ../binary/test.mcsema.inline.ll -o {1}/test.mcsema.opt.ll'.format(
            opt_seq, tmp_dir)
        mcsema_opt_result = self.call_program(mcsema_opt_cmd)
        if mcsema_opt_result['returncode'] != 0:
          print(mcsema_opt_result)
          assert 0

        matcher = args.matcher
        if(matcher == ''):
            matcher = home + '/Github//validating-binary-decompilation/source/build/bin//matcher'

        matcher_run_cmd = '{0} --file1 {1}/test.mcsema.opt.ll:{2} --file2 {1}/test.proposed.opt.ll:{2} --potential-match-accuracy'.format(
            matcher, tmp_dir, args.func)

        matcher_run_result = self.call_program(matcher_run_cmd)
        if matcher_run_result['returncode'] != 0:
          print(matcher_run_result)
          assert 0

        matcher_stderr = matcher_run_result['stderr']
        z = re.findall(
            r"^Accuracy:(\d+\.[\deE+-]+)",
            matcher_stderr,
            re.MULTILINE)
        cost = 1 - float(z[0])

        log.debug('[Run] Cost:{0} [{1}]'.format(cost, opt_seq))

        # Early exit
        outfile = args.outdir + '/' + 'normalizer_final_config.json'
        if cost == 0:
            log.info(
                "run: Early Exit: Optimal pass sequence written to {0}: [{1}]".format(
                    outfile, opt_seq))
            with open(outfile, 'a') as fd:
                fd.write('{0}\n'.format(opt_seq))

        return Result(time=cost)

    def save_final_config(self, configuration):
        """called at the end of tuning"""
        optimal_cfg = ''
        for cfg in configuration.data.keys():
            if configuration.data[cfg] == "on":
                optimal_cfg += cfg
                optimal_cfg += ' '
        log.info(
            "Optimal pass sequence seen so far: [{0}]".format(optimal_cfg))

    def program_name(self):
        return self.args.func


if __name__ == '__main__':
    opentuner.init_logging()
    args = argparser.parse_args()
    log.info(" Search Space: {0}\n\n".format(OPT_FLAGS))
    NormalizerTuner.main(args)
