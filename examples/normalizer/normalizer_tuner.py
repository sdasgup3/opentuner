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

log = logging.getLogger('tuneNormalizer')

argparser = argparse.ArgumentParser(parents=opentuner.argparsers())
argparser.add_argument('--func', default='', help='Function name')
argparser.add_argument('--outdir', default='mcsema', help='Output dir to dump the optimal pass sequence')


OPT_FLAGS = [
'-mem2reg', '-licm', '-gvn', '-early-cse', '-globalopt', '-simplifycfg',
'-aa', '-memdep', '-dse', '-deadargelim', '-libcalls-shrinkwrap', '-tailcallelim',
'-instcombine', '-memcpyopt',
'-mem2reg', '-licm', '-gvn', '-early-cse', '-globalopt', '-simplifycfg',
'-aa', '-memdep', '-dse', '-deadargelim', '-libcalls-shrinkwrap', '-tailcallelim',
'-instcombine', '-memcpyopt',
]
#OPT_FLAGS = [
#  'aa', 'adce', 'basicaa', 'basiccg', 'bdce', 'constmerge', 'correlated-propagation', 'deadargelim', 'demanded-bits', 'domtree', 'dse', 'early-cse', 'forceattrs', 'globaldce', 'globalopt', 'globals-aa', 'gvn', 'indvars', 'inferattrs', 'inline', 'instcombine', 'instsimplify', 'jump-threading', 'lcssa', 'lcssa-verification', 'libcalls-shrinkwrap', 'licm', 'loop-accesses', 'loop-deletion', 'loop-distribute', 'loop-idiom', 'loop-load-elim', 'loop-rotate', 'loops', 'loop-simplify', 'loop-sink', 'loop-unroll', 'loop-unswitch', 'loop-vectorize', 'mem2reg', 'memcpyopt', 'memdep', 'mldst-motion', 'postdomtree', 'reassociate', 'scalar-evolution', 'sccp', 'simplifycfg', 'sroa', 'tailcallelim', 'tbaa'
#  ]


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
    return self.run_precompiled(desired_result, input, limit, compile_result, 0)

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

    compd_opt_cmd = 'opt -S {0} mcsema/test.proposed.inline.ll -o {1}/test.proposed.opt.ll'.format(opt_seq, tmp_dir)
    compd_opt_result = self.call_program(compd_opt_cmd)
    assert compd_opt_result['returncode'] == 0

    mcsema_opt_cmd = 'opt -S {0} ../binary/test.mcsema.inline.ll -o {1}/test.mcsema.opt.ll'.format(opt_seq, tmp_dir)
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
    
    matcher_run_cmd = '/home/sdasgup3/Github//validating-binary-decompilation/source/build/bin//matcher --file1 {0}/test.mcsema.opt.ll:{1} --file2 {0}/test.proposed.opt.ll:{1} --potential-match-accuracy'.format(tmp_dir, args.func)

    matcher_run_result = self.call_program(matcher_run_cmd)
    if matcher_run_result['returncode'] != 0:
      print(matcher_run_result['stderr'])
      assert 0
    
    matcher_stderr = matcher_run_result['stderr']
    z = re.findall(r"^Accuracy:(\d+\.[\deE+-]+)", matcher_stderr, re.MULTILINE)
    cost = 1 - float(z[0])

    log.info('[RunPreC] Cost:{0} [{1}]'.format(cost, opt_seq))

    # Early exit
    outfile = args.outdir + '/' + 'normalizer_final_config.json'
    if cost == 0:
      log.info("Early Exit: Optimal pass sequence written to {0}: [{1}]".format(outfile, opt_seq))
      with open(outfile, 'w') as fd:
        fd.write('T:{0}'.format(opt_seq))
      exit(0)

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
        opt_seq += ' -{0}'.format(flag)

    compd_opt_cmd = 'opt -S {0} mcsema/test.proposed.inline.ll -o mcsema/test.proposed.opt.ll'.format(opt_seq)
    compd_opt_result = self.call_program(compd_opt_cmd)
    assert compd_opt_result['returncode'] == 0

    mcsema_opt_cmd = 'opt -S {0} ../binary/test.mcsema.inline.ll -o ../binary/test.mcsema.opt.ll'.format(opt_seq)
    mcsema_opt_result = self.call_program(mcsema_opt_cmd)
    assert mcsema_opt_result['returncode'] == 0

    matcher_run_cmd = '/home/sdasgup3/Github//validating-binary-decompilation/source/build/bin//matcher --file1 ../binary/test.mcsema.opt.ll:{0} --file2 mcsema/test.proposed.opt.ll:{0} --potential-match-accuracy'.format(args.func)

    matcher_run_result = self.call_program(matcher_run_cmd)
    assert matcher_run_result['returncode'] == 0
    
    matcher_stderr = matcher_run_result['stderr']
    z = re.findall(r"^Accuracy:(\d+\.[\deE+-]+)", matcher_stderr, re.MULTILINE)
    cost = 1 - float(z[0])

    log.info('[Run] Cost:{0} [{1}]'.format(cost, opt_seq))

    # Early exit
    outfile = args.outdir + '/' + 'normalizer_final_config.json'
    if cost == 0:
      log.info("Early Exit: Optimal pass sequence written to {0}: [{1}]".format(outfile, opt_seq))
      with open(outfile, 'w') as fd:
        fd.write('Test')
      exit(0)

    return Result(time=cost)

  def save_final_config(self, configuration):
    """called at the end of tuning"""
    optimal_cfg = ''
    for cfg in configuration.data.keys():
      if configuration.data[cfg] == "on":
        optimal_cfg +=  cfg
        optimal_cfg += ' '
    log.info("Optimal pass sequence seen so far: [{0}]".format(optimal_cfg))

  def program_name(self):
    return self.args.func

if __name__ == '__main__':
  opentuner.init_logging()
  args = argparser.parse_args()
  NormalizerTuner.main(args)
