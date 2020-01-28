#!/usr/bin/env python
#
# Optimize blocksize of apps/mmm_block.cpp
#
# This is an extremely simplified version meant only for tutorials
#
from __future__ import print_function
import adddeps  # fix sys.path

import opentuner
import re
from opentuner import ConfigurationManipulator
from opentuner import EnumParameter
from opentuner import IntegerParameter
from opentuner import MeasurementInterface
from opentuner import Result
import argparse
import logging

log = logging.getLogger('tuneNormalizer')

argparser = argparse.ArgumentParser(parents=opentuner.argparsers())
argparser.add_argument('--func', default='', help='Function name')


OPT_FLAGS = [
'mem2reg', 'licm', 'gvn', 'early-cse', 'globalopt', 'simplifycfg',
'aa', 'memdep', 'dse', 'deadargelim', 'libcalls-shrinkwrap', 'tailcallelim',
'instcombine', 'memcpyopt', ]
#OPT_FLAGS = [
#  'aa', 'adce', 'basicaa', 'basiccg', 'bdce', 'constmerge', 'correlated-propagation', 'deadargelim', 'demanded-bits', 'domtree', 'dse', 'early-cse', 'forceattrs', 'globaldce', 'globalopt', 'globals-aa', 'gvn', 'indvars', 'inferattrs', 'inline', 'instcombine', 'instsimplify', 'jump-threading', 'lcssa', 'lcssa-verification', 'libcalls-shrinkwrap', 'licm', 'loop-accesses', 'loop-deletion', 'loop-distribute', 'loop-idiom', 'loop-load-elim', 'loop-rotate', 'loops', 'loop-simplify', 'loop-sink', 'loop-unroll', 'loop-unswitch', 'loop-vectorize', 'mem2reg', 'memcpyopt', 'memdep', 'mldst-motion', 'postdomtree', 'reassociate', 'scalar-evolution', 'sccp', 'simplifycfg', 'sroa', 'tailcallelim', 'tbaa'
#  ]


class NormalizerTuner(MeasurementInterface):

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

#log.info('\nTrying {0}'.format(opt_seq))

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
    #print(matcher_stderr)
    z = re.findall(r"^Accuracy:(\d+\.[\deE+-]+)", matcher_stderr, re.MULTILINE)
    cost = 1 - float(z[0])

    log.info('Cost:{0} [{1}]'.format(cost, opt_seq))
    return Result(time=cost)

  def save_final_config(self, configuration):
    """called at the end of tuning"""
    optimal_cfg = ''
    for cfg in configuration.data.keys():
      if configuration.data[cfg] == "on":
        optimal_cfg +=  cfg
        optimal_cfg += ' '
    log.info("Optimal block size written to normalizer_final_config.json: [{0}]".format(optimal_cfg))
    self.manipulator().save_to_file(configuration.data,
                                    'normalizer_final_config.json')


if __name__ == '__main__':
  opentuner.init_logging()
  #argparser = opentuner.default_argparser()
  args = argparser.parse_args()
  NormalizerTuner.main(args)