
import Ganga.Core.exceptions

import copy
import tempfile

from Ganga.Utility.Shell import Shell
from Ganga.Utility.logging import getLogger

import Ganga.Utility.Config
##  Cannot configure LHCb without Gaudi changing underneath
gaudiConfig = Ganga.Utility.Config.getConfig( 'GAUDI' )

#---------------------------------------

def available_versions(appname):
    if gaudiConfig['useCMakeApplications']:
        return available_versions_cmake( appname )
    else:
        return available_versions_SP( appname )

def guess_version(appname):
    if gaudiConfig['useCMakeApplications']:
        return guess_version_cmake( appname )
    else:
        return guess_version_SP( appname )

def _getshell( self ):
    if gaudiConfig['useCMakeApplications']:
        return _getshell_cmake( self )
    else:
        return _getshell_SP( self )

def construct_merge_script( DaVinci_version, scriptName ):
    if gaudiConfig['useCMakeApplications']:
        return construct_merge_script_cmake( DaVinci_version, scriptName )
    else:
        return construct_merge_script_SP( DaVinci_version, scriptName )

def construct_run_environ():
    if gaudiConfig['useCMakeApplications']:
        return construct_run_environ_cmake()
    else:
        return construct_run_environ_SP()






def available_versions_cmake(appname):
    raise NotImplementedError

def guess_version_cmake(appname):
    raise NotImplementedError

def _getshell_cmake( self ):
    raise NotImplementedError

def construct_merge_script( DaVinci_version, scriptName ):
    raise NotImplementedError

def construct_run_environ_cmake():
    raise NotImplementedError






def construct_run_environ_SP():
    """
    This chunk of code has to run the SetupProject or equivalent at the start of
    a local/batch job's execution to setup the gaudi environment
    """
    script="""
# check that SetupProject.sh script exists, then execute it
os.environ['User_release_area'] = ''
#os.environ['CMTCONFIG'] = platform
f=os.popen('which SetupProject.sh')
setup_script=f.read()[:-1]
f.close()
if os.path.exists(setup_script):
    os.system('''/usr/bin/env bash -c '. `which LbLogin.sh` -c %s && source %s %s %s %s &&\
printenv > env.tmp' ''' % (platform, setup_script,project_opts,app,version))
    for line in open('env.tmp').readlines():
        varval = line.strip().split('=')
        if len(varval) < 2:
            pass
        else:
            content = ''.join(varval[1:])
            # Lets drop bash functions
            if not str(content).startswith('() {'):
                os.environ[varval[0]] = content
    os.system('rm -f env.tmp')
else:
    print 'Could not find %s. Your job will probably fail.' % setup_script
    sys.stdout.flush()
"""
    return script


def construct_merge_script_SP( DaVinci_version, scriptName ):

    shell_script = """#!/bin/sh
SP=`which SetupProject.sh`
if [ -n $SP ]; then
  . SetupProject.sh  --force DaVinci %s
else
  echo "Could not find the SetupProject.sh script. Your job will probably fail"
fi
gaudirun.py %s
exit $?
""" % ( DaVinci_version, scriptName)

    script_file_name = tempfile.mktemp('.sh')
    try:
        script_file = file(script_file_name,'w')
        script_file.write(shell_script)
        script_file.close()
    except:
        from Ganga.Core.exception import PostProcessException
        raise PostProcessException('Problem writing merge script')

    return script_file_name


def available_versions_SP(appname):
    """Provide a list of the available Gaudi application versions"""
    s = Shell()
    tmp = tempfile.NamedTemporaryFile(suffix='.log')
    command = 'SetupProject.sh --ask %s' % appname
    rc, output, m=s.cmd1("echo 'q\n' | %s >& %s; echo" % (command,tmp.name))
    output = tmp.read()
    tmp.close()
    versions = output[output.rfind('(')+1:output.rfind('q[uit]')].split()
    return versions

def guess_version_SP(appname):
    """Guess the default Gaudi application version"""
    s = Shell()
    tmp = tempfile.NamedTemporaryFile(suffix='.log')
    command = 'SetupProject.sh --ask %s' % appname
    rc, output, m=s.cmd1("echo 'q\n' | %s >& %s; echo" % (command, tmp.name))
    output = tmp.read()
    tmp.close()
    version = output[output.rfind('[')+1:output.rfind(']')]
    return version

## 'Simpler' but doesn't always work
#def _getshell_SP(self):
#    from Ganga.Utility.Shell import expand_vars
#    import os
#    env = expand_vars( os.environ )
#
#    import Ganga.Utility.execute
#    Ganga.Utility.execute.execute('. `which LbLogin.sh` -c %s' % self.platform, env=env, shell=True, update_env=True)
#    env['User_release_area'] = self.user_release_area
#
#    opts = ''
#    if self.setupProjectOptions: opts = self.setupProjectOptions
#
#    useflag = ''
#    if self.masterpackage:
#        (mpack, malg, mver) = CMTscript.parse_master_package( self.masterpackage )
#        useflag = '--use \"%s %s %s\"' % (malg, mver, mpack)
#    cmd = '. SetupProject.sh %s %s %s %s' % (useflag,opts,self.appname,self.version) 
#
#    Ganga.Utility.execute.execute( cmd, env=env, shell=True, update_env=True)
#
#    app_ok = False
#    ver_ok = False
#    for var in env:
#        if var.find(self.appname) >= 0: app_ok = True
#        if env[var].find(self.version) >= 0: ver_ok = True
#    if not app_ok or not ver_ok:
#        msg = 'Command "%s" failed to properly setup environment.' % cmd
#        logger.error(msg)
#        raise ApplicationConfigurationError(None,msg)
#
#    import copy
#    self.env = copy.deepcopy( env )
#    return env


def _getshell_SP(self):
    logger = getLogger()
    opts = ''
    if self.setupProjectOptions: opts = self.setupProjectOptions

    fd = tempfile.NamedTemporaryFile()
    script = '#!/bin/sh\n'
    if self.user_release_area:
        from Ganga.Utility.files import expandfilename
        script += 'User_release_area=%s; export User_release_area\n' % \
        expandfilename(self.user_release_area)
    if self.platform:
        script += '. `which LbLogin.sh` -c %s\n' % self.platform
        #script += 'export CMTCONFIG=%s\n' % self.platform
    useflag = ''
    if self.masterpackage:
        from GangaLHCb.Lib.Applications.CMTscript import parse_master_package
        (mpack, malg, mver) = parse_master_package(self.masterpackage)
        useflag = '--use \"%s %s %s\"' % (malg, mver, mpack)
    cmd = '. SetupProject.sh %s %s %s %s' % (useflag, opts, self.appname, self.version)
    script += '%s \n' % cmd
    fd.write(script)
    fd.flush()
    #logger.debug(script)

    self.shell = Shell(setup=fd.name)
    if (not self.shell): raise ApplicationConfigurationError(None,'Shell not created.')

    #import pprint
    #logger.debug(pprint.pformat(self.shell.env))

    fd.close()


    app_ok = False
    ver_ok = False
    for var in self.shell.env:
        if var.find(self.appname) >= 0: app_ok = True
        if self.shell.env[var].find(self.version) >= 0: ver_ok = True
    if not app_ok or not ver_ok:
        msg = 'Command "%s" failed to properly setup environment.' % cmd
        logger.error(msg)
        from Ganga.Core.exceptions import ApplicationConfigurationError
        raise ApplicationConfigurationError(None,msg)

    self.env = copy.deepcopy( self.shell.env )

    return self.shell.env

